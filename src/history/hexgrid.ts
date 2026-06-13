// hexgrid — pointy-top, odd-r offset 육각격자 공용 헬퍼 (TS 포팅, 지도 모듈 첫 슬라이스).
// 빌드: esbuild → assets/hexgrid.js (IIFE). 바닐라 스크립트 interop 위해 globalThis에 노출.
// polls.js·history.js가 공유 (hexPoints·hexCenter·nbrs·NBR_TO_EDGE·corner·drawHexBorders).
// 사용 페이지가 다른 render-*.js보다 먼저 <script>로 로드 (노빌드 시절 규약 유지).

export interface HexCell {
  c: number;
  r: number;
  sido?: string;
  name?: string;
  code?: string;
  [k: string]: unknown;
}

// 중심 (cx,cy)·반지름 r 육각형의 SVG points 문자열.
function hexPoints(cx: number, cy: number, r: number): string {
  const pts: string[] = [];
  for (let i = 0; i < 6; i++) {
    const a = Math.PI / 6 + (Math.PI / 3) * i;
    pts.push(`${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`);
  }
  return pts.join(' ');
}

// offset (col,row) → 픽셀 중심 [cx, cy]. 홀수 row 오른쪽 +colW/2.
function hexCenter(col: number, row: number, colW: number, rowH: number, offX: number, offY: number): [number, number] {
  return [offX + col * colW + (row % 2 ? colW / 2 : 0), offY + row * rowH];
}

// odd-r offset 이웃 6칸. 순서: NW, N, W, E, SW, S 류.
function nbrs(c: number, r: number): Array<[number, number]> {
  return r % 2 === 0
    ? [[c - 1, r - 1], [c, r - 1], [c - 1, r], [c + 1, r], [c - 1, r + 1], [c, r + 1]]
    : [[c, r - 1], [c + 1, r - 1], [c - 1, r], [c + 1, r], [c, r + 1], [c + 1, r + 1]];
}

// 이웃 인덱스(nbrs 순서) → 그 이웃과 맞닿는 edge 인덱스.
const NBR_TO_EDGE = [3, 4, 2, 5, 1, 0];

// 중심 (cx,cy)·반지름 rad 육각형의 i번째 꼭짓점 [x, y].
function corner(cx: number, cy: number, rad: number, i: number): [number, number] {
  const a = Math.PI / 6 + (Math.PI / 3) * i;
  return [cx + rad * Math.cos(a), cy + rad * Math.sin(a)];
}

// 경계 굵은 선 — keyFn 값이 다른 이웃과 닿는 면을 그림 (기본 = 시도 경계).
// lineClass 주면 stroke 색을 CSS에 위임(테마 인지) — 안 주면 기존 하드코딩 색.
function drawHexBorders(
  svg: SVGElement,
  cells: HexCell[],
  cellAt: Map<string, HexCell>,
  colW: number, rowH: number, offX: number, offY: number, r: number,
  strokeWidth: string | number,
  includeOutline = false,
  keyFn?: (d: HexCell) => string | undefined,
  lineClass?: string,
): void {
  const key = keyFn || ((d: HexCell) => d.sido);
  for (const d of cells) {
    const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
    const ns = nbrs(d.c, d.r);
    const dk = key(d);
    for (let i = 0; i < 6; i++) {
      const [nc, nr] = ns[i];
      const neighbor = cellAt.get(`${nc},${nr}`);
      if (neighbor && key(neighbor) === dk) continue;
      if (!neighbor && !includeOutline) continue;
      const e = NBR_TO_EDGE[i];
      const [x1, y1] = corner(cx, cy, r, e);
      const [x2, y2] = corner(cx, cy, r, (e + 1) % 6);
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', String(x1)); line.setAttribute('y1', String(y1));
      line.setAttribute('x2', String(x2)); line.setAttribute('y2', String(y2));
      if (lineClass) line.setAttribute('class', lineClass);
      else line.setAttribute('stroke', '#0a0e1a');
      line.setAttribute('stroke-width', String(strokeWidth));
      line.setAttribute('stroke-linecap', 'round');
      line.setAttribute('pointer-events', 'none');
      svg.appendChild(line);
    }
  }
}

// 바닐라 스크립트(render-*.js)가 전역으로 호출 — 빌드 IIFE가 노출.
Object.assign(globalThis as unknown as Record<string, unknown>, {
  hexPoints, hexCenter, nbrs, NBR_TO_EDGE, corner, drawHexBorders,
});
