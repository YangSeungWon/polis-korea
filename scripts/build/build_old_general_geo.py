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
from shapely.geometry import shape, mapping, MultiPoint
from shapely.ops import unary_union, transform as shp_transform, voronoi_diagram
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"
RES = ROOT / "data/results"
SHP = ROOT / "data/raw/sgis/bnd_sigungu_1975/bnd_sigungu_00_1975_4Q.shp"
DONG_SHP = ROOT / "data/raw/sgis/bnd_dong_1975/bnd_dong_00_1975_4Q.shp"

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

# 1975 읍면동 — 농촌 군 갑/을 분할용. canon key -> [(code, shape)]
def canon_dong(nm):
    nm = nm.strip().replace("·", ",").replace(" ", "")
    m = re.match(r"^(.+?)(\d[\d,]*)가동?$", nm)  # 동인1,2가동 → {동인1가,동인2가}
    if m:
        base = re.sub(r"동$", "", m.group(1))
        return [f"{base}{d}가" for d in re.findall(r"\d+", m.group(2))]
    return [re.sub(r"동$", "", nm)]  # 봉산동→봉산, 안계면=안계면, 교동→교


DONG = {}
_dsf = shapefile.Reader(str(DONG_SHP), encoding="cp949")
for sr in _dsf.shapeRecords():
    cd = str(sr.record["adm_dr_cd"])
    g = shp_transform(lambda x, y, z=None: _tr.transform(x, y), shape(sr.shape.__geo_interface__))
    for k in canon_dong(sr.record["adm_dr_nm"]):
        DONG.setdefault(k, []).append((cd, g))


def parse_area_tokens(area, sigungu):
    """선거구역 텍스트 → canon dong key 리스트. 시군 prefix 제거, 콤마 분할,
    '동인동1,2,3,4가'처럼 콤마로 끊긴 가-리스트는 직전 동 base에 붙여 재구성."""
    for s in sigungu:
        area = area.replace(s, "", 1)
    raw = [t.strip() for t in re.split(r"[,，]", area) if t.strip()]
    toks, base = [], None
    for t in raw:
        if re.match(r"^\d+가?$", t) and base:        # 순수 숫자(2 / 4가) → 직전 동 base
            toks.append(f"{base}{re.sub('[^0-9]', '', t)}가")
            continue
        m = re.match(r"^(.+?)(\d+)가$", t)            # 동인동1가 / 동성로3가
        if m and m.group(1)[-1:] not in "면읍리":
            base = re.sub(r"동$", "", m.group(1))
            toks.append(f"{base}{m.group(2)}가")
        else:
            base = None
            toks.append(t)
    out = []
    for t in toks:
        out += canon_dong(t)
    return out


def dong_union(race_sido, tokens):
    """동/면 토큰 → (매칭 폴리곤들, 매칭률). 시도 code로 동명 disambiguate."""
    pref = SIDO_CODE.get(DECANON.get(race_sido, race_sido))
    polys, hit = [], 0
    for t in tokens:
        cand = DONG.get(t)
        if not cand and t.endswith("읍"):  # 안동읍 등 1963 시승격 → 시 폴리곤
            cand = POLY.get(t[:-1] + "시")
        if not cand:
            continue
        sel = [g for (c, g) in cand if pref and c.startswith(pref)] or [cand[0][1]]
        polys += sel
        hit += 1
    ratio = hit / len(tokens) if tokens else 0
    return polys, ratio


# 이북(개성·개풍·장단·연백) — SGIS 1975(휴전선 이남)에 없어 HGIS 1919(38선 이남 ROK)에서 보강
IBUK = {}
_ip = ROOT / "data/geo/hgis_ibuk_1919.json"
if _ip.exists():
    for f in json.loads(_ip.read_text(encoding="utf-8")).get("features", []):
        IBUK[f["properties"]["name"]] = shape(f["geometry"])

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
    if sgg in IBUK:  # 이북 — HGIS 1919 폴리곤
        return [IBUK[sgg]]
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


def mechanical_split(geom, k):
    """경계자료 없는 분할 — 긴 축 따라 등면적 k조각으로 기계 절단(임의·추정)."""
    from shapely.geometry import box
    minx, miny, maxx, maxy = geom.bounds
    vert = (maxx - minx) >= (maxy - miny)  # 가로가 길면 세로 절단(동서)
    lo, hi = (minx, maxx) if vert else (miny, maxy)
    total = geom.area
    cuts = [lo]
    for j in range(1, k):
        target = total * j / k
        a, b = cuts[-1], hi
        for _ in range(40):  # 누적면적 = target 되는 절단선 이분탐색
            c = (a + b) / 2
            strip = box(minx, miny, c, maxy) if vert else box(minx, miny, maxx, c)
            if geom.intersection(strip).area < target:
                a = c
            else:
                b = c
        cuts.append((a + b) / 2)
    cuts.append(hi)
    pieces = []
    for j in range(k):
        strip = (box(minx, miny, cuts[j + 1], maxy) if vert
                 else box(minx, miny, maxx, cuts[j + 1]))
        prev = (box(minx, miny, cuts[j], maxy) if vert
                else box(minx, miny, maxx, cuts[j]))
        pieces.append(geom.intersection(strip).difference(prev))
    return pieces


def gabeul_idx(name):
    m = re.search(r"[갑을병정무기]", name)
    return "갑을병정무기".index(m.group()) if m else 0


def is_city_group(sido, sggs):
    """도시(서울 구·광역시) 분할 그룹 — 동 변동 커 시군 단위로 폴백되는 대상."""
    return sido == "서울특별시" or any(
        s in CITY_WHOLE or re.match(r"(부산시|대구시|인천시|광주시|대전시)", s) for s in sggs)


def voronoi_split(races, sido, sggs, area_by, n, hgis_pts):
    """도시 갑/을 — 별표 동을 1975 동 점으로 찍어 보로노이로 구 폴리곤을 근사 분할.
    1975 동 점0인 선거구는 HGIS 1919 동리 점으로 보충. 반환 [(race, geom)...] 또는 None(폴백).
    경계는 추정(approx)."""
    from shapely.geometry import Point
    container = unary_union([g for s in sggs for g in resolve(sido, s)])
    if container.is_empty:
        return None
    pts, owner = [], []
    for i, r in enumerate(races):
        area = r.get("area") or area_by.get(r["name"], "")
        polys, _ = dong_union(sido, parse_area_tokens(area, sggs)) if area else ([], 0)
        rp = [p.representative_point() for p in polys]
        rp = [p for p in rp if container.contains(p)]
        if not rp:  # 1975 점0 → HGIS 보충
            rp = [Point(lon, lat) for lon, lat in hgis_pts.get(f"{n}|{r['name']}", [])
                  if container.contains(Point(lon, lat))]
        for p in rp:
            pts.append(p); owner.append(i)
    if len(set(owner)) < len(races) or len(pts) < 2:
        return None  # 모든 선거구가 동 점을 못 가지면 근사 불가 → 시군 폴백
    cells = list(voronoi_diagram(MultiPoint(pts), envelope=container).geoms)
    race_cells = [[] for _ in races]
    for cell in cells:
        for j, pt in enumerate(pts):
            if cell.contains(pt):
                race_cells[owner[j]].append(cell)
                break
    out = []
    for i, r in enumerate(races):
        if not race_cells[i]:
            return None
        g = unary_union(race_cells[i]).intersection(container)
        if g.is_empty:
            return None
        out.append((r, g))
    return out


def build(n):
    d = json.loads((RES / f"national_assembly_{n}.json").read_text(encoding="utf-8"))["district"]
    # 별표(선거구역 텍스트) — 선거구명으로 lookup (3·4·5대만 보유)
    area_by = {}
    bpath = GEO / f"old_district_boundaries_{n}.json"
    if bpath.exists():
        for sido, rows in json.loads(bpath.read_text(encoding="utf-8")).items():
            for row in rows:
                area_by[row["district"]] = row.get("area", "")
    from collections import Counter, defaultdict
    # race별 (시군집합, 동토큰, 매칭폴리곤, 매칭률) 사전계산
    info = {}
    groups = defaultdict(list)  # (시도, 시군집합) → [race id...]
    for i, r in enumerate(d):
        sggs = r.get("sigungu_area") or sggs_of(r["name"])
        area = r.get("area") or area_by.get(r["name"], "")
        toks = parse_area_tokens(area, sggs) if area else []
        dpolys, ratio = dong_union(r["sido"], toks) if toks else ([], 0)
        info[i] = dict(sggs=sggs, dpolys=dpolys, ratio=ratio)
        if sggs:
            groups[(r["sido"], tuple(sorted(sggs)))].append(i)
    # 분할 그룹은 '전원 동매칭 양호'일 때만 동분할 — 하나라도 미달이면 전원 시군 폴백(겹침 방지)
    dong_ok = set()
    for key, ids in groups.items():
        if len(ids) > 1 and all(info[i]["ratio"] >= 0.9 and len(info[i]["dpolys"]) >= 2 for i in ids):
            dong_ok.update(ids)
    # 도시 분할(동매칭 미달) — 별표 동 점 보로노이로 근사 분할(추정 경계, approx)
    hp = GEO / "hgis_city_dong_points.json"
    hgis_pts = json.loads(hp.read_text(encoding="utf-8")) if hp.exists() else {}
    vor_geom = {}
    for (sido, sg), ids in groups.items():
        if len(ids) > 1 and not (set(ids) & dong_ok) and is_city_group(sido, list(sg)):
            res = voronoi_split([d[i] for i in ids], sido, list(sg), area_by, n, hgis_pts)
            if res:
                for (r, g), i in zip(res, ids):
                    vor_geom[i] = g
    # 나머지 분할 그룹(별표·동점 없음) — 등면적 기계 분할(임의·추정, 겹침 방지)
    mech_geom = {}
    for (sido, sg), ids in groups.items():
        if len(ids) <= 1 or (set(ids) & dong_ok) or (set(ids) & set(vor_geom)):
            continue
        container = unary_union([g for s in sg for g in resolve(sido, s)])
        if container.is_empty:
            continue
        order = sorted(ids, key=lambda i: gabeul_idx(d[i]["name"]))
        for i, pc in zip(order, mechanical_split(container, len(order))):
            if not pc.is_empty:
                mech_geom[i] = pc
    feats, nmap, skipped, miss, dong_split, vor_n, mech_n = [], {}, 0, [], 0, 0, 0
    for i, r in enumerate(d):
        sggs = info[i]["sggs"]
        polys, approx = [], False
        if i in dong_ok:  # 농촌 갑/을 — 동/면 union으로 실제 분리
            polys = info[i]["dpolys"]
            dong_split += 1
        elif i in vor_geom:  # 도시 갑/을 — 보로노이 추정 분할(점선 표시)
            polys = [vor_geom[i]]
            approx = True
            vor_n += 1
        elif i in mech_geom:  # 경계자료 없음 — 등면적 기계 분할(점선 추정)
            polys = [mech_geom[i]]
            approx = True
            mech_n += 1
        if not polys:
            for s in sggs:
                polys += resolve(r["sido"], s)
        if not polys:
            skipped += 1
            miss.append((r["sido"], r["name"], sggs))
            continue
        code = f"G{n}_{len(feats):03d}"
        sido = CANON.get(r["sido"], r["sido"])
        props = {"SGG_Code": code, "SGG": r["name"], "SIDO": sido}
        if approx:
            props["approx"] = True  # 추정 경계 → 렌더 점선
        feats.append({"type": "Feature", "properties": props,
                      "geometry": mapping(unary_union(polys))})
        nmap[f'{sido}|{r["name"]}'] = code
    (GEO / f"district_{n}_geojson.json").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), encoding="utf-8")
    (GEO / f"district_{n}_geojson_map.json").write_text(
        json.dumps({"name_to_sgg_code": nmap}, ensure_ascii=False), encoding="utf-8")
    print(f"{n}대: {len(feats)} feature, 동분할 {dong_split}, 보로노이 {vor_n}, 기계분할 {mech_n}, skip {skipped} {miss if miss else ''}")


if __name__ == "__main__":
    for n in (1, 2, 3, 4, 5, 6, 7):
        build(n)
