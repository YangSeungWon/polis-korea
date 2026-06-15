// 지역구 hex 렌더 — 데이터 무관 공유 렌더러 (history geomap·총선 폴 공용 단일 소스).
//   drawDistrictHex(svg, layout, resultFn, opts) → geom {colW,rowH,offX,offY,w,h,r,minR,maxR}
//     layout   = data/geo/district_hex_{n}.json 셀 [{sido,name,c,r,(wi)}]
//     resultFn = (sido,name) → result | null  (result.candidates / result.winners / result.uncontested)
//     opts = { selected:{sido,name}, onSelect(sido,name,result), r,
//              topFn(result)→top후보, textColor(fill,opacity,party)→글자색, emptyOpacity, emptyFill }
//   254 셀(소선거구) + 중선거구(9~12대 조랭이떡) + 시도경계 + 시도라벨까지. 비례 컬럼은
//   호출부(history geomap)가 반환된 geom으로 우측에 직접 덧그림(페이지별이라 공유 안 함).
//   의존: hexgrid.js · parties.js(partyColor/partyTextColor/SIDO_HEX_LAYOUT) · utils.js(drawSidoEdgeLabels/SIDO_EDGE_MARGIN)
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';

  // 중선거구(1구 2인) 2색 줄무늬 패턴 — geomap.ts _jungPattern 포팅
  const _jpIds = {}; let _jpN = 0;
  function jungPattern(parties) {
    const key = parties[0] + '|' + parties[1];
    if (_jpIds[key]) return `url(#${_jpIds[key]})`;
    let host = document.getElementById('jung-pat-defs');
    if (!host) {
      host = document.createElementNS(NS, 'svg');
      host.id = 'jung-pat-defs';
      host.setAttribute('style', 'position:absolute;width:0;height:0;overflow:hidden');
      host.appendChild(document.createElementNS(NS, 'defs'));
      document.body.appendChild(host);
    }
    const id = 'jp' + (_jpN++);
    _jpIds[key] = id;
    const p = document.createElementNS(NS, 'pattern');
    p.id = id; p.setAttribute('width', '8'); p.setAttribute('height', '8');
    p.setAttribute('patternUnits', 'userSpaceOnUse'); p.setAttribute('patternTransform', 'rotate(45)');
    p.innerHTML = `<rect width="8" height="8" fill="${partyColor(parties[0])}"/>`
      + `<rect width="4" height="8" fill="${partyColor(parties[1])}"/>`;
    host.querySelector('defs').appendChild(p);
    return `url(#${id})`;
  }

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
    const lay = (typeof SIDO_HEX_LAYOUT !== 'undefined') ? SIDO_HEX_LAYOUT : {};
    const abbr = sido ? ((lay[sido] && lay[sido].label) || FB[sido] || sido.slice(0, 2)) : '';
    return { prefix: abbr, short: body };
  }

  function drawDistrictHex(svg, layout, resultFn, opts) {
    opts = opts || {};
    svg.innerHTML = '';
    if (!layout || !layout.length) return null;
    const r = opts.r || 22;
    const topFn = opts.topFn || ((res) => res && res.candidates && res.candidates[0]);
    const tColor = opts.textColor || ((fill, op, party) => (typeof partyTextColor === 'function' ? partyTextColor(party) : '#0a0e1a'));
    const emptyOpacity = opts.emptyOpacity != null ? opts.emptyOpacity : 1;
    const emptyFill = opts.emptyFill || '#e6e9ef';
    const colW = r * Math.sqrt(3), rowH = r * 1.5;
    const cs = layout.map((d) => d.c), rs = layout.map((d) => d.r);
    const minC = Math.min(...cs), minR = Math.min(...rs), maxC = Math.max(...cs), maxR = Math.max(...rs);
    const w = (maxC - minC + 2) * colW, h = (maxR - minR + 2) * rowH;
    const margin = (typeof SIDO_EDGE_MARGIN !== 'undefined') ? SIDO_EDGE_MARGIN : 78;
    svg.setAttribute('viewBox', `${-margin} 0 ${Math.ceil(w) + 2 * margin} ${Math.ceil(h)}`);
    svg.setAttribute('width', '100%'); svg.setAttribute('height', '100%');
    const offX = -minC * colW + colW / 2, offY = -minR * rowH + rowH;
    const cellAt = new Map();
    for (const d of layout) cellAt.set(`${d.c},${d.r}`, d);
    const sel = opts.selected;

    for (const d of layout) {
      const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
      const result = resultFn(d.sido, d.name);
      const top = topFn(result);
      let fill = top ? partyColor(top.party) : emptyFill;
      const ws = result && result.winners;            // 중선거구(1구 2인)
      const cellWin = (d.wi !== undefined && ws && ws[d.wi]) ? ws[d.wi] : null;
      if (cellWin) fill = partyColor(cellWin.party);
      else if (ws && ws.length >= 2 && ws[0].party !== ws[1].party) fill = jungPattern([ws[0].party, ws[1].party]);
      const isPattern = fill.charAt(0) !== '#';
      const isZorangi = d.wi !== undefined;
      const isSel = sel && sel.sido === d.sido && sel.name === d.name;

      const g = document.createElementNS(NS, 'g');
      g.style.cursor = result ? 'pointer' : 'default';
      if (opts.onSelect) g.addEventListener('click', () => opts.onSelect(d.sido, d.name, result));

      const poly = document.createElementNS(NS, 'polygon');
      poly.setAttribute('points', hexPoints(cx, cy, isZorangi ? r : r - 0.7));
      poly.setAttribute('fill', fill);
      poly.setAttribute('fill-opacity', String(top ? 1 : emptyOpacity));
      if (isZorangi) { poly.setAttribute('stroke', 'none'); }
      else { poly.setAttribute('stroke', '#0a0e1a'); poly.setAttribute('stroke-width', isSel ? '1.6' : '0.7'); }
      // 여론조사 빗나감 — 실제 모드에서 막판 조사 1위 ≠ 실제 당선인 지역구.
      if (opts.missOf && opts.missOf(d.sido, d.name)) {
        poly.setAttribute('stroke-width', '2'); poly.setAttribute('stroke-dasharray', '2.5,2'); poly.classList.add('hex-poll-miss');
      }
      g.appendChild(poly);

      const title = document.createElementNS(NS, 'title');
      const unc = result && (result.uncontested || result.is_uncontested);
      title.textContent = cellWin
        ? `${d.sido} ${d.name} · ${cellWin.name} (${cellWin.party}) 당선`
        : top
          ? `${d.sido} ${d.name} · ${top.name || ''} (${top.party}) ${unc ? '무투표 당선' : (top.pct != null ? top.pct.toFixed(1) + '%' : '')}`
          : `${d.sido} ${d.name} · 데이터 없음`;
      g.appendChild(title);

      const lbl = cellWin ? { prefix: '', short: cellWin.name } : shortLabel(d.name, d.sido);
      const txt = document.createElementNS(NS, 'text');
      txt.setAttribute('x', String(cx)); txt.setAttribute('text-anchor', 'middle');
      txt.setAttribute('font-weight', '600'); txt.setAttribute('pointer-events', 'none');
      txt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
      txt.setAttribute('fill', top ? (isPattern ? '#fff' : tColor(fill, 1, top.party)) : '#0a0e1a');
      if (lbl.prefix) {
        const a = document.createElementNS(NS, 'tspan');
        a.setAttribute('x', String(cx)); a.setAttribute('y', String(cy - 2));
        a.setAttribute('font-size', '6'); a.setAttribute('opacity', '0.75'); a.textContent = lbl.prefix; txt.appendChild(a);
        const b = document.createElementNS(NS, 'tspan');
        b.setAttribute('x', String(cx)); b.setAttribute('y', String(cy + 8));
        b.setAttribute('font-size', lbl.short.length > 4 ? '6' : lbl.short.length > 3 ? '7' : '9');
        b.textContent = lbl.short; txt.appendChild(b);
      } else {
        txt.setAttribute('y', String(cy + 3));
        txt.setAttribute('font-size', lbl.short.length > 4 ? '6' : '8'); txt.textContent = lbl.short;
      }
      g.appendChild(txt);
      svg.appendChild(g);
    }

    // 조랭이떡 쌍 외곽선 — 같은 선거구 두 칸 사이는 skip(한 덩이), 나머지엔 테두리
    if (layout.some((d) => d.wi !== undefined) && typeof nbrs === 'function') {
      for (const d of layout) {
        if (d.wi === undefined) continue;
        const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
        const ns2 = nbrs(d.c, d.r);
        const selPair = sel && sel.sido === d.sido && sel.name === d.name;
        for (let i = 0; i < 6; i++) {
          const nb = cellAt.get(`${ns2[i][0]},${ns2[i][1]}`);
          if (nb && nb.name === d.name && nb.sido === d.sido) continue;
          const e = NBR_TO_EDGE[i];
          const [x1, y1] = corner(cx, cy, r, e);
          const [x2, y2] = corner(cx, cy, r, (e + 1) % 6);
          const line = document.createElementNS(NS, 'line');
          line.setAttribute('x1', String(x1)); line.setAttribute('y1', String(y1));
          line.setAttribute('x2', String(x2)); line.setAttribute('y2', String(y2));
          line.setAttribute('stroke', selPair ? '#0a0e1a' : 'rgba(10,14,26,0.5)');
          line.setAttribute('stroke-width', selPair ? '2' : '0.9');
          line.setAttribute('stroke-linecap', 'round'); line.setAttribute('pointer-events', 'none');
          svg.appendChild(line);
        }
      }
    }

    if (typeof drawHexBorders === 'function') drawHexBorders(svg, layout, cellAt, colW, rowH, offX, offY, r, '1.8', true);
    if (typeof drawSidoEdgeLabels === 'function') {
      drawSidoEdgeLabels(svg, layout.map((d) => {
        const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
        return { sido: d.sido, cx, cy };
      }));
    }
    return { colW, rowH, offX, offY, w, h, r, minR, maxR };
  }

  window.drawDistrictHex = drawDistrictHex;
})();
