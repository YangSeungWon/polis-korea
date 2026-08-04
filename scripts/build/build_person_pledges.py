"""data/pledges/{eid}.json → 인물 단위로 재색인 (person 페이지용).

공약 원본은 회차별 파일이라 한 회차가 2MB에 달한다. person 페이지가 그걸 통째로
받게 두면 한 사람 공약 5건 보자고 2MB를 내려받는 꼴이라, 인물별 소파일로 쪼갠다.

매칭: 공약 레코드(eid·tc·이름·시도) → person-index의 인물 entry.
      같은 회차·같은 직에서 당선한 동명이인은 사실상 없지만, 있으면 시도로 가른다.

Output:
  data/pledges/by-person/{person_id}.json   인물별 공약 (lazy fetch 대상)
  assets/pledges-index.json                 {person_id: 공약 수} — 섹션 노출 판단용

사용: python3 scripts/build/build_person_pledges.py
"""
from __future__ import annotations
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLEDGE_DIR = ROOT / "data/pledges"
BY_PERSON = PLEDGE_DIR / "by-person"
INDEX = ROOT / "assets/person-index.json"
OUT_INDEX = ROOT / "assets/pledges-index.json"

OFFICE_LABEL = {"1": "대통령", "3": "광역단체장", "4": "기초단체장", "11": "교육감"}


def norm(s: str) -> str:
    return (s or "").replace(" ", "").strip()


def main():
    persons = json.loads(INDEX.read_text(encoding="utf-8")).get("persons", [])
    # (이름, eid, tc) → 그 회차 그 직에 출마한 인물 entry들.
    # 당선 여부로 거르지 않는다 — 0단계 캡처로 낙선자 공약도 들어오기 때문.
    by_win: dict[tuple, list] = defaultdict(list)
    for p in persons:
        for r in p.get("races", []):
            by_win[(norm(p["name"]), r.get("eid"), r.get("tc"))].append(p)

    per_person: dict[str, dict] = {}
    matched = unmatched = 0
    misses: list[str] = []
    for fp in sorted(PLEDGE_DIR.glob("*.json")):
        doc = json.loads(fp.read_text(encoding="utf-8"))
        meta = doc.get("_meta", {})
        eid = meta.get("election_id")
        for rec in doc.get("people", []):
            tc = rec.get("sg_typecode")
            cands = by_win.get((norm(rec["name"]), eid, tc), [])
            if len(cands) > 1:   # 동명이인 — 시도로 가른다
                narrowed = [c for c in cands if rec.get("sido") in (c.get("sidos") or [])]
                cands = narrowed or cands
            if not cands:
                unmatched += 1
                misses.append(f"{eid}/tc{tc}/{rec['name']}({rec.get('sido')})")
                continue
            p = cands[0]
            entry = per_person.setdefault(p["id"], {"person_id": p["id"], "name": p["name"],
                                                    "entries": []})
            entry["entries"].append({
                "eid": eid,
                "round": meta.get("election"),
                "date": meta.get("election_date"),
                "tc": tc,
                "office": OFFICE_LABEL.get(tc, tc),
                "sido": rec.get("sido"),
                "sigungu": rec.get("sigungu"),
                "sgg_name": rec.get("sgg_name"),
                "party": rec.get("party"),
                "pledges": rec.get("pledges", []),
            })
            matched += 1

    BY_PERSON.mkdir(parents=True, exist_ok=True)
    for old in BY_PERSON.glob("*.json"):
        old.unlink()
    index = {}
    for pid, doc in per_person.items():
        doc["entries"].sort(key=lambda e: e.get("date") or "")
        (BY_PERSON / f"{pid}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        index[pid] = sum(len(e["pledges"]) for e in doc["entries"])
    OUT_INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    print(f"인물 {len(per_person)}명 · 공약 레코드 매칭 {matched} · 미매칭 {unmatched}",
          file=sys.stderr)
    print(f"→ {BY_PERSON.relative_to(ROOT)}/ ({len(per_person)} 파일)", file=sys.stderr)
    print(f"→ {OUT_INDEX.relative_to(ROOT)}", file=sys.stderr)
    if misses:
        print(f"\n미매칭 {len(misses)}건 (person-index에 당선 기록 없음):", file=sys.stderr)
        for m in misses[:15]:
            print(f"    {m}", file=sys.stderr)
        if len(misses) > 15:
            print(f"    … 외 {len(misses) - 15}건", file=sys.stderr)


if __name__ == "__main__":
    main()
