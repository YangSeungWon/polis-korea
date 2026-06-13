#!/usr/bin/env python3
"""현행 시군구 경계 — SGIS 행정동(bnd_dong_YYYY)을 시군구로 dissolve + 80m simplify.

sigungu_simple.json(2018, 폴리곤당 ~30정점 과단순화) 대신 19~21대 대선 지도용 상세 경계.
다른 연도 파일(sigungu_2002~2013, 80m·100~200정점)과 동형. props {code,name,base_year}.

방식: 동 centroid를 sigungu_simple 250유닛에 공간매칭 → 그 시-단위 code·name 부여(일반구는
시로 dissolve, 코드변경[군위 등]도 위치로 흡수) → 같은 250유닛을 상세 geometry로 재구성.

사용: python scripts/build/build_sigungu_recent.py 2025
출력: data/geo/sigungu_{year}.json
"""
import json, sys, subprocess
from pathlib import Path
import shapefile
from shapely.geometry import shape, mapping, Point
from shapely.ops import transform as shp_transform, unary_union
from shapely.strtree import STRtree
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"
_to_wgs = Transformer.from_crs("EPSG:5179", "EPSG:4326", always_xy=True)


def round_geom(geom, nd=5):
    def _r(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], nd), round(c[1], nd)]
        return [_r(x) for x in c]
    g = mapping(geom)
    g["coordinates"] = _r(g["coordinates"])
    return g


def build(year, tol=200):
    shp = ROOT / f"data/raw/sgis/bnd_dong_{year}/bnd_dong_00_{year}_2Q.shp"
    if not shp.exists():
        cand = list((ROOT / f"data/raw/sgis/bnd_dong_{year}").glob("*.shp"))
        shp = cand[0] if cand else shp
    r = shapefile.Reader(str(shp), encoding="utf-8")
    flds = [f[0] for f in r.fields[1:]]
    ci = flds.index("ADM_CD")

    # sigungu_simple 250 시-유닛 (WGS84) — 공간매칭 기준
    simple = json.loads((GEO / "sigungu_simple.json").read_text(encoding="utf-8"))
    feats = simple.get("features", simple)
    shapes = [shape(f["geometry"]) for f in feats]
    props = [f["properties"] for f in feats]
    tree = STRtree(shapes)

    # 동 geometry(5179)를 시-단위로 묶기
    by_unit = {}    # simple idx → [shapely geom(5179)]
    miss = 0
    for sr, rec in zip(r.shapes(), r.records()):
        g5179 = shape(sr.__geo_interface__)
        if g5179.is_empty:
            continue
        cen = g5179.representative_point()
        lon, lat = _to_wgs.transform(cen.x, cen.y)
        p = Point(lon, lat)
        idx = None
        for i in tree.query(p):
            if shapes[i].contains(p):
                idx = int(i); break
        if idx is None:                      # 경계 밖(섬 등) — 최근접 유닛
            idx = min(range(len(shapes)), key=lambda i: shapes[i].distance(p))
            miss += 1
        by_unit.setdefault(idx, []).append(g5179)

    out = []
    for idx, geoms in by_unit.items():
        merged = unary_union(geoms)
        if not merged.is_valid:
            merged = merged.buffer(0)
        wgs = shp_transform(lambda x, y, z=None: _to_wgs.transform(x, y), merged)
        out.append({
            "type": "Feature",
            "properties": {"code": props[idx]["code"], "name": props[idx]["name"], "base_year": str(year)},
            "geometry": round_geom(wgs),
        })
    op = GEO / f"sigungu_{year}.json"
    op.write_text(json.dumps({"type": "FeatureCollection", "features": out}, ensure_ascii=False, separators=(",", ":")))
    # mapshaper 위상 보존 단순화 — 연도파일과 동일(공유 경계 함께 줄여 틈 0 + 용량↓).
    _ms = ROOT / "node_modules/.bin/mapshaper"
    subprocess.run([str(_ms), str(op), "snap", "-simplify", "0.6%", "keep-shapes",
                    "-clean", "gap-fill-area=2km2", "-o", str(op), "force"],
                   check=True, capture_output=True, timeout=300)
    print(f"{year}: {len(out)}유닛, 경계밖동 {miss}, → {op.name} ({round(op.stat().st_size/1e6,2)}MB)")


if __name__ == "__main__":
    for y in (sys.argv[1:] or ["2025"]):
        build(int(y))
