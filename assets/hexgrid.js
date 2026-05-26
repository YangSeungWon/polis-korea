// hexgrid.js — pointy-top, odd-r offset 육각격자 공용 헬퍼.
// polls.js·history.js가 공유 (이전엔 각 render 함수에 복붙돼 있었음).
// 노빌드 환경 — 전역 함수로 노출, 사용하는 페이지가 다른 스크립트보다 먼저 <script> 로드.

// 중심 (cx,cy)·반지름 r 육각형의 SVG points 문자열.
function hexPoints(cx, cy, r) {
  const pts = [];
  for (let i = 0; i < 6; i++) {
    const a = Math.PI / 6 + (Math.PI / 3) * i;
    pts.push(`${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`);
  }
  return pts.join(' ');
}

// offset (col,row) → 픽셀 중심 [cx, cy]. 홀수 row 오른쪽 +colW/2.
function hexCenter(col, row, colW, rowH, offX, offY) {
  return [offX + col * colW + (row % 2 ? colW / 2 : 0), offY + row * rowH];
}

// odd-r offset 이웃 6칸 (홀수 row 오른쪽 offset). 순서: NW, N, W, E, SW, S 류.
function nbrs(c, r) {
  return r % 2 === 0
    ? [[c - 1, r - 1], [c, r - 1], [c - 1, r], [c + 1, r], [c - 1, r + 1], [c, r + 1]]
    : [[c, r - 1], [c + 1, r - 1], [c - 1, r], [c + 1, r], [c, r + 1], [c + 1, r + 1]];
}

// pointy-top corner 순서 (hexPoints와 동일): 0=SE, 1=S, 2=SW, 3=NW, 4=N, 5=NE.
// edge i = corner i → corner (i+1)%6.
// 이웃 인덱스(nbrs 순서) → 그 이웃과 맞닿는 edge 인덱스: NW→3, N→4, W→2, E→5, SW→1, SE→0.
const NBR_TO_EDGE = [3, 4, 2, 5, 1, 0];

// 중심 (cx,cy)·반지름 rad 육각형의 i번째 꼭짓점 [x, y].
function corner(cx, cy, rad, i) {
  const a = Math.PI / 6 + (Math.PI / 3) * i;
  return [cx + rad * Math.cos(a), cy + rad * Math.sin(a)];
}

// 시도 경계 굵은 선 — 다른 시도와 닿는 면을 그림.
// includeOutline=true면 한반도 외곽(neighbor 없는 edge)도 같이 그림 (권역 윤곽 강조).
// cells: {c,r,sido} 배열, cellAt: "c,r"→cell Map.
function drawHexBorders(svg, cells, cellAt, colW, rowH, offX, offY, r, strokeWidth, includeOutline = false) {
  for (const d of cells) {
    const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
    const ns = nbrs(d.c, d.r);
    for (let i = 0; i < 6; i++) {
      const [nc, nr] = ns[i];
      const neighbor = cellAt.get(`${nc},${nr}`);
      // 같은 시도 내부 edge → skip
      if (neighbor && neighbor.sido === d.sido) continue;
      // 외곽 (neighbor 없음) → includeOutline일 때만 그림
      if (!neighbor && !includeOutline) continue;
      const e = NBR_TO_EDGE[i];
      const [x1, y1] = corner(cx, cy, r, e);
      const [x2, y2] = corner(cx, cy, r, (e + 1) % 6);
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', x1); line.setAttribute('y1', y1);
      line.setAttribute('x2', x2); line.setAttribute('y2', y2);
      line.setAttribute('stroke', '#0a0e1a');
      line.setAttribute('stroke-width', strokeWidth);
      line.setAttribute('stroke-linecap', 'round');
      line.setAttribute('pointer-events', 'none');
      svg.appendChild(line);
    }
  }
}
