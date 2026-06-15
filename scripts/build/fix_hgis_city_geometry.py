#!/usr/bin/env python3
"""HGIS 옛 대선 경계 — 도시 구도(시/군) 지오메트리 복구.

HGIS 재구성이 옛 '시(도심)+군(주변)' 구도에서 도심 폴리곤을 못 만들어 일부 회차에서
시 지오가 깨지거나(여수·원주) 시·군이 같은 전체영역을 공유(경주·천안)해, 개표결과가
지도에 안 뜨거나 한쪽이 가려진다. 다른 회차/연도 파일의 실제 경계를 splice하고 군을
difference로 carve해 바로잡는다. (case별 명시 — 일반 규칙 아님.)

- 여수시(2~7대): 지오 퇴화/과소 → sigungu_1975 여수시 실제경계로 교체(그 회차 군 없음).
- 경주군/월성군(3대): 경주군 race=시(3만) → 경주군 지오를 경주시(hgis_4)로, 월성군=월성군−경주시.
- 천안군/천원군(7대): 천안군 race=시(3.6만), 천원군⊂천안군 → 천안군=천안군−천원군.
- 대구 북구/서구(6·7대): 서구⊂북구(지오오류) → 북구=북구−서구.
- 원주시(4대): 지오 퇴화 → 원주시(hgis_3) splice + 원주군=원주군−원주시.

cross-sido(광주/성동)=clean_hgis_seoul_overlap.py, 시/군 도넛=clean_hgis_overlaps.py.
재현: python scripts/build/fix_hgis_city_geometry.py  (멱등)
"""
import json
from pathlib import Path

from shapely.geometry import shape, mapping
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data" / "geo"
JUNK = 1e-8


def load(name):
    return json.loads((GEO / name).read_text())


def feat(d, name):
    for f in d["features"]:
        if f["properties"].get("name") == name:
            return f
    return None


def geom_of(name_file, name):
    return shape(feat(load(name_file), name)["geometry"]).buffer(0)


def drop_junk(geom):
    """면적<JUNK 보조 part·퇴화 hole 제거(최대 part 항상 보존)."""
    def _a(ring):
        return shape({"type": "Polygon", "coordinates": [ring]}).area
    def holes(rings):
        return [rings[0]] + [r for r in rings[1:] if len(r) >= 4 and _a(r) >= JUNK]
    m = mapping(geom)
    if geom.geom_type == "Polygon":
        return shape({"type": "Polygon", "coordinates": holes(m["coordinates"])})
    if geom.geom_type == "MultiPolygon":
        polys = sorted(m["coordinates"], key=lambda p: _a(p[0]), reverse=True)
        keep = [polys[0]] + [p for p in polys[1:] if _a(p[0]) >= JUNK]
        keep = [holes(p) for p in keep]
        if len(keep) == 1:
            return shape({"type": "Polygon", "coordinates": keep[0]})
        return shape({"type": "MultiPolygon", "coordinates": keep})
    return geom


def round_geom(geom, nd=9):
    def r(x):
        if isinstance(x, (list, tuple)):
            return [round(float(v), nd) for v in x] if x and isinstance(x[0], (int, float)) else [r(v) for v in x]
        return x
    m = mapping(drop_junk(geom))
    m["coordinates"] = r(m["coordinates"])
    return m


def write_fc(name, d):
    lines = ['{"type":"FeatureCollection", "features": [']
    fs = d["features"]
    for i, f in enumerate(fs):
        lines.append(json.dumps(f, ensure_ascii=False, separators=(",", ":")) + ("," if i < len(fs) - 1 else ""))
    lines.append("]}")
    (GEO / name).write_text("\n".join(lines) + "\n")


def set_geom(d, name, geom, log):
    f = feat(d, name)
    if not f:
        print(f"    ! {name} 없음 — 건너뜀")
        return
    f["geometry"] = round_geom(geom)
    print(f"    {log}")


def main():
    yeosu = geom_of("sigungu_1975.json", "여수시")

    # 1) 여수시 — 깨진 회차 전부 1975 실제경계로 교체 + 주변 여천군 carve(군이 시를 품고 있음)
    for r in [2, 3, 4, 5, 6, 7]:
        fn = f"sigungu_hgis_{r}.json"
        d = load(fn)
        f = feat(d, "여수시")
        if not f:
            continue
        print(f"여수시 {fn}:")   # splice·difference 모두 멱등 → 가드 없이 항상 적용
        set_geom(d, "여수시", yeosu, f"여수시 ← 1975 경계 (area→{yeosu.area:.4f})")
        yc = feat(d, "여천군")
        if yc:
            ycg = shape(yc["geometry"]).buffer(0)
            set_geom(d, "여천군", ycg.difference(yeosu), "여천군 = 여천군 − 여수시 (군 ring)")
        write_fc(fn, d)

    # 2) 경주군/월성군 (hgis_3): 경주군←경주시(h4), 월성군 = 월성군−경주시
    d = load("sigungu_hgis_3.json")
    kjsi = geom_of("sigungu_hgis_4.json", "경주시")
    print("경주 hgis_3:")
    set_geom(d, "경주군", kjsi, f"경주군 ← 경주시(h4) 지오 (race=시 3만)")
    wsg = shape(feat(d, "월성군")["geometry"]).buffer(0)
    set_geom(d, "월성군", wsg.difference(kjsi), f"월성군 = 월성군 − 경주시 (군 ring)")
    write_fc("sigungu_hgis_3.json", d)

    # 3) 천안군/천원군 (hgis_7): 천안군 = 천안군 − 천원군
    d = load("sigungu_hgis_7.json")
    print("천안 hgis_7:")
    cn = shape(feat(d, "천안군")["geometry"]).buffer(0)
    cw = shape(feat(d, "천원군")["geometry"]).buffer(0)
    set_geom(d, "천안군", cn.difference(cw), "천안군 = 천안군 − 천원군 (시 영역)")
    write_fc("sigungu_hgis_7.json", d)

    # 4) 대구 북구/서구 (hgis_6, 7): 북구 = 북구 − 서구
    for r in [6, 7]:
        fn = f"sigungu_hgis_{r}.json"
        d = load(fn)
        bg = feat(d, "대구시북구")
        sg = feat(d, "대구시서구")
        if bg and sg:
            print(f"대구 {fn}:")
            b = shape(bg["geometry"]).buffer(0)
            s = shape(sg["geometry"]).buffer(0)
            set_geom(d, "대구시북구", b.difference(s), "대구시북구 = 북구 − 서구")
            write_fc(fn, d)

    # 5) 원주시 (hgis_4): 원주시 ← hgis_3, 원주군 = 원주군 − 원주시
    d = load("sigungu_hgis_4.json")
    wjsi = geom_of("sigungu_hgis_3.json", "원주시")
    print("원주 hgis_4:")
    set_geom(d, "원주시", wjsi, f"원주시 ← hgis_3 경계 (area→{wjsi.area:.4f})")
    wjg = shape(feat(d, "원주군")["geometry"]).buffer(0)
    set_geom(d, "원주군", wjg.difference(wjsi), "원주군 = 원주군 − 원주시 (ring)")
    write_fc("sigungu_hgis_4.json", d)

    print("\n완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
