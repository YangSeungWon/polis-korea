"""시도 안 자치구 위치를 (lat·lon) 기준으로 재배치.

기존 district_hex_N.json (한국 전체 layout)은 유지하고 시도 안 cell들의
(col, row) 좌표만 자치구 중심에 맞게 Hungarian assignment.

분구 (강남갑·을·병)는 같은 자치구의 다른 cell — 격자에서 인접 위치 자동 배치.

사용:
  python3 scripts/_legacy/gen_district_hex_semantic.py 22 [--out v2]
  python3 scripts/_legacy/gen_district_hex_semantic.py 17 18 19 20 21 22 --all
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


def load_sigungu_centers() -> dict[str, tuple[float, float]]:
    """sigungu_simple.json → {시군구명: (lon, lat)} 중심점."""
    geo = json.loads((GEO_DIR / "sigungu_simple.json").read_text(encoding="utf-8"))
    out = {}
    for f in geo["features"]:
        name = f["properties"].get("name", "")
        if not name:
            continue
        try:
            pt = shape(f["geometry"]).centroid
            out[name] = (pt.x, pt.y)
        except Exception:
            continue
    return out


def cell_center(cell: dict, centers: dict) -> tuple[float, float]:
    """cell.sigungus의 중심 좌표 평균. 매칭 실패 시 None."""
    sgs = cell.get("sigungus", [])
    coords = []
    for s in sgs:
        if s in centers:
            coords.append(centers[s])
        else:
            # 일부 일반구 시도 (예: 강남구 등)
            # 알 수 없는 경우 모도시 추출 — '수원시장안구' → '수원시'
            base = None
            if s.endswith("구"):
                for sfx in ("구",):
                    # 모도시 추출 — "고양시덕양구" → "고양시"
                    i = s.find("시")
                    if i > 0:
                        base = s[:i + 1]
                        break
            if base and base in centers:
                coords.append(centers[base])
    if not coords:
        return None
    lon = sum(c[0] for c in coords) / len(coords)
    lat = sum(c[1] for c in coords) / len(coords)
    return (lon, lat)


def reassign_sido(cells: list[dict], centers: dict) -> int:
    """한 시도 내 cells의 (c, r)을 자치구 중심 좌표 기준 Hungarian 매칭.

    return: 변경된 cell 수.
    """
    if len(cells) <= 1:
        return 0
    # 각 cell의 지리 중심
    geos = [cell_center(c, centers) for c in cells]
    valid = [i for i, g in enumerate(geos) if g is not None]
    if len(valid) < 2:
        return 0
    # 격자 자리 (col, row)
    positions = [(c["c"], c["r"]) for c in cells]
    n_valid = len(valid)
    # valid cells만 매칭, 나머지는 유지
    geo_arr = np.array([geos[i] for i in valid], dtype=float)  # (lon, lat)
    pos_arr = np.array([positions[i] for i in valid], dtype=float)  # (col, row)

    # Normalize 각 축 [0, 1]
    def norm(arr):
        mn = arr.min(axis=0)
        mx = arr.max(axis=0)
        rng = np.where(mx - mn > 0, mx - mn, 1)
        return (arr - mn) / rng

    geo_n = norm(geo_arr)
    # 지리 좌표: lat 높음 = row 0 (위) → y flip
    geo_n[:, 1] = 1 - geo_n[:, 1]
    pos_n = norm(pos_arr)

    # Cost matrix: cell i → position j
    cost = np.zeros((n_valid, n_valid))
    for i in range(n_valid):
        for j in range(n_valid):
            dx = geo_n[i, 0] - pos_n[j, 0]
            dy = geo_n[i, 1] - pos_n[j, 1]
            cost[i, j] = dx * dx + dy * dy

    # Hungarian assignment
    row_ind, col_ind = linear_sum_assignment(cost)

    # 새 좌표 적용
    n_changed = 0
    for i_local, j_local in zip(row_ind, col_ind):
        i_global = valid[i_local]
        new_c, new_r = positions[valid[j_local]]
        if cells[i_global]["c"] != new_c or cells[i_global]["r"] != new_r:
            n_changed += 1
        cells[i_global]["c"] = new_c
        cells[i_global]["r"] = new_r
    return n_changed


def process_election(n: int, out_suffix: str = "_v2"):
    src = GEO_DIR / f"district_hex_{n}.json"
    if not src.exists():
        print(f"  ✗ {src} 없음")
        return
    cells = json.loads(src.read_text(encoding="utf-8"))
    centers = load_sigungu_centers()
    by_sido = defaultdict(list)
    for c in cells:
        by_sido[c["sido"]].append(c)

    total_changed = 0
    print(f"\n=== {n}대 총선 ({len(cells)} 지역구) ===")
    for sido, sido_cells in sorted(by_sido.items()):
        changed = reassign_sido(sido_cells, centers)
        total_changed += changed
        print(f"  {sido:20s} {len(sido_cells):3d}구 — {changed} 변경")

    out = GEO_DIR / f"district_hex_{n}{out_suffix}.json"
    out.write_text(json.dumps(cells, ensure_ascii=False), encoding="utf-8")
    print(f"  → {out.name} ({total_changed}/{len(cells)} cell 재배치)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ns", nargs="+", type=int, help="회차 (17, 18, ..., 22)")
    ap.add_argument("--out", default="_v2", help="output suffix")
    args = ap.parse_args()
    for n in args.ns:
        process_election(n, args.out)


if __name__ == "__main__":
    main()
