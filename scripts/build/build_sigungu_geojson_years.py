#!/usr/bin/env python3
"""지선 history 옛 회차용 — SGIS 시군구 경계(연도별)를 simplified WGS84 GeoJSON으로.

sigungu_simple.json(현재 2018 경계)과 동형: props {code, name, base_year}, MultiPolygon.
회차→연도 매핑은 render-local-geo.js의 LOCAL_SGG_GEO_YEAR가 사용.
  1회1995→1995  2회1998→2000(울산 광역시)  3회2002→2002  4회2006→2006  5회2010→2010  6회2014→2013(청주통합 전)

UTM-K(EPSG:5179) → WGS84(4326). 투영좌표에서 simplify(80m) 후 5자리 반올림, 미세 도서 sub-polygon 제거.
출력: data/geo/sigungu_{year}.json
"""
import json, glob, sys, re
from pathlib import Path
import shapefile
from shapely.geometry import shape, mapping
from shapely.ops import transform as shp_transform, unary_union
from pyproj import Transformer

# 일반구·시 하위행정구역(자치구 아님) — 기초단체장은 시 단위라 시로 dissolve.
# '수원시 장안구'·'고양시일산동구'·'고양시일산동' 등 = 시 뒤에 추가 토큰이 붙은 형태.
# 자치구('종로구')·시('서귀포시'·'과천시')·군('당진군')은 매칭 안 됨(추가 토큰 없음 → standalone).
_GU_RE = re.compile(r"^(.+?시)\s*\S+$")
def _parent_si(name):
    m = _GU_RE.match(name)
    return m.group(1) if m else None

ROOT = Path(__file__).resolve().parents[2]
YEARS = [1995, 2000, 2002, 2006, 2010, 2013]
ENC = {1995: "cp949", 2000: "cp949", 2002: "cp949", 2006: "utf-8", 2010: "cp949", 2013: "cp949"}

_tf = Transformer.from_crs("EPSG:5179", "EPSG:4326", always_xy=True)
def to_wgs(geom):
    return shp_transform(lambda x, y, z=None: _tf.transform(x, y), geom)

def round_geom(geom, nd=5):
    def _r(coords):
        return [[round(x, nd), round(y, nd)] for x, y in coords]
    gj = mapping(geom)
    t = gj["type"]
    if t == "Polygon":
        gj["coordinates"] = [_r(ring) for ring in gj["coordinates"]]
    elif t == "MultiPolygon":
        gj["coordinates"] = [[_r(ring) for ring in poly] for poly in gj["coordinates"]]
    return gj

def drop_tiny_islands(geom, min_area_m2=300000):
    """투영(m) 면적 기준 미세 sub-polygon 제거 — 단, 시군구가 통째 작으면 보존(최대 1개는 유지)."""
    if geom.geom_type == "Polygon":
        return geom
    polys = sorted(geom.geoms, key=lambda p: p.area, reverse=True)
    kept = [polys[0]] + [p for p in polys[1:] if p.area >= min_area_m2]
    return unary_union(kept) if len(kept) > 1 else kept[0]

def build_year(year):
    shp = glob.glob(str(ROOT / f"data/raw/sgis/bnd_sigungu_{year}/*.shp"))
    if not shp:
        print(f"{year}: SHP 없음"); return
    r = shapefile.Reader(shp[0], encoding=ENC[year])
    fl = [f[0].lower() for f in r.fields[1:]]
    ci, ni = fl.index("sigungu_cd"), fl.index("sigungu_nm")
    # 1) raw 수집 (투영좌표 유지 — dissolve·geometric containment용)
    raw = []
    for sr in r.shapeRecords():
        rec = sr.record
        code, name = str(rec[ci]), rec[ni]
        if not sr.shape.points:
            continue
        g = shape(sr.shape.__geo_interface__)
        if not g.is_valid:
            g = g.buffer(0)
        if g.is_empty:
            continue
        raw.append({"code": code, "name": name, "geom": g})

    # 2) 그룹핑 — 일반구는 시로, 그 외는 자기 이름. 출장소는 보류(기하 포함으로 후처리).
    groups = {}   # key=기초단체명 → {"code","name","geoms":[...]}
    outjang = []
    for it in raw:
        if it["name"].endswith("출장소"):
            outjang.append(it); continue
        key = _parent_si(it["name"]) or it["name"]
        gr = groups.setdefault(key, {"code": it["code"], "name": key, "geoms": []})
        gr["geoms"].append(it["geom"])
        # 일반구 dissolve 시 시도2 코드만 유지되면 됨 — 첫 code 사용

    # 3) 출장소 → 인접 그룹에 병합. 출장소는 시군구에서 카브아웃된 별도 폴리곤이라 contains 실패 →
    #    최소거리(인접=거리0) 그룹에 흡수.
    merged_pre = {k: unary_union(v["geoms"]) for k, v in groups.items()}
    for it in outjang:
        host = min(merged_pre, key=lambda k: merged_pre[k].distance(it["geom"]))
        groups[host]["geoms"].append(it["geom"])

    # 4) union → simplify → island filter → WGS84
    feats = []
    for gr in groups.values():
        g = unary_union(gr["geoms"])
        if not g.is_valid:
            g = g.buffer(0)
        g = drop_tiny_islands(g)
        g = g.simplify(80, preserve_topology=True)   # 투영(m) 단위
        if g.is_empty:
            continue
        feats.append({
            "type": "Feature",
            "properties": {"code": gr["code"], "name": gr["name"], "base_year": str(year)},
            "geometry": round_geom(to_wgs(g), 5),
        })
    out = {"type": "FeatureCollection", "features": feats}
    p = ROOT / f"data/geo/sigungu_{year}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"{year}: {len(feats)} 시군구 → {p.name} ({round(p.stat().st_size/1e6,2)}MB)")

if __name__ == "__main__":
    ys = [int(a) for a in sys.argv[1:]] or YEARS
    for y in ys:
        build_year(y)
