"""읍면동 재집계 — 원자료와 맞는가, 그리고 **추정을 하지 않았는가**.

재집계는 과거 표를 현재 선거구 경계로 다시 더한다. 여기서 틀리는 방법이 세 가지고
셋 다 조용히 틀린다:

  ① **분모 불일치** — 2020 동귀속(≈85%)을 2024 공식 전체(100%)와 빼는 것.
     획정 문제를 고치고 새 오류를 만든다. swing은 양쪽 모두 동귀속 기준이어야 한다.
  ② **임의 배분** — 어느 동 표인지 모르는 표를 인구비·면적비로 쪼개는 것.
     그건 집계가 아니라 추정이다. 한 건도 허용하지 않는다.
  ③ **가로지르는 동** — 한 동이 두 선거구에 걸치면 동 단위로는 못 나눈다.
     읍면동 자료가 있다고 모든 획정 변경을 재집계할 수 있는 게 아니다.

그리고 커버리지가 높다고 안전한 게 아니다. 하남시갑은 커버리지 85.6%, 재현오차
1.24%p인데 **승자가 뒤집힌다** — 관외사전이 민주당 쪽으로 +7.4%p 치우쳐 있어서다.
그래서 승자 일치 여부와 제외표 편향을 따로 재서 같이 내보낸다.

실행: .venv/bin/python tests/test_reaggregation.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/normalize"))
sys.path.insert(0, str(ROOT / "scripts/fetch"))
from reaggregate import (attributable, by_party, crossing, official,  # noqa: E402
                         run, shares, split_candidate)
from reaggregate import _load  # noqa: E402

TAG = "_hanam"             # 경기 하남 — split 대표 fixture
fails: list[str] = []


def ck(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    try:
        cb, pb = _load(22, TAG), _load(21, TAG)
    except FileNotFoundError as e:
        print(f"  · 원자료 없음, 건너뜀 ({e})")
        return 0

    print("\n[원자료] VCCP08 표가 스스로 맞는가")
    for n, blocks in ((22, cb), (21, pb)):
        for b in blocks:
            for r in b["rows"]:
                s = sum(r["per_candidate"].values())
                if s != r["valid"]:
                    ck(f"{n}대 후보합=유효계", False, f"{r['unit']} {s}≠{r['valid']}")
                    break
    ck("후보별 득표 합이 유효투표계와 일치", not fails)
    # 블록 소계가 그 블록 구성행의 합인가 — 동 귀속의 근거다
    for n, blocks in ((22, cb), (21, pb)):
        # 블록 = 소계 + 그 뒤의 투표구들(관내사전 포함). 선거구 '계'와 귀속 불가 행
        # (거소·관외·국외·잘못 투입)은 블록 밖이라 합에 들어가면 안 된다.
        rows = [r for b in blocks for r in b["rows"]]
        bad, want, got = [], None, 0
        for r in rows + [{"kind": "subtotal", "unit": "소계", "valid": 0}]:
            if r["kind"] == "subtotal":
                if want is not None and want != got:
                    bad.append(f"{want}≠{got}")
                want, got = (r["valid"] if r["unit"] != "계" else None), 0
            elif r["kind"] == "precinct":
                got += r["valid"]
        ck(f"{n}대 블록 소계 = 구성 투표구 합", not bad, str(bad[:3]))

    print("\n[대사] 동 귀속 + 제외 = 공식 전체")
    for n, blocks, date in ((22, cb, "2024-04-10"), (21, pb, "2020-04-15")):
        att, exc, unm = attributable(blocks)
        off = official(blocks)
        a = sum(sum(r["valid"] for r in v) for v in att.values())
        o = sum(r["valid"] for r in off.values())
        e = sum(exc.values()) + sum(unm.values())
        ck(f"{n}대 대사 ({a:,} + {e:,} = {o:,})", a + e == o, f"차 {o - a - e}")

    print("\n[경계] 동이 선거구를 가로지르지 않는가")
    ck("22대 하남에 가로지르는 동 없음", not crossing(cb), str(crossing(cb)))
    ck("21대 하남에 가로지르는 동 없음", not crossing(pb), str(crossing(pb)))

    res = run(22, 21, TAG)
    ds = res["districts"]
    print("\n[추정 금지]")
    for d, v in ds.items():
        p = v["provenance"]
        ck(f"{d}: 면적·인구 배분 0건", p["allocation_by_area_or_population"] == 0)
        ck(f"{d}: 계보 미해결 동 없음", not p["unresolved_dongs"], str(p["unresolved_dongs"]))
    ck("동 계보가 근거와 함께 기록됨",
       all("evidence" in e for e in
           json.loads((ROOT / "data/geography/dong_lineage.json")
                      .read_text(encoding="utf-8"))["하남시"]))

    print("\n[분모] swing이 같은 기준끼리인가")
    for d, v in ds.items():
        if not v["swing_attributable_basis"]:
            continue
        cs = v["attributable"]["share"]
        ps = v["prev_reaggregated"]["share"]
        os_ = v["official_reference"]["share"]
        sw = v["swing_attributable_basis"]
        ok = all(abs(sw[k] - (cs.get(k, 0) - ps.get(k, 0))) < 0.02 for k in sw)
        ck(f"{d}: swing = 동귀속(현) − 동귀속(직전)", ok)
        # 공식 전체를 섞어 쓰면 값이 달라진다 — 그 값과 같으면 안 된다
        mixed = {k: round(os_.get(k, 0) - ps.get(k, 0), 2) for k in sw}
        ck(f"{d}: 공식 전체를 섞은 값과 다름", mixed != sw, "분모가 섞였다")
        ck(f"{d}: 분모 표기 존재", v["provenance"]["denominator"].startswith("동 귀속표"))

    print("\n[검증값] 커버리지만으로 판단하지 않는가")
    for d, v in ds.items():
        va = v["validation"]
        ck(f"{d}: 승자 일치 여부 기록", "winner_agrees" in va)
        ck(f"{d}: 제외표 편향 기록", bool(va["excluded_lean_pp"]))
        ck(f"{d}: 편향 안정성 기록", bool(va["bias_stability_pp"]))
        if not va["winner_agrees"]:
            ck(f"{d}: 승자가 갈리면 validated로 올리지 않음",
               v["reaggregation_quality"] != "validated")
    # 하남시갑이 바로 그 사례다 — 이 사실이 사라지면 회귀다
    ck("하남시갑에서 승자 불일치가 잡힌다",
       ds["경기 하남시갑"]["validation"]["winner_agrees"] is False)

    print("\n[정당] identity resolver를 거치는가")
    ck("후보 문자열이 정당·이름으로 갈린다",
       split_candidate("더불어민주당최종윤") == ("더불어민주당", "최종윤"))
    ck("무소속도 갈린다", split_candidate("무소속이현재") == ("무소속", "이현재"))
    for d, v in ds.items():
        ks = set(v["attributable"]["share"]) | set(v["prev_reaggregated"]["share"])
        ck(f"{d}: 비교 키가 identity(pid:)다",
           all(k.startswith("pid:") or k == "무소속" for k in ks), str(ks))
    # 미래통합당(2020)과 국민의힘(2024)은 개명 — 한 키로 이어져야 한다
    ck("미래통합당↔국민의힘이 한 identity",
       "pid:국민의힘" in ds["경기 하남시갑"]["prev_reaggregated"]["share"])
    # 국민의당(2020)은 2022년에 흡수됐다 — 2020년 그 표가 국민의힘으로 새면 안 된다
    sys.path.insert(0, str(ROOT / "scripts/build"))
    import party_identity as PI
    ck("국민의당(2020)이 국민의힘과 섞이지 않음",
       PI.identity("국민의당(2020)", "2020-04-15") != PI.identity("국민의힘", "2024-04-10"))

    print("\n[실측] 하남 수치가 원자료에서 재현되는가")
    g = ds["경기 하남시갑"]
    ck(f"21대 하남갑 영역 민주 46.7% ({g['prev_reaggregated']['share'].get('pid:더불어민주당')})",
       abs(g["prev_reaggregated"]["share"].get("pid:더불어민주당", 0) - 46.7) < 0.2)
    ck(f"커버리지 85.6% ({g['provenance']['coverage']*100:.1f}%)",
       abs(g["provenance"]["coverage"] - 0.856) < 0.005)

    print("\n[유형별] 획정 변경 종류마다 옳은 판정이 나오는가")
    _fixtures()

    print("\n[capability] 방법과 주장할 수 있는 것을 분리했는가")
    _capability()

    print("\n[되먹임] 계보에 반영될 때 근거 없이 올라가지 않는가")
    _feedback()

    print("\n[분류] 남은 비교 불가가 왜 불가인지 전부 설명되는가")
    _taxonomy()

    print("\n[대조군] 경계가 그대로인 곳에서 direct와 수렴하는가")
    _control()

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


def _fixtures() -> None:
    """대표 fixture — 하나로 되면 다 된다고 하지 않는다.

    · split            하남      2020 하남시 → 2024 갑/을
    · merge            부산 남구  2020 갑/을 → 2024 남구
    · 행정동 재편       부천      2019년 36동→10 광역동, 2024년 되돌림 + 선거구 4→3
    · boundary exchange 고양      인접 선거구끼리 동이 오갔다
    · 광역단체 transfer  군위      경북 → 대구(2023). 시도가 바뀌어 코드 접두도 바뀐다

    막히는 것도 결과다. 부천 갑·병은 광역동이 선거구를 가로질러 재집계가 성립하지
    않는다. 다만 **닿지 않는 선거구까지 막지는 않는다** — 부천을·고양정은 멀쩡하다.
    """
    for name in ("hanam", "busan-nam", "bucheon", "goyang", "gunwi"):
        try:
            r = run(22, 21, "_" + name)
        except FileNotFoundError:
            print(f"  · {name} 원자료 없음, 건너뜀")
            continue
        for d, v in r["districts"].items():
            p = v["provenance"]
            hurt = bool(p["crossing_prev_dongs"]) or p["partial_fetch"]
            if v["method"] == "context_only":
                # 차단했으면 **수치가 남아 있으면 안 된다**. 남겨 두고 주의 문구를
                # 붙이면 문구가 떨어져 나간 자리에서 그대로 인용된다.
                ck(f"{name}/{d}: 차단 시 수치 없음",
                   v["attributable"] is None and v["prev_reaggregated"] is None
                   and v["swing_attributable_basis"] is None)
                ck(f"{name}/{d}: 차단 이유가 기록됨", hurt)
            else:
                ck(f"{name}/{d}: 성립하면 방해 요인이 없다", not hurt)
                ck(f"{name}/{d}: 커버리지가 100%를 넘지 않는다",
                   p["coverage"] <= 1.0, f"{p['coverage']:.3f}")
                ck(f"{name}/{d}: swing은 양쪽 다 출마한 정당만",
                   not (set(v["swing_attributable_basis"] or {})
                        & (set(v["newly_ran"] or {}) | set(v["no_longer_ran"] or {}))))

    # 아래는 사실 확인이다 — 사라지면 회귀다
    try:
        b = run(22, 21, "_bucheon")
        ck("부천 광역동이 선거구를 가로지르는 것이 잡힌다",
           any(x.endswith(":부천동") for x in
               b["districts"]["경기 부천시갑"]["provenance"]["crossing_prev_dongs"]))
        ck("가로지르는 동이 안 닿는 선거구는 막지 않는다",
           b["districts"]["경기 부천시을"]["method"] == "reaggregated")
        g = run(22, 21, "_goyang")
        ck("고양은 흥도동이 닿는 갑·을만 막힌다",
           {d for d, v in g["districts"].items() if v["method"] == "context_only"}
           == {"경기 고양시갑", "경기 고양시을"})
        w = run(22, 21, "_gunwi")
        # 군위군은 2023년에 경북에서 대구로 옮겨 갔다 — 코드 접두가 회차마다 다르다
        ck("시도 이관(군위)도 재집계된다",
           w["districts"]["대구 동구군위군을"]["method"] == "reaggregated")
        # 선거구가 여러 시군구에 걸치면 '계'가 여럿이다. 덮어쓰면 커버리지 614%가 나온다
        ck("일부만 회수된 선거구는 수치를 내지 않는다",
           w["districts"]["경북 의성군청송군영덕군울진군"]["provenance"]["partial_fetch"]
           and w["districts"]["경북 의성군청송군영덕군울진군"]["attributable"] is None)
    except FileNotFoundError:
        pass


def _control() -> None:
    """엔진 외부 검증 — 획정 변경 지역에서는 얻을 수 없는 control group.

    경계가 그대로인 선거구에서는 direct(공식 전체)와 reaggregated(동 귀속표)의
    delta를 둘 다 구할 수 있다. 분모가 다르니 똑같을 수는 없지만, 제외표 편향이
    안정적이면 수렴해야 한다. 어긋나면 엔진에 문제가 있다는 뜻이다.

    실제로 이 검사가 두 개의 큰 버그를 잡았다:
      · 직전 회차 제외표 편향을 전국 평균 하나로 계산해 모든 선거구에 갖다 댔다
      · 동을 이름만으로 키 잡아 전국에서 223종이 충돌했다 (다른 도시 표가 섞였다)
    고치고 나서 p90이 1.65%p → 0.37%p로 떨어졌다.
    """
    from validate_reaggregation import run as vrun
    for cur, prev in ((22, 21), (21, 20)):
        try:
            r = vrun(cur, prev)
        except FileNotFoundError:
            print(f"  · {cur}↔{prev} 원자료 없음, 건너뜀")
            continue
        if not r.get("pairs"):
            continue
        ck(f"{cur}↔{prev}: 대조군이 충분하다 ({r['control_districts']}곳)",
           r["control_districts"] >= 50)
        ck(f"{cur}↔{prev}: |차이| 중앙값 ≤ 0.5%p ({r['abs_diff_median_pp']})",
           r["abs_diff_median_pp"] <= 0.5)
        ck(f"{cur}↔{prev}: |차이| p90 ≤ 1.5%p ({r['abs_diff_p90_pp']})",
           r["abs_diff_p90_pp"] <= 1.5)
        # 부호 평균이 0에서 멀면 한쪽으로 쏠린 계통 오차다
        ck(f"{cur}↔{prev}: 계통 편차 없음 (부호평균 {r['signed_mean_pp']}%p)",
           abs(r["signed_mean_pp"]) <= 0.3)


def _taxonomy() -> None:
    """좋은 산출물은 '비교 가능 196'이 아니라 **남은 불가가 전부 설명된 상태**다.

    분류 안 된 잔여가 있으면 우리가 모르는 유형이 있다는 뜻이고, 숫자를 늘리는 것보다
    그 사실을 드러내는 게 먼저다. 그래서 미분류는 통과시키지 않는다.
    """
    from reaggregation_taxonomy import TAXONOMY, report
    for f in sorted((ROOT / "data/district_lineage").glob("*__*.json")):
        if f.stem == "blocked_taxonomy":
            continue
        r = report(f.stem)
        ck(f"{f.stem}: 비교 불가 사유가 전부 분류됨",
           not r["unclassified"], f"{len(r['unclassified'])}건")
        ck(f"{f.stem}: 사유마다 뜻과 대응이 적혀 있다",
           all(v["meaning"] and v["actionable"] for v in r["by_cause"].values()))
        ck(f"{f.stem}: 분류 합 = 비교 불가 수",
           sum(v["count"] for v in r["by_cause"].values()) == r["blocked"])
    ck("taxonomy 코드에 전부 설명이 있다",
       all(len(v) == 2 and v[0] and v[1] for v in TAXONOMY.values()))


def _capability() -> None:
    """`reaggregated`는 하나의 신뢰 상태가 아니고, `level=false`는 '값이 틀렸다'가 아니다.

    하남시갑의 동 귀속표 49.35/50.65는 **틀린 값이 아니다** — 동 귀속 가능한 표에서는
    정확하다. 틀리는 건 그걸 전체 공식 득표 수준이라고 말하는 것이다. 그래서 셋을 나눈다.

        measurement            부분집합에서 실제로 쟀는가
        inference_to_full      그 값을 전체 결과로 일반화해도 되는가
        comparison.delta       같은 분모끼리의 변화량을 말할 수 있는가

    **부분집합에서 정확한 값 ≠ 전체 수준값으로 쓸 수 있는 값.**
    """
    for name in ("hanam", "busan-nam", "bucheon", "goyang", "gunwi"):
        try:
            r = run(22, 21, "_" + name)
        except FileNotFoundError:
            continue
        for d, v in r["districts"].items():
            c = v.get("capability") or {}
            ck(f"{name}/{d}: 측정·일반화·비교가 나뉘어 있다",
               {"measurement", "inference_to_full_result", "comparison"} <= set(c))
            if not c:
                continue
            m = c["measurement"]["attributable_level"]
            inf = c["inference_to_full_result"]
            dl = c["comparison"]["delta"]
            # 잰 게 없으면 일반화도 비교도 할 수 없다 — 반대는 성립하지 않는다
            if not m["valid"]:
                ck(f"{name}/{d}: 못 쟀으면 일반화·비교도 불가",
                   not inf["level"]["allowed"] and not dl["allowed"])
            ck(f"{name}/{d}: 막힌 축에는 사유가 있다",
               all(x.get("allowed", x.get("valid")) or x.get("reason")
                   for x in (m, inf["level"], inf["winner"], dl)))
            ck(f"{name}/{d}: swing 유무 = delta 허용 여부",
               bool(v["swing_attributable_basis"]) == dl["allowed"])
            bad = {k for k, x in dl["by_party"].items() if not x["allowed"]}
            ck(f"{name}/{d}: 막힌 정당은 swing에서 빠진다",
               not (bad & set(v["swing_attributable_basis"] or {})))

    h = run(22, 21, "_hanam")["districts"]["경기 하남시갑"]
    c = h["capability"]
    # 이게 이 모델의 핵심 사례다 — 사라지면 모델이 퇴화한 것이다
    ck("하남시갑: 측정 자체는 유효하다 (값이 틀린 게 아니다)",
       c["measurement"]["attributable_level"]["valid"] is True)
    ck("하남시갑: 전체 수준·승자로 일반화는 불가",
       c["inference_to_full_result"]["level"]["allowed"] is False
       and c["inference_to_full_result"]["winner"]["allowed"] is False)
    ck("하남시갑: 그래도 변화량은 성립",
       c["comparison"]["delta"]["allowed"] is True)
    by = c["comparison"]["delta"]["by_party"]
    ck("하남시갑: 민주당 변화량 허용 (편향이동 0.5%p 미만)",
       by["pid:더불어민주당"]["allowed"] and by["pid:더불어민주당"]["bias_shift_pp"] < 0.5)
    # 국민의힘이 막히는 이유는 '관외사전 표본 문제'가 아니라 구도 변화다.
    # 2020년 무소속 이현재 15.67%로 보수표가 갈렸다 — 뭉뚱그리면 오해가 생긴다.
    ck("하남시갑: 국민의힘 차단 사유가 '구도 변화'로 구분된다",
       by["pid:국민의힘"]["reason"] == "candidacy_configuration_changed")

    print("  · 다음 해상도 명시")
    b = run(22, 21, "_bucheon")["districts"]["경기 부천시갑"]
    ck("가로지르는 동은 다음 해상도(precinct)를 밝힌다",
       b["provenance"]["resolution_required"] == "precinct")
    ck("성립한 곳에는 다음 해상도가 없다",
       run(22, 21, "_hanam")["districts"]["경기 하남시갑"]
       ["provenance"]["resolution_required"] is None)


def _feedback() -> None:
    """재집계 결과가 선거구 계보로 되먹여질 때의 불변식.

    계보 판정을 올리는 건 **근거가 있을 때만**이다. context_only는 그대로 둔다 —
    계보는 이어져 있고 수치만 못 낸다는 뜻이라 원래 판정과 같다.
    역사가 이어진다 ≠ 숫자가 직접 비교된다.
    """
    f = ROOT / "data/district_lineage/22__21.json"
    if not f.exists():
        return
    lin = json.loads(f.read_text(encoding="utf-8"))
    for u in lin["units"]:
        r = u.get("reaggregation") or {}
        m = r.get("method")
        if m == "reaggregated":
            # 재집계했다고 비교 가능이 아니다 — **변화량을 주장할 수 있어야** 한다.
            # 동구군위군을은 재집계는 되는데 2020 민주당 자리를 2024 진보당이 채워
            # 제외표 편향이 회차 사이에 흔들린다. 그래서 비교 불가로 남는다.
            ck(f"{u['district']}: 비교 가능 여부 = delta capability",
               (u["comparable"] == "yes") == bool((r.get("capability") or {}).get("delta")))
            ck(f"{u['district']}: 품질이 insufficient가 아님",
               r.get("quality") != "insufficient")
            ck(f"{u['district']}: 분모가 명시됨",
               (r.get("denominator") or "").startswith("동 귀속표"))
        elif m == "context_only":
            # 못 하는 이유가 없는 채로 막혀 있으면 안 된다
            ck(f"{u['district']}: 차단 이유가 있다", bool(r.get("blocked_by")))
            ck(f"{u['district']}: 차단인데 비교 가능으로 올리지 않음",
               u.get("reason_code") != "reaggregated_from_dong")
    # 근거 없이 comparable이 올라간 게 없는지 — reason_code가 있어야 한다
    ck("재집계로 올린 곳은 전부 reason_code가 붙어 있다",
       all((u.get("reaggregation") or {}).get("method") == "reaggregated"
           for u in lin["units"] if u.get("reason_code") == "reaggregated_from_dong"))
    ev = json.loads((ROOT / "data/geography/events.json").read_text(encoding="utf-8"))
    for e in ev["events"]:
        if e.get("kind") == "admin_unit":
            continue
        if e.get("comparison_capability") in ("reaggregated", "context_only"):
            ck(f"{e['id']}: 등급에 근거가 붙어 있다", bool(e.get("capability_evidence")))


if __name__ == "__main__":
    sys.exit(main())
