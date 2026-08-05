"""총선 선거구 계보 — 비교 가능/불가능을 데이터로 판정하는가.

이 프로젝트의 완료조건은 화면이 아니다. **두 회차를 비교해도 되는 단위와 안 되는
단위를 데이터로 가를 수 있는가**다. 판정이 서기 전에는 총선 swing·득표율 delta를
만들지 않는다 — 경계가 바뀐 단위를 이어 붙이면 없던 변화가 만들어진다.

읍·면·동 시계열(오래된 병목)을 기다리지 않고 선거구 폴리곤 교차로 판정한다.
검증은 **실제 획정 변화**로 한다 — 2024년 22대 획정은 공개된 사실이므로 fixture가 된다.

실행: .venv/bin/python tests/test_district_lineage.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIN = ROOT / "data/district_lineage"
fails: list[str] = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def load(cur: int, prev: int) -> dict | None:
    fp = LIN / f"{cur}__{prev}.json"
    return json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else None


def main() -> int:
    d = load(22, 21)
    ck("22대↔21대 계보가 있다", d is not None)
    if not d:
        print("\n실패 1")
        return 1
    by = {u["district"]: u for u in d["units"]}

    # ── 실제 2024년 획정 변화 (공개된 사실) ─────────────────────────────────
    print("\n[2024 획정] 실제 변화를 데이터가 잡는가")
    FIXTURES = [
        # (선거구, 기대 관계, 왜 — 사람이 검증할 수 있게 남긴다)
        ("경기 하남시갑", "split", "하남시가 갑·을로 분구"),
        ("경기 하남시을", "split", "하남시가 갑·을로 분구"),
        ("부산 남구", "merged", "남구갑+남구을 통합"),
        ("대구 동구군위군을", "merged", "군위군이 경북→대구로 편입"),
        ("경기 부천시갑", "merged", "부천 4→3 감소"),
        ("경기 안산시병", "merged", "안산 4→3 감소"),
    ]
    for name, want, why in FIXTURES:
        u = by.get(name)
        got = u["relation"] if u else "(없음)"
        ck(f"{name} = {want} ({why})", got == want, f"실제 {got}")

    # 경계만 움직인 곳은 '같다'로 쓰면 안 된다
    print("\n[경계 변화] 이름이 같아도 비교 가능이 아니다")
    for name, why in [("서울 노원구갑", "노원 3→2 재획정"),
                      ("전북 남원시장수군임실군순창군", "장수군 편입")]:
        u = by.get(name)
        ck(f"{name} 비교 불가 ({why})",
           bool(u) and u["comparable"] == "no", (u or {}).get("comparable", "(없음)"))

    # ── 판정 불가를 '같다'로도 '다르다'로도 쓰지 않는다 ─────────────────────
    print("\n[3-state] 모르는 것을 안다고 하지 않는가")
    states = {u["comparable"] for u in d["units"]}
    ck("comparable이 yes/no/unknown 셋뿐", states <= {"yes", "no", "unknown"}, str(states))
    unk = [u for u in d["units"] if u["comparable"] == "unknown"]
    ck(f"판정 불가가 별도 상태로 있다 ({len(unk)}건)", True)
    ck("판정 불가는 전부 minor_boundary_change",
       all(u["relation"] == "minor_boundary_change" for u in unk),
       str({u["relation"] for u in unk}))
    ck("판정 불가에 사유가 적혀 있다",
       all("구분 불가" in u["reason"] for u in unk[:5]))
    ck("_meta가 폴리곤 출처 차이를 밝힌다", "polygon_caveat" in d["_meta"])

    # ── 불변식 ──────────────────────────────────────────────────────────────
    print("\n[불변식]")
    c = d["counts"]
    rel_sum = sum(v for k, v in c.items() if k not in (
        "total", "comparable", "comparable_unknown", "previous_total", "previous_unmatched"))
    ck(f"관계 합 = 전체 ({rel_sum} = {c['total']})", rel_sum == c["total"])
    ck("모든 단위에 사유가 있다", all(u.get("reason") for u in d["units"]))
    ck("exact는 이름이 같다",
       all(u["district"] == u["previous"][0]["prev"]
           for u in d["units"] if u["relation"] == "exact"))
    ck("renamed는 이름이 다르다",
       all(u["district"] != u["previous"][0]["prev"]
           for u in d["units"] if u["relation"] == "renamed"))
    ck("new는 대응이 없다",
       all(not u["previous"] for u in d["units"] if u["relation"] == "new"))

    # ── 전 회차 커버리지 ────────────────────────────────────────────────────
    print("\n[커버리지]")
    pairs = sorted(LIN.glob("*__*.json"))
    ck(f"인접 회차 계보 {len(pairs)}쌍", len(pairs) >= 20, str(len(pairs)))
    bad = []
    for fp in pairs:
        dd = json.loads(fp.read_text(encoding="utf-8"))
        if {u["comparable"] for u in dd["units"]} - {"yes", "no", "unknown"}:
            bad.append(fp.stem)
    ck("전 쌍이 같은 상태 어휘를 쓴다", not bad, str(bad[:3]))

    # 총선 비교 산출물이 아직 없어야 한다 — 판정이 선 뒤에 만든다
    print("\n[게이트] 판정 전에 swing을 만들지 않았는가")
    cmp_general = list((ROOT / "data/comparisons").glob("*general*.json"))
    ck("총선 회차 간 비교 산출물 없음 (normalization 완료 전)",
       not cmp_general, str([p.name for p in cmp_general[:3]]))

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
