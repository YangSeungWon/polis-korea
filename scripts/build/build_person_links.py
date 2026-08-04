"""후보 ↔ 인물 연결 색인 → data/person-links/{election_id}.json.

결과 파일의 후보에는 식별자가 없다(name·party·votes뿐). 반면 person-index의 race는
eid·tc·place를 들고 있으므로, 그 조합을 역색인해 (회차, 직, 지역, 이름) → 인물 slug를
만든다. 이름 문자열만으로 잇지 않는 이유는 동명이인 때문이다.

**모호하면 잇지 않는다.** 같은 키에 인물이 둘 이상 걸리면 unresolved로 남긴다. 잘못
연결된 인물 페이지는 없는 링크보다 나쁘다 — 다른 사람의 이력을 그 사람 것으로 보여준다.

Output:
  data/person-links/{election_id}.json
    {"_meta": {...}, "links": {"3|서울특별시|오세훈": "오세훈-1961-01-04", ...},
     "unresolved": [{"key":..., "candidates":[...]}]}

사용: python3 scripts/build/build_person_links.py [--election 9th-local-2026]
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "assets/person-index.json"
RESULTS = ROOT / "data/results"
OUT_DIR = ROOT / "data/person-links"

# 인물 페이지가 있는 조건 — build_person_pages와 같은 규칙이어야 죽은 링크가 안 생긴다.
PLEDGE_DIR = ROOT / "data/pledges/by-person"


def slug_of(person: dict) -> str:
    return f"{person['name']}-{person['dob']}"


def has_page(person: dict, with_pledge: set) -> bool:
    if not person.get("dob"):
        return False
    return bool(person.get("assembly_id")
                or any(r.get("won") for r in person.get("races") or [])
                or person["id"] in with_pledge)


def key_of(tc: str, place: str, name: str) -> str:
    return f"{tc}|{place}|{name}"


def build(eid: str, persons: list, with_pledge: set) -> dict:
    # (tc, place, name) → 후보 인물들
    cand = defaultdict(list)
    for p in persons:
        for r in p.get("races") or []:
            if r.get("eid") != eid:
                continue
            cand[key_of(r.get("tc") or "", r.get("place") or "", p["name"])].append(p)

    links, unresolved, no_page = {}, [], []
    for k, people in sorted(cand.items()):
        usable = [p for p in people if has_page(p, with_pledge)]
        if len(people) > 1 and len({p["id"] for p in people}) > 1:
            # 같은 회차·같은 직·같은 지역에 동명이인 — 근거 없이 고르지 않는다.
            unresolved.append({"key": k, "reason": "동명이인",
                               "candidates": [p["id"] for p in people]})
            continue
        if not usable:
            no_page.append(k)
            continue
        links[k] = slug_of(usable[0])
    return {"links": links, "unresolved": unresolved, "no_page": no_page,
            "n_keys": len(cand)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--election", help="특정 회차만")
    args = ap.parse_args()

    persons = json.loads(INDEX.read_text(encoding="utf-8"))["persons"]
    with_pledge = {f.stem for f in PLEDGE_DIR.glob("*.json")} if PLEDGE_DIR.exists() else set()

    eids = ([args.election] if args.election
            else sorted({r.get("eid") for p in persons for r in p.get("races") or [] if r.get("eid")}))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total_l = total_u = total_n = 0
    for eid in eids:
        if not (RESULTS / f"{eid}.json").exists():
            continue
        b = build(eid, persons, with_pledge)
        if not b["links"] and not b["unresolved"]:
            continue
        doc = {
            "_meta": {
                "election_id": eid,
                "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "source": "polis 계산",
                "method": ("person-index의 race(eid·tc·place)와 이름으로 역색인. "
                           "같은 키에 동명이인이 걸리면 잇지 않고 unresolved로 남긴다."),
                "n_keys": b["n_keys"], "n_links": len(b["links"]),
                "n_unresolved": len(b["unresolved"]), "n_no_page": len(b["no_page"]),
            },
            "links": b["links"], "unresolved": b["unresolved"],
        }
        (OUT_DIR / f"{eid}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        total_l += len(b["links"]); total_u += len(b["unresolved"]); total_n += len(b["no_page"])
        if len(b["links"]) >= 50:
            rate = len(b["links"]) / b["n_keys"] * 100 if b["n_keys"] else 0
            print(f"  {eid:<24} 링크 {len(b['links']):>5} / 키 {b['n_keys']:>5}"
                  f" ({rate:.1f}%) · 동명이인 {len(b['unresolved']):>3}"
                  f" · 페이지 없음 {len(b['no_page']):>4}", file=sys.stderr)
    print(f"→ {OUT_DIR.relative_to(ROOT)}/ · 링크 {total_l:,} · 미해결 {total_u:,}"
          f" · 페이지 없음 {total_n:,}", file=sys.stderr)


if __name__ == "__main__":
    main()
