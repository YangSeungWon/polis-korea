#!/usr/bin/env python3
"""sigungu_2026.json — 9회 지선(2026)용. sigungu_2025 + 인천 2026-07 개편 반영.

9회 데이터는 개편 후(제물포구·영종구·검단구·서구)인데 SGIS 2025-2Q 경계는 개편 전(중구·동구·서구).
bnd_dong_2025의 인천 동을 개편 구로 dissolve해 4개 폴리곤을 만들고 sigungu_2025의 중구·동구·서구를 교체.

영종구=중구 영종도, 제물포구=중구 육지+동구, 검단구=서구 검단일대, 서구=서구 나머지.
"""
import json, subprocess
from pathlib import Path
import shapefile
from shapely.geometry import shape, mapping
from shapely.ops import transform as shp_transform, unary_union
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"
_to_wgs = Transformer.from_crs("EPSG:5179", "EPSG:4326", always_xy=True)

# 동명 → 개편 구 (인천 중구23010·동구23020·서구23080)
YEONGJONG = {"용유동", "운서동", "영종동", "영종1동", "영종2동"}
GEOMDAN = {"검단동", "불로대곡동", "오류왕길동", "당하동", "마전동", "원당동", "아라동"}


def assign(code5, nm):
    if code5 == "23010":
        return ("23012", "영종구") if nm in YEONGJONG else ("23011", "제물포구")
    if code5 == "23020":
        return ("23011", "제물포구")
    if code5 == "23080":
        return ("23081", "검단구") if nm in GEOMDAN else ("23080", "서구")
    return None


def round_geom(geom, nd=5):
    def _r(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], nd), round(c[1], nd)]
        return [_r(x) for x in c]
    g = mapping(geom); g["coordinates"] = _r(g["coordinates"]); return g


def main():
    r = shapefile.Reader(str(ROOT / "data/raw/sgis/bnd_dong_2025/bnd_dong_00_2025_2Q.shp"), encoding="utf-8")
    fl = [f[0] for f in r.fields[1:]]; ci = fl.index("ADM_CD"); ni = fl.index("ADM_NM")
    groups = {}   # (code,name) → [geom 5179]
    for sr in r.shapeRecords():
        rec = sr.record; code = str(rec[ci]); a = assign(code[:5], rec[ni])
        if not a:
            continue
        groups.setdefault(a, []).append(shape(sr.shape.__geo_interface__))
    new = []
    for (code, name), geoms in groups.items():
        g = unary_union(geoms)
        if not g.is_valid:
            g = g.buffer(0)
        wgs = shp_transform(lambda x, y, z=None: _to_wgs.transform(x, y), g)
        new.append({"type": "Feature",
                    "properties": {"code": code, "name": name, "base_year": "2026"},
                    "geometry": round_geom(wgs)})
    print("개편 폴리곤:", sorted(f["properties"]["name"] for f in new))
    # 개편 4폴리곤만 mapshaper 0.6%(2025와 동일 디테일) — 2025 본체는 이미 단순화돼 재처리 금지.
    _ms = ROOT / "node_modules/.bin/mapshaper"
    tmp = GEO / "_inc2026_tmp.json"
    tmp.write_text(json.dumps({"type": "FeatureCollection", "features": new}, ensure_ascii=False, separators=(",", ":")))
    subprocess.run([str(_ms), str(tmp), "snap", "-simplify", "0.6%", "keep-shapes",
                    "-clean", "gap-fill-area=2km2", "-o", str(tmp), "force"],
                   check=True, capture_output=True, timeout=300)
    new = json.loads(tmp.read_text(encoding="utf-8"))["features"]
    tmp.unlink()

    base = json.loads((GEO / "sigungu_2025.json").read_text(encoding="utf-8"))
    DROP = {"23010", "23020", "23080"}   # 개편 전 중구·동구·서구 제거
    feats = [f for f in base["features"] if str(f["properties"]["code"]) not in DROP] + new
    op = GEO / "sigungu_2026.json"
    op.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(feats)}유닛 → {op.name} ({round(op.stat().st_size/1e6,2)}MB)")


if __name__ == "__main__":
    main()
