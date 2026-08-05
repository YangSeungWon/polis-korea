"""정당 계보 그래프의 **비대칭을 고친다** — 새 사실을 넣지 않는다.

`A.successors = [B]`인데 `B.predecessors`가 비어 있는 경우가 있다. 같은 관계를 한
방향으로만 적어 둔 것이고, 반대 방향을 채우는 건 새 주장이 아니라 이미 있는 주장을
읽을 수 있게 만드는 일이다.

이게 실제로 lineage_family 유도를 막고 있었다. 민주계 사슬이 2011년 민주통합당에서
끊겨 더불어민주당이 `unknown`이었는데, 원인은 자료가 없어서가 아니라
`통합민주당.successors = ['민주통합당']`만 있고 그 반대가 없어서였다.

**하지 않는 것**: 없는 관계를 추정해서 만들지 않는다. 당명이 비슷하다거나 시기가
이어진다는 이유로 잇지 않는다. 한쪽에 명시적으로 적힌 것만 반대편에 복사한다.
그리고 시점이 맞지 않으면(전신이 후신보다 나중에 생겼다면) 복사하지 않고 보고한다 —
같은 당명이 수십 년 뒤 재사용되기 때문이다(민주노동당 2000 ↔ 2025).

사용: python scripts/normalize/symmetrize_party_graph.py [--write]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "data/parties/registry.json"


def ym(s: str | None) -> str:
    return (s or "")[:7]


def temporal_ok(reg: dict, child: str, parent: str) -> bool:
    """전신(parent)이 후신(child)보다 먼저 있었는가."""
    cf, pf = ym(reg[child].get("founded")), ym(reg[parent].get("founded"))
    if not cf or not pf:
        return True
    return pf <= cf


def split_rename_absorptions(reg: dict) -> list[str]:
    """개명·합당의 전신은 **후신이 생길 때 이미 해산해 있어야** 한다.

    아니면 그건 전신이 아니라 나중에 흡수당한 당이다. 창당 연도만 보면 못 가른다:

      새누리당(2012-02, 한나라당 개명)이 2012-11에 흡수한 자유선진당은 2008년 창당이라
      '먼저 있었다'는 검사를 통과한다.
      한나라당(1997-11)이 2006-04에 흡수한 자유민주연합은 1995년 창당이라 마찬가지다.

    그대로 두면 국민의힘 계보가 충청 지역계로 흘러간다(실제로 그랬다).

    분당(split)은 다르다 — 모체가 계속 존속하므로 이 규칙을 적용하지 않는다.
    (정의당은 통합진보당에서 갈라졌고 통진당은 2014년까지 있었다.)
    날짜가 없으면 판단하지 않는다.
    """
    moved = []
    for name, info in reg.items():
        if info.get("relation") not in ("rename", "merge"):
            continue
        f = ym(info.get("founded"))
        if not f:
            continue
        keep, drop = [], []
        for p in info.get("predecessors") or []:
            d = ym((reg.get(p) or {}).get("dissolved"))
            (drop if d and d > f else keep).append(p)
        if not drop or not keep:
            continue          # 전부 남거나 전부 빠지면 판단 근거가 약하다 — 건드리지 않는다
        for p in drop:
            info.setdefault("absorbed", []).append(p)
            moved.append(f"{name}({f}): 전신 → 흡수 {p}"
                         f"(해산 {ym(reg[p].get('dissolved'))}) · 전신은 {'·'.join(keep)}")
        info["predecessors"] = keep
    return moved


def main(write: bool) -> int:
    doc = json.loads(REG.read_text(encoding="utf-8"))
    reg = doc["parties"]
    added_p, added_s, rejected, absorbed = [], [], [], []

    for name, info in reg.items():
        for s in info.get("successors") or []:
            if s not in reg:
                continue
            preds = reg[s].setdefault("predecessors", [])
            if name in preds:
                continue
            if not temporal_ok(reg, s, name):
                # 후신이 전신보다 먼저 생겼다 = 전신이 아니라 **흡수당한 쪽**이다.
                # 더불어시민당(2020)은 더불어민주당(2015)의 전신일 수 없다 — 위성정당이
                # 합당으로 들어간 것이다. 이걸 predecessors에 넣으면 계열 전파가
                # 거꾸로 흐른다. absorbed로 따로 적어 전파에서 빼게 한다.
                if name in (reg[s].get("predecessors") or []):
                    pass
                else:
                    reg[s].setdefault("absorbed", [])
                    if name not in reg[s]["absorbed"]:
                        reg[s]["absorbed"].append(name)
                        absorbed.append(f"{s} ⊃ {name}")
                rejected.append(f"{s} ← {name}: 흡수({ym(info.get('founded'))} > "
                                f"{ym(reg[s].get('founded'))})")
                continue
            preds.append(name)
            added_p.append(f"{s} ← {name}")

    for name, info in reg.items():
        for p in info.get("predecessors") or []:
            if p not in reg:
                continue
            succ = reg[p].setdefault("successors", [])
            if name in succ:
                continue
            if not temporal_ok(reg, name, p):
                rejected.append(f"{p}.successors += {name} (시점 불일치)")
                continue
            succ.append(name)
            added_s.append(f"{p} → {name}")

    moved = split_rename_absorptions(reg)

    # 빈 리스트를 새로 만들지 않는다 — 원래 없던 키가 생기면 diff가 지저분해진다
    for info in reg.values():
        for k in ("predecessors", "successors", "absorbed"):
            if k in info and not info[k]:
                del info[k]
            elif k in info:
                info[k] = sorted(dict.fromkeys(info[k]))

    print(f"predecessors 보강 {len(added_p)}건")
    for x in added_p:
        print(f"  {x}")
    print(f"successors 보강 {len(added_s)}건")
    for x in added_s[:10]:
        print(f"  {x}")
    if moved:
        print(f"\n개명 정당의 전신 정리 {len(moved)}건")
        for x in moved:
            print(f"  {x}")
    if absorbed:
        print(f"\n흡수로 기록 {len(absorbed)}건 (전신이 아니라 흡수당한 쪽 — 계열 전파에서 제외)")
        for x in absorbed:
            print(f"  {x}")
    if rejected:
        print(f"\n전신으로 잇지 않음 {len(rejected)}건")
        for x in rejected:
            print(f"  {x}")
    if write:
        REG.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("\n→ registry.json 갱신")
    else:
        print("\n(--write 없이 실행 — 저장하지 않음)")
    return 0


if __name__ == "__main__":
    sys.exit(main("--write" in sys.argv))
