// 대선 폴 페이지 — 시도 비례(격자/dorling)를 PollCellAdapter + Archive.sidoProp로 렌더.
//   여론조사(pct) ↔ 실제(votes) 토글. 지선 모놀리식 경로를 타지 않고 별도 init(initPresIfNeeded).
//   PoC: 시도 비례 + 전국 요약 패널. (지도 모드·시군구는 후속.)
(function () {
  'use strict';

  const ps = { mode: 'polls', viewmode: 'dorling', sidoRaces: [], nationRace: null, weights: {} };

  // 전국 대통령(후보) 폴만 — 추이선용
  function nationalCandPolls() {
    return (state.data.polls || []).filter((p) => p.office_level === '대통령' && !p.sido && (p.candidates || []).length);
  }

  // 헤드라인: 본선 후보 지지율 추이 (전국 시계열 + 선거일 실제 ◆)
  // 본선 horse-race만 — 실제 결과 후보(권위)를 본선 집합으로, 상위 2인(당선·차점) 모두
  // 등장 + 본선후보 합≥70 인 폴만. 경선·가상대결·truncated/단독적합 자동 제외(날짜 하드코딩 X).
  function renderTrend() {
    let host = document.getElementById('pres-trend');
    if (!host) return;
    if (typeof buildPartyTrendSVG !== 'function') { host.hidden = true; return; }
    const finalCands = ((ps.nationRace && ps.nationRace.candidates) || [])
      .filter((c) => c.pct != null).slice().sort((a, b) => b.pct - a.pct);
    if (finalCands.length < 2) { host.hidden = true; return; }
    const finalSet = new Set(finalCands.map((c) => c.name));
    const top2 = [finalCands[0].name, finalCands[1].name];
    const polls = nationalCandPolls().filter((p) => {
      const named = (p.candidates || []).filter((c) => c.pct != null);
      const names = new Set(named.map((c) => c.name));
      if (!top2.every((n) => names.has(n))) return false;              // 본선 양강 모두 있어야
      const s = named.filter((c) => finalSet.has(c.name)).reduce((a, c) => a + c.pct, 0);
      return s >= 70;                                                  // 본선후보 합 정상 (truncated/적합 컷)
    }).map((p) => ({ ...p, candidates: (p.candidates || []).filter((c) => finalSet.has(c.name)) }));
    if (!polls.length) { host.hidden = true; return; }
    const actual = finalCands.map((c) => ({ key: c.name, pct: c.pct }));
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
      const races = d.races || [];
      ps.sidoRaces = races.filter((x) => x.scope === 'sido');
      ps.nationRace = races.find((x) => x.scope === 'nation') || null;
      ps.weights = PollCellAdapter.weightsFromResults(races);
    } catch (e) { /* 결과 없으면 폴 모드만 */ }
  }

  function cells() {
    return ps.mode === 'result'
      ? PollCellAdapter.cellsFromResults(ps.sidoRaces)
      : PollCellAdapter.cellsFromPolls(state.data.polls || [], { office: '대통령', weights: ps.weights });
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
    sp[ps.viewmode === 'grid' ? 'drawGrid' : 'drawDorling'](h, cs, legend ? { legend } : undefined);
    renderDetail();
  }

  // 우측 패널 — 전국 요약 (모드별: 여론조사 최신 전국 / 실제 전국)
  function renderDetail() {
    const pane = document.getElementById('detail-pane');
    if (!pane) return;
    let cands = [];
    let title = '';
    if (ps.mode === 'result') {
      cands = (ps.nationRace && ps.nationRace.candidates || []).map((c) => ({ name: c.name, party: c.party, pct: c.pct }));
      title = '전국 실제 결과';
    } else {
      // 최신 전국 대선 폴
      let best = null;
      for (const p of state.data.polls || []) {
        if (p.office_level !== '대통령' || p.sido) continue;
        if (!best || (p.period_end || '') > (best.period_end || '')) best = p;
      }
      cands = (best && best.candidates || []).map((c) => ({ name: c.name, party: c.party, pct: c.pct }));
      title = best ? `전국 여론조사 (최신 ${best.period_end || ''})` : '전국 여론조사';
    }
    cands = cands.filter((c) => c.pct != null).sort((a, b) => (b.pct || 0) - (a.pct || 0));
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
        <button class="seg-btn is-active" data-pmode="polls">여론조사</button>
        <button class="seg-btn" data-pmode="result">실제 결과</button>
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
    render();        // 보조 (지역·비례 dorling/격자 + 전국 바)
    return true;
  }

  window.initPresIfNeeded = initPresIfNeeded;
})();
