"""관측된 정당명 → `data/parties/observed.json` — **확인된 정당과 다른 층**.

registry.json은 정식명·창당·계보를 **확인한** 정당의 목록이다. 결과 데이터에 이름이
나왔다는 것만으로 거기 넣으면 '계보를 안다'는 뜻이 희석된다 — 한 그릇에 두 의미를
담는 그 실패다.

그래서 관측은 관측대로 따로 싣는다. 여기 들어가는 것은 **원자료에서 확실히 유도되는
사실뿐**이다:

    elections / candidates / votes / wins

창당일·계보·동일정당 여부는 **추론하지 않는다**. 모르면 registry_id가 null이고
status가 unresolved다. '없다'와 '모른다'를 같은 칸에 쓰지 않는다.

사용: python scripts/build/build_observed_parties.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/build"))
from build_party_pages import build_runs  # noqa: E402  (dedup·동음이의 처리 단일 출처)

OUT = ROOT / "data/parties/observed.json"
REG = ROOT / "data/parties/registry.json"
HOM = ROOT / "data/parties/known_homonyms.json"


def main() -> int:
    reg = json.loads(REG.read_text(encoding="utf-8"))["parties"]
    hom = {x["name"]: x for x in
           json.loads(HOM.read_text(encoding="utf-8"))["unresolved"]}
    runs = build_runs()
    rows = []
    for name, rs in runs.items():
        if not rs:
            continue
        rows.append({
            "name": name,
            "elections": len(rs),
            "candidates": sum(r["candidates"] for r in rs),
            "votes": sum(r["votes"] for r in rs),
            "wins": sum(r["won"] for r in rs),
            "first": min(r["date"] for r in rs),
            "last": max(r["date"] for r in rs),
            # 확인된 정당과 이어졌는가. 이어지지 않았다고 '없는 정당'인 것은 아니다.
            "registry_id": name if name in reg else None,
            "status": ("registry" if name in reg
                       else "needs_disambiguation" if name in hom
                       else "unresolved"),
        })
        # 이름이 같다고 **그 정당인 것은 아니다.** registry 노드의 생존 구간을
        # 벗어난 관측이 섞여 있으면 그 사실을 적는다 — 링크를 조용히 유지하면
        # '한나라당 1997~2026 한 정당'처럼 없는 사실이 만들어진다.
        # (예전엔 1971년 정의당·2016년 민주당이 이런 식으로 최신 정당에 붙었다)
        r = rows[-1]
        node = reg.get(r["registry_id"] or "")
        if node:
            f = (node.get("founded") or "")[:7]
            d = (node.get("dissolved") or "9999-99")[:7]
            if f and (r["first"][:7] < f or r["last"][:7] > d):
                r["outside_registry_interval"] = {
                    "node_span": f"{f}~{d}", "observed_span": f'{r["first"][:7]}~{r["last"][:7]}',
                    "why": "같은 이름의 다른 정당이 섞였거나 노드의 날짜 경계가 틀렸다 — 아직 안 갈랐다",
                }
    # 영향도 순 — 222종을 다 조사하는 게 목표가 아니다. 큰 것부터 확인하면 된다.
    rows.sort(key=lambda r: (-r["votes"], -r["candidates"], r["name"]))
    doc = {
        "_note": ("결과 데이터에 **관측된** 정당명. registry.json(정식명·창당·계보를 "
                  "확인한 정당)과 다른 층이다 — 여기 있다고 계보를 아는 게 아니다."),
        "_derived_only": ["elections", "candidates", "votes", "wins", "first", "last"],
        "_not_inferred": ["창당일", "해산일", "계보", "동일정당 여부"],
        "_status": {
            "registry": "registry.json에 확인된 항목이 있다",
            "needs_disambiguation": "이름이 같은 다른 정당이 섞여 있다 — known_homonyms 큐",
            "unresolved": "아직 확인하지 않았다 (없는 정당이라는 뜻이 **아니다**)",
        },
        "_order": "votes desc — 영향이 큰 것부터 확인한다",
        "_outside_registry_interval": (
            "registry 노드의 생존 구간을 벗어난 관측이 섞인 행에 붙는다. "
            "링크를 끊지는 않는다 — 그 이름의 관측 **일부**는 맞기 때문이다"
            "(한나라당 1997~2012은 맞고 2016~2026이 다른 정당이다). "
            "행을 시기별로 쪼개려면 registry에 시기 노드가 있어야 하고, "
            "그건 1차 자료로 하나씩 확인할 일이다. 그때까지 사실을 드러내 둔다."),
        "n": len(rows),
        "parties": rows,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    import collections
    c = collections.Counter(r["status"] for r in rows)
    print(f"→ observed.json: {len(rows)}종 · {dict(c)}", file=sys.stderr)
    top = [r for r in rows if r["status"] == "unresolved"][:5]
    print("  미확인 상위:", ", ".join(f"{r['name']}({r['votes']:,})" for r in top),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
