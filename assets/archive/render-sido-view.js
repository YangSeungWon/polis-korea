// 시도 결과 — 헥스/지도 토글. races(scope=sido) 계산·섹션 표시 후 두 렌더러에 위임.
// opts: {tc='3'(광역단체장)|'1'(대선), hostId}. governorHex.draw + sidoMap.draw 사용.

(function () {
  function init(ctx, opts) {
    opts = opts || {};
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

    host.innerHTML = `
      <div class="ar-sido-toggle" role="tablist" aria-label="보기 전환">
        <button type="button" class="ar-sido-tab is-active" data-view="hex" aria-selected="true">헥스</button>
        <button type="button" class="ar-sido-tab" data-view="map" aria-selected="false">지도</button>
      </div>
      <div class="ar-sido-view" data-view="hex"></div>
      <div class="ar-sido-view" data-view="map" hidden></div>`;

    const hexView = host.querySelector('.ar-sido-view[data-view="hex"]');
    const mapView = host.querySelector('.ar-sido-view[data-view="map"]');
    A.governorHex?.draw?.(hexView, races);
    const mapDrawn = A.sidoMap?.draw?.(mapView, races);
    // 지도 모듈 없거나 실패하면 토글 숨김 (헥스만)
    if (!A.sidoMap) host.querySelector('.ar-sido-toggle')?.setAttribute('hidden', '');

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
    return mapDrawn;
  }

  window.Archive = window.Archive || {};
  window.Archive.sidoView = { init };
})();
