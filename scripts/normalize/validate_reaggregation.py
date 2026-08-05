"""엔진 외부 검증 — 경계가 안 바뀐 곳에서 direct와 reaggregated가 수렴하는가.

하남 같은 획정 변경 지역에서는 정답을 모른다. 재집계 값을 검산할 대상이 없기 때문이다.
그런데 **경계가 그대로인 선거구**에서는 두 값을 다 구할 수 있다.

    direct        공식 전체 득표율의 회차 간 차이          (분모 100%)
    reaggregated  동 귀속표 득표율의 회차 간 차이          (분모 ≈89%)

둘은 분모가 다르니 똑같을 수 없다. 하지만 제외표 편향이 회차 사이에 안정적이라면
그 차이는 상쇄되고 두 delta는 수렴해야 한다. 수렴하면 엔진이 맞다는 외부 근거가 되고,
**체계적으로 어긋나면** attributable 분모나 membership 처리에 또 다른 문제가 있다는
뜻이다 — 어느 쪽이든 우리가 몰랐던 것을 알려준다.

이건 획정이 바뀐 지역에서는 얻을 수 없는 control group이다.

사용: python scripts/normalize/validate_reaggregation.py 22 21
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/normalize"))
from reaggregate import ELECTION_DATE, _load, by_party, official, shares  # noqa: E402

OUT = ROOT / "data/reaggregated"
TOL_MEDIAN = 0.5     # 중앙값이 이보다 크면 계통 편차다
TOL_P90 = 1.5


def run(cur: int, prev: int) -> dict:
    lin = json.loads((ROOT / f"data/district_lineage/{cur}__{prev}.json")
                     .read_text(encoding="utf-8"))
    # 경계가 사실상 그대로인 곳만 — 여기서만 direct가 정답 노릇을 한다
    ctrl = {u["district"] for u in lin["units"]
            if u.get("reason_code") == "exact_overlap" and u.get("comparable") == "yes"}
    res = json.loads((OUT / f"{cur}__{prev}.json").read_text(encoding="utf-8"))["districts"]

    cb, pb = _load(cur, ""), _load(prev, "")
    coff, poff = official(cb), official(pb)
    cdate, pdate = ELECTION_DATE[cur], ELECTION_DATE[prev]

    rows = []
    for d in sorted(ctrl):
        v = res.get(d)
        if not v or v["method"] != "reaggregated":
            continue
        sw = v["swing_attributable_basis"]
        if not sw or d not in coff or d not in poff:
            continue
        # direct — 공식 전체끼리
        cs = shares(by_party([coff[d]], cdate))
        ps = shares(by_party([poff[d]], pdate))
        for p, r_delta in sw.items():
            if p not in cs or p not in ps:
                continue
            d_delta = cs[p] - ps[p]
            rows.append({"district": d, "party": p,
                         "direct": round(d_delta, 2),
                         "reaggregated": round(r_delta, 2),
                         "diff": round(r_delta - d_delta, 2)})
    if not rows:
        return {"pairs": 0}
    diffs = [abs(r["diff"]) for r in rows]
    signed = [r["diff"] for r in rows]
    diffs.sort()
    out = {
        "current": cur, "previous": prev,
        "control_districts": len({r["district"] for r in rows}),
        "pairs": len(rows),
        "abs_diff_median_pp": round(statistics.median(diffs), 3),
        "abs_diff_p90_pp": round(diffs[int(len(diffs) * 0.9)], 3),
        "abs_diff_max_pp": round(diffs[-1], 3),
        # 부호 있는 평균이 0에서 멀면 한쪽으로 쏠린 계통 오차다
        "signed_mean_pp": round(statistics.fmean(signed), 3),
        "converges": (statistics.median(diffs) <= TOL_MEDIAN
                      and diffs[int(len(diffs) * 0.9)] <= TOL_P90),
        "worst": sorted(rows, key=lambda r: -abs(r["diff"]))[:10],
        "_note": ("경계가 그대로인 선거구에서 direct(공식 전체)와 "
                  "reaggregated(동 귀속표)의 delta를 비교한다. 분모가 달라 똑같을 수는 "
                  "없고, 제외표 편향이 안정적이면 수렴한다. 계통 편차가 있으면 "
                  "분모나 membership 처리에 문제가 있다는 뜻이다."),
    }
    (OUT / f"validation_{cur}__{prev}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    r = run(int(a[0]), int(a[1]))
    if not r.get("pairs"):
        print("대조군 없음")
        sys.exit(0)
    print(f"\n대조군 {r['control_districts']}곳 · 정당쌍 {r['pairs']}")
    print(f"  |차이| 중앙값 {r['abs_diff_median_pp']}%p · p90 {r['abs_diff_p90_pp']}%p "
          f"· 최대 {r['abs_diff_max_pp']}%p")
    print(f"  부호 평균 {r['signed_mean_pp']}%p (0에서 멀면 계통 편차)")
    print(f"  {'✓ 수렴' if r['converges'] else '✗ 수렴하지 않는다 — 엔진을 의심하라'}")
    for w in r["worst"][:5]:
        print(f"    {w['district']:16} {w['party'][4:]:10} "
              f"direct {w['direct']:+6.2f}  reagg {w['reaggregated']:+6.2f}  "
              f"차 {w['diff']:+.2f}")
    sys.exit(0 if r["converges"] else 1)
