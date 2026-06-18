// 시도 결과 뷰 — 모드 토글. races(scope=sido) 계산·섹션 표시 후 렌더러 위임.
//   대선(tc=1): 격자 / dorling — 둘 다 득표 비례(승자독식 단색 거부).
//   지선 광역장(tc=3): 헥스 / 지도 — 시도마다 1명 실제 당선이라 1위 단색이 사실에 맞음.
// opts: {tc, hostId}.

(function () {
  // 투표율 → 연한→진한 teal(정당색과 안 겹치는 중립 단색). 상대 스케일: lo·hi를 주면 이 선거
  // 최저~최고로 정규화(지역차 또렷). 없으면 절대 45~80% fallback. 선거마다 투표율대가 크게
  // 달라(지선 33~82·대선 71~87) 절대 스케일은 한쪽에 뭉쳐 — 지도당 상대화가 패턴을 드러냄.
  // 밝은 끝을 흰배경(≈250)·no-data 회색과 구분되는 연한 teal로(이전 238,243,241은 배경에 묻힘).
  const TURNOUT_STOPS = [[196, 224, 216], [78, 163, 145], [10, 74, 66]];
  function turnoutColor(pct, lo, hi) {
    const t = (hi != null && hi > lo)
      ? Math.max(0, Math.min(1, (pct - lo) / (hi - lo)))
      : Math.max(0, Math.min(1, (pct - 45) / 35));
    const seg = t < 0.5 ? 0 : 1;
    const f = t < 0.5 ? t / 0.5 : (t - 0.5) / 0.5;
    const a = TURNOUT_STOPS[seg], b = TURNOUT_STOPS[seg + 1];
    const c = a.map((v, i) => Math.round(v + (b[i] - v) * f));
    // hex로 반환 — pickTextColor가 hex만 파싱(rgb()면 흰검 전환 안 됨).
    return '#' + c.map((x) => x.toString(16).padStart(2, '0')).join('');
  }
  function turnoutBySido(races) {
    const canon = (typeof canonSido === 'function') ? canonSido : (x) => x;
    const m = {};
    for (const r of races || []) {
      const el = r.electors || 0, vt = r.voters ?? r.voted ?? 0;
      if (el > 0 && vt > 0) m[canon(r.sido)] = vt / el * 100;
    }
    return m;
  }
  // 시도별 투표율 hex — governorHex 재사용(fillOf/titleOf/hideEmpty 훅).
  function drawTurnout(el, races, A) {
    const tb = turnoutBySido(races);
    // 전남광주 통합(2026 9회) — 데이터 sido가 통합명이면 honamMergedLayout 셀(전남광주특별시)에 매핑.
    if (tb['전남광주통합특별시'] != null && tb['전남광주특별시'] == null) tb['전남광주특별시'] = tb['전남광주통합특별시'];
    if (!Object.keys(tb).length || !A.governorHex?.draw) { el.innerHTML = '<p class="ar-empty">투표율 데이터 없음</p>'; return; }
    const vals = Object.values(tb);
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const hostDiv = document.createElement('div');
    el.innerHTML = ''; el.appendChild(hostDiv);
    const merged = tb['전남광주특별시'] != null && typeof honamMergedLayout === 'function'
      && typeof SIDO_HEX_LAYOUT === 'object';
    A.governorHex.draw(hostDiv, [], {
      hideEmpty: true,
      layout: merged ? honamMergedLayout(SIDO_HEX_LAYOUT) : undefined,
      winnerOf: (sido) => (tb[sido] != null ? { name: '', party: null, pct: tb[sido], turnout: tb[sido] } : null),
      fillOf: (sido, win) => turnoutColor(win.turnout, lo, hi),
      titleOf: (sido, win) => (win ? `${sido} · 투표율 ${win.turnout.toFixed(1)}%` : `${sido} · 데이터 없음`),
    });
    hostDiv.querySelector('svg')?.classList.add('turnout-map');   // og 캡처 분류용(결과 hex와 구분)
    const ramp = `rgb(${TURNOUT_STOPS[0]}), rgb(${TURNOUT_STOPS[1]}), rgb(${TURNOUT_STOPS[2]})`;
    const leg = document.createElement('div');
    leg.className = 'ar-turnout-legend';
    leg.innerHTML = `<span>${lo.toFixed(1)}%</span><span class="ar-turnout-bar" style="background:linear-gradient(90deg,${ramp})"></span><span>${hi.toFixed(1)}%</span>`
      + `<span class="ar-turnout-range">이 선거 최저–최고</span>`;
    el.appendChild(leg);
  }

  // 시도 1위 hex (격차명도) — 대선 1위·총선 비례 선두. governorHex 재사용(winnerOf+opacityOf).
  //   마커 클래스 sido-winner-hex → OG/공유 키 'sido1'(지선 governor와 구분, 라벨 '시도 1위').
  function drawSidoWinnerHex(el, races) {
    const A = window.Archive || {};
    if (!A.governorHex || !A.governorHex.draw) return;
    const canon = (typeof canonSido === 'function') ? canonSido : (x) => x;
    const byS = {};
    for (const r of races || []) {
      const cs = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      if (cs[0]) byS[canon(r.sido)] = { name: cs[0].name, party: cs[0].party, pct: cs[0].pct, gap: cs[1] ? (cs[0].pct || 0) - (cs[1].pct || 0) : null };
    }
    A.governorHex.draw(el, [], {
      hideEmpty: true,
      winnerOf: (s) => byS[s] || null,
      opacityOf: (w) => (typeof gapOpacity === 'function' ? gapOpacity(w.gap) : 1),
    });
    const svg = el.querySelector('svg');
    if (svg) svg.classList.add('sido-winner-hex');
  }

  // tc별 모드 정의: {key, label, draw(viewEl, races)}
  function modesFor(tc, A) {
    if (tc === '1') {
      // 대선 시도 — 표비례(격자/원형) 기본. 균등(1위 hex 격차명도)·지도(geo 격차명도)는 1위 가족. 격자 default차 뒤에.
      return [
        { key: 'grid', label: '격자', draw: (el, rs) => A.sidoProp?.drawGrid?.(el, rs) },
        { key: 'dorling', label: '원형', draw: (el, rs) => A.sidoProp?.drawDorling?.(el, rs) },
        { key: 'hex', label: '균등', draw: (el, rs) => drawSidoWinnerHex(el, rs) },
        { key: 'map', label: '지도', draw: (el, rs) => A.sidoMap?.draw?.(el, rs, { margin: true }) },
        { key: 'turnout', label: '투표율', draw: (el, rs) => drawTurnout(el, rs, A) },
      ];
    }
    return [
      { key: 'hex', label: '균등', draw: (el, rs) => A.governorHex?.draw?.(el, rs) },
      { key: 'map', label: '지도', draw: (el, rs) => A.sidoMap?.draw?.(el, rs) },
      { key: 'turnout', label: '투표율', draw: (el, rs) => drawTurnout(el, rs, A) },
    ];
  }

  // 토글 UI를 host에 깔고 각 모드를 hidden view에 렌더. drawArg = 각 모드 draw(el)에 넘길 인자.
  function mount(host, modes, drawArg) {
    modes = modes.filter((m) => typeof m.draw === 'function');
    if (!modes.length) return;
    // 인코딩 토글(공용) — 아이콘+가족 한 바. 가족 게이팅은 ENC의 fam이 자동 분류:
    //   1위(균등·지도) / 표 비례(격자·원형) / 자료(투표율). 흩어진 .seg 토글과 단일 컴포넌트로 통일.
    const views = modes.map((m, i) =>
      `<div class="ar-sido-view" data-view="${m.key}"${i === 0 ? '' : ' hidden'}></div>`
    ).join('');
    host.innerHTML = `<div class="ar-sido-toggle"></div>${views}`;
    for (const m of modes) {
      const el = host.querySelector(`.ar-sido-view[data-view="${m.key}"]`);
      if (el) m.draw(el, drawArg);
    }
    // 투표율 탭은 정당색이 아닌 그라데이션 → 캡션도 전환(결과 캡션은 mount 직후 값 보존).
    const cap = host.closest && host.closest('.ar-section')?.querySelector('.ar-source-line');
    const resultCaption = cap ? cap.textContent : '';

    // 모드 전환 — 떠나는 뷰의 줌을 capture해 새 뷰에 apply(탭 교차 포커스 전이). region=시도라
    // 렌더러(균등 governorHex·격자/원형 sidoCluster·투표율) 무관하게 같은 키. svg 없는 뷰(leaflet)는 자연 스킵.
    function activate(v) {
      let keep = null;
      if (window.SvgViewport) {
        const cur = host.querySelector('.ar-sido-view:not([hidden]) svg');
        if (cur && cur.__svgViewport) { const r = cur.__svgViewport.report(); if (r && (r.scale || 1) > 1.05) keep = r; }
      }
      host.querySelectorAll('.ar-sido-view').forEach((el) => {
        el.toggleAttribute('hidden', el.dataset.view !== v);
      });
      if (keep) {
        const next = host.querySelector(`.ar-sido-view[data-view="${v}"] svg`);
        if (next && next.__svgViewport) next.__svgViewport.focusOn(keep.region, keep.scale);
      }
      if (cap) cap.textContent = (v === 'turnout')
        ? '시·도별 투표율 — 짙을수록 높음(투표수/선거인수).' : resultCaption;
    }

    const tog = host.querySelector('.ar-sido-toggle');
    if (window.EncodingToggle) {
      window.EncodingToggle.render(tog, {
        options: modes.map((m) => ({ key: m.key, label: m.label })),
        active: modes[0].key,
        onSelect: activate,
      });
    } else {
      // 폴백 — 가족 둘(표현 방식 ┊ 투표율)로 나눈 공용 .seg 바.
      const isTurnout = (m) => m.key === 'turnout';
      const enc = modes.filter((m) => !isTurnout(m));
      const turn = modes.filter(isTurnout);
      const btn = (m, active) =>
        `<button type="button" class="seg-btn${active ? ' is-active' : ''}" data-view="${m.key}" aria-selected="${active}">${m.label}</button>`;
      const seg = (label, ms, off) => (ms.length
        ? `<div class="seg" role="tablist" aria-label="${label}">${ms.map((m, i) => btn(m, off + i === 0)).join('')}</div>` : '');
      tog.innerHTML = seg('표현 방식', enc, 0) + seg('투표율', turn, enc.length);
      tog.querySelectorAll('.seg-btn').forEach((btnEl) => {
        btnEl.addEventListener('click', () => {
          tog.querySelectorAll('.seg-btn').forEach((b) => {
            const on = b === btnEl;
            b.classList.toggle('is-active', on);
            b.setAttribute('aria-selected', on ? 'true' : 'false');
          });
          activate(btnEl.dataset.view);
        });
      });
    }
  }

  function init(ctx, opts) {
    opts = opts || {};
    // 신규: opts.modes 직접 제공 → race-filter 없이 토글만 (총선·광역의회용). draw(el) 시그니처.
    if (opts.modes && opts.host) { mount(opts.host, opts.modes, null); return; }
    const tc = opts.tc || '3';
    const hostId = opts.hostId || 'ar-governor-hex';
    const host = document.getElementById(hostId);
    if (!host) return;
    const A = window.Archive || {};
    const races = (ctx?.results?.races || []).filter(
      (r) => r.scope === 'sido' && r.sg_typecode === tc
    );
    const section = host.closest('.ar-section') || host.parentElement;
    if (!races.length) { section?.setAttribute('hidden', ''); return; }
    section?.removeAttribute('hidden');

    const hasTurnout = races.some((r) => (r.electors || 0) > 0 && (r.voters ?? r.voted ?? 0) > 0);
    const modes = modesFor(tc, A)
      .filter((m) => typeof m.draw === 'function')
      .filter((m) => m.key !== 'turnout' || hasTurnout);
    mount(host, modes, races);
  }

  window.Archive = window.Archive || {};
  // drawTurnout 노출 — 총선(general.js)은 선거구를 시도로 합산한 pseudo-race[{sido,electors,voters}]로 호출.
  window.Archive.sidoView = { init, mount, drawTurnout: (el, races) => drawTurnout(el, races, window.Archive), drawSidoWinnerHex };
  // 투표율 색 스케일 공유 — 시군구 투표율 맵(render-council-hex)도 동일 절대 스케일 사용.
  window.Archive.turnout = { color: turnoutColor, stops: TURNOUT_STOPS };
})();
