"""정당의 **조직 계보**와 **당대 이념 위치**를 나눈다.

## 왜 나누는가

registry의 `stream`은 한 필드가 두 일을 하고 있었다. `lineage.js`는 이걸 가로축
열로 쓰면서 주석에 "좌→우 이념 스펙트럼"이라 적었고, parties.html 본문도 "왼쪽 진보 ·
오른쪽 보수"라고 쓴다. 그런데 같은 페이지 meta는 "보수·민주·진보·**충청 계열**"이라고
한다 — 충청계는 이념 위치가 아니라 조직 계보다. `_schema`에는 정의조차 없다.

그래서 문헌 조사에서 "조직 계보는 민주당계인데 당대 문헌은 보수라고 서술한다"는
충돌이 9건 나왔다. 이건 데이터 오류가 아니라 **한 필드에 두 개념을 넣은 결과**다.
나누면 모순이 아니다:

    lineage_family: democratic      조직적으로 어디서 갈라져 나왔나
    contemporary_position: conservative   그 시점에 어느 위치였나

## 세 축

    party lineage graph      개명·합당·분당의 실제 조직 계보 (registry가 이미 가짐)
    lineage_family           보수계/민주계/진보계/지역계/기타/unknown — 계보 그래프에서 **유도**
    contemporary_position    시점별 위치. valid_from/valid_to·source·confidence 필수.

`stream`은 **건드리지 않는다**. 값의 의미가 무엇이었는지 확정되지 않았으므로
`legacy_polis_classification`으로 표시만 하고 보존한다.

## 유도의 한계

lineage_family는 그래프에서 유도한다 — 씨앗 뿌리 정당 몇 개에만 계열을 주고
predecessors를 타고 전파한다. 씨앗에 닿지 않으면 `unknown`이다. 추정해서 채우지 않는다.
**합당으로 계열이 갈리면(서로 다른 계열이 합쳐지면) unknown**이다 — 합당체를 한쪽
계열로 몰면 그게 곧 편집자 판단이 된다.

사용: python scripts/build/political_axes.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data/parties/registry.json"
OUT = ROOT / "data/parties/political_axes.json"

# predecessor edge의 **의미**. 다 같은 무게로 보면 안 된다.
#   자유선진당이 새누리당에 흡수됐다고 새누리당 전체가 mixed가 되면 곤란하다.
#   반면 A+B가 해산하고 C를 신설한 진짜 합당이면 C가 mixed인 게 자연스럽다.
EDGE = {
    "rename": "이름만 바뀌었다 — 계열이 그대로 이어진다",
    "continuation": "조직이 그대로 이어진다",
    "split": "갈라져 나왔다 — 모체의 계열을 잇는다",
    "merge": "여럿이 해산하고 새로 만들었다 — 계열이 갈리면 mixed다",
    "absorption": "존속 정당이 다른 당을 흡수했다 — **존속 쪽 계열을 유지한다**",
    "alliance": "선거연합 — 계열을 잇지 않는다",
    "temporary_rename": "한시 당명 — 원래 정당의 계열을 그대로 쓴다",
    "new": "신설 — 잇지 않는다",
    "dissolve": "해산",
}
# lineage edge 유형별 전파 여부. 생애 사건(formed_by/ended_by)이 아니라 **edge**를 본다.
CARRY_EDGE = {
    "continuation": True,    # 개명·조직 연속
    "split_from": True,      # 모체 계열을 후보값으로
    "merged_from": True,     # 진짜 합당 — 갈리면 mixed
    "absorbed_into": False,  # 흡수당의 계열을 존속당에 전파하지 않는다
    "alliance": False,
    "unrelated": False,
}

FAMILIES = {
    "conservative": "보수계",
    "democratic": "민주계",
    "progressive": "진보계",
    "regional": "지역계",
    "other": "기타",
    "mixed": "복수 계열 합당",
}

# 계보 그래프의 **뿌리**에만 계열을 준다. 여기 적는 것은 조직적 기원이지
# 이념 위치가 아니다 — 한국민주당이 '보수적'이었느냐는 별개 축에서 따로 다룬다.
# 씨앗을 늘릴 때는 반드시 근거를 같이 적는다.
SEEDS = {
    "한국민주당": ("democratic",
                "해방 후 민주당계의 조직적 기원. 민국당→민주당(1955)→신민당→"
                "…→더불어민주당으로 이어지는 계보의 출발점."),
    "자유당": ("conservative", "이승만 집권여당. 보수계의 초기 조직 축."),
    "민주공화당": ("conservative", "박정희 집권여당. 민정당→민자당→…→국민의힘 계보의 기원."),
    "민주정의당": ("conservative", "전두환 집권여당. 민자당→신한국당→한나라당→국민의힘."),
    "진보당": ("progressive", "조봉암. 혁신계의 조직적 기원."),
    "민주노동당": ("progressive", "2000년 원내 진입. 통합진보당·정의당·진보당 계보의 출발점."),
    "자유민주연합": ("regional", "김종필 충청 기반. 지역계 — 이념축과 별개다."),
    "신민주공화당": ("regional", "김종필. 충청 지역 기반."),
}


def load() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["parties"]


LIFE = ROOT / "data/parties/lifecycle.json"


def _lineage(reg: dict) -> dict:
    """정당 → [(전신, edge 유형)]. **생애 사건이 아니라 계보 edge만** 본다.

    `ended_by=dissolution`이라고 계보가 끊기는 게 아니다 — 신민당은 1980년에 해산했지만
    1967년에 민중당에서 이어져 나왔고, 그 계보는 유효하다. 반대로
    `ended_by=absorption_into A`라고 A가 흡수당의 계열을 상속하는 것도 아니다.
    """
    if not LIFE.exists():
        return {}
    life = json.loads(LIFE.read_text(encoding="utf-8"))["parties"]
    return {n: [(e["to"], e["type"]) for e in v.get("lineage") or []
                if e["to"] in reg]
            for n, v in life.items() if n in reg}


def _temporal_ok(reg: dict, child: str, parent: str) -> bool:
    """전신이 후신보다 먼저 있었는가. **같은 당명이라는 이유만으로 잇지 않는다.**

    민주노동당이 그 경고였다 — registry에 2020년 창당으로 적혀 있었지만 실제로는
    2025년 정의당의 한시 당명이었다. 당명은 수십 년 뒤 재사용된다.
    """
    cf = (reg[child].get("founded") or "")[:7]
    pf = (reg[parent].get("founded") or "")[:7]
    return not (cf and pf and pf > cf)


def derive_family(reg: dict) -> dict:
    """계보 edge를 거슬러 **가장 가까운 씨앗 조상**의 계열을 준다.

    순서에 의존하면 안 된다. 전신 하나가 먼저 풀렸다는 이유로 확정하면 국민의힘이
    '국민의당(2020)에서 rename'이 되어 버린다(실제로 그랬다) — 개명 전신은 미래통합당인데.

    edge 유형별로 전파 여부가 다르다(PROPAGATE). 흡수·선거연합은 타고 올라가지 않는다.
    같은 거리에 다른 계열이 있으면 `mixed`고, 그건 줄여야 할 오류가 아니라 사실이다.
    """
    from collections import deque
    lin = _lineage(reg)

    out: dict = {}
    for name in reg:
        if name in SEEDS:
            out[name] = {"family": SEEDS[name][0], "families": [SEEDS[name][0]],
                         "basis": "seed", "derivation": "seed", "cause": None,
                         "evidence": f"씨앗: {SEEDS[name][1]}"}
            continue
        seen, q, found, dist, skipped = {name}, deque([(name, 0)]), {}, None, []
        via_edges: list = []
        while q:
            cur, d = q.popleft()
            if dist is not None and d > dist:
                break
            for pr, et in lin.get(cur, []):
                if pr in seen:
                    continue
                seen.add(pr)
                if not CARRY_EDGE.get(et, False):
                    skipped.append(f"{pr}({et})")
                    continue
                if not _temporal_ok(reg, cur, pr):
                    skipped.append(f"{pr}(시점 불일치)")
                    continue
                if pr in SEEDS:
                    dist = d + 1
                    found.setdefault(SEEDS[pr][0], []).append(pr)
                    via_edges.append(f"{cur} ←{et}― {pr}")
                else:
                    q.append((pr, d + 1))
        note = ("  · 전파 제외: " + ", ".join(skipped[:3])) if skipped else ""
        if not found:
            # 왜 못 닿았는지 남긴다. 숫자보다 원인이 중요하다.
            has_edges = bool(lin.get(name))
            f4 = (reg[name].get("founded") or "")[:4]
            # 1980-10 신군부가 모든 정당을 강제해산했고(민주공화당·신민당·민주통일당),
            # 1981-01에 새 정당들이 생겼다. 계보 그래프가 여기서 통째로 끊긴다.
            # **모델 결함이 아니라 실제 역사적 단절이다.** 이어붙일지는 판단이 필요하다.
            cause = ("forced_dissolution_1980" if f4 in ("1980", "1981") and not has_edges
                     else "ambiguous_relation" if not has_edges
                     and (reg[name].get("predecessors") or []) else
                     "missing_edge" if not has_edges else "disconnected_component")
            out[name] = {"family": "unknown", "families": [], "basis": "no_path_to_seed",
                         "derivation": "no_path", "cause": cause,
                         "evidence": "씨앗에 닿는 계보 경로가 없다" + note}
        elif len(found) == 1:
            f, via = next(iter(found.items()))
            out[name] = {"family": f, "families": [f], "basis": "lineage_graph",
                         "derivation": "single_family_ancestry", "cause": None,
                         "evidence": f"{'·'.join(sorted(via))}까지 계보 {dist}단계"
                                     + (f" ({via_edges[0]})" if via_edges else "") + note}
        else:
            out[name] = {
                "family": "mixed", "families": sorted(found),
                "basis": "lineage_graph", "derivation": "merge_of_multiple_families",
                "cause": None,
                "evidence": ("같은 거리에서 계열이 갈린다 — "
                             + ", ".join(f"{k}({'·'.join(sorted(v))})"
                                         for k, v in sorted(found.items()))
                             + (" | " + "; ".join(via_edges[:3]) if via_edges else "")
                             + note),
            }
    return out


def main() -> int:
    reg = load()
    fam = derive_family(reg)
    # `relation`이 '어떻게 생겼나'와 '어떻게 끝났나'를 한 필드에 담고 있다.
    # 신민당은 relation=dissolve(1980 해산)인데 predecessors=['민중당'](1967 창당 경위)이다.
    # 그래서 계열 전파가 거기서 끊긴다. **값을 고치지 않고 드러낸다** — `stream`과 같은
    # 종류의 혼재라, 고치려면 formed_by/ended_by로 나누는 스키마 변경이 필요하다.
    conflated = sorted(n for n, v in reg.items()
                       if v.get("relation") in ("dissolve",) and (v.get("predecessors") or []))
    doc = {
        "_note": ("정당의 조직 계보(lineage_family)와 당대 이념 위치"
                  "(contemporary_position)를 나눠 담는다. registry의 `stream`은 두 개념이 "
                  "섞여 있어 그대로 두고 여기서 다시 세운다. **stream을 이 값들로 "
                  "덮어쓰거나 rename하지 않는다.**"),
        "_axes": {
            "lineage_family": ("조직적으로 어느 흐름에서 갈라져 나왔나. 계보 그래프에서 "
                               "유도한다. 이념 위치가 아니다 — 충청 지역계처럼 이념축에 "
                               "얹을 수 없는 것도 있다."),
            "contemporary_position": ("그 **시점**에 어느 위치였나. 정당당 상수가 아니라 "
                                      "valid_from/valid_to를 갖는 시계열이다. source와 "
                                      "confidence가 없으면 unknown으로 남긴다. 창당~해산 "
                                      "전 기간에 현대의 분류를 소급 적용하지 않는다."),
        },
        "_families": FAMILIES,
        "_edge_types": EDGE,
        "_edge_rule": ("predecessor edge를 같은 무게로 보지 않는다. absorption은 흡수당한 "
                       "쪽을 타고 올라가지 않고(존속 정당의 계열 유지), alliance·new는 "
                       "잇지 않는다. merge에서만 계열이 갈려 mixed가 나온다 — "
                       "mixed는 줄여야 할 오류가 아니라 사실일 수 있다. "
                       "그리고 같은 당명이라는 이유만으로 잇지 않는다: 전신의 존속 기간이 "
                       "후신 창당 시점과 맞는지 확인한다(민주노동당 사례)."),
        "_confidence": {
            "supported": "복수의 신뢰 가능한 자료가 같은 방향을 가리킨다",
            "contested": "자료가 갈린다 — 값을 쓰지 않고 갈린다는 사실을 남긴다",
            "insufficient": "근거가 부족하다",
        },
        "_unknown_causes": {
            "forced_dissolution_1980": ("1980-10 신군부가 모든 정당을 강제해산하고 "
                                        "1981-01에 새 정당이 창당됐다. 계보 그래프가 "
                                        "통째로 끊긴다 — 실제 역사적 단절이지 결함이 "
                                        "아니다. 이어붙이려면 '강제해산 뒤 재창당을 "
                                        "조직적 연속으로 볼 것인가'라는 판단이 필요하다."),
            "missing_edge": "전신 기록 자체가 없다",
            "ambiguous_relation": "전신은 있는데 관계 유형을 확정할 수 없다",
            "disconnected_component": "계보는 이어지는데 그 줄기가 씨앗에 닿지 않는다",
        },
        "_relation_conflation": {
            "_note": ("registry의 `relation`이 형성(new/rename/merge/split)과 "
                      "종료(dissolve)를 한 필드에 담고 있다. 아래 정당들은 종료 값이 "
                      "적혀 있어 형성 관계를 읽을 수 없고, 그래서 계열 전파가 끊긴다. "
                      "값을 고치지 않고 드러낸다 — formed_by/ended_by로 나누는 것이 "
                      "옳은 해결이고 그건 스키마 변경이다."),
            "parties": conflated,
        },
        "lineage_family": fam,
        "_position_schema": {
            "party": "정식명(registry 키)",
            "position": "conservative|center_right|center|center_left|progressive",
            "valid_from": "YYYY-MM — 이 위치가 성립하는 시작",
            "valid_to": "YYYY-MM 또는 null(현재)",
            "source": "확인한 자료 (URL 또는 문헌명)",
            "confidence": "supported|contested|insufficient",
            "note": "갈리는 지점이 있으면 여기에",
        },
        "_position_rule": ("정당당 상수가 아니다. 창당~해산 전 기간에 현대의 분류를 "
                           "소급 적용하지 않는다. 자료가 갈리면 값을 쓰지 말고 "
                           "confidence=contested로 갈린다는 사실을 남긴다. "
                           "근거가 없으면 아예 넣지 않는다 — 없는 것이 unknown이다."),
        # **비워 두는 것이 기본값이다.** 근거를 확인한 것만 채운다.
        "contemporary_position": {},
    }
    if OUT.exists():
        prev = json.loads(OUT.read_text(encoding="utf-8"))
        doc["contemporary_position"] = prev.get("contemporary_position", {})
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    import collections
    c = collections.Counter(v["family"] for v in fam.values())
    print(f"→ {OUT.name}")
    print("  lineage_family:", dict(c))
    print(f"  relation 혼재(형성/종료 한 필드): {len(conflated)}종 {conflated[:5]}")
    cu = collections.Counter(v["cause"] for v in fam.values() if v["family"] == "unknown")
    print("  unknown 원인:", dict(cu))
    print(f"  contemporary_position: {len(doc['contemporary_position'])}종 기록 "
          f"(나머지는 unknown — 근거 없이 채우지 않는다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
