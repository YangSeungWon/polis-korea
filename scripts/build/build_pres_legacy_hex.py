#!/usr/bin/env python3
"""옛 대선(2~14대) 회차별 전국 시군구 hex — 그 시점 자치구 집합으로 새로 배치.

현대 25구 고정 레이아웃은 옛 회차의 구 분할과 안 맞음(5대 서울=9구). 회차마다 그 시점
데이터의 자치구(선거구 갑/을 병합)를 centroid에 비닝해 1셀=1구 카토그램을 만듦.

centroid: 현대 sigungu_simple.json 우선, 옛 직할시형('부산시동구'→부산 동구)·옛 군/시
(명주군→강릉 등) 별칭, 시도 fallback. 패킹: lon/lat→격자 비닝 + BFS 충돌해소 + hole-fill.
출력: data/geo/sigungu_hex_pres_{n}.json  (cell: {sido,name,c,r} — sido/name은 데이터 그대로).
"""
import json, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"
RES = ROOT / "data/results"
sys.path.insert(0, str(Path(__file__).resolve().parent))


def centroid(geom):
    xs, ys = [], []
    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for x in c: walk(x)
    walk(geom["coordinates"])
    return (sum(xs) / len(xs), sum(ys) / len(ys))


# 현대 시군구 centroid 인덱스 — simple엔 sido 없고 code만 → hex_legacy의 sido+code로 연결.
_simple = json.loads((GEO / "sigungu_simple.json").read_text(encoding="utf-8"))
_sfeats = _simple.get("features", _simple)
CODE_CEN = {str(f["properties"].get("code")): centroid(f["geometry"]) for f in _sfeats}
_hex = json.loads((GEO / "sigungu_hex_legacy.json").read_text(encoding="utf-8"))
CEN = {}                       # (sido,name) → (lon,lat)
NAMEONLY = defaultdict(list)
BY_METRO = defaultdict(list)   # 광역시/특별시 sido → [centroid] (전체 평균용)
for c in _hex:
    sd = c.get("sido") or ""; nm = c.get("name") or ""; cen = CODE_CEN.get(str(c.get("code")))
    if not cen:
        continue
    CEN[(sd, nm)] = cen
    NAMEONLY[nm].append((sd, cen))
    if sd.endswith("광역시") or sd.endswith("특별시"):
        BY_METRO[sd].append(cen)

# 시도 centroid (fallback)
_sido = json.loads((GEO / "sido_simple.json").read_text(encoding="utf-8"))
SIDO_CEN = {f["properties"]["name"]: centroid(f["geometry"])
            for f in _sido.get("features", _sido)}
SIDO_ALIAS = {"강원특별자치도": "강원도", "전북특별자치도": "전라북도", "제주특별자치도": "제주도"}

# 옛 '○○시X구'/'○○시제N' → 현대 광역시. (직할시 승격 전 데이터 sido는 모도 道)
METRO_PREFIX = {
    "부산시": "부산광역시", "대구시": "대구광역시", "인천시": "인천광역시",
    "광주시": "광주광역시", "대전시": "대전광역시", "울산시": "울산광역시",
}
# 옛 군/시/구 → 현대 시군구 이름(같은 道 안에서 centroid 조회). 분할/개명/승격 successor.
HIST_ALIAS = {
    # 강원
    "명주군": "강릉시", "원성군": "원주시", "춘성군": "춘천시", "김화군": "철원군",
    # 경기
    "고양군": "고양시", "용인군": "용인시", "미금시": "남양주시", "송탄시": "평택시",
    # 경남
    "동래군": "기장군", "마산시": "창원시", "삼천포시": "사천시", "울산군": "울주군",
    "의창군": "창원시", "진양군": "진주시", "장승포시": "거제시", "진해시": "창원시",
    "창원군": "창원시", "충무시": "통영시",
    "마산시합포구": "창원시마산합포구", "마산시회원구": "창원시마산회원구",
    # 경북
    "금릉군": "김천시", "선산군": "구미시", "영일군": "포항시", "영풍군": "영주시",
    "월성군": "경주시", "점촌시": "문경시",
    # 전남/광주
    "광산군": "광산구", "동광양시": "광양시", "송정시": "광산구", "승주군": "순천시",
    "여천군": "여수시", "여천시": "여수시",
    # 전북
    "옥구군": "군산시", "이리시": "익산시", "정주시": "정읍시",
    # 제주
    "남제주군": "서귀포시", "북제주군": "제주시",
    # 충남/대전/세종
    "대덕군": "대덕구", "대천시": "보령시", "연기군": "세종특별자치시",
    "온양시": "아산시", "천안군": "천안시", "천원군": "천안시",
    # 충북
    "제원군": "제천시", "중원군": "충주시", "청원군": "청주시",
    # 부산광역시 sido로 들어온 짧은/중복 이름
    "동래": "동래구", "부산진": "부산진구", "부산진구구": "부산진구", "금구": "금정구",
    # 데이터 노이즈
    "성남시수구": "성남시수정구",
}


def metro_avg(metro_sido):
    pts = BY_METRO.get(metro_sido)
    if not pts: return None
    return (sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts))


def name_lookup(sido, nm):
    """현대 인덱스에서 (sido,nm) 우선, 같은 道 name, 단일 name 순."""
    if (sido, nm) in CEN: return CEN[(sido, nm)]
    same = [c for (s, c) in NAMEONLY.get(nm, []) if s == sido]
    if same: return same[0]
    cands = NAMEONLY.get(nm, [])
    if len(cands) == 1: return cands[0][1]
    # 같은 道 우선(시도 통합/개명 흡수)
    if cands: return cands[0][1]
    return None


def resolve(sido, name):
    # 1) 직접
    c = name_lookup(sido, name)
    if c: return c
    # 2) 옛 직할시형 '○○시X구' / '○○시제N' / '○○시구' / '○○시'
    for pre, metro in METRO_PREFIX.items():
        if name.startswith(pre):
            rest = name[len(pre):]
            m = re.match(r"^([가-힣]+구)$", rest)
            if m and (metro, m.group(1)) in CEN:
                return CEN[(metro, m.group(1))]
            return metro_avg(metro)            # 제N선거구·통째·구미상 → 메트로 중심
    # 3) 역사 별칭
    if name in HIST_ALIAS:
        al = HIST_ALIAS[name]
        c = name_lookup(sido, al)
        if c: return c
        # 별칭이 광역구(광산구/대덕구 등)인데 道 sido면 광역시에서 조회
        for (s, n), cc in CEN.items():
            if n == al: return cc
    # 4) 군→시
    if name.endswith("군"):
        c = name_lookup(sido, name[:-1] + "시")
        if c: return c
    # 5) 시도 fallback
    sd = SIDO_CEN.get(sido) or SIDO_CEN.get(SIDO_ALIAS.get(sido, ""))
    return sd


def jachi(name):
    m = re.match(r"^(.+?)[갑을병정무]구$", name)
    return m.group(1) + "구" if m else name


def build_cells(n, path):
    """회차 데이터 → period 자치구 셀 [{sido,name,_cen}] (배치는 build_zone_hex가)."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    seen = {}
    for r in d["races"]:
        if r.get("scope") != "sigungu" or not r.get("sigungu"):
            continue
        sido = r.get("sido"); nm = jachi(r["sigungu"])
        key = (sido, nm)
        if key in seen: continue
        seen[key] = {"sido": sido, "name": nm, "_cen": list(resolve(sido, nm) or ())}
    cells = list(seen.values())
    miss = [c for c in cells if not c["_cen"]]
    for c in miss: print(f"  centroid 실패: {c['sido']} {c['name']}", file=sys.stderr)
    cells = [c for c in cells if c["_cen"]]
    if len(cells) < 20:
        print(f"{n}대: 시군구 데이터 {len(cells)}개 — 간선/미보유, skip")
        return None
    return cells


if __name__ == "__main__":
    import glob
    targets = {}
    for f in glob.glob(str(RES / "*-pres-*.json")):
        num = int(re.match(r"(\d+)", Path(f).name).group(1))
        if num >= 15: continue
        # 같은 회차 여러 파일이면 races 많은 쪽
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        cnt = sum(1 for r in d.get("races", []) if r.get("scope") == "sigungu")
        if num not in targets or cnt > targets[num][1]:
            targets[num] = (f, cnt)
    import build_zone_hex
    want = [int(a) for a in sys.argv[1:]] or sorted(targets)
    combined = {}
    for n in want:
        if n not in targets:
            continue
        cells = build_cells(n, targets[n][0])
        if not cells:
            continue
        # 시도별 주먹밥 배치(build_zone_hex.process) — _cen 직접 사용, pretty 저장.
        per = GEO / f"_pres_tmp_{n}.json"
        per.write_text(json.dumps(cells, ensure_ascii=False))
        info = build_zone_hex.process(per, dry=False, backup=False)
        packed = json.loads(per.read_text(encoding="utf-8"))
        per.unlink()
        out = [{"sido": c["sido"], "name": c["name"], "c": c["c"], "r": c["r"]}
               for c in packed if "c" in c]
        combined[str(n)] = out
        print(f"{n}대: {len(out)}셀 → {info['bbox']}, 미배치 {len(packed)-len(out)}")
    # 통합 파일 (렌더러가 회차별로 조회) — 회차→셀 배열. pretty(리포 컨벤션, minify 금지).
    (GEO / "sigungu_hex_pres.json").write_text(json.dumps(combined, ensure_ascii=False, indent=2))
    print(f"\n통합: data/geo/sigungu_hex_pres.json ({len(combined)}개 회차)")
