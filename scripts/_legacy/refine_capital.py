"""수도권 (서울·인천·경기) cell 위치 lat·lon 기반 격자 재배치.

사용자 의도:
- 서울 중심 cluster
- 인천 서울 좌측 직접 연결 (서울 서 = 인천 동)
- 경기 서울 둘러쌈 (북·동·동남·남·서남)
- 경기 남부 두꺼움 / 북부·동남부 얇음

작업: 수도권 69 cell의 lat·lon centroid → 격자 (col, row).
시도 boundary 무시 (수도권 전체 한 cluster로 lat·lon 매핑).
target grid는 col 0~10·row 0~10 정도. Hungarian + swap.

사용:
  python3 scripts/_legacy/refine_capital.py [--out _v2]
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[2]
GEO_DIR = ROOT / "data/geo"

SIDO_CODE = {
    '11':'서울특별시','23':'인천광역시','31':'경기도',
}

CAPITAL_SIDOS = {'서울특별시', '인천광역시', '경기도'}


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
    sido = cell.get("sido", "")
    name = cell.get("name", "")
    if (sido, name) in centers:
        return centers[(sido, name)]
    i = name.find("시")
    if i > 0 and (sido, name[:i+1]) in centers:
        return centers[(sido, name[:i+1])]
    return None


def reassign_capital(cells: list[dict], centers: dict, w_lon: float = 2.5,
                     n_swap_passes: int = 100) -> int:
    """수도권 cells (시도 무관) lat·lon → 격자 매핑."""
    geos = [cell_geo(c, centers) for c in cells]
    valid = [i for i, g in enumerate(geos) if g is not None]
    if len(valid) < 2:
        return 0
    positions = [(c["c"], c["r"]) for c in cells]
    n = len(valid)
    geo_arr = np.array([geos[i] for i in valid], dtype=float)
    pos_arr = np.array([positions[i] for i in valid], dtype=float)

    def norm(arr):
        mn = arr.min(axis=0); mx = arr.max(axis=0)
        rng = np.where(mx - mn > 0, mx - mn, 1)
        return (arr - mn) / rng

    geo_n = norm(geo_arr); geo_n[:, 1] = 1 - geo_n[:, 1]
    pos_n = norm(pos_arr)

    def pc(g, p):
        dx = g[0] - p[0]; dy = g[1] - p[1]
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

    # 수도권 cells extract
    cap_idx = [i for i, c in enumerate(cells) if c["sido"] in CAPITAL_SIDOS]
    cap_cells = [cells[i] for i in cap_idx]
    print(f"\n=== {src_name} 수도권 {len(cap_cells)} cell ===")
    changed = reassign_capital(cap_cells, centers, w_lon=w_lon)
    # 원본에 적용
    for i_local, i_global in enumerate(cap_idx):
        cells[i_global]["c"] = cap_cells[i_local]["c"]
        cells[i_global]["r"] = cap_cells[i_local]["r"]

    out = src.with_name(src.stem + out_suffix + src.suffix)
    out.write_text(json.dumps(cells, ensure_ascii=False), encoding="utf-8")
    print(f"  {changed}/{len(cap_cells)} cell 재배치 → {out.name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--w-lon", type=float, default=2.5)
    ap.add_argument("--out", default="_v2")
    args = ap.parse_args()
    for src in ["sigungu_hex.json", "sigungu_hex_legacy.json"]:
        process(src, args.out, w_lon=args.w_lon)


if __name__ == "__main__":
    main()
