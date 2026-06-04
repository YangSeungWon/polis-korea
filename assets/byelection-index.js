// /byelection/ — 역대 재·보궐선거 시간축 + 목록 + 변곡점.

(async function () {
  // 통합 동시 회차 매핑 (date → parent archive id)
  const INTEGRATED_BY_DATE = {
    '2010-06-02': '5th-local-2010',
    '2012-04-11': '19th-general-2012',
    '2014-06-04': '6th-local-2014',
    '2016-04-13': '20th-general-2016',
    '2017-05-09': '19th-pres-2017',
    '2018-06-13': '7th-local-2018',
    '2020-04-15': '21st-general-2020',
    '2022-03-09': '20th-pres-2022',
    '2022-06-01': '8th-local-2022',
    '2024-04-10': '22nd-general-2024',
    '2025-06-03': '21st-pres-2025',
    '2026-06-03': '9th-local-2026',
  };

  // 변곡점 큐레이션 (정치 흐름 의미 있던 회차)
  const HOT_PICKS = [
    {
      id: 'byelection-2014-07-30',
      title: '2014 7·30',
      lead: '나경원 vs 노회찬 0.21pp · 안철수 대표 사퇴',
      result_party: '새누리당',
    },
    {
      id: 'byelection-2019-04-03',
      title: '2019 4·3 창원성산',
      lead: '여영국(정의당) 45.76 vs 강기윤 45.22 — 0.54pp 신승',
      result_party: '정의당',
    },
    {
      id: 'byelection-2021-04-07',
      title: '2021 4·7 서울·부산',
      lead: '오세훈 57.50 · 박형준 62.67 — 이듬해 윤석열 당선 신호',
      result_party: '국민의힘',
    },
    {
      id: 'byelection-2023-04-05',
      title: '2023 4·5 전주을',
      lead: '강성희(진보당) 39.07% — 진보정당 첫 광역',
      result_party: '진보당',
    },
    {
      id: 'byelection-2024-10-16',
      title: '2024 10·16',
      lead: '부산 금정·인천 강화 등 — 윤석열 정부 평가',
      result_party: '국민의힘',
    },
  ];

  const idx = await Elections.loadElectionsIndex();
  const allIds = [...(idx.active || []), ...(idx.archive || [])];
  const allMetas = await Promise.all(allIds.map((id) => Elections.loadElectionMeta(id)));

  // 단독 byelection (kind === 'byelection' 이면서 통합 회차 날짜가 아님)
  const standalone = allMetas
    .filter((m) => m?.kind === 'byelection' && !INTEGRATED_BY_DATE[m.date])
    .sort((a, b) => b.date.localeCompare(a.date));

  // 통합 — 부모 회차 (kind != byelection) 중 INTEGRATED_BY_DATE에 매핑된 것
  const integrated = allMetas
    .filter((m) => m && INTEGRATED_BY_DATE[m.date] === m.id && m.kind !== 'byelection')
    .sort((a, b) => b.date.localeCompare(a.date));

  // 캘린더 fetch
  let calendar = null;
  try {
    calendar = await fetch('/data/byelection_calendar.json').then((r) => r.ok ? r.json() : null);
  } catch {}

  renderHot(standalone, allMetas);
  renderTimeline(standalone, integrated);
  renderList(standalone, integrated);
  renderCoverage(calendar);

  // ---

  function partyColor(party) {
    return (typeof window.partyColor === 'function') ? window.partyColor(party) : '#999';
  }

  async function renderHot(standalone, allMetas) {
    const host = document.getElementById('bx-hot-grid');
    for (const pick of HOT_PICKS) {
      const meta = allMetas.find((m) => m?.id === pick.id);
      if (!meta) continue;
      const col = partyColor(pick.result_party);
      const card = document.createElement('a');
      card.className = 'bx-hot-card';
      card.href = meta.archive?.page || `/archive/${meta.id}/`;
      card.style.borderTop = `3px solid ${col}`;
      card.innerHTML = `
        <div class="bx-hot-date">${meta.date}</div>
        <div class="bx-hot-title">${pick.title}</div>
        <div class="bx-hot-lead">${pick.lead}</div>
      `;
      host.appendChild(card);
    }
  }

  async function renderTimeline(standalone, integrated) {
    const host = document.getElementById('bx-timeline-host');
    const all = [...standalone, ...integrated];
    if (!all.length) return;

    // 결과 race 수 fetch (각 회차) — 데이터 작으니 병렬
    const sizes = await Promise.all(all.map(async (m) => {
      try {
        const path = m.archive?.results_path || `data/results/${m.id}.json`;
        const r = await fetch(path).then((x) => x.ok ? x.json() : null);
        return r?.races?.length || 0;
      } catch { return 0; }
    }));
    // 통합 회차의 byelection race 수 — byelectionId 가 있으면 그 파일
    for (let i = 0; i < all.length; i++) {
      const m = all[i];
      if (m.kind !== 'byelection' && m.archive?.byelection_id) {
        try {
          const r = await fetch(`data/results/${m.archive.byelection_id}.json`).then((x) => x.ok ? x.json() : null);
          sizes[i] = r?.races?.length || sizes[i];
        } catch {}
      }
    }

    // SVG 시간축
    const W = 1000, H = 160, P = { l: 30, r: 30, t: 40, b: 40 };
    const innerW = W - P.l - P.r;
    const allDates = all.map((m) => new Date(m.date).getTime());
    const d0 = Math.min(...allDates), d1 = Math.max(...allDates);
    const xf = (d) => P.l + ((new Date(d).getTime() - d0) / (d1 - d0 || 1)) * innerW;
    const yMid = H / 2 + 10;
    const maxR = 12;
    const maxSize = Math.max(...sizes, 1);
    const rOf = (n) => Math.max(3, Math.min(maxR, 3 + Math.sqrt(n) * 1.5));

    let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;max-height:180px">`;
    // base line
    svg += `<line x1="${P.l}" x2="${W - P.r}" y1="${yMid}" y2="${yMid}" stroke="var(--rule)" stroke-width="1"/>`;
    // year ticks
    const startYear = new Date(d0).getFullYear();
    const endYear = new Date(d1).getFullYear();
    for (let y = Math.ceil(startYear / 5) * 5; y <= endYear; y += 5) {
      const x = xf(`${y}-07-01`);
      svg += `<line x1="${x}" x2="${x}" y1="${yMid - 4}" y2="${yMid + 4}" stroke="var(--ink-mute)" stroke-width="0.7"/>`;
      svg += `<text x="${x}" y="${H - 12}" text-anchor="middle" font-size="11" fill="var(--ink-soft)">${y}</text>`;
    }
    // dots
    for (let i = 0; i < all.length; i++) {
      const m = all[i];
      const isStandalone = m.kind === 'byelection';
      const x = xf(m.date);
      const r = rOf(sizes[i]);
      const fill = isStandalone ? 'var(--ink)' : 'var(--ink-mute)';
      const opacity = isStandalone ? 0.85 : 0.55;
      const href = m.archive?.page || `/archive/${m.id}/`;
      svg += `<a href="${href}"><circle cx="${x}" cy="${yMid}" r="${r}" fill="${fill}" opacity="${opacity}" stroke="var(--bg)" stroke-width="1.5"><title>${m.name} (${m.date}) · ${sizes[i]} race</title></circle></a>`;
    }
    // 범례
    svg += `<g transform="translate(${P.l}, ${P.t - 25})">
      <circle cx="6" cy="0" r="5" fill="var(--ink)" opacity="0.85"/>
      <text x="16" y="4" font-size="11" fill="var(--ink-soft)">단독</text>
      <circle cx="60" cy="0" r="5" fill="var(--ink-mute)" opacity="0.55"/>
      <text x="70" y="4" font-size="11" fill="var(--ink-soft)">통합 (지선·총선·대선 동시)</text>
    </g>`;
    svg += '</svg>';
    host.innerHTML = svg;
  }

  function renderCoverage(calendar) {
    const host = document.getElementById('bx-coverage');
    if (!host) return;
    const allYears = [];
    for (let y = 1987; y <= 2026; y++) allYears.push(y);
    const byYear = {};
    if (calendar?.cycles) {
      for (const c of calendar.cycles) {
        (byYear[c.year] = byYear[c.year] || []).push(c);
      }
    }
    let html = '<div class="bx-cov-legend">'
      + '<span class="bx-cov-tag bx-cov-tag-nec">NEC API</span>'
      + '<span class="bx-cov-tag bx-cov-tag-wiki">위키</span>'
      + '<span class="bx-cov-tag bx-cov-tag-none">데이터 없음</span>'
      + '</div><div class="bx-cov-grid">';
    for (const y of allYears) {
      const cycles = byYear[y] || [];
      const hasNec = cycles.some((c) => c.source !== 'wikipedia-ko');
      const hasWiki = cycles.some((c) => c.source === 'wikipedia-ko');
      const status = hasNec ? 'nec' : (hasWiki ? 'wiki' : (y < 2010 ? 'gap' : 'unknown'));
      const n = cycles.reduce((s, c) => s + (c.reasons_count || 0), 0);
      const label = cycles.length
        ? (cycles.length === 1 ? `1회 · ${n}건` : `${cycles.length}회 · ${n}건`)
        : (y < 2010 ? '미확인' : '실시 안 함');
      html += `<div class="bx-cov-cell bx-cov-${status}" title="${y} · ${cycles.length} 회차">
        <div class="bx-cov-year">${y}</div>
        <div class="bx-cov-meta">${label}</div>
      </div>`;
    }
    html += '</div>';
    host.innerHTML = html;
  }

  function renderList(standalone, integrated) {
    const host = document.getElementById('bx-list');
    // 통합도 같이 한 list에 — 날짜 desc
    const all = [
      ...standalone.map((m) => ({ ...m, _type: 'standalone' })),
      ...integrated.map((m) => ({ ...m, _type: 'integrated' })),
    ].sort((a, b) => b.date.localeCompare(a.date));

    for (const m of all) {
      const row = document.createElement('a');
      row.className = 'bx-list-row';
      row.href = m._type === 'standalone'
        ? (m.archive?.page || `/archive/${m.id}/`)
        : `/archive/${m.id}/#ar-byelection`;
      row.innerHTML = `
        <span class="bx-list-date">${m.date}</span>
        <span class="bx-list-name">${m.name}</span>
        <span class="bx-list-tag bx-list-tag-${m._type}">${m._type === 'standalone' ? '단독' : '통합'}</span>
        <span class="bx-list-note">${m.archive?.context_note || ''}</span>
      `;
      host.appendChild(row);
    }
  }
})();
