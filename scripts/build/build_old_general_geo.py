"""옛 총선(1·2·6·7대) 지리적 지도 — 1995 시군 폴리곤 union으로 선거구 경계 근사.

정확한 당시 선거구 획정 별표가 없으므로, 선거구명의 시군(예 '제1선거구(중구)')을 1995년
시군 폴리곤에 매핑해 `unary_union`으로 선거구 경계를 합성. 통폐합 시군은 ALIAS로 환원.
산출: data/geo/district_{n}_geojson.json (+ _map.json: "시도|선거구명" → SGG_Code).

한계:
- 도시 갑/을/병 다선거구는 같은 시군 폴리곤에 중첩 → 지도엔 최상위 1개만 표시(hex가 정본).
- 3·4·5대(전부 '제N선거구')·6·7대 대도시('제N지역구')는 시군명이 없어 geo 불가 → skip.
- 이북·DMZ(개성·연백·장단·개풍)는 1995 경계에 없어 skip.

사용: python scripts/build/build_old_general_geo.py
"""
import json, re
from pathlib import Path
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"
RES = ROOT / "data/results"

POLY = {}
for f in json.loads((GEO / "sigungu_1995.json").read_text(encoding="utf-8"))["features"]:
    POLY.setdefault(f["properties"]["name"], []).append(shape(f["geometry"]))

# 옛 시군명 → 1995 시군명 (통폐합·개명)
ALIAS = {"옥구군": "군산시", "선산군": "구미시", "월성군": "경주시", "연일군": "포항시",
         "영일군": "포항시", "명주군": "강릉시", "원성군": "원주시", "천원군": "천안시",
         "춘성군": "춘천시", "금릉군": "김천시", "중원군": "충주시", "진양군": "진주시",
         "삼천포시": "사천시", "충무시": "통영시", "승주군": "순천시", "울주군": "울산시",
         "이리시": "익산시", "대덕군": "대전시"}
SKIP = {"개성시", "개풍군", "연백군", "장단군"}  # 이북·DMZ
CANON = {"전라북도": "전북특별자치도", "강원도": "강원특별자치도", "제주도": "제주특별자치도"}


def find_poly(nm):
    nm = ALIAS.get(nm, nm)
    if nm in POLY:
        return POLY[nm]
    for k in POLY:  # 앞 2글자 prefix fallback (시/군 접미 차이)
        if k[:2] == nm[:2]:
            return POLY[k]
    return None


def sggs(name):
    m = re.search(r"[(（](.+?)[)）]", name)
    if not m:
        return []
    return [re.sub(r"\s*[갑을병정무]\s*구?$", "", s.strip()) for s in re.split(r"[·,.]", m.group(1))]


def build(n):
    d = json.loads((RES / f"national_assembly_{n}.json").read_text(encoding="utf-8"))["district"]
    feats, nmap, skipped = [], {}, 0
    for r in d:
        polys = []
        for s in sggs(r["name"]):
            if s in SKIP:
                continue
            p = find_poly(s)
            if p:
                polys += p
        if not polys:
            skipped += 1
            continue
        code = f"G{n}_{len(feats):03d}"
        sido = CANON.get(r["sido"], r["sido"])
        feats.append({"type": "Feature",
                      "properties": {"SGG_Code": code, "SGG": r["name"], "SIDO": sido},
                      "geometry": mapping(unary_union(polys))})
        nmap[f'{sido}|{r["name"]}'] = code
    (GEO / f"district_{n}_geojson.json").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), encoding="utf-8")
    (GEO / f"district_{n}_geojson_map.json").write_text(
        json.dumps({"name_to_sgg_code": nmap}, ensure_ascii=False), encoding="utf-8")
    print(f"{n}대: {len(feats)} feature, skip {skipped}")


if __name__ == "__main__":
    for n in (1, 2, 6, 7):
        build(n)
