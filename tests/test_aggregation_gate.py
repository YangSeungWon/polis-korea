"""집계 게이트 — 정확한 부분집합을 전체처럼 쓰지 않는가.

`comparable == "yes"`는 **그 선거구 하나의 delta를 계산할 수 있다**는 뜻일 뿐,
그 부분집합을 합친 값이 전국을 대표한다는 뜻이 아니다.

비교 가능한 곳은 경계가 안정적인 곳이고 제외되는 곳은 재획정이 많은 도시권에 몰린다.
선거구 계보를 고치기 전 22↔21 실측에서 1위 정당 구성이 민주당 -5.5%p / 국민의힘
+6.1%p 기울었다 — **측정하려는 swing(±4%p)보다 편향이 컸다.** 계보가 좋아진 지금
그 편차는 0.9%p로 내려갔고, 차단은 세종 coverage 0%가 이어받았다.
**그래서 검사는 특정 수치가 아니라 '적힌 사유가 기록된 수치에서 나오는가'를 본다.**

그래서 경고 문구로 해결하지 않는다. 대표성이 검증되지 않으면 **집계 지표를 만들지
않는다.** 값이 존재하면 결국 어딘가에서 전국 지표로 쓰인다.

  null ≠ 0 · '최근 데이터 없음' ≠ '수집 실패' · **정확한 부분집합 ≠ 대표 가능한 전체**

실행: .venv/bin/python tests/test_aggregation_gate.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CMP = ROOT / "data/comparisons/general"
AGG_KEYS = ("party_swing_in_compared", "turnout_in_compared", "biggest_moves")
fails: list[str] = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    # national__ 은 전국 집계라 units가 없다 — 층이 다르므로 여기서 보지 않는다.
    files = sorted(p for p in CMP.glob("*__*.json")
                   if not p.name.startswith("national__")) if CMP.exists() else []
    ck(f"총선 비교 파일이 있다 ({len(files)})", bool(files))

    for fp in files:
        d = json.loads(fp.read_text(encoding="utf-8"))
        tag = fp.stem[:24]
        print(f"\n[{tag}]")

        # ── 게이트가 존재하고 근거를 남기는가 ──────────────────────────────
        ck("aggregation_allowed가 있다", "aggregation_allowed" in d)
        ck("coverage 감사 결과가 있다", "coverage" in d)
        cov = d.get("coverage") or {}
        for k in ("districts", "electorate", "metro_share", "by_winning_party", "by_sido"):
            ck(f"coverage.{k}", k in cov)

        allowed = d.get("aggregation_allowed")
        if not allowed:
            ck("차단 사유가 적혀 있다", bool(d.get("aggregation_blocked_because")))
            # **핵심**: 차단되면 집계 키가 아예 없어야 한다. 있으면 언젠가 쓰인다.
            leaked = [k for k in AGG_KEYS if k in d]
            ck("차단 시 집계 지표가 생성되지 않았다", not leaked, str(leaked))
        else:
            ck("허용 시 집계 지표가 있다", any(k in d for k in AGG_KEYS))

        # ── unit-level은 게이트와 무관하게 유효하다 ────────────────────────
        # 개별 선거구 delta는 그 선거구 안에서 완결된 사실이다.
        with_delta = [u for u in d["units"] if u.get("share_delta")]
        ck(f"개별 선거구 delta는 남아 있다 ({len(with_delta)}곳)", bool(with_delta))
        bad = [u["district"] for u in with_delta if u["comparable"] != "yes"]
        ck("비교 불가 단위에는 delta가 없다", not bad, str(bad[:3]))

        # ── 차단 사유가 기록된 숫자에서 실제로 나오는가 ────────────────────
        # 예전엔 '22↔21은 1위 정당 구성 ±6%p라서 차단'을 상수로 박아 뒀다. 그런데
        # 선거구 계보가 좋아져 비교 가능 선거구가 215→237로 늘자 그 편차는 0.9%p로
        # 내려갔고(차단은 세종 coverage 0%로 유지), **사실이 나아졌는데 검사가 실패**했다.
        # 그러니 특정 수치가 아니라 사유와 수치의 대응을 본다.
        if "22nd" in fp.stem:
            ck("22↔21은 집계가 차단된다", allowed is False,
               str(d.get("aggregation_blocked_because")))
            skews = {p: v["skew_pp"] for p, v in cov["by_winning_party"].items()}
            ck("정당 구성 편차가 기록돼 있다", bool(skews), str(skews))
        for why in (d.get("aggregation_blocked_because") or []):
            if "선거인 coverage" in why:
                ok, ev = cov["electorate"]["pct"] < 90, cov["electorate"]["pct"]
            elif "1위 정당 구성 편차" in why:
                ev = max((abs(v["skew_pp"]) for v in cov["by_winning_party"].values()),
                         default=0)
                ok = ev > 3.0
            elif "미만 시도" in why:
                thin = {s: b["pct"] for s, b in cov["by_sido"].items() if b["pct"] < 30}
                ok, ev = bool(thin), thin
            else:
                ok, ev = False, "알 수 없는 사유 형식"
            ck(f"차단 사유가 수치와 맞는다 — {why[:34]}", ok, str(ev))

    # ── 생성기에 게이트가 하드코딩으로 우회되지 않았는가 ──────────────────
    print("\n[생성기]")
    src = (ROOT / "scripts/build/build_general_comparison.py").read_text(encoding="utf-8")
    ck("aggregation_gate를 호출한다", "aggregation_gate(" in src)
    ck("게이트 실패 시 빈 dict를 쓴다", "if allowed else {}" in src)
    ck("문구가 아니라 모델에서 막는다는 걸 명시", "경고 문구로 대신하지 않는다" in src)

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
