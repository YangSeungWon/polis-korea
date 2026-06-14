// 총선 폴 페이지 (Phase 1) — 정당 지지율 추이(헤드라인) + 비례 실제결과 바.
//   추이 선별·정규화는 PollAdapter.genTrend가 담당. 254 지역구 hex는 Phase 2(후속).
//   POLL_ELECTION.kind==='general_election'이면 지선 모놀리식 우회(initGenIfNeeded).
(function () {
  'use strict';
  const gs = { propRace: null };

  async function loadResults() {
    try {
      const r = await fetch(POLL_ELECTION.results_path);
      if (!r.ok) return;
      const d = await r.json();
      const nat = (d.races || []).filter((x) => x.scope === 'nation' && (x.candidates || []).length);
      // 비례 = 정당 후보 다수인 nation race
      nat.sort((a, b) => (b.candidates || []).length - (a.candidates || []).length);
      gs.propRace = nat[0] || null;
    } catch (e) { /* 결과 없으면 추이만 */ }
  }

  function pc(p) { return typeof partyColor === 'function' ? partyColor(p) : '#888'; }
  function ptc(p) { return typeof partyTextColor === 'function' ? partyTextColor(p) : 'inherit'; }

  // 헤드라인: 정당 지지율 추이 (정당지지 풀사이클 + 비례 실제 ◆, 위성→본당)
  function renderTrend() {
    const host = document.getElementById('gen-trend');
    if (!host) return;
    if (typeof buildPartyTrendSVG !== 'function' || !window.PollAdapter) { host.hidden = true; return; }
    const { polls, actual } = PollAdapter.genTrend(state.data.polls || [], gs.propRace);
    if (!polls.length) { host.hidden = true; return; }
    const electionTs = Date.parse(POLL_ELECTION.date + 'T18:00:00+09:00');
    const svg = buildPartyTrendSVG(polls, {
      showBand: true, minPts: 8, topN: 6,           // party 모드(기본) — 정당 키
      actual, electionTs: isFinite(electionTs) ? electionTs : null,
      w: 720, h: 300,
    });
    host.innerHTML = '<h3 class="pres-trend-title">정당 지지율 추이 '
      + '<span class="pres-trend-sub">전국 정당지지 · ◆ 비례대표 실제 득표(위성정당→본당)</span></h3>'
      + `<div class="pres-trend-chart">${svg}</div>`;
    host.hidden = false;
  }

  // 비례 실제 결과 바 (위성정당 그대로 — 실제 의석 배분 기준)
  function renderProp() {
    const host = document.getElementById('gen-prop');
    if (!host) return;
    const cands = ((gs.propRace && gs.propRace.candidates) || [])
      .filter((c) => c.pct != null).slice().sort((a, b) => b.pct - a.pct).slice(0, 10);
    if (!cands.length) { host.hidden = true; return; }
    const maxPct = Math.max(...cands.map((c) => c.pct)) || 100;
    const bars = cands.map((c) => `<div class="pc-bar-row">
      <span class="name">${c.name || c.party || ''}</span>
      <span class="pc-bar"><span class="pc-bar-fill" style="width:${(c.pct / maxPct) * 100}%;background:${pc(c.party)}"></span></span>
      <span class="pct" style="color:${ptc(c.party)}">${c.pct}%</span></div>`).join('');
    host.innerHTML = '<h3 class="pres-trend-title">비례대표 실제 득표</h3>'
      + `<div class="poll-card">${bars}</div>`;
    host.hidden = false;
  }

  function ensureHosts() {
    const controls = document.querySelector('.controls');
    const anchor = controls || document.querySelector('.viz');
    const parent = anchor && anchor.parentElement;
    if (!parent) return;
    for (const id of ['gen-trend', 'gen-prop']) {
      if (!document.getElementById(id)) {
        const sec = document.createElement('section');
        sec.id = id; sec.className = id === 'gen-trend' ? 'pres-trend' : 'gen-prop';
        parent.insertBefore(sec, anchor);
      }
    }
    // 지선 컨트롤·viz 숨김 (Phase 1은 추이+비례바만)
    if (controls) controls.hidden = true;
    const viz = document.querySelector('.viz'); if (viz) viz.hidden = true;
  }

  async function initGenIfNeeded() {
    if (!(typeof POLL_ELECTION === 'object' && POLL_ELECTION.kind === 'general_election')) return false;
    ensureHosts();
    await loadResults();
    renderTrend();
    renderProp();
    return true;
  }

  window.initGenIfNeeded = initGenIfNeeded;
})();
