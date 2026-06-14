// archive 총선 모드 — 254 지역구 + 비례 47석.
// 사용: Archive.general.render(ctx).

(function () {
  const { SIDO_ORDER, ssh, pcol, mainParty, renderTrendSVG } = window.Archive;

  function propSg(meta) { return meta.proportionalSgTypecode || '7'; }

  function districtRaces(results, sg) {
    return (results?.races || []).filter((r) => r.scope === 'district' && r.sg_typecode === sg);
  }
  function propNationRace(results, propSgCode) {
    return (results?.races || []).find((r) => r.scope === 'nation' && r.sg_typecode === propSgCode);
  }

  // 정당별 의석 = 지역구 winner + 비례 의석. 지역구·비례를 분리해 반환(상세표·반원 공용).
  function computeSeatSplit(results, sgTypecode, propSgCode) {
    const dist = {}, prop = {};
    for (const r of districtRaces(results, sgTypecode)) {
      // 중선거구(9~12대 2인 당선) 대응 — won 후보 전원 카운트. won 없으면 최다득표 1명 fallback.
      const won = (r.candidates || []).filter((c) => c.won);
      const winners = won.length ? won
        : (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0)).slice(0, 1);
      for (const c of winners) { const p = mainParty(c.party); dist[p] = (dist[p] || 0) + 1; }
    }
    const propNat = propNationRace(results, propSgCode);
    if (propNat?.candidates) {
      for (const c of propNat.candidates) {
        const n = c.proportional_seats != null ? c.proportional_seats : (c.seats != null ? c.seats : null);
        if (n != null) prop[mainParty(c.party)] = (prop[mainParty(c.party)] || 0) + n;
      }
    }
    const total = {};
    for (const p of new Set([...Object.keys(dist), ...Object.keys(prop)])) total[p] = (dist[p] || 0) + (prop[p] || 0);
    return { dist, prop, total };
  }
  function computeSeats(results, sgTypecode, propSgCode) {
    return computeSeatSplit(results, sgTypecode, propSgCode).total;
  }

  function renderHero(ctx) {
    const { results, polls, exitData, meta, sgTypecode } = ctx;
    if (!results) return;
    const { total } = computeSeatSplit(results, sgTypecode, propSg(meta));
    const sorted = Object.entries(total).sort((a, b) => b[1] - a[1]);
    if (sorted.length === 0) return;
    const sc = document.getElementById('ar-scorecard');
    if (sc) sc.removeAttribute('hidden');
    // 히어로 = 의석 반원 헤드라인(전 정당). 정당별 지역구/비례 상세는 '의회 구성' 섹션 표로.
    if (sc && typeof renderParliamentChart === 'function' && !sc.querySelector('.ar-parliament')) {
      const totalSeats = sorted.reduce((s, [, n]) => s + n, 0);
      if (totalSeats > 0) {
        const pp = sorted.map(([party, seats]) => ({ party, seats, color: pcol(party) }));
        const legend = sorted.filter(([, n]) => n >= 1).slice(0, 8)
          .map(([party, seats]) => `<span class="ar-pl-leg"><span class="ar-pl-dot" style="background:${pcol(party)}"></span><b>${seats}</b> ${party}</span>`).join('');
        sc.insertAdjacentHTML('afterbegin', `<div class="ar-parliament">`
          + renderParliamentChart(pp, totalSeats, 460, 210)
          + `<div class="ar-pl-total">${totalSeats}석</div>`
          + `<div class="ar-pl-legend">${legend}</div></div>`);
      }
    }
    const setText = (id, txt) => { const e = document.getElementById(id); if (e) e.textContent = txt; };
    let voters = 0, electors = 0;
    for (const r of districtRaces(results, sgTypecode)) {
      voters += r.voters || 0; electors += r.electors || 0;
    }
    if (electors > 0) setText('ar-turnout', (voters / electors * 100).toFixed(1) + '%');
    // 박빙 — 1·2위 차이 5%p 미만 지역구
    let closeN = 0;
    for (const r of districtRaces(results, sgTypecode)) {
      const cs = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      if (cs.length >= 2 && cs[0].pct != null && cs[1].pct != null && cs[0].pct - cs[1].pct < 5) closeN++;
    }
    if (closeN > 0) {
      setText('ar-close-count', `${closeN}곳`);
      document.getElementById('ar-hm-close')?.removeAttribute('hidden');
    }
    if (polls?.length) {
      setText('ar-polls-count', polls.length.toLocaleString() + '건');
      document.getElementById('ar-hm-polls')?.removeAttribute('hidden');
    }
    const m = results._meta || {};
    const sourceLabel = m.source === 'wikipedia-ko-infobox' ? '위키'
      : (m.source === 'nec-live-portal' ? '잠정' : (m.is_final ? '확정' : '진행'));
    setText('ar-status', `${sourceLabel} 결과 · 갱신 ${m.fetched_at || m.election_date || '미상'}`);
  }

  // '의회 구성' 섹션 — 반원은 히어로가 가지므로 여기선 정당별 지역구/비례/계 상세표(중복 제거).
  function renderParliament(ctx) {
    const { results, meta, sgTypecode } = ctx;
    if (!results) return;
    const { dist, prop, total } = computeSeatSplit(results, sgTypecode, propSg(meta));
    const rows = Object.keys(total).map((p) => ({ p, d: dist[p] || 0, pr: prop[p] || 0, t: total[p] }))
      .filter((r) => r.t >= 1)
      .sort((a, b) => b.t - a.t || b.pr - a.pr);
    if (!rows.length) return;
    // 데이터 체제별 3모드:
    //  split  지역구·비례 둘 다 (17대~)  → 정당/지역구/비례/계
    //  dist   지역구만, 비례 의석 없음    → 정당/지역구 당선
    //  total  지역구 없음, 정당 총합만(13~16대) → 정당/의석
    const hasDist = rows.some((r) => r.d > 0);
    const hasProp = rows.some((r) => r.pr > 0);
    const mode = hasDist && hasProp ? 'split' : (hasDist ? 'dist' : 'total');
    const sumD = rows.reduce((s, r) => s + r.d, 0);
    const sumP = rows.reduce((s, r) => s + r.pr, 0);
    const grand = rows.reduce((s, r) => s + r.t, 0);
    let head, cells, foot, note = '';
    if (mode === 'split') {
      head = '<span></span><span>정당</span><span>지역구</span><span>비례</span><span>계</span>';
      cells = (r) => `<span class="ar-parl-n">${r.d || '·'}</span><span class="ar-parl-n">${r.pr || '·'}</span><span class="ar-parl-n ar-parl-tot">${r.t}</span>`;
      foot = `<span class="ar-parl-n">${sumD}</span><span class="ar-parl-n">${sumP}</span><span class="ar-parl-n ar-parl-tot">${grand}</span>`;
    } else if (mode === 'dist') {
      head = '<span></span><span>정당</span><span>지역구 당선</span>';
      cells = (r) => `<span class="ar-parl-n ar-parl-tot">${r.d}</span>`;
      foot = `<span class="ar-parl-n ar-parl-tot">${sumD}</span>`;
      note = '비례대표는 정당 득표율만 기록 — 의석 배분 미집계. 지역구 당선만 표시.';
    } else {
      head = '<span></span><span>정당</span><span>의석</span>';
      cells = (r) => `<span class="ar-parl-n ar-parl-tot">${r.t}</span>`;
      foot = `<span class="ar-parl-n ar-parl-tot">${grand}</span>`;
      note = '정당별 총 의석만 기록 — 지역구·비례(전국구) 미분리.';
    }
    const table = document.getElementById('ar-parliament-table');
    table.innerHTML = `<div class="ar-parl-table${mode === 'split' ? '' : ' two-col'}">
      <div class="ar-parl-thead">${head}</div>
      ${rows.map((r) => `<div class="ar-parl-trow">
        <span class="ar-parl-swatch" style="background:${pcol(r.p)}"></span>
        <span class="ar-parl-name">${r.p}</span>${cells(r)}
      </div>`).join('')}
      <div class="ar-parl-trow ar-parl-foot"><span></span><span class="ar-parl-name">합계</span>${foot}</div>
    </div>${note ? `<p class="ar-parl-note">${note}</p>` : ''}`;
    document.getElementById('ar-parliament').hidden = false;
  }

  function renderProportional(ctx) {
    const propNat = propNationRace(ctx.results, propSg(ctx.meta));
    if (!propNat?.candidates) return;
    const cands = (propNat.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
    const total = cands.reduce((s, c) => s + (c.votes || 0), 0) || 1;
    const top8 = cands.slice(0, 8);
    let html = '<div class="ar-nation-bars">';
    for (const c of top8) {
      const w = (c.votes / total) * 100;
      const col = pcol(c.party);
      html += `<div class="ar-nation-row">
        <div class="ar-nation-name"><span style="color:${col};font-weight:700">${c.party}</span></div>
        <div class="ar-nation-bar"><span class="ar-nation-fill" style="width:${w.toFixed(2)}%;background:${col}"></span></div>
        <div class="ar-nation-pct">${(c.pct || 0).toFixed(2)}<span class="unit">%</span></div>
        <div class="ar-nation-votes">${(c.votes || 0).toLocaleString()}표</div>
      </div>`;
    }
    html += '</div>';
    document.getElementById('ar-proportional-host').innerHTML = html;
    document.getElementById('ar-proportional').hidden = false;
  }

  function renderDistricts(ctx) {
    const drs = districtRaces(ctx.results, ctx.sgTypecode);
    if (!drs.length) return;
    const bySido = {};
    for (const r of drs) (bySido[r.sido || '기타'] = bySido[r.sido || '기타'] || []).push(r);
    const host = document.getElementById('ar-districts-host');
    let html = '';
    for (const sido of SIDO_ORDER) {
      const list = bySido[sido];
      if (!list?.length) continue;
      html += `<div class="ar-dist-block"><h3 class="ar-dist-sido">${ssh(sido)} <span class="ar-dist-count">${list.length}곳</span></h3><div class="ar-dist-rows">`;
      list.sort((a, b) => (a.district || a.sigungu || '').localeCompare(b.district || b.sigungu || ''));
      for (const r of list) {
        const cands = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
        const top = cands[0], second = cands[1];
        if (!top) continue;
        const col = pcol(top.party);
        const margin = second ? (top.pct - second.pct) : null;
        const name = r.district || r.sigungu || '?';
        html += `<div class="ar-dist-row" style="border-left:3px solid ${col}">
          <span class="ar-dist-name">${name}</span>
          <span class="ar-dist-cand" style="color:${col};font-weight:700">${top.name}</span>
          <span class="ar-dist-meta">${(top.pct || 0).toFixed(1)}${margin != null ? ` <span style="color:var(--ink-mute)">+${margin.toFixed(1)}</span>` : ''}</span>
        </div>`;
      }
      html += '</div></div>';
    }
    host.innerHTML = html;
    document.getElementById('ar-districts').hidden = false;
  }

  // 의석 예측 vs 실제 — 22대형 출구조사 (방송사별 정당 의석 범위).
  function renderExitPoll(ctx) {
    const { exitData, results, meta, sgTypecode } = ctx;
    if (!exitData?.sources) {
      // 결과·시도별 dict 형태 source가 있으면 pres 함수 fallback.
      if (exitData?.sources) window.Archive.pres.renderExitPoll(ctx);
      return;
    }
    const now = new Date();
    const seatBlocks = exitData.sources.filter((ep) => {
      const qa = ep.quote_after ? new Date(ep.quote_after) : null;
      if (qa && now < qa) return false;
      return ep.seats && Object.keys(ep.seats).length > 0;
    });
    if (!seatBlocks.length) {
      // 권역별 (results dict) source가 있으면 pres 함수 호출.
      const regionBlocks = exitData.sources.some((ep) => ep.results && Object.keys(ep.results).length);
      if (regionBlocks) window.Archive.pres.renderExitPoll(ctx);
      return;
    }
    const actualSeats = results ? computeSeats(results, sgTypecode, propSg(meta)) : {};
    const host = document.getElementById('ar-exitpoll-grid');
    for (const ep of seatBlocks) {
      const card = document.createElement('div');
      card.className = 'ar-exit-block';
      // 적중률 — 실제가 predicted [min, max] 안에 들어오나
      let hits = 0, tot = 0;
      for (const [party, range] of Object.entries(ep.seats)) {
        const actual = actualSeats[party];
        if (actual == null) continue;
        tot += 1;
        if (actual >= range.min && actual <= range.max) hits += 1;
      }
      const stats = tot ? `<span style="color:var(--ink-soft);font-size:12px;margin-left:10px">${hits}/${tot} 범위 적중</span>` : '';
      card.innerHTML = `<h3 class="ar-exit-source">${ep.name || ep.key}${stats}</h3>`;
      const grid = document.createElement('div');
      grid.className = 'ar-seat-rows';
      for (const [party, range] of Object.entries(ep.seats)) {
        const col = pcol(party);
        const actual = actualSeats[party];
        const hit = actual != null && actual >= range.min && actual <= range.max;
        const sat = range.satellite ? ` <span class="ar-seat-sat">+${range.satellite}</span>` : '';
        const predText = range.min === range.max ? `${range.min}` : `${range.min}~${range.max}`;
        const row = document.createElement('div');
        row.className = 'ar-seat-row ' + (actual != null ? (hit ? 'is-hit' : 'is-miss') : '');
        row.innerHTML = `
          <span class="ar-seat-party" style="color:${col};font-weight:700">${party}${sat}</span>
          <span class="ar-seat-pred">${predText}석</span>
          ${actual != null ? `<span class="ar-seat-actual">실제 ${actual}석 ${hit ? '✓' : '✗'}</span>` : ''}
        `;
        grid.appendChild(row);
      }
      card.appendChild(grid);
      host.appendChild(card);
    }
    document.getElementById('ar-exitpoll').hidden = false;
  }

  function renderTrend(ctx) {
    const { polls } = ctx;
    if (!polls?.length) return;
    const partyPolls = polls.filter((p) => p.metric_type === '정당지지');
    if (!partyPolls.length) return;
    const byParty = new Map();
    for (const p of partyPolls) {
      for (const c of (p.candidates || [])) {
        const pty = c.party || c.name;
        if (!pty || c.pct == null) continue;
        if (!byParty.has(pty)) byParty.set(pty, { party: pty, points: [] });
        byParty.get(pty).points.push({ d: p.period_end || p.period_start, pct: c.pct });
      }
    }
    const top = Array.from(byParty.values()).sort((a, b) => b.points.length - a.points.length).slice(0, 6);
    if (!top.length) return;
    const series = top.map((c) => ({ label: c.party, color: pcol(c.party), points: c.points }));
    const host = document.getElementById('ar-trend-host');
    if (renderTrendSVG(host, series, { yMin: 50, yStep: 10 })) {
      document.getElementById('ar-polls-trend').hidden = false;
    }
  }

  // 지역구 의석 — 시도별 hex 지도(SIDO_HEX_LAYOUT). 각 시도 = 1 hex, 최다 정당색 + 의석수.
  // HTML 템플릿 변경 없이 #ar-parliament 뒤에 섹션 동적 주입(멱등).
  function renderGeneralHex(ctx) {
    const { results } = ctx;
    const drs = (results?.races || []).filter((r) => r.scope === 'district');
    if (!drs.length || typeof SIDO_HEX_LAYOUT !== 'object') return;
    const canon = (typeof canonSido === 'function') ? canonSido : (x) => x;
    const bySido = {};
    for (const r of drs) {
      const won = (r.candidates || []).filter((c) => c.won);
      const winners = won.length ? won
        : (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0)).slice(0, 1);
      const sd = canon(r.sido || '기타');
      const m = (bySido[sd] = bySido[sd] || {});
      for (const c of winners) { const p = mainParty(c.party); m[p] = (m[p] || 0) + 1; }
    }
    if (!Object.keys(bySido).length) return;
    let sec = document.getElementById('ar-general-hex');
    if (!sec) {
      const anchor = document.getElementById('ar-parliament');
      if (!anchor || !anchor.parentElement) return;
      sec = document.createElement('section');
      sec.className = 'ar-section';
      sec.id = 'ar-general-hex';
      sec.innerHTML = '<h2 class="ar-section-title">지역구 의석 — 시도별</h2>'
        + '<div class="ar-genhex-host"></div><div class="ar-genhex-legend ch-leg-row"></div>';
      anchor.parentElement.insertBefore(sec, anchor.nextSibling);
    }
    const NS = 'http://www.w3.org/2000/svg';
    const COL_W = 80, ROW_H = 70, OFF_X = 50, OFF_Y = 50, R = 36;
    const hexPoints = (cx, cy, rr) => {
      const p = [];
      for (let i = 0; i < 6; i++) { const a = Math.PI / 6 + i * Math.PI / 3; p.push(`${cx + rr * Math.cos(a)},${cy + rr * Math.sin(a)}`); }
      return p.join(' ');
    };
    const cells = []; const seen = new Set();
    for (const [sido, pos] of Object.entries(SIDO_HEX_LAYOUT)) {
      const key = `${pos.col},${pos.row}`;
      if (seen.has(key)) continue; seen.add(key);
      cells.push({ sido, cx: OFF_X + pos.col * COL_W + (pos.row % 2 ? COL_W / 2 : 0), cy: OFF_Y + pos.row * ROW_H * 0.87, seats: bySido[sido] });
    }
    const maxCx = Math.max(...cells.map((c) => c.cx)) + R + 20;
    const maxCy = Math.max(...cells.map((c) => c.cy)) + R + 20;
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('xmlns', NS);
    svg.setAttribute('viewBox', `0 0 ${maxCx} ${maxCy}`);
    svg.setAttribute('class', 'ar-genhex-svg');
    const partyTotal = {};
    for (const cell of cells) {
      const entries = Object.entries(cell.seats || {}).sort((a, b) => b[1] - a[1]);
      const tot = entries.reduce((s, e) => s + e[1], 0);
      const topParty = entries[0] ? entries[0][0] : null;
      const poly = document.createElementNS(NS, 'polygon');
      poly.setAttribute('points', hexPoints(cell.cx, cell.cy, R));
      poly.setAttribute('fill', topParty ? pcol(topParty) : 'var(--bg3)');
      poly.setAttribute('class', topParty ? 'ar-genhex-cell has-data' : 'ar-genhex-cell no-data');
      const tt = document.createElementNS(NS, 'title');
      tt.textContent = tot ? `${cell.sido} · ${entries.map(([p, n]) => `${p} ${n}`).join(', ')} (${tot}석)` : `${cell.sido} · 데이터 없음`;
      poly.appendChild(tt);
      svg.appendChild(poly);
      const t1 = document.createElementNS(NS, 'text');
      t1.setAttribute('x', cell.cx); t1.setAttribute('y', cell.cy - 3);
      t1.setAttribute('text-anchor', 'middle');
      t1.setAttribute('class', 'ar-genhex-label' + (topParty ? '' : ' no-data'));
      t1.textContent = ssh(cell.sido);
      svg.appendChild(t1);
      if (tot) {
        const t2 = document.createElementNS(NS, 'text');
        t2.setAttribute('x', cell.cx); t2.setAttribute('y', cell.cy + 13);
        t2.setAttribute('text-anchor', 'middle'); t2.setAttribute('class', 'ar-genhex-seats');
        t2.textContent = `${tot}`;
        svg.appendChild(t2);
      }
      for (const [p, n] of entries) partyTotal[p] = (partyTotal[p] || 0) + n;
    }
    const host = sec.querySelector('.ar-genhex-host');
    host.innerHTML = ''; host.appendChild(svg);
    const legend = sec.querySelector('.ar-genhex-legend');
    if (legend) {
      legend.innerHTML = Object.entries(partyTotal).sort((a, b) => b[1] - a[1]).slice(0, 8)
        .map(([p, n]) => `<span class="ch-leg" style="color:${pcol(p)}"><b>${n}</b> ${p}</span>`).join(' · ')
        + ` <span class="ar-genhex-note">· 지역구 1위 정당 색 · hex hover로 분포</span>`;
    }
  }

  window.Archive.general = {
    render(ctx) {
      // 254 지역구·정당지지 추이는 /history.html에서 시각화로 더 강력
      renderHero(ctx);
      renderParliament(ctx);
      renderGeneralHex(ctx);
      renderProportional(ctx);
      renderExitPoll(ctx);   // 코어 단계엔 exitData=null → 스킵
    },
    // 2차 데이터(여론조사 건수·출구조사) 도착 후 — 코어 섹션 재렌더 안 함.
    renderDeferred(ctx) {
      renderHero(ctx);       // 여론조사 건수 갱신 (setText·차트 가드라 idempotent)
      renderExitPoll(ctx);
    },
  };
})();
