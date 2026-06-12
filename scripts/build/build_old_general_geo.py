"""옛 총선(1~7대) 지리적 지도 — SGIS 1975 시군 경계 union으로 선거구 경계 근사.

선거구의 시군을 SGIS 1975 시군 폴리곤(가장 오래된 보유본, UTM-K 5179)에 매핑해
unary_union으로 경계를 합성. 1975는 1954~71 선거에 가장 가까운 행정구역 — 대구·인천·광주는
아직 도(경북·경기·전남) 소속, 옛 군명(옥구·선산·월성 등)도 1995 통폐합 전이라 직접 매칭됨.
8대는 build_district_geojson.py(SGIS 1975)가 별도 생성.

 - 3·4·5대: 별표 통합으로 race['sigungu_area']=[시군] 보유 → 직접 사용.
 - 1·2·6·7대: 선거구명 괄호 '제N선거구(중구)'에서 시군 파싱.

대도시(부산·대구·인천·광주·대전)는 1975에 구/출장소로 분할 → 시 전체 union.
동명 구(서울/부산 중구 등)는 시도 code(11·21·31~39, 37=대구포함경북)로 disambiguate.
ALIAS_1975: 1955~56 시승격 개명(강릉군→명주군 등) 환원. 이북·DMZ는 매칭 없어 skip.

한계: 도시 갑/을/병 다선거구는 같은 시군 폴리곤에 중첩 → 지도엔 최상위 1개만 표시(hex 정본).
재현: python scripts/build/build_old_general_geo.py
"""
import json, re
from pathlib import Path
import shapefile  # pyshp
from shapely.geometry import shape, mapping
from shapely.ops import unary_union, transform as shp_transform
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"
RES = ROOT / "data/results"
SHP = ROOT / "data/raw/sgis/bnd_sigungu_1975/bnd_sigungu_00_1975_4Q.shp"

_tr = Transformer.from_crs(5179, 4326, always_xy=True)

# name -> [(code, shape)],  code 앞2자리 = 시도(11서울 21부산 31경기 32강원 33충북
# 34충남 35전북 36전남 37경북 38경남 39제주; 대구∈37·인천∈31·광주∈36·대전∈34)
POLY = {}
_REC = []  # (code, name, shape) 전체
_sf = shapefile.Reader(str(SHP), encoding="cp949")
for sr in _sf.shapeRecords():
    nm = sr.record["sigungu_nm"]
    cd = str(sr.record["sigungu_cd"])
    g = shp_transform(lambda x, y, z=None: _tr.transform(x, y), shape(sr.shape.__geo_interface__))
    POLY.setdefault(nm, []).append((cd, g))
    _REC.append((cd, nm, g))

CANON = {"전라북도": "전북특별자치도", "강원도": "강원특별자치도", "제주도": "제주특별자치도"}
DECANON = {"강원특별자치도": "강원도", "전북특별자치도": "전라북도", "제주특별자치도": "제주도"}
SIDO_CODE = {"서울특별시": "11", "부산직할시": "21", "경기도": "31", "강원도": "32",
             "충청북도": "33", "충청남도": "34", "전라북도": "35", "전라남도": "36",
             "경상북도": "37", "경상남도": "38", "제주도": "39"}
METRO_CODE = {"서울": "11", "부산": "21", "대구": "37", "인천": "31", "광주": "36", "대전": "34"}
CITY_WHOLE = {"부산시", "대구시", "인천시", "광주시", "대전시"}  # 1975 분할 → 시 전체 union
# 1954~60 시군명 → 1975 시군명(들). 1955~56 시승격 개명·1962 통폐합 반영.
ALIAS = {"강릉군": ["명주군"], "경주군": ["월성군"], "원주군": ["원성군"], "충주군": ["중원군"],
         "천안군": ["천안시", "천원군"], "울산군": ["울산시", "울주군"], "부천군": ["부천시"],
         "동래군": ["동래구"], "김화군": ["철원군"], "영원군": ["영월군"],
         "옥구군": ["옥구군"]}  # 옥구는 1975 존재(자기자신) — 1995 alias 무효화


def city_whole(city):
    if city == "부산시":
        return [g for (c, n, g) in _REC if c.startswith("21")]
    if city == "대전시":
        return [g for (c, n, g) in _REC if c.startswith("3401")]  # 동/북/중/서부출장소
    pre = city[:-1]  # 대구/인천/광주
    return [g for (c, n, g) in _REC if n.startswith(pre + "시")]


def pick(name, codepref):
    cand = POLY.get(name)
    if not cand:  # 앞2글자 prefix fallback
        for k, lst in POLY.items():
            if k[:2] == name[:2]:
                cand = lst
                break
    if not cand:
        return []
    if len(cand) == 1:
        return [cand[0][1]]
    match = [g for (c, g) in cand if codepref and c.startswith(codepref)]
    return match or [cand[0][1]]


def resolve(race_sido, sgg):
    sgg = sgg.strip()
    if sgg in CITY_WHOLE:
        return city_whole(sgg)
    m = re.match(r"(부산시|대구시|인천시|광주시|대전시)\s+(\S+)", sgg)  # '부산시 동구'
    if m:
        return pick(m.group(2), METRO_CODE[m.group(1)[:2]])
    if sgg in ALIAS:
        out = []
        for t in ALIAS[sgg]:
            out += city_whole(t) if t in CITY_WHOLE else pick(t, None)
        return out
    return pick(sgg, SIDO_CODE.get(DECANON.get(race_sido, race_sido)))


def sggs_of(name):
    m = re.search(r"[(（](.+?)[)）]", name)
    if not m:
        return []
    return [re.sub(r"\s*[갑을병정무]\s*구?$", "", s.strip()) for s in re.split(r"[·,.]", m.group(1))]


def build(n):
    d = json.loads((RES / f"national_assembly_{n}.json").read_text(encoding="utf-8"))["district"]
    feats, nmap, skipped, miss = [], {}, 0, []
    for r in d:
        sggs = r.get("sigungu_area") or sggs_of(r["name"])
        polys = []
        for s in sggs:
            polys += resolve(r["sido"], s)
        if not polys:
            skipped += 1
            miss.append((r["sido"], r["name"], sggs))
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
    print(f"{n}대: {len(feats)} feature, skip {skipped} {miss if miss else ''}")


if __name__ == "__main__":
    for n in (1, 2, 3, 4, 5, 6, 7):
        build(n)
