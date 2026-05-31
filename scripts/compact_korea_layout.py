"""압축 한국 hex layout — 시도 cells dense pack + 시도들 한국 지리 인접.

Stage 1: 시도별 dense bbox (사각형, cells 갯수에 정확)
Stage 2: 시도 centroid → 한국 지리 격자 (사용자 시도 hex 5 row 영감)
Stage 3: 시도 cluster들 인접 배치 (offset 누적)
Stage 4: cells lat·lon → bbox 자리 (Hungarian)

이전 apply_korea_layout과 차이 — 사용자 의도 "섬처럼 떨어지지 X" + "서로 끌어당김".
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from collections import defaultdict

import numpy as np
from scipy.optimize import linear_sum_assignment
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
GEO_DIR = ROOT / "data/geo"

SIDO_CODE = {
    '11':'서울특별시','21':'부산광역시','22':'대구광역시','23':'인천광역시',
    '24':'광주광역시','25':'대전광역시','26':'울산광역시','29':'세종특별자치시',
    '31':'경기도','32':'강원특별자치도','33':'충청북도','34':'충청남도',
    '35':'전북특별자치도','36':'전라남도','37':'경상북도','38':'경상남도','39':'제주특별자치도',
}

# centroid hardcode (sigungu_simple.json에 없는 분할구·신설)
HARDCODE_CENTROID = {
    ('인천광역시', '영종구'): (126.55, 37.46),
    ('인천광역시', '검단구'): (126.65, 37.55),
    ('인천광역시', '제물포구'): (126.66, 37.48),
    ('인천광역시', '미추홀구'): (126.66, 37.45),
    ('제주특별자치도', '제주시'): (126.53, 33.50),
    ('제주특별자치도', '서귀포시'): (126.56, 33.25),
    ('충청남도', '계룡시'): (127.25, 36.27),
    ('충청남도', '연기군'): (127.26, 36.56),
    ('강원특별자치도', '고성군'): (128.47, 38.38),
}


# 시도별 cells 갯수 max (시군구·legacy·22대 지역구) — dense bbox 크기 결정
SIDO_MAX_CELLS = {
    '인천광역시': 14, '서울특별시': 48, '경기도': 60,
    '강원특별자치도': 18, '충청북도': 14, '충청남도': 16,
    '세종특별자치시': 2, '대전광역시': 7,
    '경상북도': 23, '대구광역시': 12, '울산광역시': 6,
    '경상남도': 22, '부산광역시': 18,
    '전북특별자치도': 15, '전라남도': 22, '광주광역시': 8,
    '제주특별자치도': 3,
}

# 시도별 bbox shape (width × height) — cells 갯수에 fit (사각형 또는 직사각형)
# 시도 형태 한국 지리 따라 (가로 긴 vs 세로 긴)
SIDO_BASE_SHAPE = {
    # max cells (22대 또는 legacy) 기준 시도 cluster shape.
    # cells 적은 회차는 shape_for(cells)로 작은 shape 자동 계산 (dense).
    # 여유 자리 25~50% 확보 — 분구 cluster 매핑 위해 (강남갑·을·병 자리 선택권 확대).
    # 외곽 빈자리만 발생, 시도 내부 빈자리 X (작은 회차 cells에는 shape_for로 dense).
    '인천광역시':     (2, 8),    # 16 (max 14 + 여유 2) col 0~1 row 3~10 — col 2 비워서 서울 서측 도시 (부천·광명·시흥) 자리
    '서울특별시':     (7, 8),    # 56 (max 48 + 여유 8) — 분구 cluster 위해
    '경기도':         (11, 12),  # bbox col 0~10 row 0~11 (132) - 서울 56 - 인천 16 = 60 자리 (cells 60 정확 fit).

    '강원특별자치도': (4, 6),    # 24 (max 18 + 여유 6)
    '경상북도':       (5, 6),    # 30 (max 23 + 여유 7)

    '충청남도':       (4, 5),    # 20 (max 16 + 여유 4)
    '세종특별자치시': (1, 5),    # col 7 row 12~16 (cells 1~2 → 외곽 빈자리 충남↔충북 사이 채움)
    '충청북도':       (4, 5),    # 20 (max 14 + 여유 6)
    '대전광역시':     (3, 3),    # 9 (max 7 + 여유 2)
    '대구광역시':     (4, 4),    # 16 (max 12 + 여유 4)
    '울산광역시':     (2, 3),    # 6 (정확)
    '전북특별자치도': (4, 5),    # 20 (max 15 + 여유 5)
    '경상남도':       (3, 7),    # 21 (max 18 + 여유 3) — col 11~13 row 16~22
    '부산광역시':     (5, 5),    # 25 (max 18 + 여유 7) — col 14~18 row 16~20
    '광주광역시':     (3, 4),    # 12 (max 8 + 여유 4)
    '전라남도':       (5, 6),    # 30 (max 22 + 여유 8)
    '제주특별자치도': (3, 1),    # 3 (정확)
}


def compute_gyeonggi_ring(n_cells: int, seoul_shape: tuple[int, int]) -> tuple[int, int]:
    """경기 ring shape — 서울 둘러쌈 + cells N fit + 여유 20%.

    outer × outer ≥ (cells + seoul_total) * 1.2. ring 두께 ≥ 1.
    """
    sw, sh = seoul_shape
    s_total = sw * sh
    target = (n_cells + s_total) * 1.2  # 여유 20% — 분구 cluster 매핑 위해
    side = math.ceil(math.sqrt(target))
    min_side = max(sw, sh) + 2  # ring 두께 ≥ 1
    side = max(side, min_side)
    return (side, side)


def shape_for(sido: str, n_cells: int) -> tuple[int, int]:
    """cells 갯수에 fit shape.

    경기 — cells fit ring (서울 둘러쌈, dynamic).
    서울 — cells fit (시군구 25 vs 22대 48 큰 차이).
    나머지 시도 — base 유지 (50% 이상 — 시도 boundary 인접).
    """
    base = SIDO_BASE_SHAPE.get(sido, (3, 3))
    if sido == '경기도':
        # 경기 bbox 고정 (15, 12) col 0~14 row 0~11. 서울·인천 exclude.
        return base
    # base 유지 — 시도 cluster 크기 일정. 작은 회차에는 외곽 빈자리만 (시도 boundary
    # 위치 일정). 시도 사이 gap 0 유지.
    return base


# 호환 alias
SIDO_SHAPE = SIDO_BASE_SHAPE

# 시도 centroid 격자 위치 (사용자 시도 hex 5 row layout 영감)
# col·row = 시도 시작점 (top-left of bbox)
# 시도 cluster들이 서로 인접하도록
SIDO_OFFSET = {
    # 한국 지리 dense 배치. 모든 시도 boundary 인접 (gap 0).
    # 사용자 의도 — 경기↔강원 gap 줄임, 중남부 시도들 상승.
    '인천광역시':     (0, 3),    # col 0~1 row 3~10 (2×8=16)
    '서울특별시':     (3, 3),    # col 3~9 row 3~10 (7×8=56) — 여유 8
    '경기도':         (0, 0),    # bbox col 0~14 row 0~11. 서울·인천 exclude.
    '강원특별자치도': (11, 0),   # col 11~14 row 0~5 (경기 col 10 인접)
    '경상북도':       (11, 6),   # col 11~15 row 6~11
    '충청남도':       (3, 12),   # col 3~6 row 12~16 (경기 row 11 인접)
    '세종특별자치시': (7, 12),   # col 7 row 12~13 (충남 col 6 인접)
    '충청북도':       (8, 12),   # col 8~11 row 12~16 (세종 col 7 인접)
    '대구광역시':     (12, 12),  # col 12~15 row 12~15 (경북 col 11 인접)
    '울산광역시':     (16, 13),  # col 16~17 row 13~15
    '대전광역시':     (7, 17),   # col 7~9 row 17~19 (전북 col 6 인접)
    '전북특별자치도': (3, 17),   # col 3~6 row 17~21
    '경상남도':       (12, 16),  # col 12~14 row 16~22 (충북 col 11 인접)
    '부산광역시':     (15, 16),  # col 15~19 row 16~20 (경남 col 14 인접)
    '광주광역시':     (3, 22),   # col 3~5 row 22~25
    '전라남도':       (6, 22),   # col 6~10 row 22~27
    '제주특별자치도': (7, 28),   # col 7~9 row 28
}


def load_centers():
    geo = json.loads((GEO_DIR / "sigungu_simple.json").read_text(encoding="utf-8"))
    out = dict(HARDCODE_CENTROID)
    for f in geo["features"]:
        name = f["properties"].get("name", "")
        code = f["properties"].get("code", "")
        if not name or not code:
            continue
        sido = SIDO_CODE.get(code[:2], "")
        if not sido:
            continue
        try:
            pt = shape(f["geometry"]).centroid
            out[(sido, name)] = (pt.x, pt.y)
        except Exception:
            continue
    return out


def cell_geo(cell, centers):
    sido = cell.get("sido", "")
    name = cell.get("name", "")
    sido = {'강원도': '강원특별자치도', '전라북도': '전북특별자치도',
            '제주도': '제주특별자치도'}.get(sido, sido)
    # 1) cell.sigungus field 우선 — 자치구 list 평균 centroid
    #    (강남구갑 → ['강남구'], 수원시갑 → ['수원시장안구·권선·팔달·영통'])
    sigungus = cell.get("sigungus", [])
    if sigungus:
        geos = [centers.get((sido, s)) for s in sigungus]
        valid = [g for g in geos if g is not None]
        if valid:
            return (sum(g[0] for g in valid) / len(valid),
                    sum(g[1] for g in valid) / len(valid))
    if (sido, name) in centers:
        return centers[(sido, name)]
    if name.endswith('시') or name.endswith('군'):
        matches = [v for (s, n), v in centers.items()
                   if s == sido and n.startswith(name) and n != name]
        if matches:
            return (sum(m[0] for m in matches) / len(matches),
                    sum(m[1] for m in matches) / len(matches))
    if name == '미추홀구' and (sido, '남구') in centers:
        return centers[(sido, '남구')]
    if name == '남구' and sido == '인천광역시' and (sido, '미추홀구') in centers:
        return centers[(sido, '미추홀구')]
    if name == '청주시청원구' and (sido, '청원군') in centers:
        return centers[(sido, '청원군')]
    i = name.find("시")
    if i > 0 and i < len(name) - 1 and (sido, name[:i+1]) in centers:
        return centers[(sido, name[:i+1])]
    # name 끝 [갑을병정무] 제거 → 자치구명 (은평구갑 → 은평구)
    import re
    m = re.match(r'^(.+?)([갑을병정무]+)$', name)
    if m and (sido, m.group(1)) in centers:
        return centers[(sido, m.group(1))]
    # 시도 평균 fallback
    sido_geos = [v for (s, _), v in centers.items() if s == sido]
    if sido_geos:
        return (sum(g[0] for g in sido_geos) / len(sido_geos),
                sum(g[1] for g in sido_geos) / len(sido_geos))
    return None


def positions_in_bbox(offset, shape_, exclude_bboxes):
    """offset = (col, row) 시작점. shape = (width, height)."""
    cstart, rstart = offset
    w, h = shape_
    out = []
    for c in range(cstart, cstart + w):
        for r in range(rstart, rstart + h):
            excluded = False
            for eb in exclude_bboxes:
                if eb[0] <= c <= eb[2] and eb[1] <= r <= eb[3]:
                    excluded = True
                    break
            if not excluded:
                out.append((c, r))
    return out


def normalize(arr):
    mn = arr.min(axis=0); mx = arr.max(axis=0)
    rng = np.where(mx - mn > 0, mx - mn, 1)
    return (arr - mn) / rng


def assign_cells_ring(cells, positions, centers, ring_center_geo, ring_center_pos):
    """경기·서울 ring 모양 자리에 매핑.

    cells lat·lon → polar (angle, distance) 기준 ring center.
    분구 cells에 group jitter (cell.name 순 격자) — 같은 group cells 인접 매핑.
    Hungarian 전체 cells → positions.
    """
    if not positions or not cells:
        return [None] * len(cells)

    by_group = defaultdict(list)
    for c in cells:
        sigungus = tuple(sorted(c.get("sigungus", [c.get("name", "")])))
        sido = c.get("sido", "")
        by_group[(sido, sigungus)].append(c)

    # cells 각자 geo (분구 jitter 적용 — group cells 안 격자 위치)
    JITTER_OFFSET = 0.025  # 자치구 spacing 절반 정도 (서울 spacing ~0.04~0.05)
    geos = []
    for c in cells:
        sigungus = tuple(sorted(c.get("sigungus", [c.get("name", "")])))
        sido = c.get("sido", "")
        grp = by_group[(sido, sigungus)]
        g = cell_geo(c, centers)
        if g is None:
            geos.append(None); continue
        if len(grp) > 1:
            grp_sorted = sorted(grp, key=lambda x: x.get("name", ""))
            idx = grp_sorted.index(c)
            side = math.ceil(math.sqrt(len(grp)))
            jr = idx // side
            jc = idx % side
            jx = (jc - (side - 1) / 2) * JITTER_OFFSET
            jy = (jr - (side - 1) / 2) * JITTER_OFFSET
            g = (g[0] + jx, g[1] + jy)
        geos.append(g)

    def polar_geo(g):
        dx = g[0] - ring_center_geo[0]
        dy = g[1] - ring_center_geo[1]
        return math.atan2(dy, dx), math.hypot(dx, dy)

    def polar_pos(p):
        dx = p[0] - ring_center_pos[0]
        dy = -(p[1] - ring_center_pos[1])
        return math.atan2(dy, dx), math.hypot(dx, dy)

    valid_idx = [i for i, g in enumerate(geos) if g is not None]
    if not valid_idx or len(valid_idx) > len(positions):
        return [None] * len(cells)

    cell_polars = [polar_geo(geos[i]) for i in valid_idx]
    pos_polars = [polar_pos(p) for p in positions]

    cell_dists = [d for _, d in cell_polars]
    pos_dists = [d for _, d in pos_polars]
    cd_max = max(cell_dists) if cell_dists else 1
    pd_max = max(pos_dists) if pos_dists else 1
    cd_max = cd_max if cd_max > 0 else 1
    pd_max = pd_max if pd_max > 0 else 1

    # 각도 + 거리 cost — w_dist ↑ (남부 도시들 진짜 남쪽 row 11에 매핑)
    w_angle = 2.0
    w_dist = 2.0
    cost = np.zeros((len(valid_idx), len(positions)))
    for i in range(len(valid_idx)):
        ca, cd = cell_polars[i]
        cd_n = cd / cd_max
        for j in range(len(positions)):
            pa, pd = pos_polars[j]
            pd_n = pd / pd_max
            ad = ca - pa
            while ad > math.pi: ad -= 2 * math.pi
            while ad < -math.pi: ad += 2 * math.pi
            dd = cd_n - pd_n
            cost[i, j] = w_angle * ad * ad + w_dist * dd * dd
    _, col_ind = linear_sum_assignment(cost)

    out_pos = [None] * len(cells)
    for i_local, j in enumerate(col_ind):
        out_pos[valid_idx[i_local]] = positions[j]
    return out_pos


def assign_cells(cells, positions, centers, w_lon=2.5):
    """cells 직접 Hungarian + 분구 group jitter — cells N 정확 fit bbox에 dense 매핑.

    분구 cells (강남갑·을·병)에 cell.name 순 격자 jitter → 같은 group cells가 자연
    인접 자리에 매핑. 자치구 단위 매핑 X (자치구 anchor 정확 + 분구 X 자리 trade-off).
    """
    if not positions or not cells:
        return [None] * len(cells)

    by_group = defaultdict(list)
    for c in cells:
        sigungus = tuple(sorted(c.get("sigungus", [c.get("name", "")])))
        sido = c.get("sido", "")
        by_group[(sido, sigungus)].append(c)

    # 분구 jitter — group 안 cell.name 순서 격자 위치
    JITTER_OFFSET = 0.020  # 자치구 spacing 절반 (서울 0.04~0.05, 경기 0.05~0.1)
    geos = []
    for c in cells:
        sigungus = tuple(sorted(c.get("sigungus", [c.get("name", "")])))
        sido = c.get("sido", "")
        grp = by_group[(sido, sigungus)]
        g = cell_geo(c, centers)
        if g is None:
            geos.append(None); continue
        if len(grp) > 1:
            grp_sorted = sorted(grp, key=lambda x: x.get("name", ""))
            idx = grp_sorted.index(c)
            side = math.ceil(math.sqrt(len(grp)))
            jr = idx // side
            jc = idx % side
            jx = (jc - (side - 1) / 2) * JITTER_OFFSET
            jy = (jr - (side - 1) / 2) * JITTER_OFFSET
            g = (g[0] + jx, g[1] + jy)
        geos.append(g)

    valid_idx = [i for i, g in enumerate(geos) if g is not None]
    if not valid_idx or len(valid_idx) > len(positions):
        return [None] * len(cells)

    geo_arr = np.array([geos[i] for i in valid_idx], dtype=float)
    pos_arr = np.array(positions, dtype=float)
    geo_n = normalize(geo_arr); geo_n[:, 1] = 1 - geo_n[:, 1]
    pos_n = normalize(pos_arr) if len(positions) > 1 else np.array([[0.5, 0.5]])
    cost = np.zeros((len(valid_idx), len(positions)))
    for i in range(len(valid_idx)):
        for j in range(len(positions)):
            dx = geo_n[i, 0] - pos_n[j, 0]; dy = geo_n[i, 1] - pos_n[j, 1]
            cost[i, j] = w_lon * dx * dx + dy * dy
    _, col_ind = linear_sum_assignment(cost)

    out_pos = [None] * len(cells)
    for i_local, j in enumerate(col_ind):
        out_pos[valid_idx[i_local]] = positions[j]
    return out_pos


# 이전 Hungarian-only 함수 보존 (참고)
def _assign_cells_hungarian(cells, positions, centers, w_lon=2.5, n_swap=50):
    geos = [cell_geo(c, centers) for c in cells]
    valid = [i for i, g in enumerate(geos) if g is not None]
    if len(valid) < 1:
        return [None] * len(cells)
    n = len(valid)
    if n > len(positions):
        return [None] * len(cells)
    geo_arr = np.array([geos[i] for i in valid], dtype=float)
    pos_arr = np.array(positions, dtype=float)
    geo_n = normalize(geo_arr); geo_n[:, 1] = 1 - geo_n[:, 1]
    pos_n = normalize(pos_arr) if len(positions) > 1 else np.array([[0.5, 0.5]])

    def pc(g, p):
        dx = g[0] - p[0]; dy = g[1] - p[1]
        return w_lon * dx * dx + dy * dy

    cost = np.zeros((n, len(positions)))
    for i in range(n):
        for j in range(len(positions)):
            cost[i, j] = pc(geo_n[i], pos_n[j])
    _, col_ind = linear_sum_assignment(cost)
    assign = list(col_ind)
    for _ in range(n_swap):
        improved = False
        for i in range(n):
            for j in range(i+1, n):
                a, b = assign[i], assign[j]
                if pc(geo_n[i], pos_n[b]) + pc(geo_n[j], pos_n[a]) < \
                   pc(geo_n[i], pos_n[a]) + pc(geo_n[j], pos_n[b]) - 1e-9:
                    assign[i], assign[j] = b, a
                    improved = True
        if not improved:
            break
    out_pos = [None] * len(cells)
    for i_local, j in enumerate(assign):
        out_pos[valid[i_local]] = positions[j]
    return out_pos


def process(src_name, out_suffix="_v2"):
    src = GEO_DIR / src_name
    cells = json.loads(src.read_text(encoding="utf-8"))
    centers = load_centers()
    by_sido = defaultdict(list)
    for c in cells:
        by_sido[c["sido"]].append(c)


    # 회차별 cells 갯수 → shape 동적 계산
    seoul_cells_n = len(by_sido.get('서울특별시', []))
    seoul_shape = shape_for('서울특별시', seoul_cells_n)
    gyeonggi_shape = SIDO_BASE_SHAPE['경기도']  # 고정 (15, 12)
    seoul_offset = SIDO_OFFSET.get('서울특별시', (3, 3))
    seoul_bbox = (seoul_offset[0], seoul_offset[1],
                  seoul_offset[0] + seoul_shape[0] - 1,
                  seoul_offset[1] + seoul_shape[1] - 1)
    icn_shape = SIDO_BASE_SHAPE['인천광역시']
    icn_offset = SIDO_OFFSET['인천광역시']
    icn_bbox = (icn_offset[0], icn_offset[1],
                icn_offset[0] + icn_shape[0] - 1,
                icn_offset[1] + icn_shape[1] - 1)

    print(f"\n=== {src_name} ({len(cells)} cells) ===")
    for sido, sido_cells in sorted(by_sido.items()):
        if sido not in SIDO_OFFSET:
            print(f"  {sido} skip")
            continue
        n = len(sido_cells)
        offset = SIDO_OFFSET[sido]
        # 동적 shape — 서울·경기는 위에서 계산한 값
        if sido == '서울특별시':
            shape_ = seoul_shape
        elif sido == '경기도':
            shape_ = gyeonggi_shape
        else:
            shape_ = shape_for(sido, n)
        if sido == '경기도':
            excludes = [seoul_bbox, icn_bbox]
        else:
            excludes = []
        positions = positions_in_bbox(offset, shape_, excludes)
        if sido == '경기도':
            # 경기 ring projection — 서울 중심 lat·lon + 자리 중심 기준 polar
            seoul_centers = [v for (s, _), v in centers.items() if s == '서울특별시']
            seoul_geo_center = (sum(g[0] for g in seoul_centers) / len(seoul_centers),
                                sum(g[1] for g in seoul_centers) / len(seoul_centers))
            seoul_pos_center = ((seoul_bbox[0] + seoul_bbox[2]) / 2,
                                (seoul_bbox[1] + seoul_bbox[3]) / 2)
            new_pos = assign_cells_ring(sido_cells, positions, centers,
                                         seoul_geo_center, seoul_pos_center)
        else:
            new_pos = assign_cells(sido_cells, positions, centers)
        applied = 0
        for cell, p in zip(sido_cells, new_pos):
            if p:
                cell["c"], cell["r"] = p
                applied += 1
        print(f"  {sido:20s} {n:3d} cells → shape {shape_} 자리 {len(positions)} 적용 {applied}")

    out = src.with_name(src.stem + out_suffix + src.suffix)
    out.write_text(json.dumps(cells, ensure_ascii=False), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", default=[
        "sigungu_hex.json", "sigungu_hex_legacy.json",
        "district_hex_17.json", "district_hex_18.json", "district_hex_19.json",
        "district_hex_20.json", "district_hex_21.json", "district_hex_22.json",
    ])
    args = ap.parse_args()
    for src in args.files:
        if (GEO_DIR / src).exists():
            process(src)


if __name__ == "__main__":
    main()
