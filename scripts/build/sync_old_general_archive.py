"""3·4·5대 총선 — 별표 통합 결과(national_assembly_{n})를 페이지가 로드하는 아카이브
({ordinal}-general-{year}.json)에 동기화.

history 페이지는 newSchemaPath로 아카이브를 로드하는데, 별표 통합(실제 선거구명·시군·제주
backfill·정담→정준)은 national_assembly_{n}에만 적용돼 있었음 → 지도(아카이브 제N선거구) vs
hex/geo(national 실제명) 이름 불일치로 색 매칭 실패. 아카이브의 district명을 실제명으로,
제주 race도 추가해 일치시킨다. (geo _map·hex는 이미 national 실제명 기반)

조인 키: national_assembly의 sg_no(원래 제N) ↔ 아카이브 district. 시도는 canon으로 정규화.
재현: python scripts/build/sync_old_general_archive.py
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "data" / "results"
IDS = {3: ("3rd", 1954), 4: ("4th", 1958), 5: ("5th", 1960)}
CANON = {"강원특별자치도": "강원도", "전북특별자치도": "전라북도", "제주특별자치도": "제주도"}


def cs(s):
    return CANON.get(s, s)


def sync(n, ordinal, year):
    na = json.loads((RES / f"national_assembly_{n}.json").read_text(encoding="utf-8"))["district"]
    arcpath = RES / f"{ordinal}-general-{year}.json"
    doc = json.loads(arcpath.read_text(encoding="utf-8"))
    races = doc["races"]
    # national index: (canon 시도, 제N) → race
    by_no = {(cs(r["sido"]), r.get("sg_no")): r for r in na if r.get("sg_no")}
    jeju = [r for r in na if cs(r["sido"]) == "제주도"]
    renamed = 0
    for race in races:
        if race.get("scope") != "district" or str(race.get("sg_typecode")) != "2":
            continue
        nar = by_no.get((cs(race["sido"]), race.get("district")))
        if nar:
            race["district"] = nar["name"]              # 제N선거구 → 실제 선거구명
            if nar.get("sigungu_area"):
                race["sigungu_area"] = nar["sigungu_area"]
            race["candidates"] = nar.get("candidates", race.get("candidates", []))  # 정준 등 수정 반영
            renamed += 1
    # 제주 backfill — 아카이브에 없던 제주 race 추가(실제명)
    jadd = 0
    have = {(cs(r["sido"]), r.get("district")) for r in races if r.get("scope") == "district"}
    for jr in jeju:
        if (cs(jr["sido"]), jr["name"]) in have:
            continue
        races.append({
            "sg_typecode": "2", "scope": "district", "sido": "제주도",
            "district": jr["name"], "sigungu_area": jr.get("sigungu_area", []),
            "electors": jr.get("electors", 0), "voters": jr.get("voters", 0),
            "valid_votes": sum(c.get("votes", 0) for c in jr.get("candidates", [])),
            "invalid_votes": 0, "candidates": jr.get("candidates", []),
            "backfill": jr.get("backfill"),
        })
        jadd += 1
    arcpath.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{n}대: 실제명 동기화 {renamed} + 제주 추가 {jadd} → {arcpath.name}", file=sys.stderr)


if __name__ == "__main__":
    for n, (o, y) in IDS.items():
        sync(n, o, y)
