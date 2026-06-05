"""sigungu_hex.json vs NEC race set diff — 행정개편/fetch누락 둘 다 감지.

원칙: hex cells = 사람이 선언한 현행 행정구역 진실. NEC race = 검증자.
mismatch 두 종류:
  - hex만 있음 (NEC에 race 없음): 진짜 폐지 OR NEC fetch 누락 — 사람 판단.
  - NEC만 있음 (hex에 cell 없음): 신설 행정구 → hex에 추가 필요.

사용:
  .venv/bin/python scripts/audit/check_hex_vs_nec.py
  .venv/bin/python scripts/audit/check_hex_vs_nec.py --results data/results/9th-local-2026.json
exit 0 = 일치, 1 = mismatch.
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hex", default="data/geo/sigungu_hex.json")
    ap.add_argument("--results", default="data/results/9th-local-2026.json",
                    help="NEC 결과 JSON. tc=4 race를 sigungu 진실 set으로 사용.")
    args = ap.parse_args()

    hex_path = ROOT / args.hex
    res_path = ROOT / args.results

    hex_cells = json.loads(hex_path.read_text(encoding="utf-8"))
    res = json.loads(res_path.read_text(encoding="utf-8"))

    # single_tier: 세종·제주 단층 자치 — tc=4 race 자체 없음. 기초장 hex에서 제외 정상.
    hex_set = defaultdict(set)
    for c in hex_cells:
        if c.get("single_tier"):
            continue
        hex_set[c["sido"]].add(c["name"])
    nec_set = defaultdict(set)
    for r in res.get("races", []):
        if r.get("sg_typecode") == "4":
            nec_set[r["sido"]].add(r.get("sigungu", ""))

    sidos = sorted(set(hex_set) | set(nec_set))
    mismatch = 0
    print(f"[check_hex_vs_nec] hex={hex_path.name} · results={res_path.name}\n")
    for sido in sidos:
        h, n = hex_set[sido], nec_set[sido]
        only_hex = sorted(h - n)
        only_nec = sorted(n - h)
        if not only_hex and not only_nec:
            continue
        mismatch += 1
        print(f"{sido}: hex={len(h)}, nec={len(n)}")
        if only_hex:
            print(f"  hex만 (폐지 or NEC fetch누락): {only_hex}")
        if only_nec:
            print(f"  nec만 (hex에 추가 필요): {only_nec}")
    if mismatch == 0:
        print("모든 시도 일치.")
        return 0
    print(f"\n{mismatch}개 시도 mismatch.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
