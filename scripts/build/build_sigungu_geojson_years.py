#!/usr/bin/env python3
"""지선 history 옛 회차용 — SGIS 시군구 경계(연도별)를 simplified WGS84 GeoJSON으로.

sigungu_simple.json(현재 2018 경계)과 동형: props {code, name, base_year}, MultiPolygon.
회차→연도 매핑은 geomap.ts의 LOCAL_SGG_GEO_YEAR가 사용.
  1회1995→1995  2회1998→2000(울산 광역시)  3회2002→2002  4회2006→2006  5회2010→2010  6회2014→2013(청주통합 전)

UTM-K(EPSG:5179) → WGS84(4326). 투영좌표에서 simplify(80m) 후 5자리 반올림, 미세 도서 sub-polygon 제거.
출력: data/geo/sigungu_{year}.json
"""
import json, glob, sys, re, subprocess
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
YEARS = [1975, 1980, 1985, 1990, 1995, 2000, 2002, 2006, 2010, 2013]
ENC = {1975: "cp949", 1980: "cp949", 1985: "cp949", 1990: "cp949", 1995: "cp949", 2000: "cp949", 2002: "cp949", 2006: "utf-8", 2010: "cp949", 2013: "cp949"}

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
    # SGIS 원본 오기 보정 (코드는 맞고 이름만 틀린 경우). {(year,code): 정정명}
    SGG_NAME_FIX = {
        (1985, "36460"): "나주군",   # 원본이 '춘성군'(강원) 오기 — 위치는 전남 나주(무안↔함평 사이)
    }
    # 1) raw 수집 (투영좌표 유지 — dissolve·geometric containment용)
    raw = []
    for sr in r.shapeRecords():
        rec = sr.record
        code = str(rec[ci]); name = SGG_NAME_FIX.get((year, code), rec[ni])
        if not sr.shape.points:
            continue
        g = shape(sr.shape.__geo_interface__)
        if not g.is_valid:
            g = g.buffer(0)
        if g.is_empty:
            continue
        raw.append({"code": code, "name": name, "geom": g})

    # 2) 그룹핑 — 일반구·출장소는 모도시로(이름에서 시 추출), 그 외는 자기 이름.
    #    출장소도 _parent_si로 시 그룹 생성('안양시만안출장소'→'안양시'): 기준 시 레코드 없어도
    #    출장소만으로 시가 만들어짐(1990 안양 등 누락 방지). 시 prefix 없는 출장소만 spatial fallback.
    groups = {}   # key=(시도2, 기초단체명) → {"code","name","geoms":[...]}
    outjang = []
    for it in raw:
        disp = _parent_si(it["name"])
        if it["name"].endswith("출장소") and not disp:
            outjang.append(it); continue
        disp = disp or it["name"]
        key = (it["code"][:2], disp)   # 시도(code 앞 2자리)로 동명 시군구 구분 — 중구·동구 등 시도별 분리
        gr = groups.setdefault(key, {"code": it["code"], "name": disp, "geoms": []})
        gr["geoms"].append(it["geom"])

    # 3) 시 prefix 없는 출장소(군 출장소·도서 등) → 인접 그룹에 흡수(최소거리).
    if outjang:
        merged_pre = {k: unary_union(v["geoms"]) for k, v in groups.items()}
        for it in outjang:
            host = min(merged_pre, key=lambda k: merged_pre[k].distance(it["geom"]))
            groups[host]["geoms"].append(it["geom"])

    # 4) union → island filter → WGS84 (raw, 단순화 안 함). 인접 시군구가 동/sigungu edge를
    #    정확히 공유 → mapshaper(아래)가 위상 보존 단순화로 틈 0 + 용량↓.
    feats = []
    for gr in groups.values():
        g = unary_union(gr["geoms"])
        if not g.is_valid:
            g = g.buffer(0)
        g = drop_tiny_islands(g)
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
    # mapshaper 위상 보존 단순화 — 공유 경계 함께 줄여 인접 시군구 틈 0 + 용량 ~400KB.
    _ms = ROOT / "node_modules/.bin/mapshaper"
    try:
        subprocess.run([str(_ms), str(p), "snap", "-simplify", "2%", "keep-shapes",
                        "-clean", "gap-fill-area=2km2", "-o", str(p), "force"],
                       check=True, capture_output=True, timeout=300)
    except Exception as e:
        print(f"  ⚠ mapshaper 실패: {e}", file=sys.stderr)
    print(f"{year}: {len(feats)} 시군구 → {p.name} ({round(p.stat().st_size/1e6,2)}MB)")

if __name__ == "__main__":
    ys = [int(a) for a in sys.argv[1:]] or YEARS
    for y in ys:
        build_year(y)
