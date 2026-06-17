// SVG viewBox 팬·줌 (방식 뷰 공용) — 휠=커서 기준 줌, 드래그=팬, base 경계 clamp, 최소 배율 1.
//   attach(svg, {baseViewBox?, cells?, maxScale?}) → handle {update, report, focusOn, reset, detach, scale}
//     cells: [{region, cx, cy}]  focus 앵커(report/focusOn용; Phase 1엔 선택).
//   같은 svg에 재호출하면 리스너 유지하고 base/cells만 갱신 — 렌더러가 innerHTML 비우고 viewBox를
//   base로 리셋해도 update()가 현재 줌/중심을 다시 적용(applyViewBox). 따라서 지역 선택 재렌더에도 줌 유지.
//   커서↔유저좌표는 getScreenCTM().inverse()로 — preserveAspectRatio letterbox까지 정확.
(function () {
  function parseVB(svg) {
    const v = (svg.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
    return (v.length === 4 && v.every((n) => !isNaN(n))) ? v : [0, 0, 100, 100];
  }

  function attach(svg, opts) {
    opts = opts || {};
    if (svg.__svgViewport) { svg.__svgViewport.update(opts); return svg.__svgViewport; }

    let base = opts.baseViewBox || parseVB(svg);
    let cells = opts.cells || [];
    let maxScale = opts.maxScale || 8;
    let scale = 1, cx = base[0] + base[2] / 2, cy = base[1] + base[3] / 2;
    let moved = false;

    const clampS = (s) => Math.max(1, Math.min(maxScale, s));
    function applyViewBox() {
      scale = clampS(scale);
      const w = base[2] / scale, h = base[3] / scale;
      cx = Math.max(base[0] + w / 2, Math.min(base[0] + base[2] - w / 2, cx));
      cy = Math.max(base[1] + h / 2, Math.min(base[1] + base[3] - h / 2, cy));
      svg.setAttribute('viewBox', `${(cx - w / 2).toFixed(2)} ${(cy - h / 2).toFixed(2)} ${w.toFixed(2)} ${h.toFixed(2)}`);
    }
    function clientToUser(x, y) {
      const m = svg.getScreenCTM(); if (!m) return { x: cx, y: cy };
      const p = svg.createSVGPoint(); p.x = x; p.y = y;
      const q = p.matrixTransform(m.inverse());
      return { x: q.x, y: q.y };
    }
    // 커서 고정 줌 — 줌 전/후 커서 아래 유저좌표 차이만큼 중심 보정(letterbox 무관).
    function zoomAt(x, y, ns) {
      ns = clampS(ns); if (ns === scale) return;
      const u = clientToUser(x, y);
      scale = ns; applyViewBox();
      const u2 = clientToUser(x, y);
      cx += u.x - u2.x; cy += u.y - u2.y;
      applyViewBox();
    }

    function onWheel(e) {
      e.preventDefault();
      zoomAt(e.clientX, e.clientY, scale * Math.exp(-e.deltaY * 0.0015));
    }
    let dragging = false, lx = 0, ly = 0, travel = 0;
    function onDown(e) {
      if (e.button != null && e.button !== 0) return;
      dragging = true; moved = false; travel = 0; lx = e.clientX; ly = e.clientY;
      try { svg.setPointerCapture(e.pointerId); } catch (_) { /* noop */ }
    }
    function onMove(e) {
      if (!dragging) return;
      const m = svg.getScreenCTM(); if (!m) return;
      const dx = e.clientX - lx, dy = e.clientY - ly;
      travel += Math.abs(dx) + Math.abs(dy);
      if (travel > 4) moved = true;   // 임계 넘으면 드래그 → 뒤 click 억제
      cx -= dx / m.a; cy -= dy / m.d;
      lx = e.clientX; ly = e.clientY;
      applyViewBox();
    }
    function onUp(e) { dragging = false; try { svg.releasePointerCapture(e.pointerId); } catch (_) { /* noop */ } }
    // 드래그 직후의 click(셀 선택)은 삼킴 — 팬과 선택 구분.
    function onClickCapture(e) { if (moved) { e.stopPropagation(); e.preventDefault(); moved = false; } }

    svg.addEventListener('wheel', onWheel, { passive: false });
    svg.addEventListener('pointerdown', onDown);
    svg.addEventListener('pointermove', onMove);
    svg.addEventListener('pointerup', onUp);
    svg.addEventListener('pointercancel', onUp);
    svg.addEventListener('click', onClickCapture, true);
    svg.style.touchAction = 'none';
    svg.style.cursor = 'grab';

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
      focusOn(region, s) {
        const c = region && cells.find((x) => x.region === region);
        if (c) { cx = c.cx; cy = c.cy; scale = clampS(s || 1); }
        else { cx = base[0] + base[2] / 2; cy = base[1] + base[3] / 2; scale = 1; }
        applyViewBox();
      },
      reset() { scale = 1; cx = base[0] + base[2] / 2; cy = base[1] + base[3] / 2; applyViewBox(); },
      detach() {
        svg.removeEventListener('wheel', onWheel);
        svg.removeEventListener('pointerdown', onDown);
        svg.removeEventListener('pointermove', onMove);
        svg.removeEventListener('pointerup', onUp);
        svg.removeEventListener('pointercancel', onUp);
        svg.removeEventListener('click', onClickCapture, true);
        svg.style.cursor = ''; svg.style.touchAction = '';
        delete svg.__svgViewport;
      },
      get scale() { return scale; },
    };
    svg.__svgViewport = handle;
    applyViewBox();
    return handle;
  }

  window.SvgViewport = { attach };
})();
