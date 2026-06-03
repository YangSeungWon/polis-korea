"""지선 새 schema (Nth-local-YYYY.json)에 옛 schema (local_N.json)의 누락 시군구 백필.

이유: NEC API가 5/6/7/8회 일부 시군구 결과를 안 줌 (또는 일부 누락).
local_N.json은 옛 가공(OCR/scraping 포함)으로 287개 시군구 완비.
새 schema는 API만 사용해 220개 정도만 → 빈 셀 다수.

이 스크립트가 옛 schema에만 있는 시군구를 새 schema race로 변환해 추가.

사용:
  python3 scripts/merge_local_legacy_into_new.py [--rounds 5,6,7,8]
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SG_ID = {5: "20100602", 6: "20140604", 7: "20180613", 8: "20220601"}
DATE = {5: "2010-06-02", 6: "2014-06-04", 7: "2018-06-13", 8: "2022-06-01"}
ELECTION_ID = {n: f"{['','1st','2nd','3rd','4th','5th','6th','7th','8th'][n]}-local-{DATE[n].split('-')[0]}"
               for n in (5, 6, 7, 8)}
OFFICE_TC = {"광역단체장": "3", "기초단체장": "4", "교육감": "11"}


def to_race(rec: dict, tc: str, scope: str) -> dict:
    """옛 sigungu rec → 새 race format."""
    out = {
        "sg_id": "",  # 채워지지 않으나 schema 호환
        "sg_typecode": tc,
        "sido": rec.get("sido", ""),
        "scope": scope,
        "electors": rec.get("electors", 0) or 0,
        "voters": rec.get("voted", 0) or 0,
        "valid_votes": rec.get("voted", 0) or 0,
        "invalid_votes": rec.get("invalid", 0) or 0,
        "abstain": 0,
        "candidates": rec.get("candidates", []) or [],
    }
    # scope=sigungu(tc 3·11): sigungu = 시군구명. tc=4: 동일.
    out["sigungu"] = rec.get("name", "")
    return out


def merge(round_n: int) -> None:
    sg_id = SG_ID[round_n]
    eid = ELECTION_ID[round_n]
    new_path = ROOT / f"data/results/{eid}.json"
    old_path = ROOT / f"data/results/local_{round_n}.json"
    if not new_path.exists() or not old_path.exists():
        print(f"  {round_n}회: 파일 누락, skip")
        return
    new_data = json.loads(new_path.read_text(encoding="utf-8"))
    old_data = json.loads(old_path.read_text(encoding="utf-8"))
    races = new_data.get("races", [])
    added_total = 0
    for office, tc in OFFICE_TC.items():
        existing = {(r.get("sido"), r.get("sigungu"))
                    for r in races
                    if r.get("scope") == "sigungu" and r.get("sg_typecode") == tc}
        old_office = (old_data.get("offices") or {}).get(office) or {}
        added = 0
        for sg in old_office.get("sigungu", []) or []:
            key = (sg.get("sido"), sg.get("name"))
            if key in existing or not key[0] or not key[1]:
                continue
            race = to_race(sg, tc, "sigungu")
            race["sg_id"] = sg_id
            races.append(race)
            added += 1
        if added:
            print(f"  {round_n}회 {office}: +{added}개 백필")
        added_total += added
    if added_total:
        new_data["races"] = races
        meta = new_data.setdefault("_meta", {})
        meta["legacy_merge"] = (meta.get("legacy_merge") or "") + f"; merged {added_total} from local_{round_n}.json"
        new_path.write_text(
            json.dumps(new_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  → {new_path.name} 저장 (+{added_total} race)")
    else:
        print(f"  {round_n}회: 백필 불필요")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=str, default="5,6,7,8")
    args = ap.parse_args()
    for n in [int(x) for x in args.rounds.split(",")]:
        print(f"=== {n}회 ===")
        merge(n)


if __name__ == "__main__":
    main()
