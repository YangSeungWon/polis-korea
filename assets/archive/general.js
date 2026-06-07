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

  // 정당별 의석 = 지역구 winner + 비례 의석 (proportional_seats 또는 seats 필드).
  function computeSeats(results, sgTypecode, propSgCode) {
    const seats = {};
    for (const r of districtRaces(results, sgTypecode)) {
      const cands = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      const top = cands[0];
      if (top) {
        const p = mainParty(top.party);
        seats[p] = (seats[p] || 0) + 1;
      }
    }
    const propNat = propNationRace(results, propSgCode);
    if (propNat?.candidates) {
      for (const c of propNat.candidates) {
        const n = c.proportional_seats != null ? c.proportional_seats : (c.seats != null ? c.seats : null);
        if (n != null) {
          seats[mainParty(c.party)] = (seats[mainParty(c.party)] || 0) + n;
        }
      }
    }
    return seats;
  }

  function renderHero(ctx) {
    const { results, polls, exitData, meta, sgTypecode } = ctx;
    if (!results) return;
    // 지역구 + 비례 분리 카운트
    const dist = {}, prop = {};
    for (const r of districtRaces(results, sgTypecode)) {
      const cs = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      if (cs[0]) {
        const p = mainParty(cs[0].party);
        dist[p] = (dist[p] || 0) + 1;
      }
    }
    const propNat = propNationRace(results, propSg(meta));
    if (propNat?.candidates) {
      for (const c of propNat.candidates) {
        const n = c.proportional_seats != null ? c.proportional_seats : (c.seats != null ? c.seats : null);
        if (n != null) prop[mainParty(c.party)] = (prop[mainParty(c.party)] || 0) + n;
      }
    }
    const total = {};
    for (const p of new Set([...Object.keys(dist), ...Object.keys(prop)])) {
      total[p] = (dist[p] || 0) + (prop[p] || 0);
    }
    const sorted = Object.entries(total).sort((a, b) => b[1] - a[1]);
    if (sorted.length === 0) return;
    const p1 = sorted[0][0], p2 = sorted[1]?.[0] || null;
    const sc = document.getElementById('ar-scorecard');
    if (sc) sc.removeAttribute('hidden');
    const setText = (id, txt) => { const e = document.getElementById(id); if (e) e.textContent = txt; };
    const setHTML = (id, html) => { const e = document.getElementById(id); if (e) e.innerHTML = html; };
    const renderParty = (party) => {
      const col = pcol(party);
      return `<span class="ar-sc-pname" style="color:${col};border-bottom:3px solid ${col}">${party}</span>`;
    };
    setHTML('ar-sc-p1', renderParty(p1));
    setText('ar-sc-dist-l', (dist[p1] || 0).toLocaleString());
    setText('ar-sc-prop-l', (prop[p1] || 0).toLocaleString());
    setText('ar-sc-total-l', total[p1].toLocaleString());
    if (p2) {
      setHTML('ar-sc-p2', renderParty(p2));
      setText('ar-sc-dist-r', (dist[p2] || 0).toLocaleString());
      setText('ar-sc-prop-r', (prop[p2] || 0).toLocaleString());
      setText('ar-sc-total-r', total[p2].toLocaleString());
    }
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

  function renderParliament(ctx) {
    const { results, meta, sgTypecode } = ctx;
    if (!results) return;
    const seats = computeSeats(results, sgTypecode, propSg(meta));
    const total = Object.values(seats).reduce((a, b) => a + b, 0);
    if (!total) return;
    const parties = Object.entries(seats)
      .sort((a, b) => b[1] - a[1])
      .map(([party, n]) => ({ party, seats: n, color: pcol(party) }));
    const host = document.getElementById('ar-parliament-host');
    if (typeof renderParliamentChart === 'function') {
      host.innerHTML = renderParliamentChart(parties, total, 480, 230);
    }
    const table = document.getElementById('ar-parliament-table');
    table.innerHTML = parties.slice(0, 10).map(({ party, seats: n, color }) =>
      `<div class="ar-parl-row">
        <span class="ar-parl-swatch" style="background:${color}"></span>
        <span class="ar-parl-name">${party}</span>
        <span class="ar-parl-seats">${n}석</span>
      </div>`).join('');
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

  window.Archive.general = {
    render(ctx) {
      // 254 지역구·정당지지 추이는 /history.html에서 시각화로 더 강력
      renderHero(ctx);
      renderParliament(ctx);
      renderProportional(ctx);
      renderExitPoll(ctx);
    },
  };
})();
