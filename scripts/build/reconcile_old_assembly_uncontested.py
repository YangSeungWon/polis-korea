"""VCCP09(개표현황)는 무투표 당선 선거구를 제외(개표가 없음) → 당선인 명부에서 보충.

fetch_old_assembly_vccp.mjs로 받은 archive(전체 후보)에, 기존 명부(national_assembly_N)에만
있고 archive엔 없는 선거구 = 무투표 당선 → is_uncontested로 archive에 주입. archive_to_assembly
실행 전에 돌려야 함(명부가 원본일 때). 멱등: 이미 주입됐으면 누락 없음.

사용: python3 scripts/build/reconcile_old_assembly_uncontested.py
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "data" / "results"
IDS = {9: "9th-general-1973", 10: "10th-general-1978", 11: "11th-general-1981",
       12: "12th-general-1985", 13: "13th-general-1988"}


def reconcile(n, aid):
    arc_path = RES / f"{aid}.json"
    roster_path = RES / f"national_assembly_{n}.json"
    if not arc_path.exists() or not roster_path.exists():
        print(f"{n}대: 파일 없음 — skip")
        return
    arc = json.loads(arc_path.read_text(encoding="utf-8"))
    roster = json.loads(roster_path.read_text(encoding="utf-8")).get("district", [])
    have = {(r["sido"], r.get("district")) for r in arc["races"]
            if r.get("scope") == "district" and str(r.get("sg_typecode")) == "2"}
    added = 0
    for d in roster:
        key = (d["sido"], d.get("name"))
        if key in have:
            continue
        cands = [{"name": c["name"], "party": c.get("party"), "votes": 0, "pct": None,
                  "rank": c.get("rank"), "won": True, "uncontested": True}
                 for c in d.get("candidates", [])]
        arc["races"].append({
            "sg_typecode": "2", "scope": "district", "sido": d["sido"], "name": d.get("name"),
            "district": d.get("name"), "electors": 0, "voters": 0, "valid_votes": 0,
            "invalid_votes": 0, "is_uncontested": True, "candidates": cands,
        })
        added += 1
    if added:
        arc_path.write_text(json.dumps(arc, ensure_ascii=False, indent=1), encoding="utf-8")
    n_dist = sum(1 for r in arc["races"] if r.get("scope") == "district" and str(r.get("sg_typecode")) == "2")
    print(f"{n}대: 무투표 {added}곳 주입 → 지역구 {n_dist}")


if __name__ == "__main__":
    for n, aid in IDS.items():
        reconcile(n, aid)
