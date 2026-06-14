// 시도 결과 뷰 — 모드 토글. races(scope=sido) 계산·섹션 표시 후 렌더러 위임.
//   대선(tc=1): 격자 / dorling — 둘 다 득표 비례(승자독식 단색 거부).
//   지선 광역장(tc=3): 헥스 / 지도 — 시도마다 1명 실제 당선이라 1위 단색이 사실에 맞음.
// opts: {tc, hostId}.

(function () {
  // tc별 모드 정의: {key, label, draw(viewEl, races)}
  function modesFor(tc, A) {
    if (tc === '1') {
      return [
        { key: 'grid', label: '격자', draw: (el, rs) => A.sidoProp?.drawGrid?.(el, rs) },
        { key: 'dorling', label: 'dorling', draw: (el, rs) => A.sidoProp?.drawDorling?.(el, rs) },
      ];
    }
    return [
      { key: 'hex', label: '헥스', draw: (el, rs) => A.governorHex?.draw?.(el, rs) },
      { key: 'map', label: '지도', draw: (el, rs) => A.sidoMap?.draw?.(el, rs) },
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

    const modes = modesFor(tc, A).filter((m) => typeof m.draw === 'function');
    mount(host, modes, races);
  }

  window.Archive = window.Archive || {};
  window.Archive.sidoView = { init, mount };
})();
