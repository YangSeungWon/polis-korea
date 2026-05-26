"""시군구 해안/내륙 분류 ground truth.

한국 전체 polygon union → boundary가 곧 해안선.
각 시군구 polygon이 그 해안선과 충분히 닿으면 해안.

출력: data/geo/sigungu_coastal.json
"""
from __future__ import annotations
import json
from pathlib import Path
from shapely.geometry import shape, Polygon, MultiPolygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "geo" / "sigungu_simple.json"
OUT = ROOT / "data" / "geo" / "sigungu_coastal.json"


def safe_shape(g):
    t = g["type"]; coords = g["coordinates"]
    if t == "Polygon":
        rings = [r for r in coords if len(r) >= 4]
        return Polygon(rings[0], rings[1:]) if rings else None
    if t == "MultiPolygon":
        polys = []
        for poly in coords:
            rings = [r for r in poly if len(r) >= 4]
            if rings:
                polys.append(Polygon(rings[0], rings[1:]))
        return MultiPolygon(polys) if len(polys) > 1 else (polys[0] if polys else None)
    return shape(g)


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    features = data["features"]

    codes = []; geoms = []
    name_by_code = {}
    for feat in features:
        code = feat["properties"]["code"]
        g = safe_shape(feat["geometry"])
        if g is None or g.is_empty:
            continue
        if not g.is_valid:
            g = g.buffer(0)
        codes.append(code)
        geoms.append(g)
        name_by_code[code] = feat["properties"]["name"]

    print("union 계산 중...")
    korea = unary_union(geoms)
    coast = korea.boundary
    print(f"전체 해안선 길이: {coast.length:.1f}")

    coastal = {}
    for i, geom in enumerate(geoms):
        inter = geom.boundary.intersection(coast)
        length = inter.length if not inter.is_empty else 0
        # threshold: boundary 중 20% 이상이 해안과 닿으면 해안 시군구
        ratio = length / geom.boundary.length if geom.boundary.length else 0
        coastal[codes[i]] = ratio > 0.20

    n_coastal = sum(1 for v in coastal.values() if v)
    print(f"해안 시군구: {n_coastal}/{len(coastal)}")

    out = {
        "_meta": {"n": len(coastal), "n_coastal": n_coastal},
        "coastal": [{"code": c, "name": name_by_code[c]} for c in codes if coastal[c]],
        "inland":  [{"code": c, "name": name_by_code[c]} for c in codes if not coastal[c]],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
