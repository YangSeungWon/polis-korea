"""데이터 신선도 판정 — '최근 데이터 없음'과 '수집 실패'는 다르다.

null ≠ 0, 무투표 ≠ 결손과 같은 계열이다. 경과일만 보면 **예정된 휴간이 지연으로**
잡힌다. 실제로 한국갤럽 2026년 여름 휴가철 2주 휴간(7/27~8/7)이 'stale'로 울렸다.

상태를 다섯으로 가른다:
  fresh          다음 예정일이 아직 안 왔다
  expected_pause 원출처가 쉬는 기간 — 결함이 아니다
  manual_refresh 원출처가 CI 러너 IP를 차단 — 로컬에서 돌려야 한다
  overdue        예정일이 지났는데 안 들어왔다 — 봐야 한다
  fetch_failed   파일 자체가 없다

기관 달력을 거대한 시스템으로 만들지 않는다. **지금 확인 가능한 예외만** 고정한다.

실행: .venv/bin/python tests/test_freshness.py
"""
from __future__ import annotations
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/audit"))
from health import in_pause, next_expected, PAUSES, CI_BLOCKED, REFRESH_TARGETS  # noqa: E402

fails: list[str] = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    D = date.fromisoformat

    # ── 갤럽 여름 휴간 (공식 일정) ──────────────────────────────────────────
    # https://www.gallup.co.kr/company/noticeContents.asp?seqNo=10330
    print("\n[갤럽] 2026 여름 휴가철 휴간 7/27~8/7")
    ck("휴간 첫날이 휴간으로 잡힌다", in_pause("gallup", D("2026-07-27")) is not None)
    ck("휴간 마지막날이 휴간으로 잡힌다", in_pause("gallup", D("2026-08-07")) is not None)
    ck("휴간 하루 전은 아니다", in_pause("gallup", D("2026-07-26")) is None)
    ck("휴간 다음날은 아니다", in_pause("gallup", D("2026-08-08")) is None)
    ck("다른 기관엔 갤럽 휴간이 적용되지 않는다",
       in_pause("realmeter", D("2026-07-30")) is None)
    ck("휴간이 없는 기관은 항상 통과", in_pause(None, D("2026-07-30")) is None)

    # 예정일이 휴간을 건너뛰는가 — 이게 '예정된 휴간을 지연으로 부르지 않는' 핵심이다
    print("\n[예정일] 휴간을 건너뛴다")
    nxt = next_expected(D("2026-07-25"), 10, "gallup")
    ck(f"7/25 + 10일 → 8/8 (휴간 넘김, 실제 {nxt})", nxt == D("2026-08-08"), str(nxt))
    nxt2 = next_expected(D("2026-07-25"), 10, None)
    ck(f"휴간 없는 기관은 그대로 8/4 (실제 {nxt2})", nxt2 == D("2026-08-04"), str(nxt2))
    # 휴간 안에 떨어지지 않으면 밀지 않는다
    nxt3 = next_expected(D("2026-06-01"), 10, "gallup")
    ck(f"휴간과 무관한 날짜는 그대로 (실제 {nxt3})", nxt3 == D("2026-06-11"), str(nxt3))

    # ── CI 차단 소스 ────────────────────────────────────────────────────────
    print("\n[CI 차단] 우리 결함도 외부 지연도 아니다")
    ck("리얼미터가 CI 차단 목록에 있다", "realmeter" in CI_BLOCKED)
    ck("갤럽은 CI 차단이 아니다", "gallup" not in CI_BLOCKED)
    wf = (ROOT / ".github/workflows/tracker-refresh.yml").read_text(encoding="utf-8")
    ck("워크플로에도 차단 사실이 적혀 있다", "러너 IP를 차단" in wf)

    # ── 현재 상태가 실제로 갈리는가 ─────────────────────────────────────────
    print("\n[현재] 상태 분포")
    from health import data_freshness
    fresh = data_freshness()
    states = {f["label"]: f["state"] for f in fresh}
    for k, v in states.items():
        print(f"    {k:18} {v}")
    ck("모든 대상이 판정된다", len(fresh) == len(REFRESH_TARGETS))
    ck("상태가 정의된 다섯 중 하나",
       all(f["state"] in {"fresh", "expected_pause", "manual_refresh",
                          "overdue", "fetch_failed"} for f in fresh),
       str(states))
    # 갤럽 휴간이 overdue로 잡히면 모델이 되돌아간 것이다
    gal = [f for f in fresh if "갤럽" in f["label"]]
    ck("갤럽이 overdue로 잡히지 않는다 (휴간 반영)",
       all(f["state"] != "overdue" for f in gal),
       str({f["label"]: f["state"] for f in gal}))

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
