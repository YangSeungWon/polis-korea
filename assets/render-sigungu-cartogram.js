// 시군구 표-비례 카토그램 (공용) — 격자: 시군구당 N개 작은 hex(1 hex=2만표, 후보별 배분) /
//   dorling: 원(표 비례·force-directed). 역대 흐름 render-sigungu 알고리즘을 페이지 비결합 함수로.
//   종합(대선 아카이브)·폴 재사용. 의존: partyColor·drawSidoEdgeLabels·gapOpacity(전역).
//   Archive.drawSigunguCartogram(svg, cells, resultFn, opts)
//     cells = [{sido,name,c,r}] (council 레이아웃)
//     resultFn(sido,name) → {candidates:[{party,name,votes,pct}], voted} | null
//     opts = { mode:'격자'|'dorling', r=22, unit=20000, onSelect(sido,name) }
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const pcol = (p) => (typeof partyColor === 'function' ? partyColor(p) : '#888');
  function hexPoints(cx, cy, r) {
    const p = [];
    for (let i = 0; i < 6; i++) { const a = Math.PI / 6 + i * Math.PI / 3; p.push(`${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`); }
    return p.join(' ');
  }
  const hexCenter = (col, row, colW, rowH, offX, offY) => [offX + col * colW + (row % 2 ? colW / 2 : 0), offY + row * rowH];

  // 공용 알고리즘 — cartogram-util.js (역대 흐름과 단일화).
  const CU = window.CartogramUtil || {};
  const hexSpiral = CU.hexSpiral, allocateByVotes = CU.allocateByVotes, convexHull = CU.convexHull;
  // 권역(시도) 테두리 — 인접 셀 시도 다른 변(pointy-top odd-r).
  const sidoBorders = (svg, cells, colW, rowH, offX, offY, r) =>
    CU.drawSidoBorders(svg, cells, { colW, rowH, offX, offY, r });

  function drawSigunguCartogram(svg, cells, resultFn, opts) {
    opts = opts || {};
    const mode = opts.mode || '격자';
    const r = opts.r || 22, colW = r * Math.sqrt(3), rowH = r * 1.5;
    const minC = Math.min(...cells.map((c) => c.c)), minR = Math.min(...cells.map((c) => c.r));
    const maxC = Math.max(...cells.map((c) => c.c)), maxR = Math.max(...cells.map((c) => c.r));
    const offX = -minC * colW + colW / 2, offY = -minR * rowH + rowH;
    const w = (maxC - minC + 1) * colW + colW, h = (maxR - minR + 1) * rowH + rowH;
    const EM = (typeof SIDO_EDGE_MARGIN !== 'undefined') ? SIDO_EDGE_MARGIN : 78;
    svg.innerHTML = '';
    const vb = [-EM, 0, Math.ceil(w) + 2 * EM, Math.ceil(h)];   // base viewBox(줌·포커스용)
    svg.setAttribute('viewBox', `${vb[0]} ${vb[1]} ${vb[2]} ${vb[3]}`);
    svg.setAttribute('width', Math.ceil(w) + 2 * EM); svg.setAttribute('height', Math.ceil(h));
    // 줌·포커스 앵커 — region(시도|시군구)→셀 중심(그리드). 단색/격자/원형 교차 보존에 공통 키.
    const focusCells = cells.map((d) => { const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY); return { region: d.sido + '|' + d.name, cx, cy }; });

    const rmap = new Map(); let maxVoted = 0;
    for (const d of cells) { const res = resultFn(d.sido, d.name); if (res && res.voted) { rmap.set(d, res); maxVoted = Math.max(maxVoted, res.voted); } }
    sidoBorders(svg, cells, colW, rowH, offX, offY, r);
    if (typeof drawSidoEdgeLabels === 'function') {
      drawSidoEdgeLabels(svg, cells.map((d) => { const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY); return { sido: d.sido, cx, cy }; }));
    }
    const bindClick = (g, d) => { if (opts.onSelect) { g.style.cursor = 'pointer'; g.addEventListener('click', () => opts.onSelect(d.sido, d.name)); } };
    const titleOf = (d, top, extra) => `${d.sido} ${d.name}` + (top ? ` · ${top.name || top.party}(${top.party}) ${(top.pct || 0).toFixed(1)}%${extra || ''}` : '');

    if (mode === 'dorling' && maxVoted > 0) {
      const gapOp = (typeof gapOpacity === 'function') ? gapOpacity : () => 1;
      const nodes = [];
      for (const d of cells) {
        const res = rmap.get(d); if (!res) continue;
        const cs = (res.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
        const top = cs[0], gap = (cs[0] && cs[1]) ? (cs[0].pct - cs[1].pct) : null;
        const [cx0, cy0] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
        nodes.push({ d, top, cands: cs, cx0, cy0, cx: cx0, cy: cy0,
          radius: Math.max(3, (r - 0.7) * Math.sqrt((res.voted || 0) / maxVoted)),
          fill: top ? pcol(top.party) : '#e6e9ef', op: top ? gapOp(gap) : 1 });
      }
      CU.packCircles(nodes, 40);
      // 권역(시도) 테두리 — 시도별 convex hull(원 외곽 padding 포함).
      const groups = new Map();
      for (const n of nodes) { const k = n.d.sido; (groups.get(k) || groups.set(k, []).get(k)).push(n); }
      for (const [, list] of groups) {
        const pts = [];
        for (const n of list) for (let k = 0; k < 12; k++) { const a = k * Math.PI / 6; pts.push({ x: n.cx + Math.cos(a) * (n.radius + 3), y: n.cy + Math.sin(a) * (n.radius + 3) }); }
        const hull = convexHull(pts);
        if (hull.length < 3) continue;
        const poly = document.createElementNS(NS, 'polygon');
        poly.setAttribute('points', hull.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '));
        poly.setAttribute('fill', 'rgba(10,14,26,0.04)'); poly.setAttribute('stroke', 'rgba(10,14,26,0.4)');
        poly.setAttribute('stroke-width', '1.4'); poly.setAttribute('stroke-linejoin', 'round'); poly.setAttribute('pointer-events', 'none');
        svg.appendChild(poly);
      }
      // 득표 비례 파이 원 — 후보 구성(승자독식 색 왜곡 제거). pieSlice는 공용.
      const pieSlice = CU.pieSlice;
      for (const n of nodes) {
        const g = document.createElementNS(NS, 'g'); bindClick(g, n.d);
        const cs = n.cands, totalV = cs.reduce((s, c) => s + (c.votes || 0), 0);
        if (totalV > 0 && cs.filter((c) => (c.votes || 0) > 0).length > 1) {
          let a0 = -Math.PI / 2;
          for (const cand of cs) { const frac = (cand.votes || 0) / totalV; if (frac <= 0) continue; const a1 = a0 + frac * 2 * Math.PI; const p = document.createElementNS(NS, 'path'); p.setAttribute('d', pieSlice(n.cx, n.cy, n.radius, a0, a1)); p.setAttribute('fill', pcol(cand.party)); g.appendChild(p); a0 = a1; }
          const ring = document.createElementNS(NS, 'circle'); ring.setAttribute('cx', n.cx.toFixed(1)); ring.setAttribute('cy', n.cy.toFixed(1)); ring.setAttribute('r', n.radius.toFixed(1)); ring.setAttribute('fill', 'none'); ring.setAttribute('stroke', 'var(--ink,#0a0e1a)'); ring.setAttribute('stroke-width', '0.5'); g.appendChild(ring);
        } else {
          const c = document.createElementNS(NS, 'circle'); c.setAttribute('cx', n.cx.toFixed(1)); c.setAttribute('cy', n.cy.toFixed(1)); c.setAttribute('r', n.radius.toFixed(1)); c.setAttribute('fill', n.fill); c.setAttribute('stroke', 'var(--ink,#0a0e1a)'); c.setAttribute('stroke-width', '0.5'); g.appendChild(c);
        }
        const tt = document.createElementNS(NS, 'title'); tt.textContent = titleOf(n.d, n.top, ' · ' + (rmap.get(n.d).voted || 0).toLocaleString() + '표'); g.appendChild(tt);
        svg.appendChild(g);
      }
      return { shown: nodes.length, cells: focusCells, viewBox: vb };
    }

    // 격자 — 시군구당 N개 작은 hex
    const unit = opts.unit || 20000, smallR = 3.2;
    let shown = 0;
    for (const d of cells) {
      const res = rmap.get(d); if (!res) continue;
      const N = Math.max(1, Math.ceil(res.voted / unit));
      const [cx0, cy0] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
      const cands = (res.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      const alloc = allocateByVotes(cands, N);
      const g = document.createElementNS(NS, 'g'); bindClick(g, d); shown += 1;
      const tt = document.createElementNS(NS, 'title'); tt.textContent = titleOf(d, cands[0], ' · ' + N + '석(2만표=1)'); g.appendChild(tt);
      const fills = [];
      for (let i = 0; i < cands.length; i++) for (let k = 0; k < alloc[i]; k++) fills.push(pcol(cands[i].party));
      while (fills.length < N) fills.push('#e6e9ef');
      const spiral = hexSpiral(N);
      let ext = 0; for (const [q, ar] of spiral) ext = Math.max(ext, Math.hypot(Math.sqrt(3) * (q + ar / 2), 1.5 * ar));
      const sr = Math.min(smallR, (r - 2) / (ext + 1));
      for (let i = 0; i < spiral.length; i++) {
        const [q, ar] = spiral[i];
        const sx = cx0 + sr * Math.sqrt(3) * (q + ar / 2), sy = cy0 + sr * 1.5 * ar;
        const poly = document.createElementNS(NS, 'polygon');
        poly.setAttribute('points', hexPoints(sx, sy, sr - 0.35));
        poly.setAttribute('fill', fills[i] || '#e6e9ef');
        g.appendChild(poly);
      }
      svg.appendChild(g);
    }
    return { shown, cells: focusCells, viewBox: vb };
  }

  window.Archive = window.Archive || {};
  window.Archive.drawSigunguCartogram = drawSigunguCartogram;
})();
