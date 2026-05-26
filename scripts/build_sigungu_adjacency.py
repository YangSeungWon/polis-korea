"""시군구 polygon 인접 ground truth 생성 (한 번만).

각 시군구 polygon 쌍에 대해 shapely로 touches/intersects 검사.
결과를 data/geo/sigungu_adjacency.json에 저장 — eval에서 ground truth로 사용.

옹진군 같은 outlier 섬은 본토 시군구와 안 닿지만 같은 시도라서 cluster상 인접 필요.
시도 내 시군구는 모두 인접 (sido cluster connectivity 보장 위해)으로 추가.
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _geo import sigungu_to_sido, SIGUNGU_SIDO_OVERRIDE

from shapely.geometry import shape, Polygon, MultiPolygon
from shapely.strtree import STRtree


def safe_shape(geometry):
    """ring < 4 좌표 polygon (작은 섬) 제외하고 shape 생성."""
    t = geometry["type"]
    coords = geometry["coordinates"]
    if t == "Polygon":
        rings = [r for r in coords if len(r) >= 4]
        if not rings:
            return None
        return Polygon(rings[0], rings[1:])
    if t == "MultiPolygon":
        polys = []
        for poly in coords:
            rings = [r for r in poly if len(r) >= 4]
            if rings:
                polys.append(Polygon(rings[0], rings[1:]))
        if not polys:
            return None
        return MultiPolygon(polys) if len(polys) > 1 else polys[0]
    return shape(geometry)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "geo" / "sigungu_simple.json"
OUT = ROOT / "data" / "geo" / "sigungu_adjacency.json"


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    features = data["features"]

    codes = []
    geoms = []
    name_by_code = {}
    sido_by_code = {}
    for feat in features:
        props = feat["properties"]
        code = props["code"]
        sido = sigungu_to_sido(code)
        if not sido:
            continue
        g = safe_shape(feat["geometry"])
        if g is None or g.is_empty:
            continue
        codes.append(code)
        geoms.append(g)
        name_by_code[code] = props["name"]
        sido_by_code[code] = sido

    print(f"검사 시작: {len(codes)} 시군구")

    # 공간 인덱스로 빠른 검색
    tree = STRtree(geoms)
    adj_pairs = set()
    for i, geom in enumerate(geoms):
        # 근접 후보들
        candidates = tree.query(geom.buffer(0.01))  # 약간 buffer
        for j in candidates:
            if i >= j:
                continue
            other = geoms[j]
            if geom.touches(other) or geom.intersects(other):
                pair = tuple(sorted([codes[i], codes[j]]))
                adj_pairs.add(pair)
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(codes)}")

    # 시도별 cluster: 같은 시도 시군구가 polygon 인접 안 해도 시도 cluster 안에선 인접 보장 필요
    # 그건 따로 처리 (eval에서). adjacency.json은 진짜 polygon 인접만.

    # 출력
    out = {
        "_meta": {
            "source": "sigungu_simple.json polygon touches/intersects",
            "n_sigungu": len(codes),
            "n_pairs": len(adj_pairs),
        },
        "pairs": [
            {"a": a, "b": b, "a_name": name_by_code[a], "b_name": name_by_code[b],
             "a_sido": sido_by_code[a], "b_sido": sido_by_code[b]}
            for a, b in sorted(adj_pairs)
        ],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n인접 쌍 {len(adj_pairs)}건 → {OUT.relative_to(ROOT)}")

    # 같은 시도 vs 다른 시도 분포
    same = sum(1 for a, b in adj_pairs if sido_by_code[a] == sido_by_code[b])
    cross = len(adj_pairs) - same
    print(f"  같은 시도 내 인접: {same}")
    print(f"  시도 경계 (다른 시도 간) 인접: {cross}")


if __name__ == "__main__":
    main()
