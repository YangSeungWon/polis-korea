"""1단계 Hungarian 후 2단계 swap optimization으로 cell 위치 개선.

quality metric: 각 cell의 정규화된 격자 위치 vs 정규화된 지리 중심의 거리².
swap: 시도 안 두 cell의 (c, r) 교환이 total cost를 줄이면 적용.
반복으로 local 최적까지 진행.

사용:
  python3 scripts/refine_district_hex.py 22 [--out v2]
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from collections import defaultdict

import numpy as np
from scipy.optimize import linear_sum_assignment
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
GEO_DIR = ROOT / "data/geo"


SIDO_CODE = {
    '11': '서울특별시', '21': '부산광역시', '22': '대구광역시',
    '23': '인천광역시', '24': '광주광역시', '25': '대전광역시',
    '26': '울산광역시', '29': '세종특별자치시',
    '31': '경기도', '32': '강원특별자치도', '33': '충청북도',
    '34': '충청남도', '35': '전북특별자치도', '36': '전라남도',
    '37': '경상북도', '38': '경상남도', '39': '제주특별자치도',
}


def load_sigungu_centers() -> dict[tuple[str, str], tuple[float, float]]:
    """(시도, 시군구) → (lon, lat). 시도 중복 명 (중구·강서구 등) 분리."""
    geo = json.loads((GEO_DIR / "sigungu_simple.json").read_text(encoding="utf-8"))
    out = {}
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


def cell_geo(cell: dict, centers: dict) -> tuple[float, float] | None:
    sgs = cell.get("sigungus", [])
    sido = cell.get("sido", "")
    coords = []
    for s in sgs:
        key = (sido, s)
        if key in centers:
            coords.append(centers[key])
        else:
            # 모도시 추출 — '수원시장안구' → '수원시'
            i = s.find("시")
            if i > 0:
                base = s[:i+1]
                if (sido, base) in centers:
                    coords.append(centers[(sido, base)])
    if not coords:
        return None
    return (sum(c[0] for c in coords) / len(coords),
            sum(c[1] for c in coords) / len(coords))


def normalize(arr: np.ndarray) -> np.ndarray:
    mn = arr.min(axis=0)
    mx = arr.max(axis=0)
    rng = np.where(mx - mn > 0, mx - mn, 1)
    return (arr - mn) / rng


def assign_and_swap(cells: list[dict], centers: dict, n_swap_passes: int = 50,
                    w_lon: float | None = None) -> int:
    """1단계 Hungarian + 2단계 swap optimization.

    w_lon: lon축 cost weight. None이면 시도의 aspect ratio (geo lon_range / lat_range
      vs pos col_range / row_range)로 자동.

    return: 변경된 cell 수.
    """
    if len(cells) <= 1:
        return 0
    geos = [cell_geo(c, centers) for c in cells]
    valid_idx = [i for i, g in enumerate(geos) if g is not None]
    if len(valid_idx) < 2:
        return 0
    positions = [(c["c"], c["r"]) for c in cells]
    n = len(valid_idx)
    geo_arr = np.array([geos[i] for i in valid_idx], dtype=float)
    pos_arr = np.array([positions[i] for i in valid_idx], dtype=float)

    # raw range 자동 weight 계산 (정규화 전)
    geo_xr = geo_arr[:, 0].max() - geo_arr[:, 0].min()
    geo_yr = geo_arr[:, 1].max() - geo_arr[:, 1].min()
    pos_xr = pos_arr[:, 0].max() - pos_arr[:, 0].min()
    pos_yr = pos_arr[:, 1].max() - pos_arr[:, 1].min()
    if w_lon is None:
        # geo aspect / pos aspect — 시도가 가늘 길면 lon weight ↑
        try:
            geo_aspect = (geo_xr / geo_yr) if geo_yr > 0 else 1.0
            pos_aspect = (pos_xr / pos_yr) if pos_yr > 0 else 1.0
            # weight = pos_aspect / geo_aspect — pos가 더 wide면 lon에 weight ↑
            w = pos_aspect / geo_aspect if geo_aspect > 0 else 1.0
            w_lon = max(0.5, min(4.0, w))  # cap [0.5, 4.0]
        except Exception:
            w_lon = 1.0

    geo_n = normalize(geo_arr)
    geo_n[:, 1] = 1 - geo_n[:, 1]  # lat 높음 = row 0
    pos_n = normalize(pos_arr)

    # cost function with weight
    def pair_cost(geo_i, pos_j):
        dx = geo_i[0] - pos_j[0]
        dy = geo_i[1] - pos_j[1]
        return w_lon * dx * dx + dy * dy

    # 1단계: Hungarian
    cost = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            cost[i, j] = pair_cost(geo_n[i], pos_n[j])
    _, col_ind = linear_sum_assignment(cost)
    assign = list(col_ind)

    # 2단계: pair swap optimization
    for _ in range(n_swap_passes):
        improved = False
        for i in range(n):
            for j in range(i + 1, n):
                a, b = assign[i], assign[j]
                old_i = pair_cost(geo_n[i], pos_n[a])
                old_j = pair_cost(geo_n[j], pos_n[b])
                new_i = pair_cost(geo_n[i], pos_n[b])
                new_j = pair_cost(geo_n[j], pos_n[a])
                if new_i + new_j < old_i + old_j - 1e-9:
                    assign[i], assign[j] = b, a
                    improved = True
        if not improved:
            break

    # 적용
    n_changed = 0
    for i_local, j_local in enumerate(assign):
        i_global = valid_idx[i_local]
        new_c, new_r = positions[valid_idx[j_local]]
        if cells[i_global]["c"] != new_c or cells[i_global]["r"] != new_r:
            n_changed += 1
        cells[i_global]["c"] = new_c
        cells[i_global]["r"] = new_r
    return n_changed


def quality_report(cells: list[dict], centers: dict, sido: str) -> list[tuple]:
    """각 cell의 (격자 위치) vs (지리 중심) 거리. 큰 순 정렬.

    return: [(name, dist, geo_xy, pos_xy), ...]
    """
    geos = [cell_geo(c, centers) for c in cells]
    valid = [i for i, g in enumerate(geos) if g is not None]
    if len(valid) < 2:
        return []
    geo_arr = np.array([geos[i] for i in valid], dtype=float)
    pos_arr = np.array([[cells[i]["c"], cells[i]["r"]] for i in valid], dtype=float)
    geo_n = normalize(geo_arr)
    geo_n[:, 1] = 1 - geo_n[:, 1]
    pos_n = normalize(pos_arr)
    out = []
    for k, i in enumerate(valid):
        d = ((geo_n[k, 0] - pos_n[k, 0]) ** 2 +
             (geo_n[k, 1] - pos_n[k, 1]) ** 2) ** 0.5
        out.append((cells[i]["name"], d, tuple(geo_n[k]), tuple(pos_n[k])))
    return sorted(out, key=lambda x: -x[1])


def process(n: int, out_suffix: str = "_v2", show_quality: bool = True,
            w_lon: float | None = None):
    src = GEO_DIR / f"district_hex_{n}.json"
    cells = json.loads(src.read_text(encoding="utf-8"))
    centers = load_sigungu_centers()
    by_sido = defaultdict(list)
    for c in cells:
        by_sido[c["sido"]].append(c)

    print(f"\n=== {n}대 총선 ({len(cells)}구) ===")
    total_changed = 0
    for sido, sido_cells in sorted(by_sido.items()):
        changed = assign_and_swap(sido_cells, centers, w_lon=w_lon)
        total_changed += changed
        print(f"  {sido:20s} {len(sido_cells):3d}구 — {changed} 변경")
        if show_quality:
            qs = quality_report(sido_cells, centers, sido)
            # 상위 어색 case 3건
            for name, d, geo, pos in qs[:3]:
                if d > 0.3:
                    print(f"    어색 {name:20s} geo=({geo[0]:.2f},{geo[1]:.2f}) pos=({pos[0]:.2f},{pos[1]:.2f}) d={d:.2f}")

    out = GEO_DIR / f"district_hex_{n}{out_suffix}.json"
    out.write_text(json.dumps(cells, ensure_ascii=False), encoding="utf-8")
    print(f"  → {out.name} ({total_changed}/{len(cells)})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ns", nargs="+", type=int)
    ap.add_argument("--out", default="_v2")
    ap.add_argument("--w-lon", type=float, default=None,
                    help="lon weight. None=시도 aspect ratio 자동")
    args = ap.parse_args()
    for n in args.ns:
        process(n, args.out, w_lon=args.w_lon)


if __name__ == "__main__":
    main()
