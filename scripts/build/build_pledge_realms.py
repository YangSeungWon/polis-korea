"""공약 분야 집계 → data/pledges/realm-summary.json (archive 페이지 시각화용).

회차별 공약 원본은 최대 2MB라 archive 페이지가 통째로 받게 둘 수 없다. 분포를 그리는 데
필요한 건 분야별 건수뿐이므로 작게 미리 접어 둔다.

분야는 classify_pledges.py가 추정한 realm_auto(대표 분야) 기준으로 센다 — 다중 라벨을
다 세면 합이 공약 수를 넘어 '비중'을 읽을 수 없다. 정당별 내역은 상위 정당만 담는다.

사용: python3 scripts/build/build_pledge_realms.py
"""
from __future__ import annotations
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLEDGE_DIR = ROOT / "data/pledges"
OUT = PLEDGE_DIR / "realm-summary.json"

TOP_PARTIES = 4     # 툴팁에 보여줄 정당 수 — 그 아래는 '그 외'로 접는다


def main():
    out = {}
    for fp in sorted(PLEDGE_DIR.glob("*.json")):
        if fp.name == "realm-summary.json":
            continue
        doc = json.loads(fp.read_text(encoding="utf-8"))
        meta = doc.get("_meta", {})
        eid = meta.get("election_id")
        if not eid:
            continue
        counts = Counter()
        by_party = defaultdict(Counter)
        n_pledges = unclassified = 0
        people = doc.get("people", [])
        for person in people:
            party = (person.get("party") or "").strip() or "무소속"
            for pl in person.get("pledges", []):
                n_pledges += 1
                realm = pl.get("realm_auto")
                if not realm:
                    unclassified += 1
                    continue
                counts[realm] += 1
                by_party[realm][party] += 1
        if not counts:
            continue
        realms = []
        for realm, n in counts.most_common():
            parties = by_party[realm].most_common(TOP_PARTIES)
            rest = sum(by_party[realm].values()) - sum(n for _, n in parties)
            realms.append({
                "realm": realm, "n": n,
                "parties": [{"party": p, "n": c} for p, c in parties]
                           + ([{"party": "그 외", "n": rest}] if rest else []),
            })
        out[eid] = {
            "election": meta.get("election"),
            "date": meta.get("election_date"),
            "roster_scope": meta.get("roster_scope"),
            "n_people": len(people),
            "n_pledges": n_pledges,
            "n_unclassified": unclassified,
            "realms": realms,
        }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tot = sum(v["n_pledges"] for v in out.values())
    print(f"→ {OUT.relative_to(ROOT)} · {len(out)}개 회차 · 공약 {tot}건", file=sys.stderr)
    for eid, v in sorted(out.items(), key=lambda x: -x[1]["n_pledges"])[:4]:
        top = " · ".join(f"{r['realm']} {r['n']}" for r in v["realms"][:3])
        print(f"   {eid:<24} {v['n_pledges']:>5}건 · {top}", file=sys.stderr)


if __name__ == "__main__":
    main()
