"""정당의 **생애 사건**과 **계보 edge**를 나눈다.

## 왜

registry의 `relation` 한 필드가 '어떻게 생겼나'와 '어떻게 끝났나'를 같이 담고 있다.
신민당은 `relation=dissolve`(1980 해산)인데 `predecessors=['민중당']`(1967 창당 경위)이라,
계열 전파가 거기서 끊긴다. `stream`·`level`·`comparable`과 같은 종류의 압축이다.

    ended_by = dissolution      ≠  계보에 후신이 없다
    ended_by = absorption_into A ≠  A가 흡수당의 계열을 상속한다

그래서 세 가지를 따로 둔다.

    formed_by   어떻게 생겼나 — foundation | rename | merger | split | ambiguous
    ended_by    어떻게 끝났나 — dissolution | rename | merger | absorption_into | split | ambiguous
    lineage     누구의 계보를 잇나 — continuation | split_from | merged_from | absorbed_into

**날짜는 검증 근거이지 사실 생성기가 아니다.** 기존 predecessors/successors와
창당·해산 시점으로 **확정되는 것만** 유도하고, 확정 안 되면 `ambiguous`로 남긴다.
legacy `relation`은 지우지 않는다.

사용: python scripts/normalize/party_lifecycle.py [--write]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "data/parties/registry.json"
OUT = ROOT / "data/parties/lifecycle.json"

# 계보 edge 유형 → 계열을 전파하는가
PROPAGATE = {
    "continuation": True,    # 개명·조직 연속 — 그대로 전파
    "split_from": True,      # 모체 계열을 후보값으로 전파
    "merged_from": True,     # 진짜 합당 — 각 계열을 union, 갈리면 mixed
    "absorbed_into": False,  # 흡수 — 흡수당의 계열을 존속당에 전파하지 않는다
    "alliance": False,       # 선거연합
    "unrelated": False,
}


def ym(s) -> str:
    return (s or "")[:7]


def derive(reg: dict) -> dict:
    """확정되는 것만 유도한다. 애매하면 ambiguous."""
    out: dict = {}
    # 누가 누구를 전신으로 적었는지 (successors 방향 역인덱스)
    for name, info in reg.items():
        f, d = ym(info.get("founded")), ym(info.get("dissolved"))
        preds = [p for p in (info.get("predecessors") or []) if p in reg]
        succs = [s for s in (info.get("successors") or []) if s in reg]
        absorbed = [a for a in (info.get("absorbed") or []) if a in reg]

        # ── 어떻게 생겼나 ────────────────────────────────────────────────
        # 한시 개명(왕복) — A의 전신이자 후신이 같은 B다. 정의당→민주노동당(2025)→정의당.
        # 이걸 split으로 보면 계열이 갈라져 나온 것처럼 읽힌다. 같은 entity의 이름 변경이다.
        roundtrip = sorted(set(preds) & set(succs))

        formed, fwhy, fparts, cause = None, "", [], None
        if roundtrip:
            formed, fparts = "temporary_rename", roundtrip
            fwhy = f"{'·'.join(roundtrip)}의 전신이자 후신 — 한시 당명(같은 정당)"
        elif not preds:
            if info.get("relation") == "new":
                formed, fwhy = "foundation", "relation=new이고 전신이 없다"
            else:
                formed, cause = "ambiguous", "missing_predecessor_record"
                fwhy = (f"legacy relation={info.get('relation')}는 상대가 있는 관계인데 "
                        "전신이 기록돼 있지 않다")
        else:
            # 전신이 후신 창당 시점에 해산했는가 — 끊김 없이 이어졌다는 뜻
            cont = [p for p in preds if f and ym(reg[p].get("dissolved")) == f]
            alive = [p for p in preds if p not in cont]
            if len(preds) == 1 and cont:
                formed, fparts = "rename", preds
                fwhy = f"{preds[0]}이 {f}에 해산하고 같은 달에 생겼다"
            elif len(preds) == 1 and alive:
                formed, fparts = "split", preds
                fwhy = f"{preds[0]}이 존속하는 중에 갈라져 나왔다"
            elif len(preds) >= 2 and not alive:
                formed, fparts = "merger", preds
                fwhy = f"전신 {len(preds)}곳이 모두 {f}에 해산했다"
            else:
                formed, fparts, cause = "ambiguous", preds, "partial_timing_match"
                fwhy = (f"전신 중 일부만 시점이 맞물린다 — 해산 일치 {cont}, "
                        f"존속 {alive}")

        # ── 어떻게 끝났나 ────────────────────────────────────────────────
        ended, ewhy, eparts = None, "", []
        if not d:
            ended, ewhy = None, "현존"
        elif not succs:
            ended, ewhy = "dissolution", "후신 기록이 없다"
        elif roundtrip and set(succs) <= set(roundtrip):
            # 한시 당명은 **끝난 게 아니라 이름을 되돌린 것**이다. 형성 쪽에서만
            # roundtrip을 보고 종료 쪽에서 안 보면, 모체가 먼저 생겼다는 이유로
            # absorption_into가 붙어 '정의당에 흡수됐다'가 된다 — 흡수가 아니다.
            ended, eparts = "temporary_rename", list(roundtrip)
            ewhy = f"{'·'.join(roundtrip)}으로 이름을 되돌렸다 — 흡수가 아니다"
        else:
            later = [s for s in succs if ym(reg[s].get("founded")) == d]
            earlier = [s for s in succs if ym(reg[s].get("founded")) and
                       ym(reg[s].get("founded")) < d]
            if len(succs) == 1 and later:
                s = succs[0]
                n_pred = len([p for p in (reg[s].get("predecessors") or []) if p in reg])
                ended, eparts = ("rename" if n_pred == 1 else "merger"), succs
                ewhy = (f"{s}이 같은 달({d})에 생겼고 그 전신이 "
                        f"{n_pred}곳이다")
            elif earlier:
                ended, eparts = "absorption_into", earlier
                ewhy = f"{'·'.join(earlier)}은 이미 있던 정당이다 — 흡수됐다"
            elif len(succs) >= 2 and later:
                ended, eparts = "split", succs
                ewhy = f"{d}에 여러 곳으로 갈라졌다"
            else:
                ended, eparts = "ambiguous", succs
                ewhy = "후신 시점이 해산 시점과 맞물리지 않는다"
                cause = cause or "successor_timing_mismatch"

        # ── 계보 edge ────────────────────────────────────────────────────
        # 생애 사건과 별개다. dissolution이어도 계보는 이어질 수 있고,
        # absorption이면 흡수당의 계열을 존속당에 전파하지 않는다.
        edges = []
        if formed in ("rename", "temporary_rename"):
            edges += [{"to": p, "type": "continuation"} for p in fparts]
        elif formed == "split":
            edges += [{"to": p, "type": "split_from"} for p in fparts]
        elif formed == "merger":
            edges += [{"to": p, "type": "merged_from"} for p in fparts]
        for a in absorbed:
            if a in roundtrip:
                continue          # 한시 당명은 흡수가 아니다
            edges.append({"to": a, "type": "absorbed_into", "note": "계열 전파 없음"})

        out[name] = {
            "founded": info.get("founded"), "dissolved": info.get("dissolved"),
            "legacy_relation": info.get("relation"),
            "formed_by": {"type": formed, "parties": fparts, "why": fwhy},
            "ended_by": {"type": ended, "parties": eparts, "why": ewhy},
            "lineage": edges,
            "migration": ("derived" if formed not in (None, "ambiguous")
                          and ended != "ambiguous" else "ambiguous"),
            "ambiguity_cause": cause,
        }
    return out


def main(write: bool) -> int:
    reg = json.loads(REG.read_text(encoding="utf-8"))["parties"]
    life = derive(reg)
    import collections
    cf = collections.Counter(v["formed_by"]["type"] for v in life.values())
    ce = collections.Counter(v["ended_by"]["type"] for v in life.values())
    cm = collections.Counter(v["migration"] for v in life.values())
    print("formed_by:", dict(cf))
    print("ended_by :", dict(ce))
    print("migration:", dict(cm))
    amb = [n for n, v in life.items() if v["migration"] == "ambiguous"]
    print(f"\nambiguous {len(amb)}종 — 자료만으로 확정할 수 없다(추정하지 않는다)")
    for n in amb[:8]:
        v = life[n]
        print(f"  {n:14} formed={v['formed_by']['type']:10} {v['formed_by']['why'][:56]}")
    doc = {
        "_note": ("정당의 생애 사건(formed_by/ended_by)과 계보 edge(lineage)를 나눠 담는다. "
                  "registry의 `relation`은 두 의미가 섞여 있어 그대로 두고(legacy_relation) "
                  "여기서 다시 세운다. 날짜는 검증 근거이지 사실 생성기가 아니다 — "
                  "확정되는 것만 유도하고 나머지는 ambiguous다."),
        "_rules": {
            "ended_by=dissolution": "계보에 후신이 없다는 뜻이 **아니다**",
            "ended_by=absorption_into A": "A가 흡수당의 계열을 상속한다는 뜻이 **아니다**",
            "propagate": PROPAGATE,
        },
        "parties": life,
    }
    if write:
        OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
        print(f"\n→ {OUT.name}")
    else:
        print("\n(--write 없이 실행 — 저장하지 않음)")
    return 0


if __name__ == "__main__":
    sys.exit(main("--write" in sys.argv))
