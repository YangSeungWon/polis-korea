// /about/data-coverage/ — 데이터 가용성·source 매트릭스.

(async function () {
  const YEAR_START = 1987;
  const YEAR_END = 2026;

  const idx = await Elections.loadElectionsIndex();
  const allIds = [...(idx.active || []), ...(idx.archive || [])];
  const allMetas = (await Promise.all(allIds.map(Elections.loadElectionMeta))).filter((m) => m);

  // 캘린더 (재보궐 + 1987-2009 위키 source)
  const calendar = await fetch('/data/byelection_calendar.json')
    .then((r) => r.ok ? r.json() : null).catch(() => null);

  // 출처는 **적혀 있는 것**에서 읽는다. 예전엔 없으면 연도로 떨어뜨렸다 —
  // `year >= 2010 ? 'nec' : 'wiki'`. 그래서 13~16대 총선처럼 NEC 개표현황·LOD로
  // 받아 온 회차가 전부 '위키'로 칠해졌다. 그럴듯한 기본값이 사실을 덮은 것이다.
  //
  // 한 회차에 출처가 둘인 경우가 실제로 있다(14~16대 총선: 선거구=LOD·전국구=위키).
  // 둘 중 하나로 고르면 어느 쪽도 참이 아니라서 'mixed'로 따로 둔다.
  // 아무 표시도 없으면 'unknown'이다 — 추정하지 않는다.
  const NEC_MARK = /(NEC|선관위|중앙선거관리|개표현황|당선인명부|OpenAPI|LOD|info\.nec|당선인 API)/;
  const WIKI_MARK = /위키/;
  function classifySource(meta) {
    if (!meta) return 'none';
    if (meta.is_final === false) return 'live';
    const note = [meta.archive?.data_source_note, meta._data_caveat, meta.nec?._note]
      .filter(Boolean).join(' ');
    if (!note) return 'unknown';
    const nec = NEC_MARK.test(note), wiki = WIKI_MARK.test(note);
    if (nec && wiki) return 'mixed';
    if (nec) return 'nec';
    if (wiki) return 'wiki';
    return 'unknown';
  }

  // 각 회차 → (kind, year) cell
  const cellMap = {};
  for (const m of allMetas) {
    const kind = m.kind === 'general_election' ? 'general' : m.kind;
    const year = parseInt(m.date.slice(0, 4));
    cellMap[`${kind}|${year}`] = { source: classifySource(m), meta: m };
  }

  // 재보궐 캘린더: wiki entries만 추가 (NEC 회차는 위에서 처리됨)
  if (calendar?.cycles) {
    for (const c of calendar.cycles) {
      const key = `byelection|${c.year}`;
      if (!cellMap[key]) {
        cellMap[key] = {
          source: c.source === 'wikipedia-ko' ? 'wiki' : 'nec',
          calendar: c,
        };
      } else if (cellMap[key].source === 'nec' && c.source === 'wikipedia-ko') {
        // 같은 연도에 NEC + wiki 있으면 NEC 유지
      }
    }
  }

  renderSummary();
  renderMatrix();

  function renderSummary() {
    const host = document.getElementById('cov-summary');
    const counts = { nec: 0, live: 0, wiki: 0, mixed: 0, unknown: 0, total: 0 };
    for (const [_, v] of Object.entries(cellMap)) {
      counts.total += 1;
      if (v.source in counts) counts[v.source] += 1;
    }
    const byKind = {};
    for (const k of Object.keys(cellMap)) {
      const kind = k.split('|')[0];
      byKind[kind] = (byKind[kind] || 0) + 1;
    }
    const wikiCycles = (calendar?.cycles || []).filter((c) => c.source === 'wikipedia-ko').length;
    host.innerHTML = `
      <div class="cov-stat-row">
        <div class="cov-stat"><div class="cov-stat-n">${counts.total}</div><div class="cov-stat-lbl">전체 (회차/연도 셀)</div></div>
        <div class="cov-stat"><div class="cov-stat-n">${counts.nec + counts.live}</div><div class="cov-stat-lbl">NEC API</div></div>
        <div class="cov-stat"><div class="cov-stat-n">${counts.mixed}</div><div class="cov-stat-lbl">출처 둘</div></div>
        <div class="cov-stat"><div class="cov-stat-n">${counts.wiki}</div><div class="cov-stat-lbl">위키</div></div>
        <div class="cov-stat"><div class="cov-stat-n">${counts.unknown}</div><div class="cov-stat-lbl">출처 미기재</div></div>
        <div class="cov-stat"><div class="cov-stat-n">${wikiCycles}</div><div class="cov-stat-lbl">재보궐 (위키 회차)</div></div>
      </div>
      <p class="cov-note">대선 ${byKind.presidential || 0} · 총선 ${byKind.general || 0} · 지선 ${byKind.local || 0} · 재보궐 연도 ${byKind.byelection || 0}.</p>
    `;
  }

  function renderMatrix() {
    const host = document.getElementById('cov-matrix');
    const kinds = [
      { id: 'presidential', label: '대선', short: '대선' },
      { id: 'general', label: '총선', short: '총선' },
      { id: 'local', label: '지선', short: '지선' },
      { id: 'byelection', label: '재보궐', short: '재보궐' },
    ];
    let html = '<div class="cov-mat-head"><div class="cov-mat-row-lbl"></div>';
    for (let y = YEAR_START; y <= YEAR_END; y++) {
      html += `<div class="cov-mat-yr">${y % 100}</div>`;
    }
    html += '</div>';
    for (const k of kinds) {
      html += `<div class="cov-mat-row"><div class="cov-mat-row-lbl">${k.label}</div>`;
      for (let y = YEAR_START; y <= YEAR_END; y++) {
        const cell = cellMap[`${k.id}|${y}`];
        const status = cell?.source || 'none';
        const meta = cell?.meta;
        let tooltip = '데이터 없음';
        let link = '';
        if (meta) {
          const note = meta.archive?.data_source_note || meta._data_caveat || '';
          // 라벨은 뭉뚱그린 것이고 사실은 문장에 있다 — 있으면 문장을 보여준다.
          tooltip = `${meta.name}\n${meta.date}\nsource: ${status}`
            + (note ? `\n${note}` : '\n출처가 적혀 있지 않다');
          if (meta.archive?.page) link = meta.archive.page;
        } else if (cell?.calendar) {
          const c = cell.calendar;
          tooltip = `${c.year}년 재보궐 (${c.reasons_count || '?'}건)\nsource: ${status}`;
        }
        const cls = `cov-mat-cell cov-mat-${status}`;
        if (link) {
          html += `<a class="${cls}" href="${link}" title="${tooltip}"></a>`;
        } else {
          html += `<div class="${cls}" title="${tooltip}"></div>`;
        }
      }
      html += '</div>';
    }
    host.innerHTML = html;
  }
})();
