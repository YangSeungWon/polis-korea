// 시군구 1위색 hex — 데이터 무관 공유 렌더러 (폴 기초단체장·향후 아카이브 공용 단일 소스).
//   drawSigunguHex(svg, cells, resultFn, opts) → geom {colW,rowH,offX,offY}
//     cells    = [{sido,name,c,r,...}]  (data/geo/sigungu_hex.json 등)
//     resultFn = (sido,name,cell) → winner | null   winner={party,name?,pct?,...}
//     opts = { r=22, selected:{sido,name}, onSelect(sido,name,winner,cell),
//              opacityOf(winner)→fill-opacity, dashOf(winner)→stroke-dasharray|null,
//              tooltipOf(sido,name,winner)→title, labelFn(name,sido)→{prefix,short},
//              borders=true, borderWidth='1.6' }
//   단일 hex(1위 정당색) choropleth만 — 격자/dorling 카토그램은 호출부(history)가 자체 처리.
//   의존: hexgrid.js(hexCenter/hexPoints/drawHexBorders) · parties.js(partyColor/pickTextColor) · shortSigunguLabel(utils)
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';

  function drawSigunguHex(svg, cells, resultFn, opts) {
    opts = opts || {};
    svg.innerHTML = '';
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', '100%');
    if (!cells || !cells.length) return null;
    const r = opts.r || 22;
    const colW = r * Math.sqrt(3), rowH = r * 1.5;
    const cs = cells.map((d) => d.c), rs = cells.map((d) => d.r);
    const minC = Math.min(...cs), minR = Math.min(...rs), maxC = Math.max(...cs), maxR = Math.max(...rs);
    const w = (maxC - minC + 2) * colW, h = (maxR - minR + 2) * rowH;
    const m = opts.margin || 0;   // 좌우 여백(history 시도 워터마크/edge 라벨용)
    svg.setAttribute('viewBox', `${-m} 0 ${Math.ceil(w) + 2 * m} ${Math.ceil(h)}`);
    const offX = -minC * colW + colW / 2, offY = -minR * rowH + rowH;
    // underlay: 셀 뒤(배경) 그리기 — history 시도명 워터마크 등. clear 직후·셀 루프 전.
    if (opts.underlay) opts.underlay(svg, { colW, rowH, offX, offY });
    const sel = opts.selected;
    const isSel = (d) => !!(sel && sel.sido === d.sido && sel.name === d.name);
    const labelFn = opts.labelFn || ((typeof shortSigunguLabel === 'function') ? shortSigunguLabel : (n) => ({ short: n }));

    for (const d of cells) {
      const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
      const result = resultFn(d.sido, d.name, d);
      const fill = result ? partyColor(result.party) : 'var(--bg3, #e6e9ef)';
      const op = (result && opts.opacityOf) ? opts.opacityOf(result) : 1;
      const poly = document.createElementNS(NS, 'polygon');
      poly.setAttribute('class', 'hex-cell ' + (result ? 'has-data' : 'no-data') + (isSel(d) ? ' is-selected' : ''));
      poly.setAttribute('points', hexPoints(cx, cy, r - 0.7));
      poly.setAttribute('fill', fill);
      poly.setAttribute('stroke', 'var(--ink, #0a0e1a)');
      poly.setAttribute('stroke-width', isSel(d) ? '1.6' : '0.7');
      poly.setAttribute('fill-opacity', op);
      if (result && opts.dashOf) { const dash = opts.dashOf(result); if (dash) poly.setAttribute('stroke-dasharray', dash); }
      // 여론조사 빗나감 — 점선 테두리색 = 여론조사가 예측한 정당색(missOf 반환).
      const missCol = opts.missOf && opts.missOf(d.sido, d.name);
      if (missCol) { poly.setAttribute('stroke', missCol); poly.setAttribute('stroke-width', '2.2'); poly.setAttribute('stroke-dasharray', '2.5,2'); poly.classList.add('hex-poll-miss'); }
      if (opts.onSelect) {
        poly.style.cursor = 'pointer';
        poly.addEventListener('click', () => opts.onSelect(d.sido, d.name, result, d));
      }
      const title = document.createElementNS(NS, 'title');
      title.textContent = opts.tooltipOf ? opts.tooltipOf(d.sido, d.name, result)
        : `${d.sido} ${d.name}${result ? ' · ' + (result.name || result.party || '') : ''}`;
      poly.appendChild(title);
      svg.appendChild(poly);

      // 라벨 — prefix 있으면 두 줄
      const label = labelFn(d.name, d.sido);
      if (label && label.short) {
        const txt = document.createElementNS(NS, 'text');
        txt.setAttribute('x', cx);
        txt.setAttribute('text-anchor', 'middle');
        txt.setAttribute('font-weight', '600');
        txt.setAttribute('fill', result && typeof pickTextColor === 'function' ? pickTextColor(fill, op) : 'var(--ink, #0a0e1a)');
        txt.setAttribute('pointer-events', 'none');
        txt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
        if (label.prefix) {
          const tp1 = document.createElementNS(NS, 'tspan');
          tp1.setAttribute('x', cx); tp1.setAttribute('y', cy - 2);
          tp1.setAttribute('font-size', '6'); tp1.setAttribute('opacity', '0.75');
          tp1.textContent = label.prefix; txt.appendChild(tp1);
          const tp2 = document.createElementNS(NS, 'tspan');
          tp2.setAttribute('x', cx); tp2.setAttribute('y', cy + 8);
          tp2.setAttribute('font-size', label.short.length > 3 ? '7' : '9');
          tp2.textContent = label.short; txt.appendChild(tp2);
        } else {
          txt.setAttribute('y', cy + 3);
          txt.setAttribute('font-size', label.short.length > 3 ? '7' : '9');
          txt.textContent = label.short;
        }
        svg.appendChild(txt);
      }
    }

    if (opts.borders !== false && typeof drawHexBorders === 'function') {
      const cellAt = new Map();
      for (const d of cells) cellAt.set(`${d.c},${d.r}`, d);
      drawHexBorders(svg, cells, cellAt, colW, rowH, offX, offY, r, opts.borderWidth || '1.6', true);
    }
    return { colW, rowH, offX, offY };
  }

  window.drawSigunguHex = drawSigunguHex;
})();
