"""golden test runner — tests/golden/*.json의 expected와 parse_from_grids 결과 diff.

사용:
    .venv/bin/python tests/test_golden.py             # diff 보임 (fail 시 비-zero)
    .venv/bin/python tests/test_golden.py --update    # 차이 보고 → golden 갱신 (검증 후만)

PDF parse 룰 변경 후 회귀 검출용. 각 golden = (양식, ntt, expected questions·candidates).
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRIDS = ROOT / "data/raw/grids"
GOLDEN = ROOT / "tests/golden"
sys.path.insert(0, str(ROOT / "scripts"))
from parse_pdf_v2 import parse_from_grids  # type: ignore


def cand_key(c):
    return (c.get("name", ""), c.get("party", ""), c.get("pct"))


def diff_questions(expected, actual):
    """questions 리스트 비교. (added, removed, changed) 반환."""
    exp_by_title = {q.get("title", ""): q for q in expected}
    act_by_title = {q.get("title", ""): q for q in actual}
    added = [t for t in act_by_title if t not in exp_by_title]
    removed = [t for t in exp_by_title if t not in act_by_title]
    changed = []
    for title in exp_by_title:
        if title not in act_by_title:
            continue
        exp_c = sorted(map(cand_key, exp_by_title[title].get("candidates", [])))
        act_c = sorted(map(cand_key, act_by_title[title].get("candidates", [])))
        if exp_c != act_c:
            changed.append((title, exp_c, act_c))
    return added, removed, changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="diff 있는 golden 갱신")
    args = ap.parse_args()

    golden_files = sorted(GOLDEN.glob("*.json"))
    if not golden_files:
        print("골든 없음. scripts/build/build_golden.py 먼저 실행.", file=sys.stderr)
        return 1

    n_pass = n_fail = 0
    for gp in golden_files:
        golden = json.load(open(gp, encoding="utf-8"))
        ntt = golden["ntt_id"]
        note = golden.get("note", "")
        grid_files = list(GRIDS.glob(f"{ntt}_*.json"))
        if not grid_files:
            print(f"  SKIP {ntt}: 격자 없음")
            continue
        # 풍부한 쪽 (질문지 vs 결과보고서)
        best = None
        for gf in grid_files:
            g = json.load(open(gf, encoding="utf-8"))
            r = parse_from_grids(g)
            score = sum(len(q.get("candidates", [])) for q in r.get("questions", []))
            if best is None or score > best[0]:
                best = (score, r)
        result = best[1]
        expected = golden.get("expected_questions", [])
        actual = result.get("questions", [])
        added, removed, changed = diff_questions(expected, actual)

        if not (added or removed or changed):
            n_pass += 1
            print(f"  PASS {ntt} — {note[:50]}")
            continue
        n_fail += 1
        print(f"\nFAIL {ntt} — {note}")
        if added:
            print(f"  + 추가된 questions ({len(added)}):")
            for t in added[:5]:
                print(f"     · {t[:60]!r}")
        if removed:
            print(f"  - 사라진 questions ({len(removed)}):")
            for t in removed[:5]:
                print(f"     · {t[:60]!r}")
        if changed:
            print(f"  ~ candidates 바뀐 questions ({len(changed)}):")
            for title, exp_c, act_c in changed[:3]:
                print(f"     title: {title[:50]!r}")
                exp_set = set(exp_c); act_set = set(act_c)
                only_exp = exp_set - act_set
                only_act = act_set - exp_set
                if only_exp: print(f"       expected only: {list(only_exp)[:5]}")
                if only_act: print(f"       actual only:   {list(only_act)[:5]}")

        if args.update:
            golden["expected_questions"] = actual
            with open(gp, "w", encoding="utf-8") as f:
                json.dump(golden, f, ensure_ascii=False, indent=2)
            print(f"  → updated {gp.name}")

    print(f"\n총 {n_pass} pass, {n_fail} fail")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
