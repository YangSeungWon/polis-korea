"""선거구 geojson의 시도 간 오매칭 조각(stray) 제거.

build_district_geojson의 동명 충돌이 잘못 해소돼, 한 선거구에 다른 도의 동
폴리곤이 붙는 경우가 있다(예: 광주 광산구에 경기도 조각, 충남 천안에 전남 조각).
현대 선거구는 시도를 넘지 않으므로 본체와 다른 시도의 조각은 오류.

단, 광역시는 모도(母道)에서 승격했으므로(경기→인천, 전남→광주, 경남→부산·울산,
경북→대구, 충남→대전·세종) 도↔자식광역시 교차는 역사적으로 동일 권역 → 보존.
또 바다 섬(어느 시도 폴리곤에도 안 드는 점, sido_of=None)도 보존(안면도·울릉도 등).

재현: python scripts/build/clean_district_strays.py [--apply] [9 .. 22]
  (--apply 없으면 리포트만)
"""
import json, sys
from pathlib import Path
from shapely.geometry import shape, mapping
from shapely.validation import make_valid

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"

# 도 ↔ 승격 광역시 = 역사적 동일 권역 (교차해도 오류 아님)
FAMILIES = [
    {"서울특별시"},
    {"경기도", "인천광역시"},
    {"강원도"}, {"강원특별자치도"},
    {"충청북도"},
    {"충청남도", "대전광역시", "세종특별자치시"},
    {"전라북도"}, {"전북특별자치도"},
    {"전라남도", "광주광역시"},
    {"경상북도", "대구광역시"},
    {"경상남도", "부산광역시", "울산광역시"},
    {"제주특별자치도", "제주도"},
]
SIDO_FULL = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "경기": "경기도", "강원": "강원도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전라북도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
    "제주": "제주특별자치도",
}


def fam_of(name):
    for f in FAMILIES:
        if name in f:
            return frozenset().union(*[g for g in FAMILIES if name in g])
    return frozenset({name}) if name else None


def clean_ring(geom):
    t, c = geom["type"], geom["coordinates"]
    ok = lambda r: len(r) >= 4
    if t == "Polygon":
        rings = [r for r in c if ok(r)]
        return {"type": "Polygon", "coordinates": rings} if rings else None
    if t == "MultiPolygon":
        polys = [[r for r in poly if ok(r)] for poly in c]
        polys = [p for p in polys if p]
        return {"type": "MultiPolygon", "coordinates": polys} if polys else None
    return geom


def load_sido():
    sd = json.loads((GEO / "sido_simple.json").read_text(encoding="utf-8"))
    sf = sd.get("features", sd) if isinstance(sd, dict) else sd
    out = []
    for f in sf:
        cg = clean_ring(f["geometry"])
        if not cg:
            continue
        g = shape(cg)
        g = g if g.is_valid else make_valid(g)
        if not g.is_empty:
            out.append((f["properties"]["name"], g))
    return out


def main():
    args = sys.argv[1:]
    apply = "--apply" in args
    rounds = [int(x) for x in args if x.isdigit()] or list(range(9, 23))
    SI = load_sido()

    def sido_of(pt):
        for nm, g in SI:
            if g.contains(pt):
                return nm
        return None

    for n in rounds:
        fp = GEO / f"district_{n}_geojson.json"
        if not fp.exists():
            continue
        d = json.loads(fp.read_text(encoding="utf-8"))
        total_drop = 0
        rows = []
        for f in d["features"]:
            g = shape(f["geometry"])
            if g.geom_type != "MultiPolygon":
                continue
            props = f["properties"]
            nm = str(props.get("SIDO_SGG") or props.get("SGG") or "?")
            sido_prop = props.get("SIDO")
            home_full = SIDO_FULL.get(sido_prop) if sido_prop else None
            parts = sorted(g.geoms, key=lambda p: -p.area)
            if not home_full:
                home_full = sido_of(parts[0].representative_point())
            home = fam_of(home_full)
            keep = [parts[0]]  # 본체는 항상 보존
            for p in parts[1:]:
                s = sido_of(p.representative_point())
                if s is None:                       # 바다 섬
                    keep.append(p); continue
                if home and fam_of(s) == home:      # 동일 권역(도↔광역시 포함)
                    keep.append(p); continue
                # 오매칭 stray → drop
                total_drop += 1
                rows.append(f"{nm}[{sido_prop}]→{s} {p.area/parts[0].area*100:.0f}%")
            if len(keep) < len(parts):
                from shapely.geometry import MultiPolygon
                newg = keep[0] if len(keep) == 1 else MultiPolygon(keep)
                f["geometry"] = mapping(newg)
        if rows:
            print(f"{n}대 drop {total_drop}: {rows}")
        if apply and total_drop:
            fp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            print(f"  ✓ {fp.name} 갱신")


if __name__ == "__main__":
    main()
