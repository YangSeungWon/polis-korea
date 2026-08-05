"""비교 불가로 남은 선거구가 **왜** 불가인지 전부 설명한다.

좋은 산출물은 '비교 가능 196 → 241' 같은 숫자가 아니라, 남은 비교 불가 단위가
하나도 빠짐없이 분류돼 있는 상태다. 그래야 다음 선거에서도 유지보수가 된다.
분류되지 않은 잔여가 있으면 그건 우리가 모르는 것이 있다는 뜻이고, 숫자를 늘리는
것보다 그 사실을 드러내는 게 먼저다.

유형은 발견된 것만 적는다. 새 유형이 나오면 여기에 추가하고, `unclassified`가
0이 아니면 실패로 다룬다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIN = ROOT / "data/district_lineage"
OUT = ROOT / "data/district_lineage"

# 코드 → (한 줄 설명, 더 손쓸 수 있는가)
TAXONOMY = {
    "crossing_dong": (
        "과거 읍면동이 현 선거구 경계를 가로지른다 — 동 단위로 나눌 수 없다. "
        "투표구 단위 경계 자료가 있어야 더 내려간다.", "needs_precinct_geometry"),
    "bias_unstable": (
        "재집계는 되지만 제외표(관외사전·국외부재자) 편향이 회차 사이에 흔들려 "
        "변화량을 주장할 수 없다. 대개 한쪽 회차에 구도가 크게 달라진 곳이다.", "no"),
    "partial_fetch": (
        "선거구가 여러 시군구에 걸치는데 일부만 회수됐다 — 회수하면 풀린다.",
        "refetch"),
    "no_reaggregation_attempted": (
        "읍면동 실측 원자료를 아직 회수하지 않았다.", "fetch"),
    "no_predecessor": (
        "대응하는 이전 선거구가 없다(신설). 비교 대상 자체가 없다.", "no"),
    "scattered_overlap": (
        "겹침이 여러 곳으로 흩어져 전신을 하나로 정할 수 없다.",
        "needs_precinct_geometry"),
    "geometry_source_mismatch": (
        "폴리곤 출처가 달라 실제 경계 변화인지 정밀도 차이인지 못 가른다.",
        "align_pipeline"),
}


def classify(u: dict) -> str:
    """비교 불가 단위 하나의 사유. 모르면 빈 문자열 — 조용히 채우지 않는다."""
    r = u.get("reaggregation") or {}
    p = r.get("method")
    if p == "context_only":
        if r.get("blocked_by", "").startswith("선거구 일부만"):
            return "partial_fetch"
        return "crossing_dong"
    if p == "reaggregated":
        # 재집계는 됐는데 변화량을 못 낸 경우
        return "bias_unstable"
    code = u.get("reason_code") or ""
    if code in TAXONOMY:
        return code
    if code in ("boundary_moved", "split_from_previous", "merged_into_current",
                "renamed_same_area", "exact_overlap"):
        return "no_reaggregation_attempted"
    return ""


def report(pair: str) -> dict:
    f = LIN / f"{pair}.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    blocked = [u for u in d["units"] if u.get("comparable") != "yes"]
    by: dict = {}
    for u in blocked:
        by.setdefault(classify(u), []).append(u["district"])
    unclassified = by.pop("", [])
    return {
        "pair": pair,
        "total": d["counts"]["total"],
        "comparable": d["counts"]["comparable"],
        "blocked": len(blocked),
        "by_cause": {k: {"count": len(v),
                         "meaning": TAXONOMY[k][0],
                         "actionable": TAXONOMY[k][1],
                         "districts": sorted(v)}
                     for k, v in sorted(by.items(), key=lambda x: -len(x[1]))},
        "unclassified": sorted(unclassified),
    }


def main() -> int:
    pairs = [f.stem for f in sorted(LIN.glob("*__*.json"))]
    out, bad = {}, 0
    for p in pairs:
        r = report(p)
        out[p] = r
        print(f"\n[{p}] 전체 {r['total']} · 비교 가능 {r['comparable']} · 불가 {r['blocked']}")
        for k, v in r["by_cause"].items():
            print(f"    {v['count']:4}  {k:28} ({v['actionable']})")
        if r["unclassified"]:
            bad += len(r["unclassified"])
            print(f"    ✗ 분류 안 됨 {len(r['unclassified'])}: "
                  f"{', '.join(r['unclassified'][:5])}")
    (OUT / "blocked_taxonomy.json").write_text(
        json.dumps({"_note": ("비교 불가 단위의 사유 전수 분류. unclassified가 0이 "
                              "아니면 우리가 모르는 유형이 있다는 뜻이다."),
                    "pairs": out}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print(f"\n{'✗ 미분류 ' + str(bad) if bad else '✓ 비교 불가 사유가 전부 분류됨'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
