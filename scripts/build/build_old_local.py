"""옛 지선 1~4회(1995~2006) — 광역단체장(시도지사) 아카이브.
NEC 당선인명부 시도지사(electionType=4·electionCode=3·cityCode=-1) 수집분(gov_1to4.json)으로
results/{id}.json(tc=3 race) + elections/{id}.json + index 등록.

당선자만(시도지사 16/15명) → 광역단체장 hex 지도 + scorecard. 기초장·의원은 추후(별도 대량 수집).

사용: python scripts/build/build_old_local.py   (이후 sync_archive_html.py)
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "lod" / "gov_1to4.json"
RESULTS = ROOT / "data" / "results"
ELECTIONS = ROOT / "data" / "elections"
INDEX = ELECTIONS / "index.json"

ROUNDS = {
    1: ("1st-local-1995", "1995-06-27", "첫 전국동시지방선거 — 민선 자치 부활"),
    2: ("2nd-local-1998", "1998-06-04", "IMF 직후 — 국민회의·자민련 공조"),
    3: ("3rd-local-2002", "2002-06-13", "한나라당 광역 압승"),
    4: ("4th-local-2006", "2006-05-31", "한나라당 광역 석권 — 열린우리당 참패"),
}


def build(n, data):
    slug, date, note = ROUNDS[n]
    govs = data.get(str(n)) or data.get(n) or []
    if not govs:
        print(f"  {n}회: 데이터 없음")
        return None
    races = []
    for g in govs:
        races.append({
            "sg_typecode": "3", "sido": g["sido"], "sigungu": "", "scope": "sido",
            "candidates": [{"name": g["name"], "party": g["party"], "votes": g["votes"],
                            "pct": g.get("pct"), "rank": 1, "won": True}],
        })
    result = {"_meta": {"election": f"제{n}회 전국동시지방선거", "election_id": slug,
                        "election_date": date, "is_final": True, "source": "nec-당선인명부",
                        "_caveat": "광역단체장만 — 기초장·의원 미수집"},
              "races": races}
    (RESULTS / f"{slug}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    pc = Counter(g["party"] for g in govs)
    ctx = " · ".join(f"{p} {c}" for p, c in pc.most_common(4))
    meta = {
        "id": slug, "name": f"제{n}회 전국동시지방선거", "kind": "local", "type": "local",
        "n": n, "date": date, "status": "archive",
        "nec": {"_note": "NEC 당선인명부 — 광역단체장(시도지사) 당선자"},
        "offices": [{"level": "광역단체장", "sg_typecode": "3", "scope": "sido"}],
        "results_file": f"data/results/{slug}.json",
        "_source_note": note,
        "_data_caveat": "광역단체장만 회수(기초장·광역/기초의원 미수집 — 추후).",
        "archive": {
            "page": f"/archive/{slug}/", "results_path": f"data/results/{slug}.json",
            "polls_path": None, "exit_poll_path": None, "polls_window": None,
            "sg_typecode": "3", "proportional_sg_typecode": "8", "list_label": "확정",
            "context_note": (note + " — " if note else "") + f"광역단체장 {ctx}",
            "data_source_note": "NEC 당선인명부 — 광역단체장. 기초장·의원은 추후 수집.",
        },
    }
    (ELECTIONS / f"{slug}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(f"  {n}회 {slug}: 광역단체장 {len(govs)} · {ctx}")
    return slug


def main():
    data = json.loads(RAW.read_text())
    slugs = [s for s in (build(n, data) for n in ROUNDS) if s]
    idx = json.loads(INDEX.read_text())
    have = set(idx["archive"])
    idx["archive"] += [s for s in slugs if s not in have]
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n")
    print(f"index 등록: {slugs}")


if __name__ == "__main__":
    main()
