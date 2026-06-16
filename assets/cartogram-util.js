// 카토그램 공용 순수 함수 — 종합/폴(render-sigungu-cartogram)·역대(render-sigungu)가 공유.
//   렌더링은 페이지별로 다르나(선택·period·구 외곽선) 알고리즘은 동일 → 여기로 단일화.
(function () {
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
  // monotone-chain convex hull (dorling 권역 테두리).
  function convexHull(pts) {
    const arr = [...pts].sort((a, b) => a.x - b.x || a.y - b.y);
    const cross = (O, A, B) => (A.x - O.x) * (B.y - O.y) - (A.y - O.y) * (B.x - O.x);
    const lower = [];
    for (const p of arr) { while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop(); lower.push(p); }
    const upper = [];
    for (let i = arr.length - 1; i >= 0; i--) { const p = arr[i]; while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop(); upper.push(p); }
    return lower.slice(0, -1).concat(upper.slice(0, -1));
  }
  // 파이 슬라이스 SVG path (top 기준 시계방향).
  function pieSlice(cx, cy, rad, a0, a1) {
    const x0 = cx + rad * Math.cos(a0), y0 = cy + rad * Math.sin(a0), x1 = cx + rad * Math.cos(a1), y1 = cy + rad * Math.sin(a1);
    return `M ${cx.toFixed(2)} ${cy.toFixed(2)} L ${x0.toFixed(2)} ${y0.toFixed(2)} A ${rad.toFixed(2)} ${rad.toFixed(2)} 0 ${(a1 - a0) > Math.PI ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} Z`;
  }
  // dorling force-directed packing(원 겹침 해소 + 원위치 anchor). nodes는 {cx,cy,cx0,cy0,radius}를 변형.
  function packCircles(nodes, iters) {
    for (let it = 0; it < (iters || 40); it++) {
      for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j], dx = b.cx - a.cx, dy = b.cy - a.cy;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.01, ov = a.radius + b.radius - dist;
        if (ov > 0) { const p = ov * 0.5 / dist; a.cx -= p * dx; a.cy -= p * dy; b.cx += p * dx; b.cy += p * dy; }
      }
      for (const n of nodes) { n.cx += (n.cx0 - n.cx) * 0.05; n.cy += (n.cy0 - n.cy) * 0.05; }
    }
    return nodes;
  }
  // 권역(시도) 테두리 — 인접 셀 시도 다른 변(pointy-top odd-r). geom={colW,rowH,offX,offY,r}.
  function drawSidoBorders(svg, cells, geom) {
    const NS = 'http://www.w3.org/2000/svg';
    const { colW, rowH, offX, offY, r } = geom;
    const center = (c, rr) => [offX + c * colW + (rr % 2 ? colW / 2 : 0), offY + rr * rowH];
    const key = (c, rr) => c + ',' + rr;
    const at = new Map(); cells.forEach((c) => at.set(key(c.c, c.r), c.sido));
    const EDGE = ['SE', 'SW', 'W', 'NW', 'NE', 'E'];
    const OFF = { 0: { E: [1, 0], W: [-1, 0], SE: [0, 1], SW: [-1, 1], NE: [0, -1], NW: [-1, -1] },
      1: { E: [1, 0], W: [-1, 0], SE: [1, 1], SW: [0, 1], NE: [1, -1], NW: [0, -1] } };
    const vert = (cx, cy, j) => [cx + r * Math.cos(Math.PI / 6 + j * Math.PI / 3), cy + r * Math.sin(Math.PI / 6 + j * Math.PI / 3)];
    const g = document.createElementNS(NS, 'g'); g.setAttribute('class', 'sido-border-layer');
    for (const cell of cells) {
      const [cx, cy] = center(cell.c, cell.r);
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
  window.CartogramUtil = { hexSpiral, allocateByVotes, convexHull, pieSlice, packCircles, drawSidoBorders };
})();
