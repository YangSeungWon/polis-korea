"""무투표(unopposed) race의 candidate 채움 — NEC roster에서 lookup.

NEC live API는 MUTU_SGG=Y 시군구에 후보 정보를 안 줌 (vote count 없음).
race shell만 emit되고 candidates=[]. 메인 카드 정당 카운트에서 누락.

이 스크립트가 data/raw/nec_roster_9th.json (build_polls 등에서 이미
populate한 roster)에서 sido+sgg 기준으로 무투표 당선자 찾아 채움.

사용:
  .venv/bin/python scripts/build/backfill_unopposed.py
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="data/results/9th-local-2026.json")
    ap.add_argument("--roster", default="data/raw/nec_roster_9th.json")
    args = ap.parse_args()
    rp = ROOT / args.results
    roster_p = ROOT / args.roster
    d = json.loads(rp.read_text(encoding="utf-8"))
    roster = json.loads(roster_p.read_text(encoding="utf-8"))

    # roster 인덱스: (sd, sgg, sg_typecode) → [(name, party), ...]
    idx: dict[tuple, list] = {}
    for full_key, v in roster.items():
        if not v:
            continue
        name = full_key.split("|", 1)[1] if "|" in full_key else None
        if not name:
            continue
        k = (v.get("sd", ""), v.get("sgg", ""), v.get("sg_typecode", ""))
        idx.setdefault(k, []).append((name, v.get("jd", "") or "무소속"))

    filled = 0
    for race in d.get("races", []):
        if not race.get("unopposed") or race.get("candidates"):
            continue
        tc = race.get("sg_typecode", "")
        key = (race.get("sido", ""), race.get("sigungu", ""), tc)
        cands = idx.get(key)
        if not cands:
            print(f"  ! 매칭 실패: {key}")
            continue
        # 무투표는 보통 1명. 여러 명이면 첫 번째.
        name, party = cands[0]
        race["candidates"] = [{
            "name": name, "party": party, "votes": 0, "pct": 0.0,
            "rank": 1, "won": True,
        }]
        print(f"  + {race['sido']} {race['sigungu']} → {name} ({party})")
        filled += 1
    print(f"backfilled: {filled}")
    rp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
