"""관측된 정당명과 **확인된 정당**을 같은 것으로 다루지 않는가.

registry.json = 정식명·창당·계보를 확인한 정당.
observed.json = 결과에 이름이 나온 것. 여기 있다고 계보를 아는 게 아니다.

둘을 한 집합으로 취급하면 '계보를 안다'는 뜻이 희석된다 — 한 그릇에 두 의미를 담는
그 실패다. 이 검사는 셋을 본다:

  ① 관측 합계가 원자료와 맞는가 (유도값이 실제로 유도된 것인가)
  ② 결과에 나왔다는 이유만으로 registry에 들어가지 않았는가
  ③ 동음이의 큐가 비어 가는가 (예외 목록으로 굳지 않는가)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/build"))
fails: list = []


def ck(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        fails.append(name)
        print(f"  ✗ {name}{' — ' + detail if detail else ''}")


obs = json.loads((ROOT / "data/parties/observed.json").read_text(encoding="utf-8"))
reg = json.loads((ROOT / "data/parties/registry.json").read_text(encoding="utf-8"))["parties"]
hom = json.loads((ROOT / "data/parties/known_homonyms.json").read_text(encoding="utf-8"))
rows = obs["parties"]

# ① 유도값이 실제로 유도된 것인가 — build_runs를 다시 돌려 합계를 맞춘다
from build_party_pages import build_runs  # noqa: E402

runs = build_runs()
tot_o = (sum(r["candidates"] for r in rows), sum(r["votes"] for r in rows),
         sum(r["wins"] for r in rows))
tot_r = (sum(x["candidates"] for rs in runs.values() for x in rs),
         sum(x["votes"] for rs in runs.values() for x in rs),
         sum(x["won"] for rs in runs.values() for x in rs))
ck(f"관측 합계가 원자료와 일치 {tot_o} vs {tot_r}", tot_o == tot_r)
ck("관측 종수가 일치", len(rows) == len([k for k, v in runs.items() if v]))

# ② 결과에 나왔다는 이유만으로 registry에 들어가지 않았는가
#    (registry는 '확인한 것'의 목록이다 — 관측이 그 자격을 주지 않는다)
linked = [r for r in rows if r["registry_id"]]
ck("registry_id는 registry에 실제로 있는 이름만",
   all(r["registry_id"] in reg for r in linked))
unres = [r for r in rows if r["status"] == "unresolved"]
ck("미확인은 registry에 링크되지 않는다", all(not r["registry_id"] for r in unres))
ck("미확인이 존재한다는 사실을 숨기지 않는다", len(unres) > 0, str(len(unres)))

# 추론 금지 필드가 새어 들어오지 않았는가
BANNED = {"founded", "dissolved", "predecessors", "successors", "stream", "lineage"}
for r in rows[:50]:
    leaked = BANNED & set(r)
    ck(f"{r['name']}: 추론 필드가 없다", not leaked, str(leaked))

# ③ 동음이의는 예외 목록이 아니라 큐다 — 사유와 상태가 있어야 한다
ck("동음이의 항목에 사유·상태가 있다",
   all(x.get("reason") and x.get("status") and x.get("note") for x in hom["unresolved"]))
ck("동음이의 큐가 무한정 늘지 않는다", len(hom["unresolved"]) <= 12,
   f'{len(hom["unresolved"])}건 — 늘어나면 해소해야 한다')

print(f"\n[관측 정당 층] 실패 {len(fails)}")
sys.exit(1 if fails else 0)
