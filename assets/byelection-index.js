// /byelection/ — 역대 재·보궐선거 시간축 + 목록 (팩트 중심: 직 구성·당선 정당. 큐레이션/해석 없음).

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
  // 직 표시 순서 (높은 직부터)
  const LEVEL_ORDER = ['국회의원', '광역단체장', '교육감', '기초단체장', '광역의원', '기초의원'];

  const idx = await Elections.loadElectionsIndex();
  const allIds = [...(idx.active || []), ...(idx.archive || [])];
  const allMetas = await Promise.all(allIds.map((id) => Elections.loadElectionMeta(id)));

  const standalone = allMetas
    .filter((m) => m?.kind === 'byelection' && !INTEGRATED_BY_DATE[m.date])
    .sort((a, b) => b.date.localeCompare(a.date));
  const integrated = allMetas
    .filter((m) => m && INTEGRATED_BY_DATE[m.date] === m.id && m.kind !== 'byelection')
    .sort((a, b) => b.date.localeCompare(a.date));

  let calendar = null;
  try {
    calendar = await fetch('/data/byelection_calendar.json').then((r) => r.ok ? r.json() : null);
  } catch {}

  // 단독 회차 결과 요약(직·당선 정당) 선로드 — 타임라인·목록 공용.
  const summaries = {};
  await Promise.all(standalone.map(async (m) => { summaries[m.id] = await loadSummary(m); }));

  renderTimeline(standalone, integrated);
  renderList(standalone, integrated);
  renderCoverage(calendar);

  // ---

  function partyColor(party) {
    return (typeof window.partyColor === 'function') ? window.partyColor(party) : '#999';
  }

  // 결과 요약 — meta.offices의 (scope, sg_typecode)로 race를 식별해 직별 건수·당선 정당 집계.
  async function loadSummary(meta) {
    const path = meta.archive?.results_path || `data/results/${meta.id}.json`;
    let res;
    try { res = await fetch(path).then((r) => r.ok ? r.json() : null); } catch { res = null; }
    if (!res?.races) return null;
    const present = [];   // {level, n}
    const winners = {};   // party → count
    let total = 0;
    for (const o of (meta.offices || [])) {
      const races = res.races.filter((r) => r.scope === o.scope && r.sg_typecode === o.sg_typecode);
      if (!races.length) continue;
      present.push({ level: o.level, n: races.length });
      total += races.length;
      for (const r of races) {
        const w = (r.candidates || []).find((c) => c.won) || (r.candidates || []).find((c) => c.rank === 1);
        if (w?.party) winners[w.party] = (winners[w.party] || 0) + 1;
      }
    }
    present.sort((a, b) => LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level));
    return { present, winners, total };
  }

  function renderTimeline(standalone, integrated) {
    const host = document.getElementById('bx-timeline-host');
    const all = [...standalone, ...integrated];
    if (!host || !all.length) return;
    const W = 1000, H = 120, P = { l: 30, r: 30, t: 34, b: 34 };
    const innerW = W - P.l - P.r;
    const dates = all.map((m) => new Date(m.date).getTime());
    const d0 = Math.min(...dates), d1 = Math.max(...dates);
    const xf = (d) => P.l + ((new Date(d).getTime() - d0) / (d1 - d0 || 1)) * innerW;
    const yMid = H / 2 + 6;

    let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;max-height:140px">`;
    svg += `<line x1="${P.l}" x2="${W - P.r}" y1="${yMid}" y2="${yMid}" stroke="var(--rule)" stroke-width="1"/>`;
    const y0 = new Date(d0).getFullYear(), y1 = new Date(d1).getFullYear();
    for (let y = Math.ceil(y0 / 5) * 5; y <= y1; y += 5) {
      const x = xf(`${y}-07-01`);
      svg += `<line x1="${x}" x2="${x}" y1="${yMid - 4}" y2="${yMid + 4}" stroke="var(--ink-mute)" stroke-width="0.7"/>`;
      svg += `<text x="${x}" y="${H - 10}" text-anchor="middle" font-size="11" fill="var(--ink-soft)">${y}</text>`;
    }
    // 균일 점 — 단독(진하게)·통합(옅게)만 구분. 크기 인코딩 없음(팩트만).
    for (const m of all) {
      const isStd = m.kind === 'byelection';
      const x = xf(m.date);
      const href = m.archive?.page || `/archive/${m.id}/`;
      svg += `<a href="${href}"><circle cx="${x}" cy="${yMid}" r="${isStd ? 5 : 4}" `
        + `fill="${isStd ? 'var(--ink)' : 'var(--ink-mute)'}" opacity="${isStd ? 0.9 : 0.5}" `
        + `stroke="var(--bg)" stroke-width="1.5"><title>${m.name} (${m.date})</title></circle></a>`;
    }
    svg += `<g transform="translate(${P.l}, ${P.t - 22})">
      <circle cx="6" cy="0" r="5" fill="var(--ink)" opacity="0.9"/>
      <text x="16" y="4" font-size="11" fill="var(--ink-soft)">단독</text>
      <circle cx="58" cy="0" r="4" fill="var(--ink-mute)" opacity="0.5"/>
      <text x="68" y="4" font-size="11" fill="var(--ink-soft)">동시(지선·총선·대선과 함께)</text>
    </g></svg>`;
    host.innerHTML = svg;
  }

  function renderList(standalone, integrated) {
    const host = document.getElementById('bx-list');
    if (!host) return;
    const all = [
      ...standalone.map((m) => ({ ...m, _type: 'standalone' })),
      ...integrated.map((m) => ({ ...m, _type: 'integrated' })),
    ].sort((a, b) => b.date.localeCompare(a.date));

    host.innerHTML = '';
    for (const m of all) {
      const row = document.createElement('a');
      row.className = 'bx-list-row';
      row.href = m._type === 'standalone'
        ? (m.archive?.page || `/archive/${m.id}/`)
        : `/archive/${m.id}/#ar-byelection`;

      let facts = '';
      const s = summaries[m.id];
      if (m._type === 'standalone' && s && s.total) {
        const offices = s.present.map((o) => `${o.level} ${o.n}`).join(' · ');
        const wins = Object.entries(s.winners)
          .sort((a, b) => b[1] - a[1])
          .map(([p, n]) => `<span class="bx-win"><span class="bx-win-dot" style="background:${partyColor(p)}"></span>${p} ${n}</span>`)
          .join('');
        facts = `<span class="bx-list-offices">${offices}</span><span class="bx-list-wins">${wins}</span>`;
      } else if (m._type === 'integrated') {
        facts = `<span class="bx-list-offices">동시 재·보궐 (${m.name})</span>`;
      }

      row.innerHTML = `
        <span class="bx-list-date">${m.date}</span>
        <span class="bx-list-tag bx-list-tag-${m._type}">${m._type === 'standalone' ? '단독' : '동시'}</span>
        <span class="bx-list-facts">${facts}</span>`;
      host.appendChild(row);
    }
  }

  function renderCoverage(calendar) {
    const host = document.getElementById('bx-coverage');
    if (!host) return;
    const allYears = [];
    for (let y = 1987; y <= 2026; y++) allYears.push(y);
    const byYear = {};
    if (calendar?.cycles) {
      for (const c of calendar.cycles) (byYear[c.year] = byYear[c.year] || []).push(c);
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
})();
