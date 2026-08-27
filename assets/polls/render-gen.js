// 총선 폴 페이지 — 정당 지지율 추이(헤드라인) + 비례 실제결과 + 254 지역구 hex(여론조사/실제).
//   추이·지역구 정규화는 PollAdapter가 담당(genTrend·districtResult*). 지역구 hex는 공유
//   drawDistrictHex(render-district-hex.js) 재사용. kind==='general_election' → initGenIfNeeded.
(function () {
  'use strict';
  const gs = { propRace: null, propSidoRaces: [], pmap: 'dorling', districtRaces: [], layout: null, dmode: (typeof IS_PAST !== 'undefined' && IS_PAST) ? 'result' : 'polls', selected: null, pollFn: null, resultFn: null };

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
      // 시도별 비례(1인2표, 17대~) — 격자/dorling 분포 맵용. 옛 총선(전국구 배분)은 없음.
      const ptc = gs.propRace && gs.propRace.sg_typecode;
      gs.propSidoRaces = races.filter((x) => x.scope === 'sido' && x.sg_typecode === ptc && (x.candidates || []).length);
    } catch (e) { /* 결과 없으면 추이/폴만 */ }
  }

  async function loadLayout() {
    try {
      const r = await fetch(`data/geo/district_hex_${POLL_ELECTION.n}.json`);
      gs.layout = r.ok ? await r.json() : null;
    } catch (e) { gs.layout = null; }
  }

  function pc(p) { return typeof partyColor === 'function' ? partyColor(p) : '#888'; }
  function ptc(p) { return typeof partyTextColor === 'function' ? partyTextColor(p) : 'inherit'; }  // 흰 배경용(정당색 글씨)
  function tc(p) { return typeof pickTextColor === 'function' ? pickTextColor(pc(p), 1) : '#fff'; }  // 정당색 배경 위 대비 글씨

  // (정당 지지율 추이 헤드라인은 '선거 무렵 분위기'(climate)로 통합 — 중복 제거.)

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
    let html = '<h3 class="pres-trend-title">비례대표 실제 득표</h3>' + `<div class="poll-card">${bars}</div>`;
    // 시도별 비례 분포 맵 — 대선 폴(render-pres)과 동일: 원형·격자(득표 비례) + 지도(격차명도). 실제 분포.
    if (window.Archive && window.Archive.sidoProp && (gs.propSidoRaces || []).length >= 4) {
      html += `<div class="gen-prop-map"><h3 class="pres-trend-title" style="margin-top:16px">시·도별 비례 분포 <span class="info-i" tabindex="0" role="button" aria-label="설명">i<span class="info-pop">실제 · 색=정당, 면적=득표</span></span></h3>`
        + `<div class="gen-prop-enc" style="justify-content:flex-end;margin:6px 0"></div>`
        + `<div id="gen-prop-map-svg"></div></div>`;
    }
    host.innerHTML = html;
    drawPropMap();
    // 방식 — 표비례(원형·격자) + 1위(지도). 공용 EncodingToggle, 없으면 폴백 seg.
    const encHost = host.querySelector('.gen-prop-enc');
    if (encHost) {
      const OPTS = [{ key: 'dorling', label: '원형' }, { key: 'grid', label: '격자' }, { key: 'map', label: '지도' }];
      if (window.EncodingToggle) {
        window.EncodingToggle.render(encHost, { options: OPTS, active: gs.pmap, onSelect: (v) => { gs.pmap = v; drawPropMap(); } });
      } else {
        encHost.classList.add('seg');
        encHost.innerHTML = OPTS.map((o) => `<button class="seg-btn${o.key === gs.pmap ? ' is-active' : ''}" data-pmap="${o.key}">${o.label}</button>`).join('');
        encHost.querySelectorAll('[data-pmap]').forEach((b) => b.addEventListener('click', () => {
          gs.pmap = b.dataset.pmap;
          encHost.querySelectorAll('[data-pmap]').forEach((x) => x.classList.toggle('is-active', x === b));
          drawPropMap();
        }));
      }
    }
    host.hidden = false;
  }

  function drawPropMap() {
    const el = document.getElementById('gen-prop-map-svg');
    if (!el || !window.Archive || !window.Archive.sidoProp) return;
    const SP = window.Archive.sidoProp;
    // 시도 클릭 → 그 시도 비례 실제 결과 detail(지선 패널 재사용).
    const onSelect = (sido) => {
      state.selectedSido = sido; state.selectedSigungu = null; state.office = '비례대표';
      if (window.renderDetail) window.renderDetail();
    };
    if (gs.pmap === 'map') {
      const SM = window.Archive.sidoMap;
      if (SM && SM.draw) { SM.draw(el, gs.propSidoRaces, { margin: true, onSelect }); return; }
    }
    (gs.pmap === 'grid' ? SP.drawGrid : SP.drawDorling)(el, gs.propSidoRaces, { onSelect });
  }

  // 254 지역구 hex (여론조사 1위 / 실제 1위 토글)
  function renderDistrict() {
    const host = document.getElementById('gen-district');
    if (!host) return;
    if (typeof drawDistrictHex !== 'function' || !gs.layout) { host.hidden = true; return; }
    const fn = gs.dmode === 'result' ? gs.resultFn : gs.pollFn;
    // 적중은 **읽는다** — 계산은 빌드가 한다(PollAdapter.accuracyOf 주석 참조).
    // 조사된 지역구 수도 같은 데서 온다(자체 의뢰 조사 제외가 이미 반영돼 있다 —
    // core.js:129가 하는 일이고, 그걸 빠뜨리면 20대 총선이 119가 아니라 125가 된다).
    const missed = (sido, name) => {
      const pp = PollAdapter.missPartyOf('국회의원', sido, name);
      return pp ? pc(pp) : null;
    };
    const acc = PollAdapter.accuracyOf('국회의원');
    const polled = acc ? acc.total : 0;
    const note = gs.dmode === 'polls'
      ? `조사된 지역구 ${polled}/${gs.layout.length} (나머지 회색)`
      : (acc ? `확정 결과 · 여론조사 적중 <b>${acc.match}/${acc.total}</b>` : '확정 결과');
    host.innerHTML = `
      <h3 class="pres-trend-title">지역구 1위 <span class="pres-trend-sub">소선거구 ${gs.layout.length}석</span> <span class="info-i" tabindex="0" role="button" aria-label="설명">i<span class="info-pop">칸=선거구, 색=1위 정당. <b>여론조사 1위</b>/<b>실제 1위</b> 토글. 점선 테두리=여론조사가 예측한 1위(실제와 다른 곳).</span></span></h3>
      <div class="gen-dist-bar">
        <div class="seg" role="tablist">
          <button class="seg-btn${gs.dmode === 'polls' ? ' is-active' : ''}" data-dmode="polls">여론조사 1위</button>
          <button class="seg-btn${gs.dmode === 'result' ? ' is-active' : ''}" data-dmode="result">실제 1위</button>
        </div>
        <span class="gen-dist-note">${note}</span>
      </div>
      <svg class="gen-dist-svg" id="gen-dist-svg"></svg>
      <div class="gen-dist-readout" id="gen-dist-readout"></div>`;
    host.hidden = false;
    const _dsvg = document.getElementById('gen-dist-svg');
    if (_dsvg) {                       // 캡처가 읽는다 — 어느 자료의 그림인지
      _dsvg.dataset.mapHost = 'polldistrict';
      _dsvg.dataset.mapToggle = 'dmode';
      _dsvg.dataset.mode = gs.dmode || 'polls';
    }
    drawDistrictHex(_dsvg, gs.layout, fn, {
      selected: gs.selected,
      missOf: gs.dmode === 'result' ? missed : null,
      onSelect: (sido, name) => {
        gs.selected = { sido, name }; renderDistrict();
        // 지선 detail 패널 재사용 — 그 지역구 실제 결과(+있으면 여론조사)를 #detail-pane에.
        state.selectedSido = sido; state.selectedSigungu = name; state.office = '국회의원';
        if (window.renderDetail) window.renderDetail();
      },
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
      ? `<span class="gdr-chip"><span class="gdr-lab">${lab}</span> <b style="color:${tc(c.party)};background:${pc(c.party)};padding:1px 6px;border-radius:3px">${c.name || c.party}</b> ${c.pct != null ? c.pct.toFixed(1) + '%' : ''}</span>`
      : `<span class="gdr-chip"><span class="gdr-lab">${lab}</span> —</span>`;
    // 판정도 **읽는다** — 여기서 따로 세면 헤드라인 합계와 어긋날 수 있다.
    const hit = PollAdapter.hitOf('국회의원', sido, name);
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
    if (window.pollEnsureActual) window.pollEnsureActual();   // 지역구 클릭 detail(지선 로직)용 실제맵 미리 로드
    await Promise.all([loadResults(), loadLayout()]);
    gs.pollFn = PollAdapter.districtResultFromPolls(state.data.polls || []);
    gs.resultFn = PollAdapter.districtResultFromResults(gs.districtRaces);
    // 정당 지지율 추이는 '선거 무렵 분위기'(climate) 한 곳에 통합 — 헤드라인 중복 제거.
    // 헤드라인이 갖던 ◆비례실제 비교는 climate 정당 차트로 흡수(12개월 + ◆, 정보 손실 없음).
    const gt = PollAdapter.genTrend(state.data.polls || [], gs.propRace, POLL_ELECTION.date);
    const gtHost = document.getElementById('gen-trend'); if (gtHost) gtHost.hidden = true;
    if (window.PollClimate) PollClimate.mount({ after: 'gen-trend', partyActual: gt.actual, polls: state.data.polls });
    renderProp();
    renderDistrict();
    return true;
  }

  window.initGenIfNeeded = initGenIfNeeded;
})();
