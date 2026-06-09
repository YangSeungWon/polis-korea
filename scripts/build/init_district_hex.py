"""옛 총선(9~16대) 지역구 hex 초기 파일 생성 — 선거구 geojson centroid 주입.

build_zone_hex는 현재 시군구 centroid를 쓰는데 옛 회차는 폐지 시군구가 많아 실패.
→ 복원한 선거구 geojson에서 centroid를 직접 계산해 _cen으로 박고, build_zone_hex가 배치.

출력: data/geo/district_hex_{n}.json [{sido, name, sigungus, _cen:[lon,lat]}]
이후: python scripts/build/build_zone_hex.py data/geo/district_hex_{n}.json (c,r 배치)
사용: python scripts/build/init_district_hex.py 9 10 11 12 13 14 15 16
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data" / "geo"
RES = ROOT / "data" / "results"
CANON = {"강원도": "강원특별자치도", "전라북도": "전북특별자치도"}


def centroid(coords):
    """GeoJSON Polygon/MultiPolygon 외곽 ring 면적가중 centroid."""
    best, ba = None, -1
    rings = []
    def collect(c, depth):
        if depth == 1:
            rings.append(c)
        else:
            for x in c:
                collect(x, depth - 1)
    # Polygon: depth2(ring=list of [x,y]) → coords=[ring,...]; MultiPolygon: depth3
    if isinstance(coords[0][0][0], (int, float)):  # Polygon
        rings = coords
    else:  # MultiPolygon
        rings = [poly[0] for poly in coords]
    for r in rings:
        a = 0
        for i in range(len(r) - 1):
            a += r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1]
        if abs(a) > ba:
            ba = abs(a); best = r
    if not best:
        return None
    a = cx = cy = 0
    for i in range(len(best) - 1):
        f = best[i][0] * best[i + 1][1] - best[i + 1][0] * best[i][1]
        a += f; cx += (best[i][0] + best[i + 1][0]) * f; cy += (best[i][1] + best[i + 1][1]) * f
    if not a:
        m = [sum(p[k] for p in best) / len(best) for k in (0, 1)]
        return m
    return [cx / (3 * a), cy / (3 * a)]


def sggs_of(name):
    m = re.search(r"\((.+)\)", name)  # 중선거구 '제1선거구(종로구·중구)'
    if m:
        return [s.strip() for s in re.split(r"[·∙•・,]", m.group(1))]
    base = re.sub(r"[갑을병정]$", "", name)  # 소선거구 '강릉시갑'·'속초시고성군양양군'
    return re.findall(r"[가-힣]+?(?:특별자치시|특별시|광역시|특별자치도|시|군|구)", base) or [base]


def build(n):
    geo = json.loads((GEO / f"district_{n}_geojson.json").read_text(encoding="utf-8"))
    cen_by_code = {f["properties"]["SGG_Code"]: centroid(f["geometry"]["coordinates"]) for f in geo["features"]}
    mp = json.loads((GEO / f"district_{n}_geojson_map.json").read_text(encoding="utf-8"))["name_to_sgg_code"]
    res = json.loads((RES / f"national_assembly_{n}.json").read_text(encoding="utf-8"))["district"]
    cells = []
    miss = 0
    for r in res:
        sido, name = r["sido"], r["name"]
        code = mp.get(f"{CANON.get(sido, sido)}|{name}")
        cen = cen_by_code.get(code) if code else None
        if not cen:
            miss += 1
            continue
        cells.append({"sido": sido, "name": name, "sigungus": sggs_of(name),
                      "_cen": [round(cen[0], 5), round(cen[1], 5)], "c": 0, "r": 0})
    (GEO / f"district_hex_{n}.json").write_text(json.dumps(cells, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{n}대: {len(cells)} cell (centroid 없음 {miss})", file=sys.stderr)


if __name__ == "__main__":
    for a in (sys.argv[1:] or [9, 10, 11, 12, 13, 14, 15, 16]):
        build(int(a))
