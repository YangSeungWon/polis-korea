"""지리 계보 불변식 — 역사 데이터는 스스로 검증할 수 있다.

**entity는 분리, lineage는 연결.** 이천군과 이천시는 다른 entity다. 합쳐버리면
1995년 행정단위가 이천시였던 것처럼 왜곡된다.

**역사가 이어진다 ≠ 숫자가 직접 비교된다.** 계보를 이어도 delta를 붙일 수 있는지는
별도 판정이고, event type에서 기계적으로 나오지 않는다.

실행: .venv/bin/python tests/test_geography_lineage.py
"""
from __future__ import annotations
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEO = ROOT / "data/geography"
KINDS = {"admin_unit", "electoral_district"}
TYPES = {"rename", "promotion", "transfer", "split", "merge",
         "boundary_change", "created", "abolished"}
CAPS = {"direct", "aggregated", "reaggregated", "context_only", "unknown"}
ONE_TO_ONE = {"rename", "promotion", "transfer"}

fails: list[str] = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    ev_fp = GEO / "events.json"
    ck("events.json이 있다", ev_fp.exists())
    if not ev_fp.exists():
        print("\n실패 1")
        return 1
    doc = json.loads(ev_fp.read_text(encoding="utf-8"))
    events = doc["events"]
    ents = {e["id"]: e for e in json.loads(
        (GEO / "entities.json").read_text(encoding="utf-8"))["entities"]}

    print(f"\n[어휘] 정의된 값만 쓰는가 (이벤트 {len(events)})")
    ck("type이 정의된 것뿐", all(e["type"] in TYPES for e in events),
       str({e["type"] for e in events} - TYPES))
    ck("kind가 둘뿐", all(e["kind"] in KINDS for e in events),
       str({e["kind"] for e in events} - KINDS))
    ck("comparison_capability가 정의된 것뿐",
       all(e["comparison_capability"] in CAPS for e in events),
       str({e["comparison_capability"] for e in events} - CAPS))

    print("\n[구조] 관계가 성립하는가")
    ck("split은 1 → N", all(len(e["from"]) == 1 and len(e["to"]) >= 2
                            for e in events if e["type"] == "split"))
    ck("merge는 N → 1", all(len(e["from"]) >= 2 and len(e["to"]) == 1
                            for e in events if e["type"] == "merge"))
    ck("rename·promotion·transfer는 1 → 1",
       all(len(e["from"]) == 1 and len(e["to"]) == 1
           for e in events if e["type"] in ONE_TO_ONE))
    ck("from·to의 entity가 전부 존재",
       all(x["id"] in ents for e in events for s in ("from", "to") for x in e[s]),
       str([x["id"] for e in events for s in ("from", "to") for x in e[s]
            if x["id"] not in ents][:3]))
    ck("모든 이벤트에 근거가 있다",
       all(e.get("evidence") for e in events),
       str([e["id"] for e in events if not e.get("evidence")]))
    ck("모든 이벤트에 사람이 읽을 label이 있다", all(e.get("label") for e in events))

    print("\n[namespace] admin과 electoral을 섞지 않는가")
    mixed = [e["id"] for e in events
             for x in (e["from"] + e["to"]) if x["kind"] != e["kind"]]
    ck("한 이벤트 안에서 kind가 일관", not mixed, str(mixed[:3]))
    ck("entity id가 kind로 시작", all(e["id"].startswith(e["kind"] + ":")
                                     for e in ents.values()),
       str([e["id"] for e in ents.values() if not e["id"].startswith(e["kind"] + ":")][:3]))
    # 선거구는 회차가 identity의 일부다 — 21대와 22대 부천시갑은 다른 영역이다
    ed = [e for e in ents.values() if e["kind"] == "electoral_district"]
    ck("선거구 id에 회차가 들어 있다",
       all(len(e["id"].split(":")) >= 4 and e["id"].split(":")[1].isdigit() for e in ed),
       str([e["id"] for e in ed if not e["id"].split(":")[1].isdigit()][:3]))

    print("\n[시간] 유효기간이 모순되지 않는가")
    bad = []
    for e in ents.values():
        f, t = e.get("valid_from"), e.get("valid_to")
        if f and t and date.fromisoformat(f) >= date.fromisoformat(t):
            bad.append(f"{e['id']} {f}~{t}")
    ck("valid_from < valid_to", not bad, str(bad[:3]))
    ck("이벤트에 시행일이 있다", all(e.get("effective_date") for e in events))

    print("\n[계보] entity를 합치지 않는가")
    # rename/promotion/transfer라고 해서 하나로 합치면 안 된다 — 별개 entity여야 한다
    same = [e["id"] for e in events if e["type"] in ONE_TO_ONE
            and e["from"][0]["id"] == e["to"][0]["id"]]
    ck("1:1 이벤트도 from ≠ to (entity는 분리)", not same, str(same))
    # 순환 없음
    nxt = defaultdict(set)
    for e in events:
        for a in e["from"]:
            for b in e["to"]:
                nxt[a["id"]].add(b["id"])
    cyc = []
    for start in nxt:
        seen, stack = set(), [start]
        while stack:
            n = stack.pop()
            if n == start and n in seen:
                cyc.append(start)
                break
            if n in seen:
                continue
            seen.add(n)
            stack.extend(nxt.get(n, ()))
    ck("계보에 순환이 없다", not cyc, str(cyc[:3]))

    print("\n[비교 가능성] type에서 기계적으로 나오지 않는가")
    for e in events:
        ck(f"{e['id'][4:32]}: capability 사유가 있다", bool(e.get("capability_reason")))
    # aggregated는 전신 전체가 후신에 포함될 때만
    agg = [e for e in events if e["comparison_capability"] == "aggregated"]
    ck("aggregated는 territorial_continuity가 same/same_total",
       all(e.get("territorial_continuity") in ("same", "same_total") for e in agg),
       str([(e["id"], e.get("territorial_continuity")) for e in agg]))
    # reaggregated는 하위 실측 provenance가 있을 때만
    rea = [e for e in events if e["comparison_capability"] == "reaggregated"]
    ck("reaggregated는 하위 실측 근거를 명시한다",
       all(any("실측" in str(v) or "투표구" in str(v) or "읍면동" in str(v)
               for v in e.get("evidence") or []) for e in rea),
       str([e["id"] for e in rea]))
    # 부분 포함인데 aggregated면 틀린 것 — 부천이 그 사례다
    partial_agg = [e["id"] for e in events
                   if e.get("territorial_continuity") == "partial"
                   and e["comparison_capability"] in ("direct", "aggregated")]
    ck("부분 포함(partial)은 direct·aggregated가 아니다", not partial_agg, str(partial_agg))

    print("\n[fixture] 대표 4건이 의도대로 판정됐는가")
    by = {e["id"]: e for e in events}
    FIX = [
        ("geo:1996-03-01:icheon-promotion", "promotion", "direct", "영역 그대로 · 군→시"),
        ("geo:2023-07-01:gunwi-transfer", "transfer", "direct", "영역 그대로 · 상위만 변경"),
        ("geo:2024-22nd:hanam-split", "split", "context_only", "갑/을로 나눌 하위 실측 없음"),
        ("geo:2024-22nd:bucheon-merge", "merge", "context_only",
         "전신 전체가 안 들어와 합산 불가"),
    ]
    for eid, typ, cap, why in FIX:
        e = by.get(eid)
        ck(f"{eid.split(':')[-1]} = {typ}/{cap} ({why})",
           bool(e) and e["type"] == typ and e["comparison_capability"] == cap,
           f"{(e or {}).get('type')}/{(e or {}).get('comparison_capability')}")

    print("\n[후보] 자동 탐지는 사실이 아니다")
    cand = json.loads((GEO / "candidates.json").read_text(encoding="utf-8"))
    ck("candidates에 '사실이 아니다'가 명시돼 있다",
       "사실의 출처가 아니" in cand["_meta"]["note"])
    ck("탐지된 후보가 있다", cand["admin_unit"] or cand["electoral_district"])
    ck("후보에는 시행일이 없다 (근거 확인 전)",
       all("effective_date" not in c for c in cand["admin_unit"]))

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
