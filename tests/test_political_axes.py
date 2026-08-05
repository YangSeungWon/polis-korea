"""조직 계보와 당대 이념 위치가 **분리돼 있는가**.

문헌 조사에서 "조직 계보는 민주당계인데 당대 자료는 보수라고 서술한다"는 충돌이
9건 나왔다. 이건 데이터 오류가 아니라 `stream` 한 필드에 두 개념이 들어 있던 결과다.
나누면 모순이 아니다 — 한국민주당은 `lineage_family=democratic`이면서 당대 위치는
보수일 수 있다. 둘은 다른 질문에 답한다.

이 검사가 지키는 것:

  · `stream`을 이 축들로 덮어쓰거나 rename하지 않는다 (값과 의미를 보존한다)
  · lineage_family는 계보 그래프에서 **유도**된다 — 근거 없이 손으로 넣지 않는다
  · 계열이 갈리는 합당은 한쪽으로 몰지 않고 `mixed`로 남긴다
  · contemporary_position은 시점별이고 source·confidence가 없으면 존재하지 않는다
  · 지역계(충청)는 이념축에 얹지 않는다

실행: .venv/bin/python tests/test_political_axes.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data/parties/registry.json"
AX = ROOT / "data/parties/political_axes.json"
POSITIONS = {"conservative", "center_right", "center", "center_left", "progressive"}
CONF = {"supported", "contested", "insufficient"}
fails: list[str] = []


def ck(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    reg = json.loads(REG.read_text(encoding="utf-8"))
    ax = json.loads(AX.read_text(encoding="utf-8"))
    parties = reg["parties"]

    print("\n[보존] 기존 stream을 바꾸지 않았는가")
    ck("stream이 registry에 그대로 있다",
       sum(1 for v in parties.values() if v.get("stream")) >= 90)
    ck("stream의 의미가 legacy로 문서화됐다",
       "legacy" in (reg["_schema"].get("stream") or "").lower())
    ck("stream 값 어휘가 그대로다",
       {v.get("stream") for v in parties.values()} <=
       {"보수", "중도보수", "중도", "중도진보", "진보", "기타", None},
       str({v.get("stream") for v in parties.values()}))
    # 새 축이 stream을 그대로 베낀 게 아니어야 한다 — 그러면 나눈 의미가 없다
    fam = ax["lineage_family"]
    same = sum(1 for n, v in fam.items()
               if v["family"] == {"보수": "conservative", "진보": "progressive"}
               .get(parties[n].get("stream")))
    ck(f"lineage_family가 stream의 복사가 아니다 (일치 {same}/{len(fam)})",
       same < len(fam) * 0.5)

    print("\n[유도] 계보 그래프에서 나왔는가")
    ck("모든 정당에 lineage_family가 있다", len(fam) == len(parties))
    ck("근거 없는 값이 없다", all(v.get("evidence") for v in fam.values()))
    ck("basis가 셋 중 하나",
       {v["basis"] for v in fam.values()} <= {"seed", "lineage_graph", "no_path_to_seed"},
       str({v["basis"] for v in fam.values()}))
    # 씨앗이 아닌데 lineage_graph면 실제로 전신 경로가 있어야 한다
    bad = [n for n, v in fam.items()
           if v["basis"] == "lineage_graph" and not (parties[n].get("predecessors") or [])]
    ck("유도된 값에는 전신이 실재한다", not bad, str(bad[:3]))
    ck("씨앗에 못 닿으면 unknown",
       all(v["family"] == "unknown"
           for v in fam.values() if v["basis"] == "no_path_to_seed"))

    print("\n[합당] 갈리는 것을 한쪽으로 몰지 않는가")
    mixed = [n for n, v in fam.items() if v["family"] == "mixed"]
    ck(f"계열이 갈린 합당은 mixed로 남는다 ({len(mixed)}종)", bool(mixed))
    ck("mixed에는 어느 계열들인지 적혀 있다",
       all("갈린다" in fam[n]["evidence"] for n in mixed))
    # 3당합당(민정+통일민주+신민주공화)의 후신은 한쪽 계열로 단정할 수 없다
    ck("국민의힘 계보가 단일 계열로 단정되지 않는다",
       fam["국민의힘"]["family"] in ("mixed", "unknown"), fam["국민의힘"]["family"])

    print("\n[충돌 해소] 축을 나누면 모순이 아닌가")
    for n in ("한국민주당", "민주국민당", "민주당(1955)"):
        if n not in fam:
            continue
        # 조사에서 '중도진보인데 자료는 보수'라고 충돌 판정된 정당들.
        # 계보는 민주계로 나오고, 이념 위치는 **다른 축**이라 충돌이 아니다.
        ck(f"{n}: 계보=민주계 · stream은 그대로 보존",
           fam[n]["family"] == "democratic" and parties[n].get("stream") == "중도진보")

    print("\n[이념축에 못 얹는 것]")
    reg_fam = [n for n, v in fam.items() if v["family"] == "regional"]
    ck(f"지역계가 이념 위치로 환원되지 않는다 ({len(reg_fam)}종)", bool(reg_fam))
    ck("families 어휘에 regional이 있다", "regional" in ax["_families"])

    print("\n[시점] contemporary_position이 시계열인가")
    pos = ax.get("contemporary_position") or {}
    ck("스키마가 valid_from/valid_to·source·confidence를 요구한다",
       {"valid_from", "valid_to", "source", "confidence"} <= set(ax["_position_schema"]))
    ck("소급 적용 금지가 명시돼 있다", "소급" in ax["_position_rule"])
    for party, recs in pos.items():
        for r in recs if isinstance(recs, list) else [recs]:
            ck(f"{party}: position 어휘", r.get("position") in POSITIONS, str(r.get("position")))
            ck(f"{party}: 근거가 있다", bool(r.get("source")))
            ck(f"{party}: confidence 어휘", r.get("confidence") in CONF)
            ck(f"{party}: 기간이 있다", bool(r.get("valid_from")))
    if not pos:
        # 비어 있는 것이 옳다 — 근거를 확인한 것만 넣는다. 다만 '없음'과 '검사 안 함'은 다르다.
        print("  · contemporary_position 0종 — 근거 확인분만 넣는다(빈 상태가 기본값)")

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
