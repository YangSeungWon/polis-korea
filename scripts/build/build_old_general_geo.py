"""옛 총선(1·2·3·4·5·6·7대) 지리적 지도 — 1995 시군구 폴리곤 union으로 선거구 경계 근사.

정확한 당시 선거구 획정 별표가 없거나(1·2·6·7대) 동 단위라(3·4·5대), 선거구의 시군을
1995년 시군구 폴리곤에 매핑해 unary_union으로 경계를 합성.
 - 3·4·5대: 별표 통합으로 race['sigungu_area']=[시군] 보유 → 직접 사용.
 - 1·2·6·7대: 선거구명 괄호 '제N선거구(중구)'에서 시군 파싱.

1995 시군구 name은 모호('중구'가 5개 시·도) → code 앞2자리(시도)로 disambiguate.
대도시(대구시·부산시·인천시·대전시·광주시)는 1995엔 구로만 존재 → 광역시 구 전체 union.
통폐합 시군은 ALIAS 환원, 이북·DMZ(개성·연백·장단·개풍)는 skip.

한계: 도시 갑/을/병 다선거구는 같은 시군 폴리곤에 중첩 → 지도엔 최상위 1개만 표시(hex 정본).
재현: python scripts/build/build_old_general_geo.py
"""
import json, re
from pathlib import Path
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"
RES = ROOT / "data/results"

POLY = {}  # name -> [(code, shape)]
for f in json.loads((GEO / "sigungu_1995.json").read_text(encoding="utf-8"))["features"]:
    p = f["properties"]
    POLY.setdefault(p["name"], []).append((str(p["code"]), shape(f["geometry"])))

ALIAS = {"옥구군": "군산시", "선산군": "구미시", "월성군": "경주시", "연일군": "포항시",
         "영일군": "포항시", "명주군": "강릉시", "원성군": "원주시", "천원군": "천안시",
         "천안군": "천안시", "춘성군": "춘천시", "금릉군": "김천시", "중원군": "충주시",
         "충주군": "충주시", "진양군": "진주시", "삼천포시": "사천시", "충무시": "통영시",
         "승주군": "순천시", "울주군": "울산시", "울산군": "울산시", "이리시": "익산시",
         "대덕군": "대전시", "원주군": "원주시", "강릉군": "강릉시", "달성군": "달성군",
         "영원군": "영월군", "김화군": "철원군"}  # 영원군=위키 오타, 김화군 1962 철원 흡수
SKIP = {"개성시", "개풍군", "연백군", "장단군"}
CANON = {"전라북도": "전북특별자치도", "강원도": "강원특별자치도", "제주도": "제주특별자치도"}
DECANON = {"강원특별자치도": "강원도", "전북특별자치도": "전라북도", "제주특별자치도": "제주도"}
# 1995 시군구 파일 code 앞2자리 (구 행정자치부 체계: 11·21~25 광역시, 31~39 도)
SIDO_CODE = {"서울특별시": "11", "경기도": "31", "강원도": "32", "충청북도": "33",
             "충청남도": "34", "전라북도": "35", "전라남도": "36", "경상북도": "37",
             "경상남도": "38", "제주도": "39"}
# 옛 시·도에 포함됐던 대도시 → 1995 광역시 code
METRO = {"서울": "11", "부산": "21", "대구": "22", "인천": "23", "광주": "24", "대전": "25"}


def metro_union(code2):
    return [s for lst in POLY.values() for (c, s) in lst if c.startswith(code2)]


def resolve(race_sido, sgg):
    """선거구의 시군 1개 → 폴리곤 리스트(대도시는 구 union)."""
    sgg = ALIAS.get(sgg, sgg)
    if sgg in SKIP:
        return []
    base = sgg[:-1] if sgg.endswith("시") else sgg
    # 대도시 whole-city (1995엔 시 단위 폴리곤 없음) → 광역시 구 union
    if base in METRO and sgg not in POLY:
        return metro_union(METRO[base])
    cand = POLY.get(sgg)
    if not cand:  # 앞2글자 prefix fallback
        for k, lst in POLY.items():
            if k[:2] == sgg[:2]:
                cand = lst
                break
    if not cand:
        return []
    if len(cand) == 1:
        return [cand[0][1]]
    # 동명(중구 등) → race 시도 code로 선택. 대도시 구는 해당 광역시 code.
    pref = METRO.get(base) or SIDO_CODE.get(DECANON.get(race_sido, race_sido))
    match = [s for (c, s) in cand if pref and c.startswith(pref)]
    return match or [cand[0][1]]


def sggs_of(name):
    m = re.search(r"[(（](.+?)[)）]", name)
    if not m:
        return []
    return [re.sub(r"\s*[갑을병정무]\s*구?$", "", s.strip()) for s in re.split(r"[·,.]", m.group(1))]


def build(n):
    d = json.loads((RES / f"national_assembly_{n}.json").read_text(encoding="utf-8"))["district"]
    feats, nmap, skipped = [], {}, 0
    for r in d:
        sggs = r.get("sigungu_area") or sggs_of(r["name"])
        polys = []
        for s in sggs:
            polys += resolve(r["sido"], s)
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
    for n in (1, 2, 3, 4, 5, 6, 7):
        build(n)
