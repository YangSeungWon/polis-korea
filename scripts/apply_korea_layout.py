"""전체 한국 hex layout 재설계 — 시도별 bbox + cells lat·lon Hungarian 매핑.

사용자 시도 hex layout (5 row) 영감 받아 시도별 영역 plan.
시도 안 자치구는 lat·lon centroid → bbox 격자 자리 자동.
"""
from __future__ import annotations
import json
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

# 시도별 bbox + 제외 영역 (서울 안 경기 제외 등)
# (cmin, rmin, cmax, rmax) + 제외 bbox list
SIDO_BBOX = {
    # bbox max cells (시군구 232 / legacy 250 / 지역구 22대 254) 다 커버.
    # 시도 내부 cells 갯수 가변 — Hungarian이 자리에 cells 매핑.
    # 외곽 빈자리만 (한국 모양 자연), 시도 boundary sharp.
    # 경기 bbox에 서울 exclude → 경기가 서울 둘러쌈 유지.
    '인천광역시':     {'bbox': (0, 0, 2, 4), 'exclude': []},   # 15 (max 14)
    '서울특별시':     {'bbox': (3, 2, 9, 8), 'exclude': []},   # 49 (max 48)
    '경기도':         {'bbox': (3, 0, 13, 11), 'exclude': [(3, 2, 9, 8), (10, 9, 13, 11)]},  # 서울·충북 exclude
    '강원특별자치도': {'bbox': (14, 0, 17, 5), 'exclude': []}, # 24
    '충청북도':       {'bbox': (10, 9, 13, 12), 'exclude': []},# 16
    '충청남도':       {'bbox': (3, 12, 9, 14), 'exclude': []}, # 21
    '세종특별자치시': {'bbox': (10, 13, 11, 13), 'exclude': []},# 2
    '대전광역시':     {'bbox': (11, 13, 13, 15), 'exclude': []},# 9
    '경상북도':       {'bbox': (14, 6, 18, 12), 'exclude': []},# 35
    '대구광역시':     {'bbox': (14, 13, 17, 15), 'exclude': [(11, 13, 13, 15)]},# 대전 exclude
    '울산광역시':     {'bbox': (18, 13, 19, 15), 'exclude': []},# 6
    '경상남도':       {'bbox': (10, 16, 14, 20), 'exclude': []},# 25
    '부산광역시':     {'bbox': (15, 16, 19, 20), 'exclude': []},# 25
    '전북특별자치도': {'bbox': (3, 15, 9, 17), 'exclude': [(7, 17, 9, 17)]}, # 광주 row 17 exclude
    '광주광역시':     {'bbox': (7, 17, 9, 19), 'exclude': []}, # 9
    '전라남도':       {'bbox': (3, 18, 6, 25), 'exclude': []}, # 32
    '제주특별자치도': {'bbox': (5, 26, 7, 26), 'exclude': []}, # 3
}


# 9회 신설/개명/legacy 분할구 등 centroid 매핑 hardcode
HARDCODE_CENTROID = {
    # 인천 9회 신설 (영종·검단·제물포)
    ('인천광역시', '영종구'): (126.55, 37.46),
    ('인천광역시', '검단구'): (126.65, 37.55),
    ('인천광역시', '제물포구'): (126.66, 37.48),
    # 미추홀구 = 남구 개명 (cells 두 이름 다 등장)
    ('인천광역시', '미추홀구'): (126.66, 37.45),
    # 제주 자치구 (sigungu_simple.json에 없음)
    ('제주특별자치도', '제주시'): (126.53, 33.50),
    ('제주특별자치도', '서귀포시'): (126.56, 33.25),
    # 충남 계룡시 (신설)
    ('충청남도', '계룡시'): (127.25, 36.27),
    # 충남 옛 연기군 = 세종
    ('충청남도', '연기군'): (127.26, 36.56),
    # 강원 옛 양양·인제·고성 등 hardcode 일부
    ('강원특별자치도', '고성군'): (128.47, 38.38),
    # 전남광주 통합 (9회+)
    ('전남광주특별시', '전남광주통합'): (126.85, 35.00),
    # 옛 시도 alias (강원도·전라북도·제주도)
    # 처리는 sido normalize로
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
    # 옛 시도 명 normalize
    sido = {'강원도': '강원특별자치도', '전라북도': '전북특별자치도',
            '제주도': '제주특별자치도'}.get(sido, sido)
    if (sido, name) in centers:
        return centers[(sido, name)]
    # 모도시 → 분할구 평균 (수원시 → 수원시장안·권선·팔달·영통 평균)
    if name.endswith('시') or name.endswith('군'):
        prefix = name
        matches = [v for (s, n), v in centers.items()
                   if s == sido and n.startswith(prefix) and n != name]
        if matches:
            return (sum(m[0] for m in matches) / len(matches),
                    sum(m[1] for m in matches) / len(matches))
    # 미추홀구 ↔ 남구 alias
    if name == '미추홀구' and (sido, '남구') in centers:
        return centers[(sido, '남구')]
    if name == '남구' and sido == '인천광역시' and (sido, '미추홀구') in centers:
        return centers[(sido, '미추홀구')]
    if name == '청주시청원구' and (sido, '청원군') in centers:
        return centers[(sido, '청원군')]
    # 일반구 → 모도시 (수원시장안구 → 수원시) — 모도시 매핑 fallback
    i = name.find("시")
    if i > 0 and i < len(name) - 1 and (sido, name[:i+1]) in centers:
        return centers[(sido, name[:i+1])]
    # 마지막 fallback — 시도 평균 (cells 모두 매핑 위해)
    sido_geos = [v for (s, _), v in centers.items() if s == sido]
    if sido_geos:
        return (sum(g[0] for g in sido_geos) / len(sido_geos),
                sum(g[1] for g in sido_geos) / len(sido_geos))
    return None


def positions_in_bbox(bbox, exclude_bboxes):
    cmin, rmin, cmax, rmax = bbox
    out = []
    for c in range(cmin, cmax + 1):
        for r in range(rmin, rmax + 1):
            excluded = False
            for eb in exclude_bboxes:
                ecmin, ermin, ecmax, ermax = eb
                if ecmin <= c <= ecmax and ermin <= r <= ermax:
                    excluded = True
                    break
            if not excluded:
                out.append((c, r))
    return out


def normalize(arr):
    mn = arr.min(axis=0); mx = arr.max(axis=0)
    rng = np.where(mx - mn > 0, mx - mn, 1)
    return (arr - mn) / rng


def assign_cells_to_positions(cells, positions, centers, w_lon=2.5, n_swap=50):
    """cells → positions (Hungarian + swap)."""
    geos = [cell_geo(c, centers) for c in cells]
    valid = [i for i, g in enumerate(geos) if g is not None]
    if len(valid) < 1:
        return [None] * len(cells)
    n = len(valid)
    if n > len(positions):
        print(f"  ✗ cells {n} > positions {len(positions)}", end=" ")
        return [None] * len(cells)
    geo_arr = np.array([geos[i] for i in valid], dtype=float)
    pos_arr = np.array(positions[:n] if n == len(positions) else positions, dtype=float)
    geo_n = normalize(geo_arr); geo_n[:, 1] = 1 - geo_n[:, 1]
    if len(positions) > 1:
        pos_n_full = normalize(np.array(positions, dtype=float))
    else:
        pos_n_full = np.array([[0.5, 0.5]])

    def pc(g, p):
        dx = g[0] - p[0]; dy = g[1] - p[1]
        return w_lon * dx * dx + dy * dy

    # n cells × len(positions) cost
    cost = np.zeros((n, len(positions)))
    for i in range(n):
        for j in range(len(positions)):
            cost[i, j] = pc(geo_n[i], pos_n_full[j])
    _, col_ind = linear_sum_assignment(cost)
    assign = list(col_ind)

    # swap optimization
    for _ in range(n_swap):
        improved = False
        for i in range(n):
            for j in range(i+1, n):
                a, b = assign[i], assign[j]
                if pc(geo_n[i], pos_n_full[b]) + pc(geo_n[j], pos_n_full[a]) < \
                   pc(geo_n[i], pos_n_full[a]) + pc(geo_n[j], pos_n_full[b]) - 1e-9:
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

    print(f"\n=== {src_name} ({len(cells)} cells) ===")
    for sido, sido_cells in sorted(by_sido.items()):
        if sido not in SIDO_BBOX:
            print(f"  {sido}: bbox 미정의, skip")
            continue
        cfg = SIDO_BBOX[sido]
        positions = positions_in_bbox(cfg['bbox'], cfg['exclude'])
        new_positions = assign_cells_to_positions(sido_cells, positions, centers)
        applied = 0
        for cell, pos in zip(sido_cells, new_positions):
            if pos:
                cell['c'], cell['r'] = pos
                applied += 1
        print(f"  {sido:20s} {len(sido_cells):3d} cells → {applied} 적용 (bbox {len(positions)} 자리)")

    out = src.with_name(src.stem + out_suffix + src.suffix)
    out.write_text(json.dumps(cells, ensure_ascii=False), encoding="utf-8")
    print(f"  → {out.name}")


if __name__ == "__main__":
    import sys
    files = sys.argv[1:] if len(sys.argv) > 1 else [
        "sigungu_hex.json", "sigungu_hex_legacy.json",
        "district_hex_17.json", "district_hex_18.json", "district_hex_19.json",
        "district_hex_20.json", "district_hex_21.json", "district_hex_22.json",
    ]
    for src in files:
        if (GEO_DIR / src).exists():
            process(src)
