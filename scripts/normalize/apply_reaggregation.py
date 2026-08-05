"""재집계 결과를 선거구 계보·지리 계보에 **되먹인다**.

계보는 폴리곤만 보고 "겹침이 부족하다 → 비교 불가"라고 판정한다. 그건 옳지만
끝이 아니다. 과거 표를 동 단위로 다시 담을 수 있으면 그 선거구는 비교가 선다.
그래서 재집계가 성립한 곳만 골라 계보의 판정을 올린다.

    comparable:  no → yes            (method가 reaggregated이고 품질이 insufficient가 아닐 때만)
    method:      direct | aggregated | reaggregated | context_only

`context_only`로 남은 곳은 **건드리지 않는다**. 계보는 이어져 있고 수치만 못 낸다는
뜻이고, 그게 원래 판정과 같다. 역사가 이어진다 ≠ 숫자가 직접 비교된다.

**build_district_lineage.py 다음에** 돌린다 — 계보를 다시 만들면 판정이 초기화되므로
재집계 결과를 그 위에 다시 얹어야 한다.

사용: python scripts/normalize/apply_reaggregation.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIN = ROOT / "data/district_lineage"
REAGG = ROOT / "data/reaggregated"
EVENTS = ROOT / "data/geography/events.json"

# 재집계 결과의 선거구명은 시도 접두가 없다(하남시갑). 계보는 '경기 하남시갑'이다.
def _match(units: list, name: str):
    for u in units:
        if u["district"].split(" ", 1)[-1] == name:
            return u
    return None


def apply_lineage() -> int:
    n = 0
    for f in sorted(REAGG.glob("*.json")):
        res = json.loads(f.read_text(encoding="utf-8"))
        lf = LIN / f"{res['current']}__{res['previous']}.json"
        if not lf.exists():
            continue
        lin = json.loads(lf.read_text(encoding="utf-8"))
        for name, v in res["districts"].items():
            u = _match(lin["units"], name)
            if u is None:
                continue
            # 이미 지오메트리로 비교되는 곳은 재집계가 필요 없다. 거기에 '재집계 불가'를
            # 달면 멀쩡한 비교에 없는 한계를 붙이는 것이다 — 방법은 direct다.
            if u.get("comparable") == "yes" and u.get("reason_code") != "reaggregated_from_dong":
                u["reaggregation"] = {"method": "direct",
                                      "note": "경계가 사실상 같아 재집계 없이 비교한다"}
                continue
            u["reaggregation"] = {
                "method": v["method"],
                "quality": v["reaggregation_quality"],
                "coverage": v["provenance"]["coverage"],
                "denominator": v["provenance"]["denominator"],
                "validation_error_pp":
                    v["provenance"]["current_election_validation_error_pp"],
                "winner_agrees": v["validation"]["winner_agrees"],
                "source": v["provenance"]["source"],
                "fixture": f.stem,
            }
            usable = (v["method"] == "reaggregated"
                      and v["reaggregation_quality"] != "insufficient")
            if usable and u.get("comparable") != "yes":
                u["comparable"] = "yes"
                u["reason_code"] = "reaggregated_from_dong"
                u["reason"] = (f"획정은 바뀌었지만 {res['previous']}대 표를 읍면동 단위로 "
                               f"{res['current']}대 경계에 다시 담아 비교한다 "
                               f"(동 귀속표 기준, 커버리지 "
                               f"{v['provenance']['coverage']*100:.1f}%)")
                n += 1
            elif v["method"] == "context_only":
                # 판정을 바꾸지 않는다 — 왜 못 하는지만 남긴다
                u["reaggregation"]["blocked_by"] = (
                    "선거구 일부만 회수" if v["provenance"]["partial_fetch"]
                    else "선거구를 가로지르는 동: "
                         + ", ".join(v["provenance"]["crossing_prev_dongs"]))
        # counts 갱신 — 판정을 바꿨으면 집계도 맞춰야 한다
        lin["counts"]["comparable"] = sum(1 for u in lin["units"]
                                          if u.get("comparable") == "yes")
        # counts는 관계별 합이 total과 맞아야 한다(불변식). 재집계 수치를 여기 섞으면
        # 그 합이 깨지므로 따로 담는다.
        lin["reaggregation_counts"] = {
            "reaggregated": sum(1 for u in lin["units"]
                                if (u.get("reaggregation") or {}).get("method")
                                == "reaggregated"),
            "context_only": sum(1 for u in lin["units"]
                                if (u.get("reaggregation") or {}).get("method")
                                == "context_only"),
        }
        lf.write_text(json.dumps(lin, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8")
    return n


def apply_events() -> int:
    """지리 이벤트의 비교 가능성 등급을 실측으로 갱신한다."""
    if not EVENTS.exists():
        return 0
    ev = json.loads(EVENTS.read_text(encoding="utf-8"))
    # 선거구명 → 재집계 판정
    verdict: dict = {}
    for f in REAGG.glob("*.json"):
        r = json.loads(f.read_text(encoding="utf-8"))
        for name, v in r["districts"].items():
            verdict[name] = v
    n = 0
    for e in ev["events"]:
        if e.get("kind") == "admin_unit":
            continue
        # entity id는 'electoral_district:22:경기:하남시갑' — 마지막 조각이 선거구명
        names = [x["id"].split(":")[-1] for x in e.get("to") or []]
        touched = [verdict[k] for k in names if k in verdict]
        if not touched:
            continue
        ok = [v for v in touched
              if v["method"] == "reaggregated" and v["reaggregation_quality"] != "insufficient"]
        want = "reaggregated" if len(ok) == len(touched) else "context_only"
        if True:
            e["comparison_capability"] = want
            why = []
            for v in touched:
                if v["method"] == "reaggregated":
                    continue
                cx = v["provenance"]["crossing_prev_dongs"]
                why.append("가로지르는 동: " + ", ".join(cx) if cx else "선거구 일부만 회수")
            e["capability_evidence"] = (
                "읍면동 실측 득표로 재집계 성립" if want == "reaggregated"
                else "읍면동 단위로 나눌 수 없음 — " + "; ".join(dict.fromkeys(why)))
            ln = ("읍면동 실측 득표(NEC 투표구별 개표)로 재집계 성립"
                  if want == "reaggregated" else e["capability_evidence"])
            ev_list = e.setdefault("evidence", [])
            if ln not in ev_list:
                ev_list.append(ln)
            n += 1
    EVENTS.write_text(json.dumps(ev, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8")
    return n


if __name__ == "__main__":
    a = apply_lineage()
    b = apply_events()
    print(f"선거구 계보: 비교 불가 → 가능 {a}곳 · 지리 이벤트 등급 갱신 {b}건")
    sys.exit(0)
