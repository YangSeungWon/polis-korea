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
    const { results, polls, meta, sgTypecode } = ctx;
    if (polls) document.getElementById('ar-polls-count').textContent = polls.length.toLocaleString() + '건';
    if (!results) return;
    const seats = computeSeats(results, sgTypecode, propSg(meta));
    const sorted = Object.entries(seats).sort((a, b) => b[1] - a[1]);
    if (sorted.length) {
      const [p1, n1] = sorted[0];
      document.getElementById('ar-winner').innerHTML =
        `<span style="color:${pcol(p1)};font-weight:700">${p1}</span> <span style="font-size:13px;color:var(--ink-soft)">${n1}석</span>`;
    }
    if (sorted.length > 1) {
      const [p2, n2] = sorted[1];
      document.getElementById('ar-runnerup').innerHTML =
        `<span style="color:${pcol(p2)};font-weight:700">${p2}</span> <span style="font-size:13px;color:var(--ink-soft)">${n2}석</span>`;
    }
    let voters = 0, electors = 0;
    for (const r of districtRaces(results, sgTypecode)) {
      voters += r.voters || 0; electors += r.electors || 0;
    }
    if (electors > 0) document.getElementById('ar-turnout').textContent = (voters / electors * 100).toFixed(1) + '%';
    document.getElementById('ar-status').textContent = `개표 완료 · ${results._meta?.fetched_at || '갱신 시각 미상'}`;
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
      renderHero(ctx);
      renderParliament(ctx);
      renderProportional(ctx);
      renderDistricts(ctx);
      // 출구조사는 pres와 동일 schema — 재사용
      window.Archive.pres.renderExitPoll(ctx);
      renderTrend(ctx);
    },
  };
})();
