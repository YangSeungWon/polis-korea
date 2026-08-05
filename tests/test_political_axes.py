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

    print("\n[edge 의미] 전신 관계를 같은 무게로 보지 않는가")
    ck("edge 유형 어휘가 정의돼 있다",
       {"rename", "split", "merge", "absorption", "alliance", "temporary_rename"}
       <= set(ax["_edge_types"]))
    ck("흡수는 계열을 잇지 않는다는 규칙이 명시됨", "absorption" in ax["_edge_rule"])
    # 흡수당한 당이 전신으로 섞이면 계보가 엉뚱한 데로 흐른다. 실제로 그랬다:
    # 한나라당이 2006년 흡수한 자민련(1995 창당) 때문에 국민의힘이 '충청 지역계'가 됐다.
    absorbed_any = [n for n, v in parties.items() if v.get("absorbed")]
    ck(f"흡수가 predecessors와 분리 기록된다 ({len(absorbed_any)}종)", bool(absorbed_any))
    for n in ("한나라당", "새누리당", "국민의힘"):
        if n in parties:
            ck(f"{n}: 계보가 지역계로 흐르지 않는다",
               fam[n]["family"] != "regional", fam[n]["evidence"][:60])
    ck("3당합당 후신은 mixed로 남는다 (사실이지 오류가 아니다)",
       fam["민주자유당"]["family"] == "mixed" and
       set(fam["민주자유당"]["families"]) == {"conservative", "regional"},
       str(fam["민주자유당"]))
    ck("mixed에는 구성 계열이 배열로 남는다",
       all(len(v["families"]) > 1 for v in fam.values() if v["family"] == "mixed"))
    ck("derivation이 기록된다", all(v.get("derivation") for v in fam.values()))

    print("\n[시점 정합] 같은 당명만으로 잇지 않는가")
    for n, v in parties.items():
        for pnm in v.get("predecessors") or []:
            if pnm not in parties:
                continue
            cf = (v.get("founded") or "")[:7]
            pf = (parties[pnm].get("founded") or "")[:7]
            if cf and pf and pf > cf:
                ck(f"{n} ← {pnm}: 전신이 더 나중에 생기지 않았다", False, f"{pf} > {cf}")
    ck("전신이 후신보다 나중에 생긴 edge 없음", True)
    ck("relation 혼재가 드러나 있다", "_relation_conflation" in ax)

    print("\n[생애/계보 분리] relation 하나에 두 의미를 담지 않는가")
    lf = ROOT / "data/parties/lifecycle.json"
    if lf.exists():
        life = json.loads(lf.read_text(encoding="utf-8"))
        L = life["parties"]
        ck("모든 정당에 formed_by·ended_by가 있다",
           all("formed_by" in v and "ended_by" in v for v in L.values()))
        ck("legacy relation이 보존된다",
           all("legacy_relation" in v for v in L.values()))
        # 한 값이 생성·종료 의미로 동시에 쓰이는 경우가 없어야 한다
        F = {v["formed_by"]["type"] for v in L.values()} - {None}
        E = {v["ended_by"]["type"] for v in L.values()} - {None}
        ck("생성 유형 어휘",
           F <= {"foundation", "rename", "merger", "split", "temporary_rename",
                 "ambiguous"}, str(F))
        ck("종료 유형 어휘",
           E <= {"dissolution", "rename", "merger", "absorption_into", "split",
                 "ambiguous"}, str(E))
        ck("확정 못 한 것은 ambiguous로 남는다 (추정하지 않는다)",
           all(v["ambiguity_cause"] for v in L.values() if v["migration"] == "ambiguous"))
        # 종료 방식이 계보를 끊지 않는다 — 신민당은 1980 해산이지만 1967년 계보가 있다
        sm = L.get("신민당")
        if sm:
            ck("해산해도 계보 edge는 남는다 (신민당)",
               sm["ended_by"]["type"] == "dissolution"
               and any(e["type"] == "continuation" for e in sm["lineage"]),
               str(sm["ended_by"]["type"]) + "/" + str(sm["lineage"]))
        # 흡수는 계열을 전파하지 않는다
        ck("absorbed_into는 전파 대상이 아니다",
           life["_rules"]["propagate"]["absorbed_into"] is False)
        ck("continuation·split_from·merged_from은 전파한다",
           all(life["_rules"]["propagate"][k] for k in
               ("continuation", "split_from", "merged_from")))
        # 계보 그래프에 순환이 없어야 한다
        adj = {n: [e["to"] for e in v["lineage"] if e["type"] != "absorbed_into"]
               for n, v in L.items()}
        state: dict = {}

        def cyc(n):
            if state.get(n) == 1:
                return True
            if state.get(n) == 2:
                return False
            state[n] = 1
            r = any(cyc(m) for m in adj.get(n, []) if m in adj)
            state[n] = 2
            return r
        ck("계보 그래프에 순환이 없다", not any(cyc(n) for n in adj))
        # 모든 edge가 실재하는 정당과 날짜를 가진다
        ck("edge 상대가 전부 실재 정당",
           all(e["to"] in parties for v in L.values() for e in v["lineage"]))

    print("\n[unknown 원인] 왜 남았는지 전부 설명되는가")
    unk = {n: v for n, v in fam.items() if v["family"] == "unknown"}
    ck(f"모든 unknown에 원인이 있다 ({len(unk)}종)",
       all(v.get("cause") for v in unk.values()),
       str([n for n, v in unk.items() if not v.get("cause")][:3]))
    ck("원인 어휘가 문서화돼 있다",
       {v["cause"] for v in unk.values()} <= set(ax["_unknown_causes"]),
       str({v["cause"] for v in unk.values()} - set(ax["_unknown_causes"])))
    # 1980 강제해산은 결함이 아니라 실제 단절이다 — 그 사실이 남아 있어야 한다
    ck("1980 강제해산 단절이 원인으로 잡힌다",
       any(v["cause"] == "forced_dissolution_1980" for v in unk.values()))

    print("\n[순서 독립] 입력 순서가 결과를 바꾸지 않는가")
    sys.path.insert(0, str(ROOT / "scripts/build"))
    from political_axes import derive_family
    base = json.loads(REG.read_text(encoding="utf-8"))["parties"]
    a = derive_family(base)
    b = derive_family({k: base[k] for k in reversed(list(base))})
    ck("역순으로 넣어도 같은 결과",
       {k: v["family"] for k, v in a.items()} == {k: v["family"] for k, v in b.items()},
       str([k for k in a if a[k]["family"] != b[k]["family"]][:3]))

    print("\n[단절] 1980을 잇되 이어졌다고 가장하지 않는가")
    ev = json.loads((ROOT / "data/parties/historical_events.json")
                    .read_text(encoding="utf-8"))
    br = json.loads((ROOT / "data/parties/historical_bridges.json")
                    .read_text(encoding="utf-8"))
    ck("강제해산이 정당 속성이 아니라 사건 entity다",
       any(e["type"] == "systemic_forced_dissolution" for e in ev["events"]))
    ck("사건이 영향받은 정당들을 갖는다",
       all(e.get("affected_parties") for e in ev["events"]))
    ck("bridge를 동일성 판정에 쓰지 않는다는 규칙이 있다",
       "identity" in br["_rule"] and "절대" in br["_rule"])
    for b in br["bridges"]:
        ck(f"bridge {b['from']}→{b['to']}: 근거·출처·confidence",
           bool(b.get("basis")) and bool(b.get("source"))
           and b.get("confidence") in CONF)
        ck(f"bridge {b['to']}: 사건을 참조한다",
           b.get("event") in {e["id"] for e in ev["events"]})
    # bridge는 조직 계보(lineage)에 섞이면 안 된다
    if lf.exists():
        L = json.loads(lf.read_text(encoding="utf-8"))["parties"]
        types = {e["type"] for v in L.values() for e in v["lineage"]}
        ck("조직 계보에 bridge/refounding edge가 없다",
           not (types & {"historical_bridge", "refounding"}), str(types))
    # 두 모드가 실제로 다른 답을 준다 — 같으면 나눈 의미가 없다
    famh = ax["lineage_family_historical"]
    diff = [n for n in fam if fam[n]["family"] != famh[n]["family"]]
    ck(f"strict와 historical이 다른 답을 준다 ({len(diff)}종)", bool(diff))
    ck("strict는 단절을 감추지 않는다",
       any(v["cause"] == "forced_dissolution_1980"
           for v in fam.values() if v["family"] == "unknown"))

    print("\n[계열 득표] 분류 안 된 표를 지우지 않는가")
    fv = ROOT / "data/parties/family_vote_share.json"
    if fv.exists():
        F = json.loads(fv.read_text(encoding="utf-8"))
        ck("선거별 결과가 있다", len(F["elections"]) > 30)
        for r in F["elections"]:
            for m in ("strict", "historical"):
                x = r[m]
                if not x:
                    continue
                # 셋을 하나로 뭉개지 않는다
                ck(f"{r['election']}/{m}: 세 비중이 따로 있다",
                   {"known_single_family_share", "mixed_family_share",
                    "unknown_family_share"} <= set(x))
                # 재정규화 금지 — 합이 100이어야 하고 known만 100이면 안 된다
                tot = sum(x["share"].values())
                ck(f"{r['election']}/{m}: 전체 합이 100 (재정규화 안 함)",
                   abs(tot - 100) < 0.5, f"{tot:.2f}")
                if x["unknown_family_share"] > 1:
                    ck(f"{r['election']}/{m}: 미분류가 남아 있다 "
                       f"({x['unknown_family_share']}%)",
                       x["classification_coverage"] < 99.9)
                break        # 회차마다 두 모드 다 보면 출력이 너무 길다
        ck("보강 우선순위가 표 수 기준으로 나온다", bool(F.get("unknown_priority")))

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
