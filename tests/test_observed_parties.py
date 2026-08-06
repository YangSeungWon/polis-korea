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
# 개수 상한을 두지 않는다 — **새 동음이의를 발견하면 큐가 느는 게 정상**이다.
# 상한을 걸면 발견을 억제하게 된다. 대신 큐가 큐답게 동작하는지를 본다:
# 해소된 항목이 unresolved로 남아 있지 않은가.
_stale = [x["name"] for x in hom["unresolved"]
          if x.get("status") == "resolved" or x["name"] in reg and "(" in x["name"]]
ck("해소된 항목이 큐에 남아 있지 않다", not _stale, str(_stale))
ck("큐 항목이 실제로 관측된 이름이다",
   all(x["name"] in {r["name"] for r in rows} for x in hom["unresolved"]),
   str([x["name"] for x in hom["unresolved"]
        if x["name"] not in {r["name"] for r in rows}]))

# ④ 이름을 재사용한 정당은 **시점으로 갈라져야 한다**
#
# disambiguate_party는 registry의 시기 노드 범위(founded~dissolved)로 가른다. 어느
# 범위에도 안 걸리면 조용히 **베이스 이름 그대로** 남는데, 그게 최신 노드로 흘러든다.
# 실제로 그랬다: 정의당(1967)의 dissolved가 1970으로 잘못 적혀 있어 1971년 7대 대선
# 진복기(정의당) 122,914표가 2012년 심상정 정의당 몫으로 붙어 있었다.
#
# 그래서 '이름'이 아니라 **시점 경계**를 검사한다. 관측 구간이 그 이름의 시기 노드
# 범위 안에 들어와야 한다.
sys.path.insert(0, str(ROOT / "scripts/build"))
from party_canon import _BASE_ERAS, _REUSED_BASES, disambiguate_party  # noqa: E402

_by_name = {r["name"]: r for r in rows}
_j = _by_name.get("정의당")
ck("현대 정의당 관측이 2012-10 이후에서 시작한다",
   bool(_j) and _j["first"][:7] >= "2012-10", _j and _j["first"])
ck("1971년 정의당은 정의당(1967)로 간다",
   disambiguate_party("정의당", "1971-04-27") == "정의당(1967)",
   disambiguate_party("정의당", "1971-04-27"))
ck("정의당(1967) 범위가 그 시절 관측을 덮는다",
   bool(_by_name.get("정의당(1967)"))
   and _by_name["정의당(1967)"]["last"][:7] <= (reg["정의당(1967)"].get("dissolved") or ""),
   str(_by_name.get("정의당(1967)")))

# 같은 구멍이 남은 이름들 — **막지는 않되 보이게 둔다.** 여기 있는 것은 시기 노드
# 범위 밖 관측이 섞여 있다는 뜻이고, 정의당과 같은 방식(1차 자료로 경계 확인)으로
# 하나씩 처리해야 한다. 수를 상한으로 막으면 발견이 억제된다.
_leak = []
for r in rows:
    if r["name"] not in _REUSED_BASES:
        continue
    spans = [(f, d) for nm, f, d in _BASE_ERAS[r["name"]] if nm == r["name"]]
    if not spans:
        continue
    f, d = spans[0]
    if r["first"][:7] < f or r["last"][:7] > d:
        _leak.append(f'{r["name"]}({r["first"][:7]}~{r["last"][:7]} vs {f}~{d})')
if _leak:
    print(f"\n  [다음 큐] 시기 노드 범위 밖 관측이 섞인 이름 {len(_leak)}종")
    for x in _leak:
        print(f"    · {x}")

print(f"\n[관측 정당 층] 실패 {len(fails)}")
sys.exit(1 if fails else 0)
