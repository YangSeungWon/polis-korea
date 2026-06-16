// 대선 폴 페이지 — 시도 비례(격자/dorling)를 PollAdapter + Archive.sidoProp로 렌더.
//   여론조사(pct) ↔ 실제(votes) 토글. 지선 모놀리식 경로를 타지 않고 별도 init(initPresIfNeeded).
//   PoC: 시도 비례 + 전국 요약 패널. (지도 모드·시군구는 후속.)
(function () {
  'use strict';

  const ps = { mode: (typeof IS_PAST !== 'undefined' && IS_PAST) ? 'result' : 'polls', viewmode: 'dorling', sidoRaces: [], sigunguRaces: [], nationRace: null, weights: {} };

  // 헤드라인: 본선 후보 지지율 추이 (전국 시계열 + 선거일 실제 ◆).
  // 본선 선별·정규화는 PollAdapter.presTrend가 담당 — 여기선 형태만 렌더로 넘김.
  function renderTrend() {
    const host = document.getElementById('pres-trend');
    if (!host) return;
    if (typeof buildPartyTrendSVG !== 'function' || !window.PollAdapter) { host.hidden = true; return; }
    const { polls, actual } = PollAdapter.presTrend(state.data.polls || [], ps.nationRace);
    if (!polls.length) { host.hidden = true; return; }
    const electionTs = Date.parse(POLL_ELECTION.date + 'T18:00:00+09:00');
    const svg = buildPartyTrendSVG(polls, {
      keyBy: 'candidate', showBand: true, minPts: 5, topN: 6,
      actual, electionTs: isFinite(electionTs) ? electionTs : null,
      w: 720, h: 300,
    });
    host.innerHTML = `<h3 class="pres-trend-title">본선 후보 지지율 추이 <span class="pres-trend-sub">전국 여론조사(본선 구도) · ◆ 선거일 실제 득표</span></h3>`
      + `<div class="pres-trend-chart">${svg}</div>`;
    host.hidden = false;
  }

  function vizMain() { return document.querySelector('.viz-main'); }
  function presHost() {
    let h = document.getElementById('pres-host');
    if (!h) {
      h = document.createElement('div');
      h.id = 'pres-host';
      h.className = 'pres-host';
      (vizMain() || document.querySelector('.viz') || document.body).appendChild(h);
    }
    return h;
  }

  async function loadResults() {
    try {
      const r = await fetch(POLL_ELECTION.results_path);
      if (!r.ok) return;
      const d = await r.json();
      let races = d.races || [];
      if (d._meta && d._meta.chunked) {   // 시군구는 .sigungu.json 청크에 — 결과 맵용
        const cr = await fetch(POLL_ELECTION.results_path.replace(/\.json$/, '.sigungu.json'))
          .then((x) => (x.ok ? x.json() : null)).catch(() => null);
        if (cr && cr.races) races = races.concat(cr.races);
      }
      ps.sidoRaces = races.filter((x) => x.scope === 'sido');
      ps.sigunguRaces = races.filter((x) => x.scope === 'sigungu');
      ps.nationRace = races.find((x) => x.scope === 'nation') || null;
      ps.weights = PollAdapter.weightsFromResults(races);
    } catch (e) { /* 결과 없으면 폴 모드만 */ }
  }

  // 시·군·구 1위 후보 결과 맵 (1위색 + 격차 명도). council-hex 재사용.
  async function renderSigunguResult() {
    const CH = window.Archive && window.Archive.councilHex;
    if (!CH || !CH.initResult || !(ps.sigunguRaces || []).length) return;
    let sec = document.getElementById('pres-sgg-result');
    if (!sec) {
      sec = document.createElement('section');
      sec.id = 'pres-sgg-result'; sec.className = 'pres-sgg-result';
      sec.innerHTML = '<h3 class="pres-trend-title">시·군·구 1위 후보 <span class="pres-trend-sub">실제 · 단색=격차 명도 · 격자/dorling=표 비례</span></h3>'
        + '<div class="pres-sgg-host"></div>';
      const anchor = document.getElementById('pres-host') || document.querySelector('.viz-main') || document.querySelector('.viz');
      (anchor && anchor.parentElement ? anchor.parentElement : document.body).appendChild(sec);
    }
    await CH.initResult(
      { results: { races: ps.sigunguRaces }, meta: { electionN: POLL_ELECTION.n, electionKind: 'presidential' } },
      sec.querySelector('.pres-sgg-host'));
  }

  function cells() {
    return ps.mode === 'result'
      ? PollAdapter.cellsFromResults(ps.sidoRaces)
      : PollAdapter.cellsFromPolls(state.data.polls || [], { office: '대통령', weights: ps.weights });
  }

  function render() {
    const sp = window.Archive && window.Archive.sidoProp;
    if (!sp) return;
    // 지선 패널 숨기고 pres-host 사용
    ['map', 'hex', 'hex2', 'poll-legend'].forEach((id) => {
      const el = document.getElementById(id); if (el) el.hidden = true;
    });
    const h = presHost(); h.hidden = false;
    const cs = cells();
    if (!cs.length) {
      h.innerHTML = `<div class="detail-empty">${ps.mode === 'polls' ? '시도 단위 여론조사가 없습니다 (대선 조사는 대부분 전국 단위).' : '결과 데이터가 없습니다.'}</div>`;
      renderDetail();
      return;
    }
    const legend = ps.mode === 'polls'
      ? (ps.viewmode === 'grid' ? '■ 면적=유권자 규모 · 색=조사 지지' : '● 크기=유권자 규모 · 파이=조사 지지 구성')
      : undefined;
    // 실제 모드: 막판 여론조사 시도 1위 vs 실제 — 빗나간 시도 점선 마커(조사 1위 정당색) + 적중 헤드라인.
    let missOf = null, m = 0, t = 0;
    const csn = (typeof canonSido === 'function') ? canonSido : (s) => s;
    if (ps.mode === 'result') {
      const pm = {}, am = {};
      PollAdapter.cellsFromPolls(state.data.polls || [], { office: '대통령' })
        .forEach((c) => { pm[csn(c.sido)] = (c.candidates[0] || {}).party; });
      cs.forEach((c) => { am[csn(c.sido)] = (c.candidates[0] || {}).party; });
      for (const k in am) { if (pm[k] && am[k]) { t++; if (pm[k] === am[k]) m++; } }
      missOf = (sido) => { const k = csn(sido), pp = pm[k], ap = am[k]; return (pp && ap && pp !== ap) ? partyColor(pp) : null; };
    }
    sp[ps.viewmode === 'grid' ? 'drawGrid' : 'drawDorling'](h, cs, { legend, onSelect: null, missOf });
    if (t) { const cap = document.createElement('div'); cap.className = 'pres-acc-note'; cap.innerHTML = `여론조사 막판 시도 1위 적중 <b>${m}/${t}곳</b> <span class="ra-legend">점선 테두리=여론조사 1위 정당</span>`; h.prepend(cap); }
    renderDetail();
  }

  // 우측 패널 — 전국 요약 (모드별: 여론조사 최신 전국 / 실제 전국)
  function renderDetail() {
    const pane = document.getElementById('detail-pane');
    if (!pane) return;
    const { title, candidates: cands } = PollAdapter.presNationalSummary(state.data.polls || [], ps.nationRace, ps.mode);
    if (!cands.length) { pane.innerHTML = '<div class="detail-empty">전국 데이터가 없습니다.</div>'; return; }
    const maxPct = Math.max(...cands.map((c) => c.pct || 0)) || 100;
    const pc = (p) => (typeof partyColor === 'function' ? partyColor(p) : '#888');
    const ptc = (p) => (typeof partyTextColor === 'function' ? partyTextColor(p) : 'inherit');
    const bars = cands.map((c) => `<div class="pc-bar-row">
      <span class="name">${c.name || c.party || ''}</span>
      <span class="pc-bar"><span class="pc-bar-fill" style="width:${(c.pct / maxPct) * 100}%;background:${pc(c.party)}"></span></span>
      <span class="pct" style="color:${ptc(c.party)}">${c.pct}%</span></div>`).join('');
    pane.innerHTML = `<div class="poll-card"><div class="arc-hdr"><span class="arc-badge">${title}</span></div>${bars}</div>`;
  }

  function buildControls() {
    const controls = document.querySelector('.controls');
    if (!controls) return;
    controls.innerHTML = `
      <div class="seg" role="tablist" aria-label="자료">
        <button class="seg-btn${ps.mode === 'polls' ? ' is-active' : ''}" data-pmode="polls">여론조사</button>
        <button class="seg-btn${ps.mode === 'result' ? ' is-active' : ''}" data-pmode="result">실제 결과</button>
      </div>
      <div class="seg" role="tablist" aria-label="방식">
        <button class="seg-btn is-active" data-pview="dorling">dorling</button>
        <button class="seg-btn" data-pview="grid">격자</button>
      </div>`;
    controls.querySelectorAll('[data-pmode]').forEach((b) => b.addEventListener('click', () => {
      ps.mode = b.dataset.pmode;
      controls.querySelectorAll('[data-pmode]').forEach((x) => x.classList.toggle('is-active', x === b));
      render();
    }));
    controls.querySelectorAll('[data-pview]').forEach((b) => b.addEventListener('click', () => {
      ps.viewmode = b.dataset.pview;
      controls.querySelectorAll('[data-pview]').forEach((x) => x.classList.toggle('is-active', x === b));
      render();
    }));
  }

  // main.js init()에서 호출 — 대선이면 인계받아 true, 아니면 false.
  // 헤드라인 추이 컨테이너를 controls 앞에 1회 삽입
  function ensureTrendHost() {
    if (document.getElementById('pres-trend')) return;
    const controls = document.querySelector('.controls');
    const sec = document.createElement('section');
    sec.id = 'pres-trend';
    sec.className = 'pres-trend';
    if (controls && controls.parentElement) controls.parentElement.insertBefore(sec, controls);
    // 보조(지역·비례) 섹션 라벨
    if (controls && !document.getElementById('pres-secondary-label')) {
      const lab = document.createElement('div');
      lab.id = 'pres-secondary-label';
      lab.className = 'pres-secondary-label';
      lab.textContent = '지역·비례 분포';
      controls.parentElement.insertBefore(lab, controls);
    }
  }

  async function initPresIfNeeded() {
    if (!(typeof POLL_ELECTION === 'object' && POLL_ELECTION.kind === 'presidential')) return false;
    // 지선 전용 보기 토글(지도/격자) 숨김 — 자체 컨트롤 사용
    const vt = document.querySelector('.view-toggle'); if (vt) vt.hidden = true;
    ensureTrendHost();
    buildControls();
    await loadResults();
    renderTrend();   // 헤드라인 (모드 무관 — 폴 추이 + 실제 ◆)
    if (window.PollClimate) PollClimate.mount({ after: 'pres-trend' });  // 선거 무렵 국정·정당 지지
    render();        // 보조 (지역·비례 dorling/격자 + 전국 바)
    renderSigunguResult();   // 시군구 1위 후보 결과 맵(비동기)
    return true;
  }

  window.initPresIfNeeded = initPresIfNeeded;
})();
