// SVG viewBox 팬·줌 (방식 뷰 공용) — history enablePinchZoom 동작을 따름:
//   · Ctrl/⌘+휠만 줌(평소 휠=페이지 스크롤) · 핀치(2손가락) · 확대 상태에서만 드래그/1손가락 pan
//   · 더블탭 리셋 · 안 확대면 touchAction:pan-y(세로 스크롤 허용)·커서 일반, 확대면 none·grab
//   attach(svg, {baseViewBox?, cells?, maxScale?}) → handle {update, report, focusOn, reset, isZoomed, detach}
//     cells: [{region, cx, cy}] focus 앵커(report/focusOn). 같은 svg 재호출 시 리스너 유지+줌 복원.
//   커서↔유저좌표는 getScreenCTM().inverse()로 — preserveAspectRatio letterbox까지 정확.
(function () {
  function parseVB(svg) {
    const v = (svg.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
    return (v.length === 4 && v.every((n) => !isNaN(n))) ? v : [0, 0, 100, 100];
  }

  // 공용 리셋 버튼(history .pz-reset 룩) — 어느 viewport든 확대 중이면 표시. 위치 의존 없이 fixed.
  const _viewports = [];
  let _resetBtn = null;
  function ensureResetBtn() {
    if (_resetBtn || typeof document === 'undefined') return _resetBtn;
    _resetBtn = document.createElement('button');
    _resetBtn.type = 'button'; _resetBtn.textContent = '⤢ 전체'; _resetBtn.setAttribute('aria-label', '줌 초기화');
    _resetBtn.style.cssText = 'position:fixed;top:12px;right:12px;z-index:1200;background:rgba(10,14,26,0.82);'
      + 'color:#fff;border:none;font:600 12px Pretendard,system-ui,sans-serif;padding:6px 12px;border-radius:999px;'
      + 'cursor:pointer;box-shadow:0 1px 4px rgba(0,0,0,0.25);display:none;';
    _resetBtn.addEventListener('click', () => { _viewports.forEach((v) => { if (v.isZoomed()) v.reset(); }); });
    (document.body || document.documentElement).appendChild(_resetBtn);
    return _resetBtn;
  }
  function updateResetBtn() {
    // 떨어진(재렌더로 교체된) svg 정리 + 보이는 확대 viewport 있으면 버튼 표시.
    for (let i = _viewports.length - 1; i >= 0; i--) { if (!document.contains(_viewports[i].svg)) _viewports.splice(i, 1); }
    const show = _viewports.some((v) => v.isZoomed() && v.svg.getClientRects().length > 0);
    const btn = ensureResetBtn(); if (btn) btn.style.display = show ? '' : 'none';
  }

  function attach(svg, opts) {
    opts = opts || {};
    if (svg.__svgViewport) { svg.__svgViewport.update(opts); return svg.__svgViewport; }

    let base = opts.baseViewBox || parseVB(svg);
    let cells = opts.cells || [];
    let maxScale = opts.maxScale || 6;
    let scale = 1, cx = base[0] + base[2] / 2, cy = base[1] + base[3] / 2;
    let moved = false;

    const clampS = (s) => Math.max(1, Math.min(maxScale, s));
    const isZoomed = () => scale > 1.001;
    function updateTA() {
      svg.style.touchAction = isZoomed() ? 'none' : 'pan-y';
      svg.style.cursor = isZoomed() ? 'grab' : '';
    }
    function applyViewBox() {
      scale = clampS(scale);
      const w = base[2] / scale, h = base[3] / scale;
      cx = Math.max(base[0] + w / 2, Math.min(base[0] + base[2] - w / 2, cx));
      cy = Math.max(base[1] + h / 2, Math.min(base[1] + base[3] - h / 2, cy));
      svg.setAttribute('viewBox', `${(cx - w / 2).toFixed(2)} ${(cy - h / 2).toFixed(2)} ${w.toFixed(2)} ${h.toFixed(2)}`);
      updateTA();
      updateResetBtn();
    }
    // 전환 애니메이션 — viewBox(cx,cy,scale) rAF 트윈. 사용자 조작/새 focusOn 시 취소.
    let _anim = null;
    function cancelAnim() { if (_anim) { cancelAnimationFrame(_anim); _anim = null; } }
    function animateTo(tcx, tcy, ts, ms) {
      cancelAnim();
      const f = { cx, cy, scale }, dur = ms || 280; let t0 = 0;
      const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);
      const step = (now) => {
        if (!t0) t0 = now;
        const t = Math.min(1, (now - t0) / dur), k = ease(t);
        cx = f.cx + (tcx - f.cx) * k; cy = f.cy + (tcy - f.cy) * k; scale = f.scale + (ts - f.scale) * k;
        applyViewBox();
        _anim = (t < 1) ? requestAnimationFrame(step) : null;
      };
      _anim = requestAnimationFrame(step);
    }
    function clientToUser(x, y) {
      const m = svg.getScreenCTM(); if (!m) return { x: cx, y: cy };
      const p = svg.createSVGPoint(); p.x = x; p.y = y;
      const q = p.matrixTransform(m.inverse());
      return { x: q.x, y: q.y };
    }
    // 앵커(커서/핀치 중심) 고정 줌 — 줌 전후 그 유저좌표 차이만큼 중심 보정(letterbox 무관).
    function zoomAt(x, y, ns) {
      ns = clampS(ns); if (ns === scale) return;
      const u = clientToUser(x, y);
      scale = ns; applyViewBox();
      const u2 = clientToUser(x, y);
      cx += u.x - u2.x; cy += u.y - u2.y;
      applyViewBox();
    }
    function panBy(dxPx, dyPx) {
      const m = svg.getScreenCTM(); if (!m) return;
      cx -= dxPx / m.a; cy -= dyPx / m.d; applyViewBox();
    }

    // ── 데스크톱: Ctrl/⌘+휠 줌 + 확대 상태 드래그 pan ──────────────────
    function onWheel(e) {
      if (!(e.ctrlKey || e.metaKey)) return;   // 평소 휠은 페이지 스크롤(가로채지 않음)
      e.preventDefault(); cancelAnim();
      zoomAt(e.clientX, e.clientY, scale * Math.exp(-e.deltaY * 0.0015));
    }
    let mDrag = null;
    function onMouseDown(e) {
      if (e.button != null && e.button !== 0) return;
      if (!isZoomed()) return;   // 안 확대면 셀 클릭/페이지에 양보
      cancelAnim();
      mDrag = { x: e.clientX, y: e.clientY }; moved = false; svg.style.cursor = 'grabbing'; e.preventDefault();
    }
    function onMouseMove(e) {
      if (!mDrag) return;
      const dx = e.clientX - mDrag.x, dy = e.clientY - mDrag.y;
      if (!moved && Math.hypot(dx, dy) < 4) return;
      moved = true; panBy(dx, dy); mDrag.x = e.clientX; mDrag.y = e.clientY;
    }
    function onMouseUp() { if (mDrag) { mDrag = null; updateTA(); } }
    function onClickCapture(e) { if (moved) { e.stopPropagation(); e.preventDefault(); moved = false; } }

    // ── 터치: 핀치 줌 + 확대 상태 1손가락 pan + 더블탭 리셋 ──────────────
    let tmode = null, startD = 0, startScale = 1, pan0 = null, lastTap = 0;
    const dist = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
    function onTouchStart(e) {
      moved = false; cancelAnim();
      if (e.touches.length === 2) {
        tmode = 'pinch'; startD = dist(e.touches); startScale = scale; e.preventDefault();
      } else if (e.touches.length === 1) {
        const now = Date.now ? Date.now() : +new Date();
        if (now - lastTap < 300 && isZoomed()) { reset(); e.preventDefault(); }
        lastTap = now;
        tmode = isZoomed() ? 'pan' : 'tap';
        pan0 = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      }
    }
    function onTouchMove(e) {
      if (tmode === 'pinch' && e.touches.length === 2) {
        e.preventDefault(); moved = true;
        const mx = (e.touches[0].clientX + e.touches[1].clientX) / 2, my = (e.touches[0].clientY + e.touches[1].clientY) / 2;
        zoomAt(mx, my, startScale * (dist(e.touches) / (startD || 1)));
      } else if (tmode === 'pan' && e.touches.length === 1) {
        const dx = e.touches[0].clientX - pan0.x, dy = e.touches[0].clientY - pan0.y;
        if (!moved && Math.hypot(dx, dy) < 6) return;
        e.preventDefault(); moved = true; panBy(dx, dy);
        pan0.x = e.touches[0].clientX; pan0.y = e.touches[0].clientY;
      }
    }
    function onTouchEnd() { tmode = null; }

    svg.addEventListener('wheel', onWheel, { passive: false });
    svg.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    svg.addEventListener('click', onClickCapture, true);
    svg.addEventListener('touchstart', onTouchStart, { passive: false });
    svg.addEventListener('touchmove', onTouchMove, { passive: false });
    svg.addEventListener('touchend', onTouchEnd);

    function reset() { scale = 1; cx = base[0] + base[2] / 2; cy = base[1] + base[3] / 2; applyViewBox(); }

    const handle = {
      update(o) {
        o = o || {};
        if (o.baseViewBox) base = o.baseViewBox;
        if (o.cells) cells = o.cells;
        if (o.maxScale) maxScale = o.maxScale;
        applyViewBox();   // 렌더러가 viewBox를 base로 리셋했어도 현재 줌 복원
      },
      report() {
        if (!cells.length) return { region: null, scale };
        let best = null, bd = Infinity;
        for (const c of cells) { const d = (c.cx - cx) ** 2 + (c.cy - cy) ** 2; if (d < bd) { bd = d; best = c; } }
        return { region: best ? best.region : null, scale };
      },
      focusOn(region, s, o) {
        const c = region && cells.find((x) => x.region === region);
        const tcx = c ? c.cx : base[0] + base[2] / 2;
        const tcy = c ? c.cy : base[1] + base[3] / 2;
        const ts = c ? clampS(s || 1) : 1;
        // 보존(applyHost)은 스냅, 교차 전환은 트윈.
        if (o && o.animate === false) { cancelAnim(); cx = tcx; cy = tcy; scale = ts; applyViewBox(); }
        else animateTo(tcx, tcy, ts);
      },
      reset,
      isZoomed,
      detach() {
        cancelAnim();
        svg.removeEventListener('wheel', onWheel);
        svg.removeEventListener('mousedown', onMouseDown);
        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup', onMouseUp);
        svg.removeEventListener('click', onClickCapture, true);
        svg.removeEventListener('touchstart', onTouchStart);
        svg.removeEventListener('touchmove', onTouchMove);
        svg.removeEventListener('touchend', onTouchEnd);
        svg.style.cursor = ''; svg.style.touchAction = '';
        const i = _viewports.findIndex((v) => v.svg === svg); if (i >= 0) _viewports.splice(i, 1);
        delete svg.__svgViewport;
        updateResetBtn();
      },
      get scale() { return scale; },
    };
    svg.__svgViewport = handle;
    _viewports.push({ reset, isZoomed, svg });
    applyViewBox();
    return handle;
  }

  // 재렌더(토글) 시 호스트의 줌을 보존 — 글로벌 Focus 없이 호스트 단위(한 페이지 여러 카토그램 간섭 방지).
  function captureHost(host) {
    const old = host && host.querySelector && host.querySelector('svg');
    if (old && old.__svgViewport && typeof old.__svgViewport.report === 'function') {
      const r = old.__svgViewport.report();
      if (r && (r.scale || 1) > 1.05) return r;
    }
    return (host && host.__svgFocus) || null;
  }
  function applyHost(host, svg, opts, keep) {
    const h = attach(svg, opts);
    if (keep && keep.region && (keep.scale || 1) > 1.05) h.focusOn(keep.region, keep.scale, { animate: false });   // 보존=스냅
    if (host) host.__svgFocus = keep || null;
    return h;
  }

  window.SvgViewport = { attach, captureHost, applyHost };
})();
