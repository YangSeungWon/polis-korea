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
SIDO_SHAPE = {
    # 22대 60 cells 경기에 맞춤. 7×7 서울 + 11×12 경기 ring → cells 다 수용.
    '인천광역시':     (3, 5),
    '서울특별시':     (7, 7),  # 49 (max 48)
    '경기도':         (11, 12), # 132-49=83 (max 60, 23 외곽 빈자리 — 한국 외)
    '강원특별자치도': (4, 5),  # 20 (max 18)
    '충청북도':       (4, 4),  # 16 (max 14)
    '충청남도':       (4, 4),
    '세종특별자치시': (1, 2),
    '대전광역시':     (3, 3),
    '경상북도':       (5, 5),
    '대구광역시':     (4, 3),
    '울산광역시':     (2, 3),
    '경상남도':       (3, 8),
    '부산광역시':     (5, 4),
    '전북특별자치도': (4, 4),
    '전라남도':       (5, 5),
    '광주광역시':     (3, 3),
    '제주특별자치도': (3, 1),
}

# 시도 centroid 격자 위치 (사용자 시도 hex 5 row layout 영감)
# col·row = 시도 시작점 (top-left of bbox)
# 시도 cluster들이 서로 인접하도록
SIDO_OFFSET = {
    # 한국 지리 dense 배치. 경기 서울 둘러쌈 + 남부 비중 (사용자 의도).
    # 시도 boundary 모두 인접 (서로 끌어당김).
    '인천광역시':     (0, 4),    # col 0~2 row 4~8
    '서울특별시':     (3, 3),    # col 3~9 row 3~9 (7×7)
    '경기도':         (3, 0),    # col 3~13 row 0~11 (서울 exclude) — 위 좁고 아래 넓음
    '강원특별자치도': (14, 0),   # col 14~17 row 0~4 (북동)
    '경상북도':       (14, 5),   # col 14~18 row 5~9 (강원 아래)
    '충청남도':       (3, 12),   # col 3~6 row 12~15 (서)
    '세종특별자치시': (7, 13),   # col 7 row 13~14 (중)
    '충청북도':       (8, 12),   # col 8~11 row 12~15 (중동)
    '대구광역시':     (14, 10),  # col 14~17 row 10~12 (동중)
    '울산광역시':     (18, 11),  # col 18~19 row 11~13 (동)
    '대전광역시':     (8, 16),   # col 8~10 row 16~18 (충북 row 12~15와 분리)
    '경상남도':       (12, 13),  # col 12~14 row 13~20 (충북 col 11 분리)
    '부산광역시':     (15, 14),  # col 15~19 row 14~17 (동남)
    '전북특별자치도': (3, 16),   # col 3~6 row 16~19 (서남)
    '광주광역시':     (3, 20),   # col 3~5 row 20~22 (남)
    '전라남도':       (6, 20),   # col 6~10 row 20~24 (가장 남)
    '제주특별자치도': (7, 25),   # col 7~9 row 25 (단독 남단)
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


def assign_cells(cells, positions, centers, w_lon=2.5, n_swap=50):
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

    # 시도별 positions — SIDO_OFFSET + SIDO_SHAPE
    # 경기 ring 처리: 서울 영역 exclude
    seoul_offset = SIDO_OFFSET.get('서울특별시', (3, 4))
    seoul_shape = SIDO_SHAPE.get('서울특별시', (7, 7))
    seoul_bbox = (seoul_offset[0], seoul_offset[1],
                  seoul_offset[0] + seoul_shape[0] - 1,
                  seoul_offset[1] + seoul_shape[1] - 1)

    print(f"\n=== {src_name} ({len(cells)} cells) ===")
    for sido, sido_cells in sorted(by_sido.items()):
        if sido not in SIDO_OFFSET:
            print(f"  {sido} skip")
            continue
        offset = SIDO_OFFSET[sido]
        shape_ = SIDO_SHAPE[sido]
        excludes = [seoul_bbox] if sido == '경기도' else []
        positions = positions_in_bbox(offset, shape_, excludes)
        new_pos = assign_cells(sido_cells, positions, centers)
        applied = 0
        for cell, p in zip(sido_cells, new_pos):
            if p:
                cell["c"], cell["r"] = p
                applied += 1
        print(f"  {sido:20s} {len(sido_cells):3d} cells → {applied} 적용 (자리 {len(positions)})")

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
