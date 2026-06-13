"""옛 회차 '그 시점 실제 시군구 경계'를 HGIS(국사편찬위) 시간축 DB에서 복원.

HGIS feature는 begin/end(YYYYMMDD)로 버전관리 — 선거일에 유효한(또는 최근접) 버전을 골라
1975 SGIS 근사 대신 진짜 옛 경계를 쓴다. (1·2대 이북·도시 동 보충에 이미 HGIS 사용 — [[hgis_historical_boundaries]].)

매칭: 결과 데이터의 (sido, sigungu)를 HGIS nm 정확일치 + sido 포함 + type(郡/府/市/區/邑)으로 찾고,
선거일 포함 버전(begin<=date<=end) 우선, 없으면 geom 있는 최근접(이전 우선) 버전.
출력 feature props {code, name, sido} — code 앞2자리=시도코드라 geomap.ts infoFor가 그대로 매칭.

raw 응답은 data/raw/hgis/ 캐시(gitignore). 부산 등 '선거구 단위'(행정구역 아님)는 매칭 불가 → 보고만.
재현: python scripts/fetch/build_sigungu_hgis.py 2 19520805
"""
import json, subprocess, sys, time, urllib.request, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"
RAW = ROOT / "data/raw/hgis"
RAW.mkdir(parents=True, exist_ok=True)
EP = "https://hgis.history.go.kr/pro_g1/gis/gisSearch.do"
UA = "Mozilla/5.0"

# 결과데이터 모던 canon 시도 → (HGIS 역사 시도명, 시도 2자리코드)
SIDO = {
    "서울특별시": ("서울특별시", "11"), "경기도": ("경기도", "31"),
    "강원특별자치도": ("강원도", "32"), "충청북도": ("충청북도", "33"),
    "충청남도": ("충청남도", "34"), "전북특별자치도": ("전라북도", "35"),
    "전라남도": ("전라남도", "36"), "경상북도": ("경상북도", "37"),
    "경상남도": ("경상남도", "38"), "제주특별자치도": ("제주도", "39"),
}
WANT_TYPES = {"郡", "府", "市", "區", "邑"}


def hgis(keyword):
    cache = RAW / f"{keyword}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    req = urllib.request.Request(EP,
        data=urllib.parse.urlencode({"keyword": keyword, "mode": "hgis"}).encode(),
        headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    cache.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    time.sleep(0.25)
    return d


def pick_version(feats, date):
    """선거일 포함 버전 우선, 없으면 geom 있는 최근접(이전 우선) 버전."""
    cand = [f for f in feats if f.get("geometry")]
    if not cand:
        return None
    def b(f): return int(f["properties"].get("begin") or 0)
    def e(f): return int(f["properties"].get("end") or 99999999)
    contain = [f for f in cand if b(f) <= date <= e(f)]
    if contain:
        return max(contain, key=b)              # 포함 중 가장 늦게 시작
    before = [f for f in cand if b(f) <= date]
    if before:
        return max(before, key=b)               # 이전 중 가장 가까운
    return min(cand, key=b)                      # 전부 이후면 가장 이른


def resolve_nm(data_sido, target_nm, date, types, keyword=None):
    """HGIS에서 nm==target_nm·해당 type·sido 일치 중 선거일 유효(또는 최근접) 버전 feature."""
    hsido = SIDO[data_sido][0]
    feats = []
    for arr in hgis(keyword or target_nm):
        for f in arr.get("features", []):
            p = f.get("properties", {})
            if p.get("nm") == target_nm and p.get("type") in types and hsido in str(p.get("name", "")):
                feats.append(f)
    return pick_version(feats, date) if feats else None


def resolve(data_sido, sigungu, date):
    return resolve_nm(data_sido, sigungu, date, WANT_TYPES), SIDO[data_sido][1]


def parent_city_mask(data_sido, name, date):
    """차용 선거구의 부모 도시(부산시·동대문구 등) HGIS 폴리곤 — voronoi clip 마스크.
    부산시갑구→부산시(市/府), 동대문갑구→동대문구(區). 그 시점 도시 범위로 가둬 인접 군과 겹침 방지."""
    import re
    from shapely.geometry import shape
    base = re.sub(r"[갑을병정무]구$", "", name)          # 부산시갑구→부산시, 동대문갑구→동대문
    parent = base if base.endswith("시") else base + "구"  # 부산시 / 동대문구
    kw = re.sub(r"(시|구)$", "", parent)                  # HGIS 검색어: 부산 / 동대문
    v = resolve_nm(data_sido, parent, date, {"市", "府", "區", "郡"}, keyword=kw)
    return shape(v["geometry"]) if v else None


def borrow_assembly(unmatched, assembly_n, date):
    """HGIS 무매칭 선거구(부산 갑~무 등 행정구역 아닌 선거구)를 동시대 총선 geo의 voronoi 폴리곤으로.
    district_{m}_geojson은 도시 선거구를 동 점 voronoi로 이미 분할 보유 → 같은 선거구명 매칭해 차용.
    단 voronoi는 1975 도시범위 기반이라 그 시점 부모도시 HGIS 폴리곤으로 clip(예: 부산이 동래군과 겹침 방지)."""
    from shapely.geometry import shape, mapping
    p = ROOT / "data/geo" / f"district_{assembly_n}_geojson.json"
    if not p.exists():
        return {}, unmatched
    feats = json.loads(p.read_text(encoding="utf-8")).get("features", [])
    got, still = {}, []
    for data_sido, name, why in unmatched:
        sgg_target = name.replace(" ", "")
        hit = next((f for f in feats
                    if sgg_target in str(f["properties"].get("SGG", "")).replace(" ", "") and f.get("geometry")), None)
        if not hit:
            still.append((data_sido, name, why)); continue
        geom = shape(hit["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        mask = parent_city_mask(data_sido, name, date)
        if mask is not None:
            clipped = geom.intersection(mask)
            if not clipped.is_empty:
                geom = clipped
        got[(data_sido, name)] = mapping(geom)
    return got, still


def simplify(path, pct="3%"):
    ms = ROOT / "node_modules/.bin/mapshaper"
    if not ms.exists():
        print("  ⚠ mapshaper 없음 — 단순화 생략(파일 큼)", file=sys.stderr); return
    # HGIS 폴리곤은 개별 수집이라 인접 경계 미공유 → snap으로 정점 병합 후 위상보존 단순화.
    # keep-shapes로 작은 구(서울 9구 등) 소실 방지. clean은 feature 삭제 위험이라 생략.
    subprocess.run([str(ms), str(path), "-snap", "-simplify", pct, "keep-shapes",
                    "-o", str(path), "format=geojson", "force"], check=True, capture_output=True, timeout=600)


def build(round_n, date, assembly_n=None):
    # 결과 파일 — 서수 접두({n}nd-pres-*) 우선
    suf = {1: "st", 2: "nd", 3: "rd"}.get(round_n, "th")
    cands = list((ROOT / "data/results").glob(f"{round_n}{suf}-pres-*.json")) or \
            list((ROOT / "data/results").glob(f"*pres*_{round_n}.json"))
    src = next((c for c in cands if "sigungu" not in c.name), cands[0] if cands else None)
    if not src:
        print(f"결과 파일 못 찾음 (round {round_n})", file=sys.stderr); return
    print(f"소스: {src.name} | 선거일 {date}", file=sys.stderr)
    data = json.loads(src.read_text(encoding="utf-8"))
    sgg = [(r["sido"], r["sigungu"]) for r in data["races"]
           if r.get("scope") == "sigungu" and r.get("sigungu")]
    uniq = sorted(set(sgg))
    feats_out, matched, unmatched = [], [], []
    for data_sido, name in uniq:
        if data_sido not in SIDO:
            unmatched.append((data_sido, name, "시도미정의")); continue
        try:
            v, code2 = resolve(data_sido, name, date)
        except Exception as ex:
            unmatched.append((data_sido, name, f"err:{type(ex).__name__}")); continue
        if not v:
            unmatched.append((data_sido, name, "HGIS무매칭")); continue
        feats_out.append({"type": "Feature",
            "properties": {"code": code2 + "000", "name": name, "sido": data_sido,
                           "hgis_begin": v["properties"].get("begin"),
                           "hgis_end": v["properties"].get("end")},
            "geometry": v["geometry"]})
        matched.append((data_sido, name, v["properties"].get("begin"), v["properties"].get("end")))
    # 무매칭(선거구 등)을 동시대 총선 voronoi로 차용
    borrowed = 0
    if assembly_n and unmatched:
        got, unmatched = borrow_assembly(unmatched, assembly_n, date)
        for (data_sido, name), geom in got.items():
            feats_out.append({"type": "Feature",
                "properties": {"code": SIDO[data_sido][1] + "000", "name": name,
                               "sido": data_sido, "borrowed_from": f"district_{assembly_n}"},
                "geometry": geom})
            borrowed += 1
    out = GEO / f"sigungu_hgis_{round_n}.json"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats_out},
                              ensure_ascii=False), encoding="utf-8")
    print(f"\nHGIS매칭 {len(matched)} + 총선차용 {borrowed} = {len(feats_out)}/{len(uniq)} → {out.name}", file=sys.stderr)
    if unmatched:
        print(f"미매칭 {len(unmatched)}개:", file=sys.stderr)
        for s, n, why in unmatched:
            print(f"   {s} {n} ({why})", file=sys.stderr)
    simplify(out)
    import os
    print(f"단순화 후 크기: {os.path.getsize(out)//1024}KB", file=sys.stderr)
    build_sido(out, round_n)


def build_sido(out_sigungu, round_n):
    """단순화된 HGIS 시군구를 시도2자리코드로 dissolve → sido_hgis_{n}.json (외곽선, fill과 정합)."""
    from collections import defaultdict
    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union
    from shapely.validation import make_valid
    d = json.loads(out_sigungu.read_text(encoding="utf-8"))
    by = defaultdict(list)
    for f in d["features"]:
        s2 = str(f["properties"]["code"])[:2]
        g = shape(f["geometry"])
        by[s2].append(g if g.is_valid else make_valid(g))
    feats = [{"type": "Feature", "properties": {"code2": s2},
              "geometry": mapping(unary_union(sh))} for s2, sh in sorted(by.items())]
    sp = GEO / f"sido_hgis_{round_n}.json"
    sp.write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                             ensure_ascii=False), encoding="utf-8")
    print(f"시도 외곽선 {len(feats)}개 → {sp.name}", file=sys.stderr)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    date = int(sys.argv[2]) if len(sys.argv) > 2 else 19520805
    asm = int(sys.argv[3]) if len(sys.argv) > 3 else None
    build(n, date, asm)
