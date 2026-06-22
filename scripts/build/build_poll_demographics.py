#!/usr/bin/env python3
"""여론조사 성×연령 '추이' served 데이터 — 회차별 폴 크로스탭 + 날짜 + 출구조사 최종치.

입력:
  data/raw/parsed/pres_demographics_<id>.json  (extract_pres_demographics, ntt→성연령)
  data/polls/aggregated_<id>.json               (ntt→period_end, agency)
  data/exit_polls/demographics_<id>.json        (출구조사 성연령 최종 — 추이 끝 ◆ 비교)
출력:
  data/polls/poll_demographics_<id>.json
    { _meta, cells: { "남성|18-29": [{date, agency, c:[{name,party,pct}]}], ... },
      exit: { "남성|18-29": [{name,party,pct}], ... } }

성×연령 그리드만(성별·연령 단독은 후속). 단일기관 위주라 추이가 house-effect로 안 섞임.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGES = ["18-29", "30", "40", "50", "60", "70+"]
SEXES = ["남성", "여성"]


def build(short: str):
    raw = json.load(open(ROOT / f"data/raw/parsed/pres_demographics_{short}pres.json", encoding="utf-8"))
    agg = json.load(open(ROOT / f"data/polls/aggregated_{short}pres.json", encoding="utf-8"))
    meta = {str(p.get("ntt_id")): (p.get("period_end"), p.get("agency")) for p in agg["polls"]}

    # 3차원 시계열: 성×연령 그리드(좁음) + 성별(남/여) + 연령(넓음). 키 형식:
    #   성연령="남성|18-29" · 성별="성별|남성" · 연령="연령|30"
    cells = {f"{s}|{a}": [] for s in SEXES for a in AGES}
    for s in SEXES:
        cells[f"성별|{s}"] = []
    for a in AGES:
        cells[f"연령|{a}"] = []
    agencies = set()
    for ntt, v in raw.items():
        d, ag = meta.get(str(ntt), (None, None))
        if not d:
            continue
        rec = lambda key, row: cells[key].append({"date": d, "agency": ag, "c": row}) or agencies.add(ag)
        grid = v.get("성연령", {})
        for s in SEXES:
            for a in AGES:
                row = grid.get(s, {}).get(a)
                if row:
                    rec(f"{s}|{a}", row)
        for s, row in (v.get("성별") or {}).items():
            if s in SEXES and row:
                rec(f"성별|{s}", row)
        for a, row in (v.get("연령") or {}).items():
            if a in AGES and row:
                rec(f"연령|{a}", row)
    for k in cells:
        cells[k].sort(key=lambda x: x["date"])

    exit_final = {}
    exp = ROOT / f"data/exit_polls/demographics_{short}pres.json"
    if exp.exists():
        ex = json.load(open(exp, encoding="utf-8"))
        for s in SEXES:
            for a in AGES:
                row = ex.get("성연령", {}).get(s, {}).get(a)
                if row:
                    exit_final[f"{s}|{a}"] = row
        for s, row in (ex.get("성별") or {}).items():
            if row:
                exit_final[f"성별|{s}"] = row
        for a, row in (ex.get("연령") or {}).items():
            if row:
                exit_final[f"연령|{a}"] = row

    npts = sum(len(v) for v in cells.values()) // (len(SEXES) * len(AGES)) if cells else 0
    out = {
        "_meta": {"election": short, "kind": "poll_demographics_trend",
                  "agencies": sorted(a for a in agencies if a),
                  "note": "여론조사 성×연령 후보지지 추이. 그리드 추출된 폴만(단일기관 위주). "
                          "끝점 ◆=방송3사 출구조사 최종."},
        "cells": cells,
        "exit": exit_final,
    }
    dst = ROOT / f"data/polls/poll_demographics_{short}pres.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    return out, dst, npts


def main():
    short = sys.argv[1] if len(sys.argv) > 1 else "21"
    out, dst, npts = build(short)
    print(f"→ {dst.name}: 셀당 ~{npts}점, 기관 {out['_meta']['agencies']}")
    c = out["cells"]["남성|18-29"]
    if c:
        print(f"  남성 18-29 추이 {len(c)}점: {c[0]['date']} ~ {c[-1]['date']}")
        print("    첫:", {x['name']: x['pct'] for x in c[0]['c']})
        print("    끝:", {x['name']: x['pct'] for x in c[-1]['c']})
        if out["exit"].get("남성|18-29"):
            print("    출구조사:", {x['name']: x['pct'] for x in out["exit"]["남성|18-29"]})


if __name__ == "__main__":
    main()
