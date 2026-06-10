"""scrape된 옛 대선 13~15 시도별 득표(data/raw/nec/pres_old_sido_{n}.json)를
생산 대선 결과에 scope=sido race(sg_typecode=1)로 추가.

기존 13~15 대선 결과는 nation(전국 합산)만 있어 시도 격자/dorling/margin(비례) 뷰가 불가했음.
시도별 race 추가로 16~21회처럼 비례 시도뷰 enable (승자독식 단색 아님 — 비례 표시용).

사용: python3 scripts/build/patch_pres_old_sido.py
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data/results"
RAW = ROOT / "data/raw/nec"
ELECTION_ID = {13: "13th-pres-1987", 14: "14th-pres-1992", 15: "15th-pres-1997"}


def main():
    for n, eid in ELECTION_ID.items():
        raw = json.loads((RAW / f"pres_old_sido_{n}.json").read_text(encoding="utf-8"))
        rp = RESULTS / f"{eid}.json"
        d = json.loads(rp.read_text(encoding="utf-8"))
        races = d.get("races", [])
        # 기존 시도 race 제거(재실행 멱등) 후 추가
        races = [r for r in races if not (r.get("sg_typecode") == "1" and r.get("scope") == "sido")]
        added = 0
        for sido, e in raw.items():
            cs = sorted(e["candidates"], key=lambda c: -c["votes"])
            tot = sum(c["votes"] for c in cs) or 1
            cands = []
            for rank, c in enumerate(cs, 1):
                cands.append({"name": c["name"], "party": c["party"], "votes": c["votes"],
                              "pct": round(c["votes"] / tot * 100, 1), "rank": rank, "won": rank == 1})
            races.append({
                "sg_typecode": "1", "sido": sido, "sigungu": "", "scope": "sido",
                "electors": e.get("electors", 0), "voters": e.get("voted", 0),
                "valid_votes": tot, "candidates": cands,
            })
            added += 1
        d["races"] = races
        d.setdefault("_meta", {})["sido_source"] = "nec-개표현황(VCCP09) 시도별"
        rp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{n}대({eid}): 시도 race {added}개 추가")


if __name__ == "__main__":
    main()
