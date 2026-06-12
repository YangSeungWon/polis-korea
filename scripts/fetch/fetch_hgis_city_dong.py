"""도시 갑/을 보로노이 근사 분할용 — 1975 동에 안 맞는 선거구의 별표 동을 HGIS 점으로 보충.

build_old_general_geo의 보로노이 분할은 각 선거구가 컨테이너(구/시) 내 동 점 ≥1개를 가져야
성립. 1954~60 도시 동명이 1975와 달라 점0이 되는 선거구(영등포 갑·대구 정 등)는 HGIS
1919 동리 점(POINT)으로 보충. HGIS는 옛 동명을 더 많이 보유(동성로·용덕동 등).
산출: data/geo/hgis_city_dong_points.json = {"{n}|{선거구명}": [[lon,lat],...]} (컨테이너 내부만).

재현: python scripts/fetch/fetch_hgis_city_dong.py
"""
import json, re, sys, time
import urllib.request, urllib.parse
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build"))
import build_old_general_geo as B  # resolve·parse_area_tokens·dong_union·is_city_group

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/geo/hgis_city_dong_points.json"
UA = "vote-via-data-research/1.0 (hislab.mueller@gmail.com)"
EP = "https://hgis.history.go.kr/pro_g1/gis/gisSearch.do"
_cache = {}


def hgis_points(term):
    """HGIS 검색 → lv4(동리/가) Point 좌표 리스트(전국 후보)."""
    if term in _cache:
        return _cache[term]
    try:
        req = urllib.request.Request(EP, data=urllib.parse.urlencode({"keyword": term, "mode": "hgis"}).encode(),
                                     headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"})
        r = json.loads(urllib.request.urlopen(req, timeout=40).read())
        pts = [f["geometry"]["coordinates"] for fc in r for f in fc.get("features", [])
               if (f.get("geometry") or {}).get("type") == "Point" and f.get("properties", {}).get("lv") == 4]
    except Exception as e:
        print(f"    [err] {term}: {type(e).__name__}", file=sys.stderr)
        pts = []
    _cache[term] = pts
    time.sleep(0.25)
    return pts


def raw_dong_names(area, sigungu):
    """별표 area → 검색용 동명(가-숫자 제거: '동인동1가'→'동인동')."""
    toks = B.parse_area_tokens(area, sigungu)  # canon key
    names = set()
    for t in toks:
        base = re.sub(r"\d+가$", "동", t) if re.search(r"\d+가$", t) else t
        names.add(base if base.endswith(("동", "면", "읍", "리", "가")) else base + "동")
    return names


def main():
    from shapely.geometry import Point
    out = {}
    for n in (3, 4, 5):
        bdy = json.loads((ROOT / f"data/geo/old_district_boundaries_{n}.json").read_text(encoding="utf-8"))
        area_by = {r["district"]: r.get("area", "") for s, rs in bdy.items() for r in rs}
        d = json.loads((ROOT / f"data/results/national_assembly_{n}.json").read_text(encoding="utf-8"))["district"]
        grp = defaultdict(list)
        for i, r in enumerate(d):
            sg = tuple(sorted(r.get("sigungu_area") or B.sggs_of(r["name"])))
            if sg:
                grp[(r["sido"], sg)].append(i)
        for (sido, sg), ids in grp.items():
            if len(ids) < 2 or not B.is_city_group(sido, list(sg)):
                continue
            cont = B.unary_union([g for s in sg for g in B.resolve(sido, s)])
            for i in ids:
                r = d[i]
                toks = B.parse_area_tokens(area_by.get(r["name"], ""), list(sg))
                polys, _ = B.dong_union(sido, toks)
                if any(cont.contains(p.representative_point()) for p in polys):
                    continue  # 1975 점 충분 → HGIS 불필요
                # 점0 선거구 → HGIS 보충
                pts = []
                for nm in raw_dong_names(area_by.get(r["name"], ""), list(sg)):
                    for lon, lat in hgis_points(nm):
                        if cont.contains(Point(lon, lat)):
                            pts.append([round(lon, 6), round(lat, 6)])
                if pts:
                    out[f"{n}|{r['name']}"] = pts
                    print(f"  {n}대 {r['name']}: HGIS 점 {len(pts)}", file=sys.stderr)
                else:
                    print(f"  {n}대 {r['name']}: HGIS 점 0 (보충 실패)", file=sys.stderr)
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"→ {OUT.name}: {len(out)} 선거구 보충", file=sys.stderr)


if __name__ == "__main__":
    main()
