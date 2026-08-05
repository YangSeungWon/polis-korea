"""정당 identity resolver — 비교 연산이 전부 같은 문을 지나는가.

정당 문자열과 비교 identity는 다른 것이다. 분리하지 않으면 같은 버그가 연산마다
다르게 나타난다. 실제로 그랬다:
  · 승자 판정은 same_party, 득표 집계는 raw name → '국민의힘 +46%p / 미래통합당 -45%p'
    (둘은 개명인데 없는 변화가 만들어졌다)
  · '민중당'은 1965년 것과 2017년 것이 다른 당인데 한 덩어리로 세어졌다

**계보에 있다고 무조건 합산하지 않는다.** 합당·분당·선거연합은 표를 귀속시킬 근거가 없다.

실행: .venv/bin/python tests/test_party_identity.py
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/build"))
from party_identity import identity, policy, unregistered, display_name  # noqa: E402

G20, G24 = "2020-04-15", "2024-04-10"
fails: list[str] = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    # ── 개명은 같은 identity ────────────────────────────────────────────────
    print("\n[개명] 같은 당이 이름만 바꿨다")
    RENAMES = [
        ("미래통합당", G20, "국민의힘", G24, "2020.9 개명"),
        ("민중당", G20, "진보당", G24, "2020.6 개명 · 1965년 민중당과 다른 당"),
        ("한나라당", "2010-06-02", "새누리당", "2014-06-04", "2012.2 개명"),
    ]
    for a, da, b, db, why in RENAMES:
        ck(f"{a} ≡ {b} ({why})", identity(a, da) == identity(b, db),
           f"{identity(a, da)} vs {identity(b, db)}")
        ck(f"{a}→{b} 전이 = same", policy(a, da, b, db) == "same", policy(a, da, b, db))

    # ── 합당·분당은 잇지 않는다 ────────────────────────────────────────────
    print("\n[합당·분당] 표를 귀속시킬 근거가 없다")
    for a, b, why in [("더불어시민당", "더불어민주당", "위성정당 합당 — 유권자 선택 구조가 달랐다"),
                      ("열린민주당", "더불어민주당", "합당"),
                      ("정의당", "녹색정의당", "선거연합 성격 — registry에 관계 없음")]:
        ck(f"{a} ≢ {b} ({why})", identity(a, G20) != identity(b, G24),
           f"{identity(a, G20)} == {identity(b, G24)}")
        ck(f"{a}→{b} 전이가 same이 아니다", policy(a, G20, b, G24) != "same",
           policy(a, G20, b, G24))

    # ── 동음이의 ────────────────────────────────────────────────────────────
    print("\n[동음이의] 이름이 같아도 다른 당")
    ck("민중당 1965 ≠ 민중당 2017",
       identity("민중당", "1965-06-01") != identity("민중당", G20),
       f'{identity("민중당", "1965-06-01")} vs {identity("민중당", G20)}')

    # ── stable id는 화면에 안 나간다 ────────────────────────────────────────
    print("\n[라벨] 계보 대표를 화면에 쓰지 않는다")
    pid = identity("국민의힘", G24)
    ck("identity는 내부 접두사를 가진다 (화면용 아님)", pid.startswith("pid:"), pid)
    ck("display_name은 그 회차 이름", display_name(pid, {pid: "국민의힘"}) == "국민의힘")
    cmp_fp = ROOT / "data/comparisons/general/22nd-general-2024__21st-general-2020.json"
    if cmp_fp.exists():
        d = json.loads(cmp_fp.read_text(encoding="utf-8"))
        # 집계는 대표성 게이트를 통과할 때만 생성된다(test_aggregation_gate 참조).
        # identity가 새는지는 **unit-level share_delta**로 본다 — 그건 항상 있다.
        keys = sorted({k for u in d["units"] for k in (u.get("share_delta") or {})})
        ck("산출물에 pid가 새지 않았다", not any(k.startswith("pid:") for k in keys), str(keys[:3]))
        ck("산출물에 옛 이름(미래통합당)이 라벨로 없다", "미래통합당" not in keys, str(keys[:6]))
        # 개명을 못 이으면 한 선거구에서 ±40%p 같은 값이 나온다 — identity가 섰는지의 신호
        worst = max((abs(v) for u in d["units"] for v in (u.get("share_delta") or {}).values()),
                    default=0)
        ck(f"선거구 delta가 현실적 범위 (최대 {worst:.1f}%p < 60)", worst < 60, str(worst))
        ck("분모 규칙이 적혀 있다", "두 회차 모두" in d.get("swing_denominator", ""))
        ck("registry 공백이 드러난다", "unregistered_parties" in d)
        ck("녹색정의당이 공백으로 잡힌다", "녹색정의당" in d["unregistered_parties"])

    # ── 비교 코드에 raw 문자열 비교가 남아 있지 않은가 ──────────────────────
    print("\n[전수] 비교 코드가 resolver를 우회하지 않는가")
    src = (ROOT / "scripts/build/build_general_comparison.py").read_text(encoding="utf-8")
    body = "\n".join(l for l in src.split("\n") if not l.strip().startswith("#"))
    raw = re.findall(r'\.party\s*==[^=]|party\s*==\s*[\'"]|same_party\(|party_key\(', body)
    ck("raw 정당명 비교가 없다", not raw, str(raw[:3]))
    ck("identity()를 쓴다", "identity(" in body)

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
