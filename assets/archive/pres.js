// archive 대선 모드 — 전국 1개 race + 시도 17개 분포.
// 사용: Archive.pres.render(ctx). renderExitPoll은 총선도 재사용.

(function () {
  const { SIDO_ORDER, ssh, pcol, renderTrendSVG } = window.Archive;

  function nationRace(results, sg) {
    return (results?.races || []).find((r) => r.scope === 'nation' && r.sg_typecode === sg);
  }
  function sidoRaces(results, sg) {
    return (results?.races || []).filter((r) => r.scope === 'sido' && r.sg_typecode === sg);
  }

  function renderHero(ctx) {
    const { results, polls, sgTypecode } = ctx;
    if (polls) document.getElementById('ar-polls-count').textContent = polls.length.toLocaleString() + '건';
    const nat = nationRace(results, sgTypecode);
    if (!nat) return;
    const cands = (nat.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
    const top = cands[0], second = cands[1];
    if (top) {
      const col = pcol(top.party);
      document.getElementById('ar-winner').innerHTML =
        `<span style="color:${col};font-weight:700">${top.name}</span> <span style="font-size:13px;color:var(--ink-soft)">${top.party}</span> <span style="font-size:13px;color:var(--ink-soft)">${(top.pct || 0).toFixed(1)}%</span>`;
    }
    if (top && second) {
      document.getElementById('ar-margin').innerHTML =
        `${(top.pct - second.pct).toFixed(2)}<span style="font-size:12px;color:var(--ink-soft)">pp</span>`;
    }
    if (nat.electors > 0) {
      document.getElementById('ar-turnout').textContent = (nat.voters / nat.electors * 100).toFixed(1) + '%';
    }
    const m = results._meta || {};
    const sourceLabel = m.source === 'nec-live-portal' ? '잠정' : (m.is_final ? '확정' : '진행');
    document.getElementById('ar-status').textContent = `${sourceLabel} 결과 · 갱신 ${m.fetched_at || '미상'}`;
  }

  function renderNation(ctx) {
    const nat = nationRace(ctx.results, ctx.sgTypecode);
    if (!nat) return;
    const host = document.getElementById('ar-nation-host');
    const cands = (nat.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
    const total = cands.reduce((s, c) => s + (c.votes || 0), 0) || 1;
    const top6 = cands.slice(0, 6);
    let html = '<div class="ar-nation-bars">';
    for (const c of top6) {
      const w = (c.votes / total) * 100;
      const col = pcol(c.party);
      html += `<div class="ar-nation-row">
        <div class="ar-nation-name"><span style="color:${col};font-weight:700">${c.name}</span> <span class="ar-nation-party">${c.party}</span></div>
        <div class="ar-nation-bar"><span class="ar-nation-fill" style="width:${w.toFixed(2)}%;background:${col}"></span></div>
        <div class="ar-nation-pct">${(c.pct || 0).toFixed(2)}<span class="unit">%</span></div>
        <div class="ar-nation-votes">${(c.votes || 0).toLocaleString()}표</div>
      </div>`;
    }
    html += '</div>';
    host.innerHTML = html;
    document.getElementById('ar-nation').hidden = false;
  }

  function renderCounting(ctx) {
    const sidos = sidoRaces(ctx.results, ctx.sgTypecode);
    if (!sidos.length) return;
    const host = document.getElementById('ar-counting-grid');
    const bySido = Object.fromEntries(sidos.map((r) => [r.sido, r]));
    for (const sido of SIDO_ORDER) {
      const r = bySido[sido];
      if (!r) continue;
      const cands = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      const top = cands[0], second = cands[1];
      if (!top) continue;
      const col = pcol(top.party);
      const margin = second ? (top.pct - second.pct) : null;
      const cell = document.createElement('div');
      cell.className = 'ar-count-cell';
      cell.innerHTML = `
        <div class="ar-count-sido">${ssh(sido)}</div>
        <div class="ar-count-bar"><span class="ar-count-fill" style="width:${(top.pct || 0).toFixed(1)}%;background:${col}"></span></div>
        <div class="ar-count-meta">
          <span style="color:${col};font-weight:700">${top.name} ${(top.pct || 0).toFixed(1)}</span>
          ${margin != null ? `<span class="ar-count-pct">+${margin.toFixed(1)}pp</span>` : ''}
        </div>
      `;
      host.appendChild(cell);
    }
    document.getElementById('ar-counting').hidden = false;
  }

  // 출구조사 vs 실제 — 전국 + 시도 후보별. 총선이 동일 schema로 재사용.
  function renderExitPoll(ctx) {
    const { exitData, results, sgTypecode } = ctx;
    if (!exitData?.sources) return;
    const host = document.getElementById('ar-exitpoll-grid');
    const now = new Date();
    const nat = nationRace(results, sgTypecode);
    const sidos = sidoRaces(results, sgTypecode);
    const actual = {};
    if (nat) {
      const c = (nat.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0))[0];
      if (c) actual['전국'] = { name: c.name, party: c.party, pct: c.pct };
    }
    for (const r of sidos) {
      const c = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0))[0];
      if (c) actual[r.sido] = { name: c.name, party: c.party, pct: c.pct };
    }
    let anyBlock = false;
    for (const ep of exitData.sources) {
      const qa = ep.quote_after ? new Date(ep.quote_after) : null;
      if (qa && now < qa) continue;
      const res = ep.results || {};
      if (!Object.keys(res).length) continue;
      anyBlock = true;
      const card = document.createElement('div');
      card.className = 'ar-exit-block';
      let hits = 0, tot = 0, errSum = 0, errN = 0;
      for (const [sido, cands] of Object.entries(res)) {
        const a = actual[sido];
        const top = cands?.[0];
        if (a && top) {
          tot += 1;
          if (a.name === top.name) hits += 1;
          if (a.pct != null && top.pct != null) { errSum += Math.abs(a.pct - top.pct); errN += 1; }
        }
      }
      const stats = tot ? `<span style="color:var(--ink-soft);font-size:12px;margin-left:10px">${hits}/${tot} 적중 · 평균 오차 ${errN ? (errSum / errN).toFixed(2) : '—'}pp</span>` : '';
      card.innerHTML = `<h3 class="ar-exit-source">${ep.name || ep.key}${stats}</h3>`;
      const grid = document.createElement('div');
      grid.className = 'ar-exit-rows';
      for (const sido of ['전국', ...SIDO_ORDER]) {
        const cands = res[sido];
        if (!cands?.[0]) continue;
        const top = cands[0];
        const a = actual[sido];
        const hit = a && a.name === top.name;
        const row = document.createElement('div');
        row.className = 'ar-exit-row ' + (a ? (hit ? 'is-hit' : 'is-miss') : '');
        if (sido === '전국') row.classList.add('is-nation');
        const col = pcol(top.party);
        row.innerHTML = `
          <span class="ar-exit-sido">${sido === '전국' ? '전국' : ssh(sido)}</span>
          <span class="ar-exit-pred" style="color:${col}">${top.name} ${(top.pct || 0).toFixed(1)}</span>
          ${a ? `<span class="ar-exit-actual">실제 ${a.name} ${(a.pct || 0).toFixed(1)}${hit ? ' ✓' : ' ✗'}</span>` : ''}
        `;
        grid.appendChild(row);
      }
      card.appendChild(grid);
      host.appendChild(card);
    }
    if (anyBlock) document.getElementById('ar-exitpoll').hidden = false;
  }

  function renderTrend(ctx) {
    const { polls } = ctx;
    if (!polls?.length) return;
    const candPolls = polls.filter((p) => p.office_level === '대통령' && p.metric_type === '후보지지');
    if (!candPolls.length) return;
    const byCand = new Map();
    for (const p of candPolls) {
      for (const c of (p.candidates || [])) {
        if (!c.name || c.pct == null) continue;
        if (!byCand.has(c.name)) byCand.set(c.name, { name: c.name, party: c.party, points: [] });
        byCand.get(c.name).points.push({ d: p.period_end || p.period_start, pct: c.pct });
      }
    }
    const top = Array.from(byCand.values()).sort((a, b) => b.points.length - a.points.length).slice(0, 6);
    if (!top.length) return;
    const series = top.map((c) => ({ label: c.name, color: pcol(c.party), points: c.points }));
    const host = document.getElementById('ar-trend-host');
    if (renderTrendSVG(host, series, { yMin: 60, yStep: 20 })) {
      document.getElementById('ar-polls-trend').hidden = false;
    }
  }

  window.Archive.pres = {
    render(ctx) {
      renderHero(ctx);
      renderNation(ctx);
      renderCounting(ctx);
      renderExitPoll(ctx);
      renderTrend(ctx);
    },
    renderExitPoll,  // 총선이 재사용
  };
})();
