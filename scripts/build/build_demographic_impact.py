#!/usr/bin/env python3
"""성×연령 '득표 기여' 데이터 — NEC 실측 투표자수 × 출구조사 득표구성.

우리 사이트 정신(추상 % 아닌 실제 크기): 성연령 칸 크기 = 실제 투표자수(NEC 실측),
칸 구성 = 후보 득표율(출구조사 추정). '몇 표를 줬나'(실제 영향)를 드러낸다.
  · voters  : NEC 투표율분석 표본 투표자수 (실측, 상대 크기 정확)
  · electors: NEC 선거인수 (인구)
  · turnout : 투표율
  · shares  : 출구조사 후보 득표율(추정, ±오차) — 합 100 미만(없음/기타 미배분)
  · votes   : voters × share (그 집단이 후보에게 준 표 추정)

입력: data/polls/turnout_demographics_<id>.json, data/exit_polls/demographics_<id>.json
출력: data/polls/demographic_impact_<id>.json
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BANDS = ["18-29", "30", "40", "50", "60", "70+"]
T2X = {"남자": "남성", "여자": "여성"}   # turnout(남자/여자) → exit(남성/여성)


def build(eid_short: str):
    turn = json.load(open(ROOT / f"data/polls/turnout_demographics_{eid_short}pres.json", encoding="utf-8"))
    ex = json.load(open(ROOT / f"data/exit_polls/demographics_{eid_short}pres.json", encoding="utf-8"))
    cells = []
    cand_votes = {}
    for tsex, xsex in T2X.items():
        for b in BANDS:
            tt = turn["전국"].get(tsex, {}).get(b)
            xx = ex["성연령"].get(xsex, {}).get(b)
            if not tt:
                continue
            shares = {c["name"]: c["pct"] for c in (xx or [])}
            parties = {c["name"]: c["party"] for c in (xx or [])}
            votes = {n: round(tt["voters"] * p / 100) for n, p in shares.items()}
            for n, v in votes.items():
                cand_votes[n] = cand_votes.get(n, 0) + v
            cells.append({
                "sex": xsex, "age": b,
                "electors": tt["electors"], "voters": tt["voters"], "turnout": tt["turnout"],
                "shares": [{"name": n, "party": parties[n], "pct": shares[n], "votes": votes[n]}
                           for n in shares],
            })
    out = {
        "_meta": {
            "election": eid_short, "kind": "demographic_impact",
            "size_source": "NEC 투표율분석(표본) 실측 투표자수 — 상대 크기",
            "fill_source": "위키백과 방송3사 심층 출구조사 — 득표 구성(추정)",
            "note": "칸 크기=실제 투표자수, 구성=출구조사. 출구조사는 ±오차 추정이라 합계는 실제와 소폭 차이.",
        },
        "total_voters": sum(c["voters"] for c in cells),
        "candidate_votes": dict(sorted(cand_votes.items(), key=lambda x: -x[1])),
        "cells": cells,
    }
    dst = ROOT / f"data/polls/demographic_impact_{eid_short}pres.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    return out, dst


def main():
    short = (sys.argv[1] if len(sys.argv) > 1 else "21")
    out, dst = build(short)
    print(f"→ {dst.name}: {len(out['cells'])} 셀, 투표자 {out['total_voters']:,}")
    print("  후보별 기여 추정:", {n: f"{v:,}" for n, v in out["candidate_votes"].items()})
    big = max(out["cells"], key=lambda c: c["voters"])
    sml = min(out["cells"], key=lambda c: c["voters"])
    print(f"  최대 셀: {big['age']} {big['sex']} 투표자 {big['voters']:,}")
    print(f"  최소 셀: {sml['age']} {sml['sex']} 투표자 {sml['voters']:,}")


if __name__ == "__main__":
    main()
