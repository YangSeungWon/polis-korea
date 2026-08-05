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
    ck("_meta가 폴리곤 출처를 밝힌다", "polygon_caveat" in d["_meta"])
    ck("_meta에 출처 지문이 있다", "source_profile" in d["_meta"])

    # 22↔21은 **같은 출처**(오마이뉴스 원본)다. 정밀도 차이로 설명할 수 없으므로
    # 겹침 90~97%는 실제 경계 변화다 — 판정 보류가 아니다.
    ck("22↔21은 같은 출처로 판정된다", d["_meta"]["source_profile"]["same_source"],
       str(d["_meta"]["source_profile"]))
    unk = [u for u in d["units"] if u["comparable"] == "unknown"]
    ck("같은 출처 쌍에는 판정 보류가 없다", not unk,
       f"{len(unk)}건: {[u['district'] for u in unk[:3]]}")

    # 출처가 다른 쌍에서는 보류가 남아야 한다 — 없으면 근거 없이 단정한 것이다
    d21 = load(21, 20)
    if d21:
        ck("21↔20은 다른 출처로 판정된다",
           not d21["_meta"]["source_profile"]["same_source"],
           str(d21["_meta"]["source_profile"]))
        u21 = [u for u in d21["units"] if u["comparable"] == "unknown"]
        ck(f"다른 출처 쌍에는 판정 보류가 있다 ({len(u21)}건)", bool(u21))
        ck("보류는 전부 minor_boundary_change",
           all(u["relation"] == "minor_boundary_change" for u in u21),
           str({u["relation"] for u in u21}))
        ck("보류에 사유가 적혀 있다", all("구분 불가" in u["reason"] for u in u21[:5]))

    # ── 불변식 ──────────────────────────────────────────────────────────────
    print("\n[판정 근거] 재현 가능한가")
    ck("모든 단위에 reason_code", all(u.get("reason_code") for u in d["units"]))
    ck("reason_code가 _meta에 정의돼 있다",
       set(u["reason_code"] for u in d["units"]) <= set(d["_meta"]["reason_codes"]),
       str(set(u["reason_code"] for u in d["units"]) - set(d["_meta"]["reason_codes"])))
    ck("양방향 overlap이 남는다 (한 방향만 보면 비대칭을 놓친다)",
       all(u.get("overlap_current") is not None and u.get("overlap_previous") is not None
           for u in d["units"] if u["relation"] != "new"))
    ck("source_relation이 남는다",
       all(u.get("source_relation") in ("same_source", "source_mismatch") for u in d["units"]))
    ck("문턱 버전이 기록된다", bool(d["_meta"].get("threshold_version")))
    ck("정규화 방법이 기록된다", bool(d["_meta"].get("normalization_method")))

    # same-source 쌍에 unknown이 없다 — 문턱을 느슨하게 하면 이게 깨진다
    print("\n[회귀 조건] same-source에서 unknown=0")
    bad_ss = []
    for fp in sorted(LIN.glob("*__*.json")):
        dd = json.loads(fp.read_text(encoding="utf-8"))
        if not dd["_meta"]["source_profile"]["same_source"]:
            continue
        u = [x for x in dd["units"] if x["comparable"] == "unknown"]
        if u:
            bad_ss.append(f"{fp.stem}({len(u)})")
    ck("출처가 같은 쌍에는 판정 보류가 없다", not bad_ss, str(bad_ss[:3]))

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

    # 판정이 선 쌍만 비교를 만든다. 게이트는 '만들지 않았는가'에서
    # '판정 없이 만들지 않았는가'로 옮겨간다 — 22↔21은 이제 판정이 섰다.
    print("\n[게이트] 계보 없이 swing을 만들지 않았는가")
    cmp_dir = ROOT / "data/comparisons/general"
    made = sorted(cmp_dir.glob("*__*.json")) if cmp_dir.exists() else []
    orphan = []
    for fp in made:
        cur, prev = fp.stem.split("__", 1)
        cn = "".join(c for c in cur.split("-")[0] if c.isdigit())
        pn = "".join(c for c in prev.split("-")[0] if c.isdigit())
        if not (LIN / f"{cn}__{pn}.json").exists():
            orphan.append(fp.name)
    ck(f"총선 비교 {len(made)}쌍이 전부 계보 위에 있다", not orphan, str(orphan[:3]))

    # 비교 가능하지 않은 단위로 delta를 만들지 않았는가 — 이게 진짜 게이트다
    for fp in made:
        cd = json.loads(fp.read_text(encoding="utf-8"))
        leaked = [u["district"] for u in cd["units"]
                  if u["comparable"] != "yes" and u.get("share_delta")]
        ck(f"{fp.stem[:22]}: 비교 불가 단위에 delta 없음", not leaked, str(leaked[:3]))
        # 경고 문구가 아니라 **게이트**가 있어야 한다 — 값이 존재하면 결국 쓰인다.
        ck(f"{fp.stem[:22]}: 집계 게이트가 있다", "aggregation_allowed" in cd)
        if not cd.get("aggregation_allowed"):
            leaked = [k for k in ("party_swing_in_compared", "turnout_in_compared",
                                  "biggest_moves") if k in cd]
            ck(f"{fp.stem[:22]}: 차단 시 집계 지표 없음", not leaked, str(leaked))

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
