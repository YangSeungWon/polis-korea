// 총선 폴 페이지 — 정당 지지율 추이(헤드라인) + 비례 실제결과 + 254 지역구 hex(여론조사/실제).
//   추이·지역구 정규화는 PollAdapter가 담당(genTrend·districtResult*). 지역구 hex는 공유
//   drawDistrictHex(render-district-hex.js) 재사용. kind==='general_election' → initGenIfNeeded.
(function () {
  'use strict';
  const gs = { propRace: null, districtRaces: [], layout: null, dmode: 'polls', selected: null, pollFn: null, resultFn: null };

  async function loadResults() {
    try {
      const r = await fetch(POLL_ELECTION.results_path);
      if (!r.ok) return;
      const d = await r.json();
      const races = d.races || [];
      const nat = races.filter((x) => x.scope === 'nation' && (x.candidates || []).length);
      nat.sort((a, b) => (b.candidates || []).length - (a.candidates || []).length);
      gs.propRace = nat[0] || null;
      gs.districtRaces = races.filter((x) => x.scope === 'district');
    } catch (e) { /* 결과 없으면 추이/폴만 */ }
  }

  async function loadLayout() {
    try {
      const r = await fetch(`data/geo/district_hex_${POLL_ELECTION.n}.json`);
      gs.layout = r.ok ? await r.json() : null;
    } catch (e) { gs.layout = null; }
  }

  function pc(p) { return typeof partyColor === 'function' ? partyColor(p) : '#888'; }
  function ptc(p) { return typeof partyTextColor === 'function' ? partyTextColor(p) : 'inherit'; }

  // 헤드라인: 정당 지지율 추이 (정당지지 + 비례 실제 ◆, 위성→본당)
  function renderTrend() {
    const host = document.getElementById('gen-trend');
    if (!host) return;
    if (typeof buildPartyTrendSVG !== 'function' || !window.PollAdapter) { host.hidden = true; return; }
    const { polls, actual } = PollAdapter.genTrend(state.data.polls || [], gs.propRace);
    if (!polls.length) { host.hidden = true; return; }
    const electionTs = Date.parse(POLL_ELECTION.date + 'T18:00:00+09:00');
    const svg = buildPartyTrendSVG(polls, {
      showBand: true, minPts: 8, topN: 6,
      actual, electionTs: isFinite(electionTs) ? electionTs : null, w: 720, h: 300,
    });
    host.innerHTML = '<h3 class="pres-trend-title">정당 지지율 추이 '
      + '<span class="pres-trend-sub">전국 정당지지 · ◆ 비례대표 실제 득표(위성정당→본당)</span></h3>'
      + `<div class="pres-trend-chart">${svg}</div>`;
    host.hidden = false;
  }

  // 비례 실제 결과 바
  function renderProp() {
    const host = document.getElementById('gen-prop');
    if (!host) return;
    const cands = PollAdapter.propSummary(gs.propRace, 10).candidates;
    if (!cands.length) { host.hidden = true; return; }
    const maxPct = Math.max(...cands.map((c) => c.pct)) || 100;
    const bars = cands.map((c) => `<div class="pc-bar-row">
      <span class="name">${c.name || c.party || ''}</span>
      <span class="pc-bar"><span class="pc-bar-fill" style="width:${(c.pct / maxPct) * 100}%;background:${pc(c.party)}"></span></span>
      <span class="pct" style="color:${ptc(c.party)}">${c.pct}%</span></div>`).join('');
    host.innerHTML = '<h3 class="pres-trend-title">비례대표 실제 득표</h3>' + `<div class="poll-card">${bars}</div>`;
    host.hidden = false;
  }

  // 254 지역구 hex (여론조사 1위 / 실제 1위 토글)
  function renderDistrict() {
    const host = document.getElementById('gen-district');
    if (!host) return;
    if (typeof drawDistrictHex !== 'function' || !gs.layout) { host.hidden = true; return; }
    const fn = gs.dmode === 'result' ? gs.resultFn : gs.pollFn;
    // 조사된 지역구 수 (폴 모드 안내)
    let polled = 0;
    for (const d of gs.layout) if (gs.pollFn(d.sido, d.name)) polled++;
    host.innerHTML = `
      <h3 class="pres-trend-title">지역구 1위 <span class="pres-trend-sub">소선거구 ${gs.layout.length}석</span></h3>
      <div class="gen-dist-bar">
        <div class="seg" role="tablist">
          <button class="seg-btn${gs.dmode === 'polls' ? ' is-active' : ''}" data-dmode="polls">여론조사 1위</button>
          <button class="seg-btn${gs.dmode === 'result' ? ' is-active' : ''}" data-dmode="result">실제 1위</button>
        </div>
        <span class="gen-dist-note">${gs.dmode === 'polls' ? `조사된 지역구 ${polled}/${gs.layout.length} (나머지 회색)` : '확정 결과'}</span>
      </div>
      <svg class="gen-dist-svg" id="gen-dist-svg"></svg>
      <div class="gen-dist-readout" id="gen-dist-readout"></div>`;
    host.hidden = false;
    drawDistrictHex(document.getElementById('gen-dist-svg'), gs.layout, fn, {
      selected: gs.selected,
      onSelect: (sido, name) => { gs.selected = { sido, name }; renderDistrict(); },
    });
    host.querySelectorAll('[data-dmode]').forEach((b) => b.addEventListener('click', () => {
      gs.dmode = b.dataset.dmode; renderDistrict();
    }));
    renderReadout();
  }

  // 선택 지역구 — 여론조사 1위 vs 실제 1위 한 줄
  function renderReadout() {
    const el = document.getElementById('gen-dist-readout');
    if (!el) return;
    if (!gs.selected) { el.innerHTML = '<span class="gen-dist-hint">지역구를 클릭하면 여론조사 1위 vs 실제 1위를 비교합니다.</span>'; return; }
    const { sido, name } = gs.selected;
    const pr = gs.pollFn(sido, name), rr = gs.resultFn(sido, name);
    const pTop = pr && pr.candidates[0], rTop = rr && rr.candidates[0];
    const chip = (c, lab) => c
      ? `<span class="gdr-chip"><span class="gdr-lab">${lab}</span> <b style="color:${ptc(c.party)};background:${pc(c.party)};padding:1px 6px;border-radius:3px">${c.name || c.party}</b> ${c.pct != null ? c.pct.toFixed(1) + '%' : ''}</span>`
      : `<span class="gdr-chip"><span class="gdr-lab">${lab}</span> —</span>`;
    const hit = pTop && rTop ? (pTop.party === rTop.party) : null;
    el.innerHTML = `<div class="gdr-head">${sido} ${name}${hit === false ? ' <span class="gdr-miss">여론조사 빗나감</span>' : (hit ? ' <span class="gdr-ok">적중</span>' : '')}</div>`
      + chip(pTop, '여론조사') + chip(rTop, '실제');
  }

  function ensureHosts() {
    const controls = document.querySelector('.controls');
    const anchor = controls || document.querySelector('.viz');
    const parent = anchor && anchor.parentElement;
    if (!parent) return;
    for (const id of ['gen-trend', 'gen-prop', 'gen-district']) {
      if (!document.getElementById(id)) {
        const sec = document.createElement('section');
        sec.id = id; sec.className = (id === 'gen-trend') ? 'pres-trend' : id;
        parent.insertBefore(sec, anchor);
      }
    }
    if (controls) controls.hidden = true;
    const viz = document.querySelector('.viz'); if (viz) viz.hidden = true;
  }

  async function initGenIfNeeded() {
    if (!(typeof POLL_ELECTION === 'object' && POLL_ELECTION.kind === 'general_election')) return false;
    ensureHosts();
    await Promise.all([loadResults(), loadLayout()]);
    gs.pollFn = PollAdapter.districtResultFromPolls(state.data.polls || []);
    gs.resultFn = PollAdapter.districtResultFromResults(gs.districtRaces);
    renderTrend();
    if (window.PollClimate) PollClimate.mount({ after: 'gen-trend' });  // 선거 무렵 국정·정당 지지
    renderProp();
    renderDistrict();
    return true;
  }

  window.initGenIfNeeded = initGenIfNeeded;
})();
