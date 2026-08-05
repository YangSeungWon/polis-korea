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


def derive_family(reg: dict) -> dict:
    """전신 그래프를 거슬러 올라가 **가장 가까운 씨앗 조상**의 계열을 준다.

    순서에 의존하면 안 된다. 전신 하나가 먼저 풀렸다는 이유로 확정하면 국민의힘이
    '국민의당(2020)에서 rename'이 되어 버린다(실제로 그랬다) — 개명 전신은 미래통합당인데.

    거리를 쓰는 이유: 한나라당은 신한국당(보수)과 통합민주당(1995)(민주계 뿌리)의
    합당이라 조상을 끝까지 타면 두 계열이 다 나온다. 그건 사실이지만, 조직적으로
    **더 가까운** 계보가 그 정당의 흐름을 결정한다. 같은 거리에서 갈리면 `mixed`다 —
    한쪽으로 몰면 그게 곧 편집자 판단이 된다.
    """
    from collections import deque

    out: dict = {}
    for name in reg:
        if name in SEEDS:
            out[name] = {"family": SEEDS[name][0], "basis": "seed",
                         "evidence": f"씨앗: {SEEDS[name][1]}"}
            continue
        # 전신 방향 BFS — 거리별로 씨앗 조상을 모은다
        seen, q, found, dist = {name}, deque([(name, 0)]), {}, None
        while q:
            cur, d = q.popleft()
            if dist is not None and d > dist:
                break
            for pr in (reg.get(cur) or {}).get("predecessors") or []:
                if pr not in reg or pr in seen:
                    continue
                seen.add(pr)
                if pr in SEEDS:
                    dist = d + 1
                    found.setdefault(SEEDS[pr][0], []).append(pr)
                else:
                    q.append((pr, d + 1))
        if not found:
            out[name] = {"family": "unknown", "basis": "no_path_to_seed",
                         "evidence": "씨앗에 닿는 계보 경로가 없다"}
        elif len(found) == 1:
            f, via = next(iter(found.items()))
            out[name] = {"family": f, "basis": "lineage_graph",
                         "evidence": f"{'·'.join(sorted(via))}까지 전신 {dist}단계"}
        else:
            out[name] = {
                "family": "mixed", "basis": "lineage_graph",
                "evidence": ("같은 거리에서 계열이 갈린다 — "
                             + ", ".join(f"{k}({'·'.join(sorted(v))})"
                                         for k, v in sorted(found.items()))),
            }
    return out


def main() -> int:
    reg = load()
    fam = derive_family(reg)
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
        "_confidence": {
            "supported": "복수의 신뢰 가능한 자료가 같은 방향을 가리킨다",
            "contested": "자료가 갈린다 — 값을 쓰지 않고 갈린다는 사실을 남긴다",
            "insufficient": "근거가 부족하다",
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
    print(f"  contemporary_position: {len(doc['contemporary_position'])}종 기록 "
          f"(나머지는 unknown — 근거 없이 채우지 않는다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
