"""회차별/연도별 시도 외곽선.

(1) 총선: district_{n}_geojson을 SIDO로 dissolve → district_{n}_sido.json.
(2) 대선·지선: sigungu_{year}을 시도 2자리코드로 dissolve → sido_{year}.json.

현대 sido_simple은 광역시(대구·인천1981·광주1986·대전1989·울산1997·세종2012)를 전부 분리하고
군위(경북→대구 2023) 등도 현재 기준이라 옛 회차에 굵은 테두리·잘못된 경계가 시대착오.
그 시점 시군구 경계(sigungu_{year})를 시도코드로 dissolve하면 당시 시도 경계가 나온다.
대선·지선 geo(geomap.ts)가 sido_{year} 있으면 그걸로, 없으면(2025/2026=현재) sido_simple 폴백.

재현: python scripts/build/build_sido_outlines.py [9 .. 22]        # 총선 회차
      python scripts/build/build_sido_outlines.py --years          # 대선·지선 연도(기본 세트)
      python scripts/build/build_sido_outlines.py --years 1990 2000 # 특정 연도
"""
import json, subprocess, sys
from pathlib import Path
from collections import defaultdict
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from shapely.validation import make_valid

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"


def simplify(path):
    ms = ROOT / "node_modules/.bin/mapshaper"
    if not ms.exists():
        return
    # 원본 선거구 geojson이 이미 단순화돼 있어 — dissolve 외곽선을 또 단순화하면 fill보다 거칠어져
    # 시도선이 선거구를 안 따라감(듬성듬성). snap+clean으로 위상만 정리하고 단순화는 생략.
    try:
        subprocess.run([str(ms), str(path), "snap", "-clean", "-o", str(path), "force"],
                       check=True, capture_output=True, timeout=300)
    except Exception as e:
        print(f"  ⚠ mapshaper 실패({path.name}): {e}", file=sys.stderr)


def build(n):
    p = GEO / f"district_{n}_geojson.json"
    if not p.exists():
        print(f"  {n}대 geojson 없음 — skip", file=sys.stderr)
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    by_sido = defaultdict(list)
    for f in d.get("features", []):
        ss = f["properties"].get("SIDO_SGG") or ""
        sido = f["properties"].get("SIDO") or (ss.split()[0] if ss else None)
        if sido and f.get("geometry"):
            g = shape(f["geometry"])
            by_sido[sido].append(g if g.is_valid else make_valid(g))
    if not by_sido:  # SIDO 속성 없는 회차(21·22대 등) — 현대 외곽선이 시대 정합이라 skip
        print(f"  {n}대: SIDO 속성 없음 — skip(현대 외곽선 사용)", file=sys.stderr)
        return
    feats = [{"type": "Feature", "properties": {"SIDO": s},
              "geometry": mapping(unary_union(sh))} for s, sh in by_sido.items()]
    out = GEO / f"district_{n}_sido.json"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                              ensure_ascii=False), encoding="utf-8")
    simplify(out)
    print(f"{n}대: 시도 {len(feats)} → {out.name}", file=sys.stderr)


# 시도 2자리 코드 → canon 시도명 (geomap.ts LOCAL_SIDO_CODE2와 동일; 옛 연도엔 미존재 코드 자동 제외).
SIDO2_NAME = {
    '11': '서울특별시', '21': '부산광역시', '22': '대구광역시', '23': '인천광역시',
    '24': '광주광역시', '25': '대전광역시', '26': '울산광역시', '29': '세종특별자치시',
    '31': '경기도', '32': '강원특별자치도', '33': '충청북도', '34': '충청남도',
    '35': '전북특별자치도', '36': '전라남도', '37': '경상북도', '38': '경상남도',
    '39': '제주특별자치도',
}
# 대선·지선 geo가 쓰는 연도 (geomap.ts PRES_SGG_GEO_YEAR ∪ LOCAL_SGG_GEO_YEAR 중 현재=2025/2026 제외).
DEFAULT_YEARS = [1975, 1985, 1990, 1995, 2000, 2002, 2006, 2010, 2013]


def build_year(year):
    p = GEO / f"sigungu_{year}.json"
    if not p.exists():
        print(f"  sigungu_{year} 없음 — skip", file=sys.stderr)
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    by_sido = defaultdict(list)
    for f in d.get("features", []):
        s2 = str(f["properties"].get("code", ""))[:2]
        if not s2 or not f.get("geometry"):
            continue
        g = shape(f["geometry"])
        by_sido[s2].append(g if g.is_valid else make_valid(g))
    feats = [{"type": "Feature", "properties": {"SIDO": SIDO2_NAME.get(s2, s2), "code2": s2},
              "geometry": mapping(unary_union(sh))} for s2, sh in sorted(by_sido.items())]
    out = GEO / f"sido_{year}.json"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                              ensure_ascii=False), encoding="utf-8")
    simplify(out)
    print(f"{year}: 시도 {len(feats)}개 → {out.name}", file=sys.stderr)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--years":
        years = [int(x) for x in args[1:]] or DEFAULT_YEARS
        for y in years:
            try:
                build_year(y)
            except Exception as e:
                print(f"  ⚠ {y} 실패: {type(e).__name__} {e}", file=sys.stderr)
    else:
        rounds = [int(x) for x in args] or list(range(9, 23))
        for n in rounds:
            try:
                build(n)
            except Exception as e:
                print(f"  ⚠ {n}대 실패: {type(e).__name__} {e}", file=sys.stderr)
