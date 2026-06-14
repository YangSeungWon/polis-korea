// 지역구(254) hex 렌더 — 데이터 무관 공유 렌더러.
//   drawDistrictHex(svg, layout, resultFn, opts)
//     layout   = data/geo/district_hex_{n}.json 셀 [{sido,name,c,r,sigungus}]
//     resultFn = (sido,name) → { candidates:[{name,party,pct,votes}] (정렬됨) } | null
//     opts     = { selected:{sido,name}, onSelect(sido,name), r }
//   src/history/geomap.ts renderDistrictHex에서 소선거구 핵심만 포팅(조랭이떡/중선거구 제외).
//   의존: hexgrid.js(hexCenter/hexPoints/drawHexBorders) · parties.js(partyColor/partyTextColor/
//   SIDO_HEX_LAYOUT) · utils.js(drawSidoEdgeLabels/SIDO_EDGE_MARGIN). (향후 geomap도 이걸 쓰도록 dedup 가능)
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';

  // 선거구명 → {prefix(시도약칭), short(축약)} — geomap.ts shortDistrictLabel 포팅
  function shortLabel(name, sido) {
    const m = name.match(/^(.+?)([갑을병정무])$/);
    const base = m ? m[1] : name;
    const suf = m ? m[2] : '';
    const parts = base.match(/[가-힣]+?(?:특별자치시|특별시|광역시|특별자치도|시|군|구)/g) || [base];
    let body = parts.length === 1
      ? parts[0].replace(/(시|군|구)$/, '')
      : parts.map((p) => p.replace(/(시|군|구)$/, '').slice(0, 2)).join('/');
    if (suf) body += suf;
    const FB = { '전라남도': '전남', '광주광역시': '광주', '강원도': '강원', '제주도': '제주', '전라북도': '전북' };
    const layout = (typeof SIDO_HEX_LAYOUT !== 'undefined') ? SIDO_HEX_LAYOUT : {};
    const abbr = sido ? ((layout[sido] && layout[sido].label) || FB[sido] || sido.slice(0, 2)) : '';
    return { prefix: abbr, short: body };
  }

  function drawDistrictHex(svg, layout, resultFn, opts) {
    opts = opts || {};
    svg.innerHTML = '';
    if (!layout || !layout.length) return;
    const r = opts.r || 22;
    const colW = r * Math.sqrt(3), rowH = r * 1.5;
    const cs = layout.map((d) => d.c), rs = layout.map((d) => d.r);
    const minC = Math.min(...cs), minR = Math.min(...rs), maxC = Math.max(...cs), maxR = Math.max(...rs);
    const w = (maxC - minC + 2) * colW, h = (maxR - minR + 2) * rowH;
    const margin = (typeof SIDO_EDGE_MARGIN !== 'undefined') ? SIDO_EDGE_MARGIN : 78;
    svg.setAttribute('viewBox', `${-margin} 0 ${Math.ceil(w) + 2 * margin} ${Math.ceil(h)}`);
    svg.setAttribute('width', '100%');
    const offX = -minC * colW + colW / 2, offY = -minR * rowH + rowH;
    const cellAt = new Map();
    for (const d of layout) cellAt.set(`${d.c},${d.r}`, d);
    const sel = opts.selected;

    for (const d of layout) {
      const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
      const result = resultFn(d.sido, d.name);
      const top = result && result.candidates && result.candidates[0];
      const fill = top ? partyColor(top.party) : '#e6e9ef';
      const isSel = sel && sel.sido === d.sido && sel.name === d.name;
      const g = document.createElementNS(NS, 'g');
      g.style.cursor = result ? 'pointer' : 'default';
      if (opts.onSelect) g.addEventListener('click', () => opts.onSelect(d.sido, d.name, result));

      const poly = document.createElementNS(NS, 'polygon');
      poly.setAttribute('points', hexPoints(cx, cy, r - 0.7));
      poly.setAttribute('fill', fill);
      poly.setAttribute('stroke', '#0a0e1a');
      poly.setAttribute('stroke-width', isSel ? '1.8' : '0.6');
      poly.setAttribute('fill-opacity', top ? '1' : '0.45');
      g.appendChild(poly);

      const title = document.createElementNS(NS, 'title');
      title.textContent = top
        ? `${d.sido} ${d.name} · ${top.name || ''} (${top.party}) ${top.pct != null ? top.pct.toFixed(1) + '%' : ''}`
        : `${d.sido} ${d.name} · 데이터 없음`;
      g.appendChild(title);

      const lbl = shortLabel(d.name, d.sido);
      const txt = document.createElementNS(NS, 'text');
      txt.setAttribute('x', String(cx));
      txt.setAttribute('text-anchor', 'middle');
      txt.setAttribute('font-weight', '600');
      txt.setAttribute('pointer-events', 'none');
      txt.setAttribute('fill', top ? partyTextColor(top.party) : '#0a0e1a');
      txt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
      if (lbl.prefix) {
        const a = document.createElementNS(NS, 'tspan');
        a.setAttribute('x', String(cx)); a.setAttribute('y', String(cy - 2));
        a.setAttribute('font-size', '6'); a.setAttribute('opacity', '0.75');
        a.textContent = lbl.prefix; txt.appendChild(a);
        const b = document.createElementNS(NS, 'tspan');
        b.setAttribute('x', String(cx)); b.setAttribute('y', String(cy + 8));
        b.setAttribute('font-size', lbl.short.length > 4 ? '6' : lbl.short.length > 3 ? '7' : '9');
        b.textContent = lbl.short; txt.appendChild(b);
      } else {
        txt.setAttribute('y', String(cy + 3));
        txt.setAttribute('font-size', lbl.short.length > 4 ? '6' : '8');
        txt.textContent = lbl.short;
      }
      g.appendChild(txt);
      svg.appendChild(g);
    }
    if (typeof drawHexBorders === 'function') drawHexBorders(svg, layout, cellAt, colW, rowH, offX, offY, r, '1.8', true);
    if (typeof drawSidoEdgeLabels === 'function') {
      drawSidoEdgeLabels(svg, layout.map((d) => {
        const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
        return { sido: d.sido, cx, cy };
      }));
    }
  }

  window.drawDistrictHex = drawDistrictHex;
})();
