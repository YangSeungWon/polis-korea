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

TAG = "_41004131"          # 경기 하남 — split 대표 fixture
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
       ds["하남시갑"]["validation"]["winner_agrees"] is False)

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
       "pid:국민의힘" in ds["하남시갑"]["prev_reaggregated"]["share"])
    # 국민의당(2020)은 2022년에 흡수됐다 — 2020년 그 표가 국민의힘으로 새면 안 된다
    sys.path.insert(0, str(ROOT / "scripts/build"))
    import party_identity as PI
    ck("국민의당(2020)이 국민의힘과 섞이지 않음",
       PI.identity("국민의당(2020)", "2020-04-15") != PI.identity("국민의힘", "2024-04-10"))

    print("\n[실측] 하남 수치가 원자료에서 재현되는가")
    g = ds["하남시갑"]
    ck(f"21대 하남갑 영역 민주 46.7% ({g['prev_reaggregated']['share'].get('pid:더불어민주당')})",
       abs(g["prev_reaggregated"]["share"].get("pid:더불어민주당", 0) - 46.7) < 0.2)
    ck(f"커버리지 85.6% ({g['provenance']['coverage']*100:.1f}%)",
       abs(g["provenance"]["coverage"] - 0.856) < 0.005)

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
