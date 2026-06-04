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

  // 메타만 보고 source 분류 — result 파일 fetch X (lazy).
  function classifySource(meta) {
    if (!meta) return 'none';
    // 위키 source 명시
    if ((meta.archive?.data_source_note || '').includes('위키')) return 'wiki';
    if ((meta._data_caveat || '').includes('위키')) return 'wiki';
    if ((meta.nec?._note || '').includes('미가용')) return 'wiki';
    // status: active이고 fetch_nec_live 시기면 잠정
    const date = meta.date || '';
    if (meta.status === 'active') return 'live';
    // 2010 이후이면 NEC API, 이전이면 wiki (소수 옛 회차)
    const year = parseInt(date.slice(0, 4)) || 0;
    if (year >= 2010) return 'nec';
    return 'wiki';
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
    const counts = { nec: 0, live: 0, wiki: 0, total: 0 };
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
        <div class="cov-stat"><div class="cov-stat-n">${counts.wiki}</div><div class="cov-stat-lbl">위키</div></div>
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
          tooltip = `${meta.name}\n${meta.date}\nsource: ${status}`;
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
