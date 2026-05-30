"""build_polls + patch_* 단계 후 aggregated.json 회귀 검출.

tests/build_golden.json의 각 case = (ntt_id, office_level, sido, sigungu, expected_candidates).
aggregated.json에서 해당 ntt+office의 poll을 찾아 expected candidates와 비교한다.

비교:
- 후보 이름 정확 일치 (정상 한국 이름 가정)
- 정당 정확 일치 (단 매핑 차이 — 더불어민주당 vs 민주당은 같이 취급)
- pct는 ±tolerance 내 (PDF 추출 단계 round 오차 허용)

회귀 패턴 잡는 게 목적이라 모든 expected 후보가 actual에 있으면 PASS.
expected에 없는 추가 후보(actual 더 많음)는 WARN — race 자체는 정확.
expected에 있는데 actual에 없으면 FAIL — 누락.

사용:
  python3 tests/test_build_golden.py        # 전체 검사
  python3 tests/test_build_golden.py -v     # 자세히
  python3 tests/test_build_golden.py 18726  # 특정 ntt만
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests/build_golden.json"
AGG = ROOT / "data/polls/aggregated.json"

# 정당명 동의어 (build_polls의 norm 비대칭으로 같은 race 안에 혼재 가능)
_PARTY_EQ = {
    "더불어민주당": "더불어민주당", "민주당": "더불어민주당", "더민주": "더불어민주당",
    "국민의힘": "국민의힘", "국힘": "국민의힘",
    "조국혁신당": "조국혁신당", "조국혁신": "조국혁신당",
    "개혁신당": "개혁신당", "진보당": "진보당", "정의당": "정의당",
    "무소속": "무소속", "": "",
}


def _canon_party(p: str) -> str:
    return _PARTY_EQ.get(p, p)


def find_poll(polls: list, case: dict) -> dict | None:
    """ntt+office_level+sido+sigungu 매칭 poll."""
    for p in polls:
        if (p.get("ntt_id") == case["ntt"]
                and p.get("office_level") == case["office_level"]
                and p.get("sido", "") == case.get("sido", "")
                and p.get("sigungu", "") == case.get("sigungu", "")):
            return p
    return None


def compare(case: dict, poll: dict | None, tolerance: float) -> tuple[str, list[str]]:
    """(level, messages). level: PASS/WARN/FAIL."""
    if poll is None:
        return "FAIL", [f"poll 없음 — ntt={case['ntt']} {case['office_level']} {case.get('sido','')} {case.get('sigungu','')}"]
    actual_cands = {(c.get("name", ""), _canon_party(c.get("party", ""))): c.get("pct")
                    for c in poll.get("candidates", [])}
    expected_cands = case["expected"]
    msgs = []
    missing = []
    pct_off = []
    for ec in expected_cands:
        key = (ec["name"], _canon_party(ec.get("party", "")))
        if key not in actual_cands:
            # 정당 차이만 봐서 한 번 더 (이름만 일치)
            name_hit = [(n, p) for (n, p) in actual_cands if n == ec["name"]]
            if not name_hit:
                missing.append(f"{ec['name']}({ec.get('party','')}) {ec['pct']}")
                continue
            key = name_hit[0]
        actual_pct = actual_cands[key]
        if actual_pct is None:
            missing.append(f"{ec['name']} pct=None")
            continue
        if abs(actual_pct - ec["pct"]) > tolerance:
            pct_off.append(f"{ec['name']} expected={ec['pct']} actual={actual_pct}")
    if missing:
        msgs.append(f"누락 {len(missing)}: " + ", ".join(missing))
    if pct_off:
        msgs.append(f"pct 차이 {len(pct_off)}: " + ", ".join(pct_off))
    extra = [(n, p, v) for (n, p), v in actual_cands.items()
             if not any(n == ec["name"] for ec in expected_cands)]
    if extra:
        msgs.append(f"추가 후보 {len(extra)}: " + ", ".join(f"{n}({p}) {v}" for n, p, v in extra[:3]))

    if missing or pct_off:
        return "FAIL", msgs
    if extra:
        return "WARN", msgs
    return "PASS", msgs


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("filter_ntt", nargs="?", help="특정 ntt만 검사")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    golden = json.load(open(GOLDEN, encoding="utf-8"))
    tolerance = golden.get("_threshold", {}).get("pct_tolerance", 1.0)
    cases = golden["cases"]
    if args.filter_ntt:
        cases = [c for c in cases if c["ntt"] == args.filter_ntt]

    polls = json.load(open(AGG, encoding="utf-8"))["polls"]

    n_pass = n_warn = n_fail = 0
    for case in cases:
        poll = find_poll(polls, case)
        level, msgs = compare(case, poll, tolerance)
        marker = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}[level]
        print(f"  {marker} {level} {case['ntt']} — {case['case'][:55]}")
        if args.verbose or level != "PASS":
            for m in msgs:
                print(f"      {m}")
        if level == "PASS":
            n_pass += 1
        elif level == "WARN":
            n_warn += 1
        else:
            n_fail += 1

    print()
    print(f"총 {len(cases)} cases: {n_pass} pass, {n_warn} warn, {n_fail} fail")
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()
