#!/usr/bin/env python3
"""지선 기초단체장 hex — 회차별 그 시점 시군구 레이아웃 (대선 period hex와 동형).

각 회차 기초장(sg_typecode 4) 시군구를 그 시점 집합으로 build_zone_hex 배치. 창원(마산·창원·
진해 분리, 1~4회)·청원(통합 전, 1~5회) 등 옛 행정구역 반영. 세종·제주(단층제, 기초장 없음)는
modern hex(sigungu_hex.json)에서 no-data 셀로 보강해 지도 연속성 유지(회색 표시).

출력: data/geo/sigungu_hex_local.json (회차→셀). render-sigungu가 지선 기초장에 사용.
"""
import json, re, sys, glob
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_pres_legacy_hex as bp   # resolve(), jachi()
import build_zone_hex

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"
RES = ROOT / "data/results"
ORD = {1: "1st", 2: "2nd", 3: "3rd"}   # 4회+ 는 {n}th
def canon(s):
    return {"강원도": "강원특별자치도", "전라북도": "전북특별자치도", "제주도": "제주특별자치도"}.get(s, s)


def round_files(n):
    pat = ORD.get(n, f"{n}th")
    return glob.glob(str(RES / f"{pat}-local-*.json"))


def build_cells(n):
    fs = round_files(n)
    if not fs:
        return None
    best = max(fs, key=lambda x: sum(1 for r in json.loads(Path(x).read_text(encoding="utf-8")).get("races", [])
                                     if r.get("sg_typecode") == "4" and r.get("scope") == "sigungu"))
    d = json.loads(Path(best).read_text(encoding="utf-8"))
    seen = {}
    for r in d["races"]:
        if r.get("sg_typecode") != "4" or r.get("scope") != "sigungu" or not r.get("sigungu"):
            continue
        sido = canon(r.get("sido"))   # 데이터 raw('강원도') → canon('강원특별자치도'); resultForSigungu·모던 일치
        nm = re.sub(r"\s*\([^)]*\)\s*$", "", r["sigungu"]).strip()  # 기초장은 갑/을 없음 — 괄호만
        key = (sido, nm)
        if key in seen:
            continue
        seen[key] = {"sido": sido, "name": nm, "_cen": list(bp.resolve(sido, nm) or ())}
    cells = [c for c in seen.values() if c["_cen"]]
    if len(cells) < 20:
        return None
    # 단층제(기초장 없는 시도) no-data 보강 — 그 회차에 실재한 것만(세종 6회+·제주 단층 4회+).
    have_sido = {c["sido"] for c in cells}
    modern = json.loads((GEO / "sigungu_hex.json").read_text(encoding="utf-8"))
    simple = {str(f["properties"].get("code")): bp.centroid(f["geometry"])
              for f in json.loads((GEO / "sigungu_simple.json").read_text(encoding="utf-8")).get("features", [])}
    for c in modern:
        sido = canon(c.get("sido"))
        # 진짜 단층제(기초장 없는 시도)만 보강 — 세종·제주. 울산 등 광역시는 자치구 기초장이 있어
        # 데이터에서 옴(미승격 회차엔 옛 도 소속으로 데이터에 있음).
        if sido not in ("세종특별자치시", "제주특별자치도"):
            continue
        if sido in have_sido:               # 그 회차에 기초장 있음(제주 1~3회) — 보강 불필요
            continue
        if sido == "세종특별자치시" and n < 6:   # 세종 2012 — 1~5회엔 없음(연기군=충남, 데이터에 있음)
            continue
        cen = simple.get(str(c.get("code")))
        if cen:
            cells.append({"sido": sido, "name": c["name"], "_cen": list(cen)})
    return cells


def main():
    want = [int(a) for a in sys.argv[1:]] or list(range(1, 10))
    combined = {}
    for n in want:
        cells = build_cells(n)
        if not cells:
            print(f"{n}회: 기초장 데이터 없음/부족 — skip")
            continue
        per = GEO / f"_local_tmp_{n}.json"
        per.write_text(json.dumps(cells, ensure_ascii=False))
        info = build_zone_hex.process(per, dry=False, backup=False)
        packed = json.loads(per.read_text(encoding="utf-8"))
        per.unlink()
        out = [{"sido": c["sido"], "name": c["name"], "c": c["c"], "r": c["r"]} for c in packed if "c" in c]
        combined[str(n)] = out
        print(f"{n}회: {len(out)}셀 → {info['bbox']}")
    (GEO / "sigungu_hex_local.json").write_text(json.dumps(combined, ensure_ascii=False, indent=2))
    print(f"\n통합: sigungu_hex_local.json ({len(combined)}개 회차)")


if __name__ == "__main__":
    main()
