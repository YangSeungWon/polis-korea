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

# centroid hardcode — sigungu_simple.json에 없는/geometry 손상된 자치구 26개 + 신설
# (lon, lat) 순서 주의. 손상은 linearring 4 coordinates 부족 (좌표 절단).
HARDCODE_CENTROID = {
    # 인천 신설 (sigungu에 없음)
    ('인천광역시', '영종구'): (126.55, 37.46),
    ('인천광역시', '검단구'): (126.65, 37.55),
    ('인천광역시', '제물포구'): (126.66, 37.48),
    ('인천광역시', '미추홀구'): (126.66, 37.45),
    ('인천광역시', '옹진군'): (126.6363, 37.4467),  # geo 손상
    # 서울 (geo 손상)
    ('서울특별시', '양천구'): (126.8665, 37.5170),
    # 경기 (geo 손상)
    ('경기도', '안산시단원구'): (126.8089, 37.3219),
    ('경기도', '화성시'): (126.8311, 37.1995),
    # 강원 (geo 손상 + 옛 이름)
    ('강원특별자치도', '강릉시'): (128.8761, 37.7519),
    ('강원특별자치도', '속초시'): (128.5919, 38.2071),
    ('강원특별자치도', '양양군'): (128.6291, 38.0763),
    ('강원특별자치도', '고성군'): (128.47, 38.38),
    # 충남 (geo 손상 + 신설)
    ('충청남도', '태안군'): (126.2978, 36.7457),
    ('충청남도', '계룡시'): (127.25, 36.27),
    ('충청남도', '연기군'): (127.26, 36.56),
    # 전북 (geo 손상)
    ('전북특별자치도', '고창군'): (126.7022, 35.4348),
    ('전북특별자치도', '부안군'): (126.7338, 35.7316),
    # 전남 (geo 손상)
    ('전라남도', '여수시'): (127.6622, 34.7604),
    ('전라남도', '완도군'): (126.7553, 34.3110),
    ('전라남도', '진도군'): (126.2638, 34.4865),
    ('전라남도', '신안군'): (126.1029, 34.8336),
    # 경북 (geo 손상)
    ('경상북도', '포항시남구'): (129.3608, 36.0090),
    ('경상북도', '포항시북구'): (129.3651, 36.0418),
    ('경상북도', '경주시'): (129.2247, 35.8562),
    ('경상북도', '울진군'): (129.4006, 36.9930),
    # 경남 (geo 손상)
    ('경상남도', '통영시'): (128.4334, 34.8540),
    ('경상남도', '사천시'): (128.0639, 35.0036),
    ('경상남도', '창원시마산합포구'): (128.5800, 35.2058),
    ('경상남도', '창원시진해구'): (128.6975, 35.1466),
    ('경상남도', '남해군'): (127.8923, 34.8378),
    ('경상남도', '하동군'): (127.7515, 35.0673),
    # 제주 (geo 손상)
    ('제주특별자치도', '제주시'): (126.5312, 33.4996),
    ('제주특별자치도', '서귀포시'): (126.5601, 33.2541),
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
    '인천광역시':     (3, 5),    # 15 col 0~2 row 4~8 (cells 14 dense fit) — 서울 row 4~8 직접 인접
    '서울특별시':     (7, 8),    # 56 (max 48 + 여유 8) — 분구 cluster 위해
    '경기도':         (12, 13),  # bbox col 0~11 row 0~12 (156) - 서울 56 - 인천 24 = 76 자리 (cells 60 + 여유 16) — 남부 cells row 11·12 cluster

    '강원특별자치도': (3, 6),    # 18 (max 18 fit) — col 12~14
    '경상북도':       (4, 6),    # 24 (max legacy 23 fit) — shape_for로 22대 cells 13는 dense (3, 5)

    '충청남도':       (4, 4),    # 16 (max legacy 16 fit) — col 3~6 row 13~16
    '세종특별자치시': (1, 4),    # 4 col 7 row 13~16 (충남 col 6 + 충북 col 8 인접)
    '충청북도':       (4, 3),    # 12 (cells 8 fit, legacy 14 일부 X) — col 8~11 row 13~15 (납작, 경기 row 12 인접)
    '대전광역시':     (4, 3),    # 12 (max 7 fit) — col 7~10 row 17~19 (충북 row 16 + 경남 col 11 인접)
    '대구광역시':     (4, 4),    # 16 (max 12 fit) — col 12~15 row 13~16
    '울산광역시':     (2, 3),    # 6 (max 6 fit) — col 16·17 row 14~16 (대구 col 15 인접)
    '전북특별자치도': (4, 3),    # 12 (cells 10 fit, legacy 15 일부 X) — col 3~6 row 17~19 (납작)
    '경상남도':       (3, 8),    # 24 (max 22 legacy fit) — col 11~13 row 17~24
    '부산광역시':     (5, 5),    # 25 (max 18 fit) — col 14~18 row 17~21 (경남 col 13 인접)
    '광주광역시':     (4, 2),    # 8 (cells 8 fit) — col 3~6 row 21·22 (전북·전남 사이, 사용자 요구)
    '전라남도':       (4, 6),    # 24 (max 22 legacy fit) — col 3~6 row 23~28
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
    # base 유지 — cells가 base 안에 spread (외측 자리도 사용). 후처리로 시도 사이
    # gap 줄임. 서울만 cells fit (회차별 크기 차이 큼).
    if sido == '서울특별시':
        w_b, h_b = base
        base_total = w_b * h_b
        target = n_cells + 1
        if target >= base_total:
            return base
        ratio = w_b / h_b
        best = base
        best_score = (base_total, abs(w_b / h_b - ratio))
        for w in range(1, w_b + 1):
            h = math.ceil(target / w)
            if h > h_b or w * h < target:
                continue
            score = (w * h, abs(w / h - ratio))
            if score < best_score:
                best = (w, h)
                best_score = score
        return best
    return base


# 호환 alias
SIDO_SHAPE = SIDO_BASE_SHAPE

# 시도 centroid 격자 위치 (사용자 시도 hex 5 row layout 영감)
# col·row = 시도 시작점 (top-left of bbox)
# 시도 cluster들이 서로 인접하도록
SIDO_OFFSET = {
    # 한국 지리 dense 배치. 모든 시도 boundary 인접 (gap 0).
    # 사용자 의도 — 경기↔강원 gap 줄임, 중남부 시도들 상승.
    '인천광역시':     (0, 4),    # col 0~2 row 4~8 (3×5=15) — dense, 서울 row 3~10 옆
    '서울특별시':     (3, 3),    # col 3~9 row 3~10 (7×8=56) — 여유 8
    '경기도':         (0, 0),    # bbox col 0~14 row 0~11. 서울·인천 exclude.
    '강원특별자치도': (12, 1),   # col 12~14 row 1~6 (사용자 — 한 row 내림)
    '경상북도':       (12, 7),   # col 12~15 row 7~12 (사용자 — 내림)
    '충청남도':       (3, 13),   # col 3~6 row 13~17 (경기 row 12 인접)
    '세종특별자치시': (7, 13),   # col 7 row 13~17 (충남 col 6 인접)
    '충청북도':       (8, 13),   # col 8~11 row 13~17 (세종 col 7 인접)
    '대구광역시':     (12, 13),  # col 12~15 row 13~16 (충북 col 11 인접)
    '울산광역시':     (16, 14),  # col 16·17 row 14~16 (대구 col 15 인접)
    '대전광역시':     (7, 17),   # col 7~10 row 17~19 (충북 row 16 인접)
    '전북특별자치도': (3, 17),   # col 3~6 row 17~21 (충남 row 16 인접)
    '경상남도':       (11, 17),  # col 11~13 row 17~24 (대전 col 10 + 대구 row 16 인접)
    '부산광역시':     (14, 17),  # col 14~18 row 17~21 (경남 col 13 인접)
    '광주광역시':     (3, 21),   # col 3~6 row 21·22 (전북 row 20 + 전남 row 23 사이)
    '전라남도':       (3, 23),   # col 3~6 row 23~28 (광주 row 22 인접)
    '제주특별자치도': (7, 27),   # col 7~9 row 27 (전남 row 23~28 옆)
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
    JITTER_OFFSET = 0.040  # 자치구 평균 spacing 만큼 — cells 자리에 spread (외측 자리 사용)
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

    # === B 시도 — rank-based normalize (unique value 기준) ===
    # 같은 col/row 자리들은 동일 rank. cells lat·lon도 unique value별 rank.
    # cells N개를 자리 분포에 강제 spread.
    n_cells = len(valid_idx)
    n_pos = len(positions)
    geo_n = np.zeros_like(geo_arr)
    pos_n = np.zeros_like(pos_arr)

    def rank_normalize(values):
        """value → 0~1 rank (unique value 기준)."""
        uniq = sorted(set(values))
        rank_map = {v: i / max(len(uniq) - 1, 1) for i, v in enumerate(uniq)}
        return np.array([rank_map[v] for v in values])

    # cells lon rank (col 방향), lat rank flip (row 방향, 큰 lat = 작은 row)
    geo_n[:, 0] = rank_normalize(geo_arr[:, 0])
    geo_n[:, 1] = 1 - rank_normalize(geo_arr[:, 1])
    # 자리 col rank, row rank
    pos_n[:, 0] = rank_normalize(pos_arr[:, 0])
    pos_n[:, 1] = rank_normalize(pos_arr[:, 1])

    cost = np.zeros((n_cells, n_pos))
    for i in range(n_cells):
        for j in range(n_pos):
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


def reconnect_cluster(cells, sidos=('경기도',), n_iter=30):
    """시도 cluster 끊어진 작은 components → 큰 cluster 인접 빈자리로 이동.

    경기·서울·인천 ring 시도 cluster 1 group 유지 위해.
    """
    by_sido = defaultdict(list)
    for c in cells:
        by_sido[c["sido"]].append(c)

    for sido in sidos:
        cs = by_sido.get(sido, [])
        if len(cs) < 2:
            continue
        for _ in range(n_iter):
            used = set((c["c"], c["r"]) for c in cells)
            pos_set = set((c["c"], c["r"]) for c in cs)
            pos_to_cell = {(c["c"], c["r"]): c for c in cs}
            # connected components (BFS)
            unvisited = set(pos_set)
            components = []
            while unvisited:
                start = next(iter(unvisited))
                comp = {start}
                stack = [start]
                while stack:
                    p = stack.pop()
                    for dc, dr in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        n = (p[0] + dc, p[1] + dr)
                        if n in pos_set and n not in comp:
                            comp.add(n)
                            stack.append(n)
                components.append(comp)
                unvisited -= comp
            if len(components) <= 1:
                break
            components.sort(key=lambda c: -len(c))
            main = components[0]
            # 작은 components cells → main 인접 빈자리로 (cell 원위치 거리 ≤ 4 자리)
            MAX_MOVE_DIST_SQ = 4 ** 2  # 거리 4 자리 이내만 이동 (너무 멀리 안 감)
            moved = False
            for small in components[1:]:
                for p in small:
                    cell = pos_to_cell[p]
                    best = None
                    best_d = float("inf")
                    for mp in main:
                        for dc, dr in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                            n = (mp[0] + dc, mp[1] + dr)
                            if n in used:
                                continue
                            d = (cell["c"] - n[0]) ** 2 + (cell["r"] - n[1]) ** 2
                            if d > MAX_MOVE_DIST_SQ:
                                continue  # 원자리에서 너무 멀음
                            if d < best_d:
                                best_d = d
                                best = n
                    if best:
                        prev = (cell["c"], cell["r"])
                        used.discard(prev)
                        used.add(best)
                        pos_set.discard(prev)
                        pos_set.add(best)
                        pos_to_cell.pop(prev, None)
                        cell["c"], cell["r"] = best
                        pos_to_cell[best] = cell
                        # main에 추가 X — cascading 막음 (main 그대로 유지)
                        moved = True
            if not moved:
                break


def fill_between_sido(cells, sido_bbox=None, n_iter=100,
                       skip=('경기도', '서울특별시', '인천광역시')):
    """시도 사이 빈자리 fill — 호남·충청·영남 다닥다닥 cluster.

    sido_bbox = {sido: (cmin, rmin, cmax, rmax)} — 시도 base 안 자리 검사.
    빈자리가 어느 시도 base 안인지 확인 → 그 시도 cells만 이동 (자기 base 안만).
    """
    from collections import Counter as _Counter
    by_sido = defaultdict(list)
    for c in cells:
        by_sido[c["sido"]].append(c)

    for _ in range(n_iter):
        used = set((c["c"], c["r"]) for c in cells)
        pos_to_cell = {(c["c"], c["r"]): c for c in cells}
        cmin = min(c["c"] for c in cells); cmax = max(c["c"] for c in cells)
        rmin = min(c["r"] for c in cells); rmax = max(c["r"] for c in cells)
        moved = False
        for col in range(cmin, cmax + 1):
            for row in range(rmin, rmax + 1):
                if (col, row) in used:
                    continue
                # 8 이웃 (4 직접 + 4 대각선) — col 6 row 22 같은 시도 사이 외측 fill 가능
                ngs = []
                for dc, dr in [(-1, 0), (1, 0), (0, -1), (0, 1),
                                (-1, -1), (1, 1), (-1, 1), (1, -1)]:
                    p = (col + dc, row + dr)
                    if p in pos_to_cell:
                        ngs.append(pos_to_cell[p])
                if len(ngs) < 1:
                    continue
                # 빈자리가 어느 시도 base 안인지 결정 — 그 시도 cells만 fill 가능
                target_sido = None
                if sido_bbox:
                    for sido, bb in sido_bbox.items():
                        if bb[0] <= col <= bb[2] and bb[1] <= row <= bb[3]:
                            target_sido = sido
                            break
                if target_sido is None:
                    continue
                if target_sido in skip:
                    continue
                top_sido = target_sido
                # 이동 자리 4 이웃에 같은 시도 cells ≥ 1 — cluster 연결 보장
                same_at_target = sum(1 for dc, dr in [(-1, 0), (1, 0), (0, -1), (0, 1)]
                    if (col + dc, row + dr) in pos_to_cell
                    and pos_to_cell[(col + dc, row + dr)]["sido"] == top_sido)
                if same_at_target < 1:
                    continue  # cluster 끊김 risk
                cs_in = by_sido[top_sido]
                if not cs_in:
                    continue
                cx = sum(c["c"] for c in cs_in) / len(cs_in)
                cy = sum(c["r"] for c in cs_in) / len(cs_in)
                # gain 한계 — 시도 base 크기 비례 (작은 시도일수록 cells 멀리 이동 OK).
                base_size = (sido_bbox[top_sido][2] - sido_bbox[top_sido][0] + 1) * \
                            (sido_bbox[top_sido][3] - sido_bbox[top_sido][1] + 1) if sido_bbox else 16
                gain_limit = -base_size  # base 안 어디든 이동 OK
                best_cand = None
                best_gain = gain_limit
                for cand in cs_in:
                    same_sido_ng = sum(
                        1 for dc, dr in [(-1, 0), (1, 0), (0, -1), (0, 1)]
                        if (cand["c"] + dc, cand["r"] + dr) in pos_to_cell
                        and pos_to_cell[(cand["c"] + dc, cand["r"] + dr)]["sido"] == top_sido
                    )
                    if same_sido_ng > 2:
                        continue
                    d_cur = (cand["c"] - cx) ** 2 + (cand["r"] - cy) ** 2
                    d_new = (col - cx) ** 2 + (row - cy) ** 2
                    gain = d_cur - d_new
                    if gain > best_gain:
                        best_gain = gain
                        best_cand = cand
                if best_cand:
                    prev = (best_cand["c"], best_cand["r"])
                    used.discard(prev)
                    used.add((col, row))
                    pos_to_cell.pop(prev, None)
                    best_cand["c"], best_cand["r"] = col, row
                    pos_to_cell[(col, row)] = best_cand
                    moved = True
        if not moved:
            break


# ===== Dynamic layout — 시도별 cells fit shape + 권역별 자동 배치 =====
# 사용자 의도 — 단계 1) 시도 cells dense cluster. 단계 2) 시도 cluster들
# 끌어당겨 합치기 (시도 사이 gap 0). 회차별 cells N 다르므로 SIDO_OFFSET 동적.

# 시도별 ratio (가로:세로) — 한국 지리 모양 따라 자치구 분포 비율
SIDO_RATIO = {
    '서울특별시':     (7, 8),   # 세로 살짝 (cells 48, chung_row 12 위해)
    '인천광역시':     (3, 8),   # 세로 길음 (강화·옹진 포함 남북)
    '경기도':         (1, 1),   # ring shape (특별 처리)
    '강원특별자치도': (1, 1),   # 정사각
    '경상북도':       (4, 4),   # 정사각 (사용자 — 영남 안 빈자리 줄임. (3,5)→(4,4) col 10~13)
    '경상남도':       (3, 4),   # 세로
    '전라북도':       (8, 2),   # 가로 8 (호남 col 0~7 확장 — 매우 납작)
    '전북특별자치도': (8, 2),
    '전라남도':       (8, 2),   # 가로 8
    '충청남도':       (4, 3),   # 가로 (동서로 김)
    '충청북도':       (4, 3),   # 가로
    '대구광역시':     (4, 4),
    '대전광역시':     (3, 3),
    '광주광역시':     (4, 2),   # 가로 4 row 2 (사용자 — 광주는 두줄이 예쁨)
    '울산광역시':     (2, 3),
    '부산광역시':     (4, 4),
    '세종특별자치시': (2, 1),   # 가로 (r12 한 row, cells 2)
    '제주특별자치도': (3, 1),   # 가로 (남북 짧음)
}


def shape_fit(sido, n_cells, slack=0):
    """cells N+slack fit 최소 shape — ratio 가까이 우선."""
    if sido not in SIDO_RATIO:
        return (3, 3)
    rw, rh = SIDO_RATIO[sido]
    target = max(n_cells + slack, 1)
    base_ratio = rw / rh
    best = None
    best_score = (float('inf'), float('inf'))
    for w in range(1, target + 1):
        h = math.ceil(target / w)
        if w * h < target:
            continue
        cur_ratio = w / h
        ratio_diff = abs(cur_ratio - base_ratio)
        # ratio 우선 (visual 모양 위해) + 자리 적은 후순위
        score = (ratio_diff, w * h)
        if score < best_score:
            best_score = score
            best = (w, h)
    return best or (1, target)


def compute_gyeonggi_ring_shape(gg_cells, seoul_shape):
    """경기 ring shape (서울 둘러쌈). 경기 cells fit ring 두께 자동."""
    sw, sh = seoul_shape
    # 경기 cells을 ring에 fit. ring 두께 r → outer (sw+2r, sh+2r), 자리 = outer - 서울.
    # 자리 ≥ gg_cells.
    for r in range(1, 10):
        outer = (sw + 2 * r) * (sh + 2 * r) - sw * sh
        if outer >= gg_cells:
            return (sw + 2 * r, sh + 2 * r, r)
    return (sw + 6, sh + 6, 3)


def compute_dynamic_layout(by_sido):
    """시도별 shape + offset 동적 계산. 권역별 grid packing.

    배치 — 한국 지도 모양:
      [인천][서울 (경기 ring 안)] [강원]
                                  [경북]
      [충남][세종][충북]           [대구][울산]
      [전북][대전]                 [경남][부산]
      [전남][광주]
      [제주]
    """
    n_cells = {sido: len(cs) for sido, cs in by_sido.items()}

    # 1. 각 시도 shape 계산
    shapes = {}
    for sido, n in n_cells.items():
        if sido not in SIDO_RATIO:
            continue
        if sido == '경기도':
            continue  # 경기 별도 처리
        shapes[sido] = shape_fit(sido, n)

    # 2. 경기 ring shape (서울 둘러쌈)
    seoul_shape = shapes.get('서울특별시', (5, 5))
    gg_cells = n_cells.get('경기도', 0)
    if gg_cells > 0:
        gg_w, gg_h, ring_thickness = compute_gyeonggi_ring_shape(gg_cells, seoul_shape)
        shapes['경기도'] = (gg_w, gg_h)
    else:
        gg_w, gg_h, ring_thickness = seoul_shape[0] + 6, seoul_shape[1] + 6, 3

    # 3. SIDO_OFFSET 자동 계산
    offsets = {}

    # 수도권 + 강원·경북 — row 0 시작
    # 인천: col 0. 경기: col w_icn 시작. 서울: 경기 안.
    icn_w, icn_h = shapes.get('인천광역시', (3, 8))
    # 인천 row: 경기 ring 중간 (인천 lat·lon이 서울보다 약간 북서)
    icn_row_offset = max(0, (gg_h - icn_h) // 2 - 1)
    offsets['인천광역시'] = (0, icn_row_offset)

    # 경기: 인천 col 끝 + 1
    gg_col = icn_w
    offsets['경기도'] = (gg_col, 0)

    # 서울: 경기 안 (ring 중심)
    seoul_col = gg_col + ring_thickness
    seoul_row = ring_thickness
    offsets['서울특별시'] = (seoul_col, seoul_row)

    # 강원: 경기 동측 row 0~
    gw_col = gg_col + gg_w
    offsets['강원특별자치도'] = (gw_col, 0)
    gw_w, gw_h = shapes.get('강원특별자치도', (3, 3))

    # 충청 row 시작 — 경기 row 끝 (gg_h)
    chung_row = gg_h
    cn_w, cn_h = shapes.get('충청남도', (4, 3))
    se_w, se_h = shapes.get('세종특별자치시', (1, 2))
    cb_w, cb_h = shapes.get('충청북도', (4, 3))

    # 충남: col 0 (사용자 요구 — 충남 왼쪽 끝)
    cn_col = 0
    offsets['충청남도'] = (cn_col, chung_row)

    # 세종: 충남 col 끝, row 12 한 row (사용자 요구)
    se_col = cn_col + cn_w
    offsets['세종특별자치시'] = (se_col, chung_row)

    # 대전: 세종 같은 col, 세종 아래 row 13~15 (사용자 요구)
    dj_w, dj_h = shapes.get('대전광역시', (3, 3))
    dj_col = se_col
    dj_row = chung_row + se_h
    offsets['대전광역시'] = (dj_col, dj_row)

    # 충북: 세종·대전 col 끝 (max width)
    cb_col = se_col + max(se_w, dj_w)
    offsets['충청북도'] = (cb_col, chung_row)

    # 경북: **충북 오른쪽** (사용자 요구 — 경기 오른쪽 아래, 충북 오른쪽)
    gb_col = cb_col + cb_w
    gb_row = chung_row
    offsets['경상북도'] = (gb_col, gb_row)
    gb_w, gb_h = shapes.get('경상북도', (4, 4))

    # 대구: 경북 아래 — 사용자 요구 (한 col 왼쪽, 경북 외)
    dg_row = gb_row + gb_h
    dg_w, dg_h = shapes.get('대구광역시', (4, 4))
    dg_col = max(0, gb_col - 1)
    offsets['대구광역시'] = (dg_col, dg_row)

    # 울산: 대구 오른쪽
    us_w, us_h = shapes.get('울산광역시', (2, 3))
    us_row = dg_row + max(0, (dg_h - us_h) // 2)
    offsets['울산광역시'] = (dg_col + dg_w, us_row)

    # 호남 row 시작 — 충청 (대전 포함) row 끝
    chung_h_max = max(cn_h, se_h, cb_h)
    honam_row = max(chung_row + chung_h_max, dj_row + dj_h)
    jb_w, jb_h = shapes.get('전북특별자치도', (4, 3))
    dj_w, dj_h = shapes.get('대전광역시', (3, 3))

    # 전북: col = cn_col (대전은 위로 이동 — 충남·충북 사이)
    offsets['전북특별자치도'] = (cn_col, honam_row)

    # 경남: 대구 아래 (대구와 같은 col — 한 col 왼쪽)
    gn_row = dg_row + dg_h
    gn_w, gn_h = shapes.get('경상남도', (3, 4))
    offsets['경상남도'] = (dg_col, gn_row)

    # 부산: 경남 오른쪽
    bs_w, bs_h = shapes.get('부산광역시', (5, 5))
    offsets['부산광역시'] = (dg_col + gn_w, gn_row)

    # 광주: 전북·전남 사이 (row = honam_row + jb_h)
    gj_row = honam_row + jb_h
    gj_w, gj_h = shapes.get('광주광역시', (3, 3))
    offsets['광주광역시'] = (cn_col, gj_row)

    # 전남: 광주 아래
    jn_row = gj_row + gj_h
    jn_w, jn_h = shapes.get('전라남도', (4, 5))
    offsets['전라남도'] = (cn_col, jn_row)

    # 제주: 전남 아래
    jj_row = jn_row + jn_h
    jj_w, jj_h = shapes.get('제주특별자치도', (3, 1))
    offsets['제주특별자치도'] = (cn_col, jj_row)

    return shapes, offsets, ring_thickness


def post_compact(cells, n_iter=30, skip=('경기도', '서울특별시', '인천광역시')):
    """후처리 — 시도 안 cells 안쪽으로 살짝 이동.

    경기·서울·인천 ring 시도는 cluster 끊어짐 risk → skip.
    """
    by_sido = defaultdict(list)
    for c in cells:
        by_sido[c["sido"]].append(c)
    used_global = set((c["c"], c["r"]) for c in cells)
    for sido, cs in by_sido.items():
        if sido in skip or len(cs) < 2:
            continue
        cx = sum(c["c"] for c in cs) / len(cs)
        cy = sum(c["r"] for c in cs) / len(cs)
        # 시도 cells의 자리 bbox (cells 분포 기준 — 후처리는 이 안에서만)
        cmin = min(c["c"] for c in cs); cmax = max(c["c"] for c in cs)
        rmin = min(c["r"] for c in cs); rmax = max(c["r"] for c in cs)
        for _ in range(n_iter):
            moved = False
            # cells centroid에서 먼 cell부터 (외측 cell 안쪽으로 우선)
            cs.sort(key=lambda c: -((c["c"] - cx) ** 2 + (c["r"] - cy) ** 2))
            for cell in cs:
                d_cur = (cell["c"] - cx) ** 2 + (cell["r"] - cy) ** 2
                best = None
                best_d = d_cur
                # 4 이웃 검사 (안쪽 = centroid 가까운)
                for dc, dr in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nc, nr = cell["c"] + dc, cell["r"] + dr
                    if (nc, nr) in used_global:
                        continue
                    # 시도 cells bbox 안만 (다른 시도 자리 X)
                    if not (cmin <= nc <= cmax and rmin <= nr <= rmax):
                        continue
                    d_new = (nc - cx) ** 2 + (nr - cy) ** 2
                    if d_new < best_d:
                        best_d = d_new
                        best = (nc, nr)
                if best:
                    used_global.discard((cell["c"], cell["r"]))
                    used_global.add(best)
                    cell["c"], cell["r"] = best
                    moved = True
            if not moved:
                break


def process(src_name, out_suffix="_v2"):
    src = GEO_DIR / src_name
    cells = json.loads(src.read_text(encoding="utf-8"))
    centers = load_centers()
    by_sido = defaultdict(list)
    for c in cells:
        by_sido[c["sido"]].append(c)


    # 회차별 cells 갯수 → dynamic layout (시도별 cells fit shape + 자동 packing)
    dyn_shapes, dyn_offsets, ring_thickness = compute_dynamic_layout(by_sido)
    seoul_shape = dyn_shapes.get('서울특별시', (5, 5))
    gyeonggi_shape = dyn_shapes.get('경기도', (11, 11))
    seoul_offset = dyn_offsets.get('서울특별시', (3, 3))
    seoul_bbox = (seoul_offset[0], seoul_offset[1],
                  seoul_offset[0] + seoul_shape[0] - 1,
                  seoul_offset[1] + seoul_shape[1] - 1)
    icn_shape = dyn_shapes.get('인천광역시', (3, 8))
    icn_offset = dyn_offsets.get('인천광역시', (0, 4))
    icn_bbox = (icn_offset[0], icn_offset[1],
                icn_offset[0] + icn_shape[0] - 1,
                icn_offset[1] + icn_shape[1] - 1)

    print(f"\n=== {src_name} ({len(cells)} cells) ===")
    for sido, sido_cells in sorted(by_sido.items()):
        if sido not in dyn_offsets:
            print(f"  {sido} skip")
            continue
        n = len(sido_cells)
        offset = dyn_offsets[sido]
        shape_ = dyn_shapes.get(sido, (3, 3))
        if sido == '경기도':
            # 인천 위쪽 (col 0~2 row 0~3) 자리 exclude — 김포·파주·고양·부천이
            # col 3+로 cluster (인천과 갈라먹지 X, 다른 경기와 인접)
            excludes = [seoul_bbox, icn_bbox, (0, 0, 2, 3)]
        else:
            excludes = []
        positions = positions_in_bbox(offset, shape_, excludes)
        if sido == '경기도':
            # 경기 ring projection — 서울 중심 기준 polar (안산·화성 등 자치구 위치 정확)
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

    # === 후처리 제거 ===
    # Pipeline: shape_fit (slack=0) + compute_dynamic_layout (시도 cluster packing) +
    # assign_cells (rank-based spread). Step 1·2가 정확하면 후처리 불필요.
    # cluster 분할 시만 reconnect (최소 이동).
    all_sidos = tuple(set(c["sido"] for c in cells))
    reconnect_cluster(cells, sidos=all_sidos)

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
