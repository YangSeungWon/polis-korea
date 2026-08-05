"""지리 계보 — 행정구역·선거구 변화를 하나의 그래프로.

**entity는 분리, lineage는 연결.** 이천군과 이천시는 다른 entity다. 1995년 데이터에
이천군이 남아야 한다 — 합치면 그때 행정단위가 이천시였던 것처럼 왜곡된다.

두 층으로 나눈다:
  candidates  우리 데이터에서 **자동 탐지**한 변화 후보 (근거 없음)
  events      근거를 확인해 확정한 이벤트 (evidence 필수)

자동 탐지는 누락을 막는 그물이지 사실의 출처가 아니다. 날짜·성격은 사람이 확인한
자료로만 채운다 — 추정해서 만들지 않는다.

Output:
  data/geography/candidates.json   탐지된 변화 후보 (검토 대기)
  data/geography/entities.json     확정 이벤트에서 파생한 entity 목록

사용: python3 scripts/normalize/build_geography_lineage.py
"""
from __future__ import annotations
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/geography"
EVENTS = OUT / "events.json"
CONTAIN = OUT / "containment.json"

sys.path.insert(0, str(ROOT / "scripts/build"))
from build_region_pages import collect as collect_regions  # noqa: E402


def entity_id(kind: str, parent: str, name: str) -> str:
    """namespace를 분리한다 — admin과 electoral을 같은 entity로 잇지 않는다."""
    return f"{kind}:{parent}:{name}"


def detect_admin_candidates() -> list:
    """선거 결과에 나타난 (시도, 시군구)의 등장 기간에서 변화 후보를 찾는다.

    두 가지를 본다:
      · 같은 시군구명인데 시도가 바뀜        → transfer 후보
      · X군 다음에 X시가 나타남(기간 인접)   → promotion 후보

    **후보일 뿐이다.** 실제 날짜와 성격은 자료로 확인해야 한다.
    """
    spans: dict = {}
    for (sido, sgg), rows in collect_regions().items():
        ds = sorted((r.get("date") or "")[:10] for r in rows if r.get("date"))
        if not ds:
            continue
        spans[(sido, sgg)] = (ds[0], ds[-1], len(rows))

    out = []
    by_name = defaultdict(list)
    for (sido, sgg), v in spans.items():
        by_name[sgg].append((sido, v))

    # ① 같은 이름, 다른 시도 — 기간이 겹치지 않으면 이관 후보
    for sgg, lst in by_name.items():
        if len(lst) < 2:
            continue
        lst = sorted(lst, key=lambda x: x[1][0])
        for i in range(1, len(lst)):
            (s0, v0), (s1, v1) = lst[i - 1], lst[i]
            if s0 == s1 or v0[1] >= v1[0]:
                continue          # 기간이 겹치면 동명이지 이관이 아니다
            out.append({
                "guess": "transfer", "kind": "admin_unit", "name": sgg,
                "from": {"parent": s0, "last_seen": v0[1], "n": v0[2]},
                "to": {"parent": s1, "first_seen": v1[0], "n": v1[2]},
            })

    # ② X군 → X시 (같은 시도, 기간 인접) — 승격 후보
    for (sido, sgg), v in spans.items():
        if not sgg.endswith("군"):
            continue
        si = sgg[:-1] + "시"
        w = spans.get((sido, si))
        if not w or v[1] >= w[0]:
            continue
        out.append({
            "guess": "promotion", "kind": "admin_unit", "name": f"{sgg} → {si}",
            "from": {"parent": sido, "name": sgg, "last_seen": v[1], "n": v[2]},
            "to": {"parent": sido, "name": si, "first_seen": w[0], "n": w[2]},
        })
    return sorted(out, key=lambda x: (x["guess"], x["name"]))


def detect_district_candidates() -> list:
    """선거구 계보(district_lineage)에서 split·merge를 이벤트 후보로 옮긴다.
    이미 폴리곤 교차로 판정한 것이므로 근거가 있다 — 다만 kind가 다르다."""
    out = []
    lin_dir = ROOT / "data/district_lineage"
    if not lin_dir.exists():
        return out
    for fp in sorted(lin_dir.glob("*__*.json"), key=lambda p: -int(p.stem.split("__")[0])):
        d = json.loads(fp.read_text(encoding="utf-8"))
        cur_n, prev_n = d["_meta"]["current_n"], d["_meta"]["previous_n"]
        for u in d["units"]:
            if u["relation"] not in ("split", "merged"):
                continue
            out.append({
                "guess": u["relation"], "kind": "electoral_district",
                "name": u["district"], "round": f"{prev_n}→{cur_n}대",
                "previous": [p["prev"] for p in u.get("previous") or []][:4],
                "reason": u["reason"], "reason_code": u["reason_code"],
                "source": f"district_lineage/{fp.stem}",
            })
        break        # 가장 최근 쌍만 — 첫 슬라이스는 좁게
    return out


def load_events() -> list:
    if EVENTS.exists():
        return json.loads(EVENTS.read_text(encoding="utf-8")).get("events") or []
    return []


def load_containments() -> list:
    if CONTAIN.exists():
        return json.loads(CONTAIN.read_text(encoding="utf-8")).get("containments") or []
    return []


def derive_entities(events: list, contains: list | None = None) -> list:
    """확정 이벤트에서 entity와 유효기간을 파생한다.

    포함관계(containment)의 하위 단위도 entity로 싣되 **상위 단위를 끝내지 않는다**.
    포항시남구는 포항시의 후신이 아니라 하위 일반구다 — from/to로 적으면 포항시가
    1995년에 소멸한 것이 된다.
    """
    ents: dict = {}

    def touch(e: dict):
        eid = e["id"]
        cur = ents.setdefault(eid, {**e})
        for k in ("valid_from", "valid_to"):
            if e.get(k) and not cur.get(k):
                cur[k] = e[k]

    for ev in events:
        for side, dk in (("from", "valid_to"), ("to", "valid_from")):
            for ent in ev.get(side) or []:
                touch({**ent, dk: ev["effective_date"]})
    for c in contains or []:
        for cid in c["children"]:
            kind, parent, name = cid.split(":", 2)
            touch({"id": cid, "kind": kind, "parent": parent, "name": name,
                   "valid_from": c["effective_date"], "contained_in": c["parent"]})
    return sorted(ents.values(), key=lambda x: (x["kind"], x["id"]))


def region_timeline(events: list) -> dict:
    """현재 지역 → 그 지역에 이르기까지의 이벤트. 지역 페이지 타임라인이 이걸 먹는다.

    선거 기록 사이에 행정구역 변화가 끼어야 '왜 1997년부터 시작하지?'가 사라진다:
        1995  제1회 지방선거      이천군
        1996  행정구역 변화        이천군 → 이천시 · 승격
        1997  제15대 대통령선거    이천시
    """
    out: dict = defaultdict(list)
    for ev in events:
        if ev["kind"] != "admin_unit":
            continue
        for to in ev.get("to") or []:
            # region 페이지 slug와 같은 형태로 — {시도}-{시군구}
            slug = f"{to['parent']}-{to['name']}"
            out[slug].append({
                "date": ev["effective_date"],
                "type": ev["type"],
                "label": ev["label"],
                "from": [f"{x['parent']} {x['name']}" for x in ev.get("from") or []],
                "comparison_capability": ev["comparison_capability"],
                "predecessor_slugs": [f"{x['parent']}-{x['name']}"
                                      for x in ev.get("from") or []],
            })
        # 전신 쪽에도 남긴다 — 옛 지역 페이지에서 후신으로 갈 수 있어야 한다
        for fr in ev.get("from") or []:
            slug = f"{fr['parent']}-{fr['name']}"
            out[slug].append({
                "date": ev["effective_date"],
                "type": ev["type"],
                "label": ev["label"],
                "to": [f"{x['parent']} {x['name']}" for x in ev.get("to") or []],
                "comparison_capability": ev["comparison_capability"],
                "successor_slugs": [f"{x['parent']}-{x['name']}"
                                    for x in ev.get("to") or []],
            })
    return {k: sorted(v, key=lambda x: x["date"]) for k, v in out.items()}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cand = {
        "_meta": {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "note": ("우리 선거 데이터에서 **자동 탐지**한 변화 후보다. 누락을 막는 "
                     "그물이지 사실의 출처가 아니다 — 실제 날짜와 성격은 자료로 "
                     "확인해 events.json에 옮긴다. 여기 있다고 사실이 아니다."),
        },
        "admin_unit": detect_admin_candidates(),
        "electoral_district": detect_district_candidates(),
    }
    (OUT / "candidates.json").write_text(
        json.dumps(cand, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    events = load_events()
    ents = derive_entities(events, load_containments())
    (OUT / "entities.json").write_text(json.dumps(
        {"_meta": {"note": "events.json에서 파생 — 직접 편집하지 않는다.",
                   "n": len(ents)},
         "entities": ents}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"→ candidates: 행정구역 {len(cand['admin_unit'])}"
          f" · 선거구 {len(cand['electoral_district'])}", file=sys.stderr)
    tl = region_timeline(events)
    (OUT / "region_timeline.json").write_text(json.dumps(
        {"_meta": {"note": ("지역 페이지 타임라인용 — 선거 기록 사이에 끼울 행정구역 "
                            "변화 이벤트. events.json에서 파생, 직접 편집하지 않는다."),
                   "n": len(tl)},
         "by_region": tl}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"→ events {len(events)} · entities {len(ents)} · 타임라인 지역 {len(tl)}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
