#!/usr/bin/env python3
"""선거구 hex 카토그램 — centroid를 올바른 종횡비 hex 그리드에 비닝.

build_zone_hex의 시군구(250개)용 정교한 배치를 적은 선거구(9~16대)에 재사용하면 시도가
좁고 길게 패킹돼 세로로 늘어남(영남 길쭉, 종횡비 3+). 대신 각 선거구 centroid(_cen)를
한반도 종횡비에 맞춘 hex 그리드 칸에 직접 배정(충돌은 인접 빈칸 BFS) → 지리적·올바른 비율.

odd-r offset (assets/hexgrid.js와 동일): 홀수 row가 오른쪽 colW/2 shift.
입력/출력: data/geo/district_hex_{n}.json (cell의 c,r만 갱신, 메타·_cen 보존).
"""
import json, math, sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def _nbrs(c, r):
    return ([(c - 1, r - 1), (c, r - 1), (c - 1, r), (c + 1, r), (c - 1, r + 1), (c, r + 1)]
            if r % 2 == 0 else
            [(c, r - 1), (c + 1, r - 1), (c - 1, r), (c + 1, r), (c, r + 1), (c + 1, r + 1)])

def generate(n, aspect=2.3, fill=1.3):
    """aspect = 목표 row/col 비(수동 17~18대 ≈1.85). fill = 그리드/선거구 밀도 여유."""
    p = ROOT / f"data/geo/district_hex_{n}.json"
    cells = json.loads(p.read_text())
    pts = [(c, c["_cen"][0], c["_cen"][1]) for c in cells if c.get("_cen")]
    if not pts:
        print(f"{n}대: _cen 없음 — skip", file=sys.stderr); return
    N = len(pts)
    lons = [x for _, x, _ in pts]; lats = [y for _, _, y in pts]
    lon0, lon1 = min(lons), max(lons); lat0, lat1 = min(lats), max(lats)
    cols = max(1, round(math.sqrt(fill * N / aspect)))
    rows = max(1, round(aspect * cols))

    occupied = {}
    # 밀집 우선 배치 — 수도권(centroid 조밀) 먼저 중심에 두고 주변이 밀려나게.
    # 간단히: 위도 북→남, 같은 위도면 경도 서→동 순. (안정적 충돌 해소)
    order = sorted(pts, key=lambda t: (-t[2], t[1]))
    for cell, lon, lat in order:
        gx = (lon - lon0) / (lon1 - lon0 + 1e-9) * (cols - 1)
        gy = (lat1 - lat) / (lat1 - lat0 + 1e-9) * (rows - 1)
        r0 = int(round(gy))
        c0 = int(round(gx - (0.5 if r0 % 2 else 0.0)))
        # 이상 칸에서 BFS로 가장 가까운 빈칸
        seen = set(); dq = deque([(c0, r0)]); placed = False
        while dq:
            cr = dq.popleft()
            if cr in seen:
                continue
            seen.add(cr)
            if cr not in occupied:
                occupied[cr] = cell; cell["c"], cell["r"] = cr; placed = True; break
            for nb in _nbrs(*cr):
                if nb not in seen:
                    dq.append(nb)
        if not placed:
            cell["c"], cell["r"] = c0, r0

    # c,r를 0 기준으로 정규화
    cs = [c["c"] for c in cells]; rs = [c["r"] for c in cells]
    mc, mr = min(cs), min(rs)
    for c in cells:
        c["c"] -= mc; c["r"] -= mr
    p.write_text(json.dumps(cells, ensure_ascii=False))
    cs = [c["c"] for c in cells]; rs = [c["r"] for c in cells]
    w = max(cs) + 1; h = max(rs) + 1
    print(f"{n}대: {N}셀 → {w}×{h} (종횡비 {h/w:.2f})")

if __name__ == "__main__":
    ns = [int(a) for a in sys.argv[1:]] or [9, 10, 11, 12, 13, 14, 15, 16]
    for n in ns:
        generate(n)
