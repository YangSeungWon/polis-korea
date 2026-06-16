// 시도 결과 뷰 — 모드 토글. races(scope=sido) 계산·섹션 표시 후 렌더러 위임.
//   대선(tc=1): 격자 / dorling — 둘 다 득표 비례(승자독식 단색 거부).
//   지선 광역장(tc=3): 헥스 / 지도 — 시도마다 1명 실제 당선이라 1위 단색이 사실에 맞음.
// opts: {tc, hostId}.

(function () {
  // 투표율 절대 스케일(45~80%) → 연한→진한 teal. 정당색과 안 겹치는 중립 단색 계열.
  const TURNOUT_STOPS = [[238, 243, 241], [78, 163, 145], [10, 74, 66]];
  function turnoutColor(pct) {
    const t = Math.max(0, Math.min(1, (pct - 45) / 35));
    const seg = t < 0.5 ? 0 : 1;
    const f = t < 0.5 ? t / 0.5 : (t - 0.5) / 0.5;
    const a = TURNOUT_STOPS[seg], b = TURNOUT_STOPS[seg + 1];
    const c = a.map((v, i) => Math.round(v + (b[i] - v) * f));
    return `rgb(${c[0]},${c[1]},${c[2]})`;
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
    if (!Object.keys(tb).length || !A.governorHex?.draw) { el.innerHTML = '<p class="ar-empty">투표율 데이터 없음</p>'; return; }
    const hostDiv = document.createElement('div');
    el.innerHTML = ''; el.appendChild(hostDiv);
    A.governorHex.draw(hostDiv, [], {
      hideEmpty: true,
      winnerOf: (sido) => (tb[sido] != null ? { name: '', party: null, pct: tb[sido], turnout: tb[sido] } : null),
      fillOf: (sido, win) => turnoutColor(win.turnout),
      titleOf: (sido, win) => (win ? `${sido} · 투표율 ${win.turnout.toFixed(1)}%` : `${sido} · 데이터 없음`),
    });
    const vals = Object.values(tb);
    const lo = Math.min(...vals).toFixed(1), hi = Math.max(...vals).toFixed(1);
    const ramp = `rgb(${TURNOUT_STOPS[0]}), rgb(${TURNOUT_STOPS[1]}), rgb(${TURNOUT_STOPS[2]})`;
    const leg = document.createElement('div');
    leg.className = 'ar-turnout-legend';
    leg.innerHTML = `<span>45%</span><span class="ar-turnout-bar" style="background:linear-gradient(90deg,${ramp})"></span><span>80%+</span>`
      + `<span class="ar-turnout-range">이 선거 ${lo}–${hi}%</span>`;
    el.appendChild(leg);
  }

  // tc별 모드 정의: {key, label, draw(viewEl, races)}
  function modesFor(tc, A) {
    if (tc === '1') {
      return [
        { key: 'grid', label: '격자', draw: (el, rs) => A.sidoProp?.drawGrid?.(el, rs) },
        { key: 'dorling', label: 'dorling', draw: (el, rs) => A.sidoProp?.drawDorling?.(el, rs) },
        { key: 'turnout', label: '투표율', draw: (el, rs) => drawTurnout(el, rs, A) },
      ];
    }
    return [
      { key: 'hex', label: '헥스', draw: (el, rs) => A.governorHex?.draw?.(el, rs) },
      { key: 'map', label: '지도', draw: (el, rs) => A.sidoMap?.draw?.(el, rs) },
      { key: 'turnout', label: '투표율', draw: (el, rs) => drawTurnout(el, rs, A) },
    ];
  }

  // 토글 UI를 host에 깔고 각 모드를 hidden view에 렌더. drawArg = 각 모드 draw(el)에 넘길 인자.
  function mount(host, modes, drawArg) {
    modes = modes.filter((m) => typeof m.draw === 'function');
    if (!modes.length) return;
    const tabs = modes.map((m, i) =>
      `<button type="button" class="ar-sido-tab${i === 0 ? ' is-active' : ''}" data-view="${m.key}" aria-selected="${i === 0}">${m.label}</button>`
    ).join('');
    const views = modes.map((m, i) =>
      `<div class="ar-sido-view" data-view="${m.key}"${i === 0 ? '' : ' hidden'}></div>`
    ).join('');
    host.innerHTML = `<div class="ar-sido-toggle" role="tablist" aria-label="보기 전환">${tabs}</div>${views}`;
    for (const m of modes) {
      const el = host.querySelector(`.ar-sido-view[data-view="${m.key}"]`);
      if (el) m.draw(el, drawArg);
    }
    // 투표율 탭은 정당색이 아닌 그라데이션 → 캡션도 전환(결과 캡션은 mount 직후 값 보존).
    const cap = host.closest && host.closest('.ar-section')?.querySelector('.ar-source-line');
    const resultCaption = cap ? cap.textContent : '';
    host.querySelectorAll('.ar-sido-tab').forEach((btn) => {
      btn.addEventListener('click', () => {
        const v = btn.dataset.view;
        host.querySelectorAll('.ar-sido-tab').forEach((b) => {
          const on = b === btn;
          b.classList.toggle('is-active', on);
          b.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        host.querySelectorAll('.ar-sido-view').forEach((el) => {
          el.toggleAttribute('hidden', el.dataset.view !== v);
        });
        if (cap) cap.textContent = (v === 'turnout')
          ? '시·도별 투표율 — 짙을수록 높음(투표수/선거인수).' : resultCaption;
      });
    });
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
  window.Archive.sidoView = { init, mount, drawTurnout: (el, races) => drawTurnout(el, races, window.Archive) };
})();
