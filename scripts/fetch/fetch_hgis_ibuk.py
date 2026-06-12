"""이북(개성·개풍·장단·연백) 선거구 경계 — 국사편찬위 한국근대지리정보(HGIS)에서 수집.

1·2대 총선(1948·1950)엔 38선 이남이라 ROK 영토였으나 전후 북한·DMZ가 된 지역 →
SGIS 1975(휴전선 이남)엔 없음. HGIS는 1919년 4월(1914 부군면 통폐합) 전국 부·군·면 폴리곤을
복원 제공(WGS84). 비인증 GeoJSON 엔드포인트 gisSearch.do로 군/부 폴리곤 직접 수집.
산출: data/geo/hgis_ibuk_1919.json (FeatureCollection, properties.name = 선거구 시군명).

재현: python scripts/fetch/fetch_hgis_ibuk.py
"""
import json, urllib.request, urllib.parse
from pathlib import Path
from shapely.geometry import shape, mapping

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/geo/hgis_ibuk_1919.json"
UA = "vote-via-data-research/1.0 (election history; hislab.mueller@gmail.com)"
EP = "https://hgis.history.go.kr/pro_g1/gis/gisSearch.do"

# (선거구 시군명, HGIS 검색어, 원하는 type) — 개성시=府(송도면 도심), 나머지=郡
TARGETS = [
    ("개성시", "개성", "府"),
    ("개풍군", "개풍", "郡"),
    ("장단군", "장단", "郡"),
    ("연백군", "연백", "郡"),
]


def search(kw):
    req = urllib.request.Request(
        EP, data=urllib.parse.urlencode({"keyword": kw, "mode": "hgis"}).encode(),
        headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def pick(kw, want_type):
    """lv2(부/군) + 원하는 type + 유효 geometry 중 면적 최대 feature."""
    r = search(kw)
    feats = r[0].get("features", []) if r else []
    best = None
    for f in feats:
        p = f.get("properties", {})
        if p.get("lv") != 2 or p.get("type") != want_type or not f.get("geometry"):
            continue
        g = shape(f["geometry"])
        if best is None or g.area > best[1].area:
            best = (f, g)
    return best


def main():
    out = []
    for name, kw, typ in TARGETS:
        b = pick(kw, typ)
        if not b:
            print(f"  [miss] {name} ({kw}/{typ})")
            continue
        geom = b[1]
        out.append({"type": "Feature",
                    "properties": {"name": name, "source": "HGIS 1919", "hgis_type": typ},
                    "geometry": mapping(geom)})
        bnds = geom.bounds
        print(f"  {name}: area={geom.area:.4f} bounds=({bnds[0]:.2f},{bnds[1]:.2f},{bnds[2]:.2f},{bnds[3]:.2f})")
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": out},
                              ensure_ascii=False), encoding="utf-8")
    print(f"→ {OUT.name}: {len(out)} 군/부")


if __name__ == "__main__":
    main()
