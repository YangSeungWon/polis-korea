"""아카이브 결과({id}.json races) → history 포맷(national_assembly_{n}.json district 리스트).

옛 총선(13~16대 등) 선거구 지도용 — history geomap이 national_assembly_{n}.district를 읽음.
사용: python scripts/build/archive_to_assembly.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "data" / "results"

# n → 아카이브 id. 9~12대 중선거구(1구 2인) → winners[]. 5~8대 소선거구(시군구 union용).
IDS = {5: "5th-general-1960", 6: "6th-general-1963", 7: "7th-general-1967", 8: "8th-general-1971",
       9: "9th-general-1973", 10: "10th-general-1978",
       11: "11th-general-1981", 12: "12th-general-1985",
       13: "13th-general-1988", 14: "14th-general-1992",
       15: "15th-general-1996", 16: "16th-general-2000"}


def convert(n, aid):
    arc = json.loads((RES / f"{aid}.json").read_text(encoding="utf-8"))
    out = []
    for r in arc.get("races", []):
        if r.get("scope") != "district" or str(r.get("sg_typecode")) != "2":
            continue
        cands = r.get("candidates", [])
        won = [c for c in cands if c.get("won")]
        w = won[0] if won else (cands[0] if cands else None)
        rec = {
            "sido": r["sido"],
            "name": r.get("district") or r.get("sigungu"),
            "winner": w["name"] if w else None,
            "winner_party": w.get("party") if w else None,
            "candidates": cands,
        }
        # 선거구별 투표율 — archive에 electors/voters 있으면 통과(없으면 전국 fallback).
        electors, voters = r.get("electors") or 0, r.get("voters") or 0
        if electors:
            rec["electors"] = electors
            rec["voters"] = voters
            rec["turnout"] = round(voters / electors * 100, 1)
        if r.get("is_uncontested"):
            rec["is_uncontested"] = True
        if len(won) > 1:  # 중선거구(1구 2인) — 당선자 전원 보존
            rec["winners"] = [{"name": c["name"], "party": c.get("party")} for c in won]
        out.append(rec)
    dst = RES / f"national_assembly_{n}.json"
    dst.write_text(json.dumps({"_meta": {"source": f"archive {aid}", "from": "archive_to_assembly"},
                               "district": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{n}대: district {len(out)} → {dst.name}", file=sys.stderr)


def main():
    for n, aid in IDS.items():
        convert(n, aid)


if __name__ == "__main__":
    main()
