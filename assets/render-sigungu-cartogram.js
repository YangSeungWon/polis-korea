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

  // 작은 hex 스파이럴(1..N) — axial BFS.
  function hexSpiral(N) {
    const out = [[0, 0]]; if (N <= 1) return out;
    const seen = new Set(['0,0']); let frontier = [[0, 0]];
    const DIRS = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]];
    while (out.length < N) {
      const next = [];
      for (const [q, ar] of frontier) for (const [dq, dr] of DIRS) {
        const nq = q + dq, nr = ar + dr, k = nq + ',' + nr;
        if (seen.has(k)) continue;
        seen.add(k); next.push([nq, nr]); out.push([nq, nr]);
        if (out.length >= N) return out;
      }
      frontier = next;
    }
    return out;
  }
  // 후보별 hex 개수 — 큰 정수 잔여(largest remainder)로 N에 정확히.
  function allocateByVotes(cands, N) {
    const total = cands.reduce((s, c) => s + (c.votes || 0), 0);
    if (!total) return cands.map(() => 0);
    const raw = cands.map((c) => (c.votes || 0) * N / total);
    const floors = raw.map(Math.floor);
    const rem = N - floors.reduce((a, b) => a + b, 0);
    const fr = raw.map((v, i) => ({ i, f: v - Math.floor(v) })).sort((a, b) => b.f - a.f);
    for (let k = 0; k < rem; k++) floors[fr[k].i] += 1;
    return floors;
  }
  // 권역(시도) 테두리 — 인접 셀 시도 다른 변(pointy-top odd-r).
  function sidoBorders(svg, cells, colW, rowH, offX, offY, r) {
    const key = (c, rr) => c + ',' + rr;
    const at = new Map(); cells.forEach((c) => at.set(key(c.c, c.r), c.sido));
    const EDGE = ['SE', 'SW', 'W', 'NW', 'NE', 'E'];
    const OFF = { 0: { E: [1, 0], W: [-1, 0], SE: [0, 1], SW: [-1, 1], NE: [0, -1], NW: [-1, -1] },
      1: { E: [1, 0], W: [-1, 0], SE: [1, 1], SW: [0, 1], NE: [1, -1], NW: [0, -1] } };
    const vert = (cx, cy, j) => [cx + r * Math.cos(Math.PI / 6 + j * Math.PI / 3), cy + r * Math.sin(Math.PI / 6 + j * Math.PI / 3)];
    const g = document.createElementNS(NS, 'g'); g.setAttribute('class', 'sido-border-layer');
    for (const cell of cells) {
      const [cx, cy] = hexCenter(cell.c, cell.r, colW, rowH, offX, offY);
      const off = OFF[cell.r % 2];
      for (let i = 0; i < 6; i++) {
        const [dc, dr] = off[EDGE[i]];
        if (at.get(key(cell.c + dc, cell.r + dr)) === cell.sido) continue;
        const [x1, y1] = vert(cx, cy, i), [x2, y2] = vert(cx, cy, (i + 1) % 6);
        const ln = document.createElementNS(NS, 'line');
        ln.setAttribute('x1', x1.toFixed(1)); ln.setAttribute('y1', y1.toFixed(1));
        ln.setAttribute('x2', x2.toFixed(1)); ln.setAttribute('y2', y2.toFixed(1));
        ln.setAttribute('class', 'sido-border'); g.appendChild(ln);
      }
    }
    svg.appendChild(g);
  }

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
    svg.setAttribute('viewBox', `${-EM} 0 ${Math.ceil(w) + 2 * EM} ${Math.ceil(h)}`);
    svg.setAttribute('width', Math.ceil(w) + 2 * EM); svg.setAttribute('height', Math.ceil(h));

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
        nodes.push({ d, top, cx0, cy0, cx: cx0, cy: cy0,
          radius: Math.max(3, (r - 0.7) * Math.sqrt((res.voted || 0) / maxVoted)),
          fill: top ? pcol(top.party) : '#e6e9ef', op: top ? gapOp(gap) : 1 });
      }
      for (let it = 0; it < 40; it++) {
        for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j], dx = b.cx - a.cx, dy = b.cy - a.cy;
          const dist = Math.sqrt(dx * dx + dy * dy) || 0.01, ov = a.radius + b.radius - dist;
          if (ov > 0) { const p = ov * 0.5 / dist; a.cx -= p * dx; a.cy -= p * dy; b.cx += p * dx; b.cy += p * dy; }
        }
        for (const n of nodes) { n.cx += (n.cx0 - n.cx) * 0.05; n.cy += (n.cy0 - n.cy) * 0.05; }
      }
      for (const n of nodes) {
        const g = document.createElementNS(NS, 'g'); bindClick(g, n.d);
        const c = document.createElementNS(NS, 'circle');
        c.setAttribute('cx', n.cx.toFixed(1)); c.setAttribute('cy', n.cy.toFixed(1)); c.setAttribute('r', n.radius.toFixed(1));
        c.setAttribute('fill', n.fill); c.setAttribute('fill-opacity', n.op.toFixed(2));
        c.setAttribute('stroke', 'var(--bg,#fff)'); c.setAttribute('stroke-width', '0.5');
        g.appendChild(c);
        const tt = document.createElementNS(NS, 'title'); tt.textContent = titleOf(n.d, n.top, ' · ' + (n.d && rmap.get(n.d).voted || 0).toLocaleString() + '표'); g.appendChild(tt);
        svg.appendChild(g);
      }
      return { shown: nodes.length };
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
    return { shown };
  }

  window.Archive = window.Archive || {};
  window.Archive.drawSigunguCartogram = drawSigunguCartogram;
})();
