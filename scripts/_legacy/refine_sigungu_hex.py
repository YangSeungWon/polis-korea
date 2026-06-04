"""sigungu_hex.json·legacy.json의 시도내 자치구 위치를 lat·lon 기준 재배치.

district_hex와 동일 algorithm — 시도 boundary 유지, 시도 안 cell들 swap.

사용:
  python3 scripts/_legacy/refine_sigungu_hex.py [--w-lon 2.5]
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from collections import defaultdict

import numpy as np
from scipy.optimize import linear_sum_assignment
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[2]
GEO_DIR = ROOT / "data/geo"

SIDO_CODE = {
    '11':'서울특별시','21':'부산광역시','22':'대구광역시','23':'인천광역시',
    '24':'광주광역시','25':'대전광역시','26':'울산광역시','29':'세종특별자치시',
    '31':'경기도','32':'강원특별자치도','33':'충청북도','34':'충청남도',
    '35':'전북특별자치도','36':'전라남도','37':'경상북도','38':'경상남도','39':'제주특별자치도',
}


def load_centers() -> dict[tuple[str, str], tuple[float, float]]:
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
    """sigungu_hex cell — {name, sido, c, r, code}. 단일 자치구."""
    sido = cell.get("sido", "")
    name = cell.get("name", "")
    if (sido, name) in centers:
        return centers[(sido, name)]
    # 모도시 추출 — '수원시장안구' → '수원시'
    i = name.find("시")
    if i > 0 and (sido, name[:i+1]) in centers:
        return centers[(sido, name[:i+1])]
    return None


def normalize(arr):
    mn = arr.min(axis=0)
    mx = arr.max(axis=0)
    rng = np.where(mx - mn > 0, mx - mn, 1)
    return (arr - mn) / rng


def reassign(cells: list[dict], centers: dict, w_lon: float = 2.5,
             n_swap_passes: int = 50) -> int:
    if len(cells) <= 1:
        return 0
    geos = [cell_geo(c, centers) for c in cells]
    valid = [i for i, g in enumerate(geos) if g is not None]
    if len(valid) < 2:
        return 0
    positions = [(c["c"], c["r"]) for c in cells]
    n = len(valid)
    geo_arr = np.array([geos[i] for i in valid], dtype=float)
    pos_arr = np.array([positions[i] for i in valid], dtype=float)
    geo_n = normalize(geo_arr)
    geo_n[:, 1] = 1 - geo_n[:, 1]
    pos_n = normalize(pos_arr)

    def pc(geo_i, pos_j):
        dx = geo_i[0] - pos_j[0]
        dy = geo_i[1] - pos_j[1]
        return w_lon * dx * dx + dy * dy

    cost = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            cost[i, j] = pc(geo_n[i], pos_n[j])
    _, col_ind = linear_sum_assignment(cost)
    assign = list(col_ind)

    for _ in range(n_swap_passes):
        improved = False
        for i in range(n):
            for j in range(i + 1, n):
                a, b = assign[i], assign[j]
                if pc(geo_n[i], pos_n[b]) + pc(geo_n[j], pos_n[a]) < \
                   pc(geo_n[i], pos_n[a]) + pc(geo_n[j], pos_n[b]) - 1e-9:
                    assign[i], assign[j] = b, a
                    improved = True
        if not improved:
            break

    changed = 0
    for i_local, j_local in enumerate(assign):
        ig = valid[i_local]
        new_c, new_r = positions[valid[j_local]]
        if cells[ig]["c"] != new_c or cells[ig]["r"] != new_r:
            changed += 1
        cells[ig]["c"] = new_c
        cells[ig]["r"] = new_r
    return changed


def process(src_name: str, out_suffix: str = "_v2", w_lon: float = 2.5):
    src = GEO_DIR / src_name
    cells = json.loads(src.read_text(encoding="utf-8"))
    centers = load_centers()
    by_sido = defaultdict(list)
    for c in cells:
        by_sido[c["sido"]].append(c)
    print(f"\n=== {src_name} ({len(cells)} cell) ===")
    total = 0
    for sido, sido_cells in sorted(by_sido.items()):
        changed = reassign(sido_cells, centers, w_lon=w_lon)
        total += changed
        print(f"  {sido:20s} {len(sido_cells):3d}개 — {changed} 변경")
    out = src.with_name(src.stem + out_suffix + src.suffix)
    out.write_text(json.dumps(cells, ensure_ascii=False), encoding="utf-8")
    print(f"  → {out.name} ({total}/{len(cells)})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--w-lon", type=float, default=2.5)
    ap.add_argument("--out", default="_v2")
    args = ap.parse_args()
    for src in ["sigungu_hex.json", "sigungu_hex_legacy.json"]:
        process(src, args.out, w_lon=args.w_lon)


if __name__ == "__main__":
    main()
