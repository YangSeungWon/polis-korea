"""8회 시군구의회 정당별 의석 (위키 scrape) → 8th-local-2022 결과에 race 주입.

8회 results 데이터는 tc=3(광역장)·tc=11(교육감)만 + sigungu chunk에 tc=4/5/6.
기초의원(tc=6)은 race 자체 있어도 multi-member won 수가 1로 잘못 집계됨.

이 스크립트가:
  1. data/raw/8th_council_party_seats.json 룩업 읽기
  2. 8th-local-2022.json에 tc=9 (기초의원 비례) race 추가 — 시군구당 1 race,
     candidates = [{party, seats}]. tc=6는 기존 race에 정당별 seats summary
     반영하긴 어려워 별도 tc=6_summary race로 emit (scope='sigungu_summary').

  → archive/local.js renderOffices가 tc=6_summary와 tc=9도 인식하게 별도 확장.

사용:
  .venv/bin/python scripts/build/inject_8th_council.py
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="data/results/8th-local-2022.json")
    ap.add_argument("--sigungu", default="data/results/8th-local-2022.sigungu.json")
    ap.add_argument("--seats", default="data/raw/8th_council_party_seats.json")
    args = ap.parse_args()

    main_p = ROOT / args.results
    sub_p = ROOT / args.sigungu
    seats_p = ROOT / args.seats
    metro_p = ROOT / "data/raw/8th_metro_party_seats.json"

    main_d = json.loads(main_p.read_text(encoding="utf-8"))
    sub_d = json.loads(sub_p.read_text(encoding="utf-8"))
    seats = json.loads(seats_p.read_text(encoding="utf-8"))
    metro = json.loads(metro_p.read_text(encoding="utf-8")) if metro_p.exists() else {}

    # 기존 추가 race 모두 삭제 후 재생성 (idempotent).
    for d in (main_d, sub_d):
        d["races"] = [r for r in d.get("races", []) if r.get("scope") not in ("sigungu_summary", "sido_summary") and r.get("sg_typecode") not in ("8", "9")]

    new_races = []
    for key, party_map in seats.items():
        if not party_map or "|" not in key:
            continue
        sido, sgg = key.split("|", 1)
        # tc=9 (비례) — 정당별 candidate entry, seats 필드
        cands_prop = []
        for party, info in party_map.items():
            n = info.get("proportional", 0)
            if n:
                cands_prop.append({"name": party, "party": party, "seats": n, "won": True})
        if cands_prop:
            new_races.append({
                "sg_typecode": "9", "sido": sido, "sigungu": sgg,
                "scope": "proportional_sigungu",
                "seats_total": sum(c["seats"] for c in cands_prop),
                "candidates": cands_prop,
            })
        # tc=6 summary — multi-member 시 실제 seats 정확값 보존용.
        # archive renderer는 이 scope 받아 tc=6 대신 카운트.
        cands_dist = []
        for party, info in party_map.items():
            n = info.get("district", 0)
            if n:
                cands_dist.append({"name": party, "party": party, "seats": n, "won": True})
        if cands_dist:
            new_races.append({
                "sg_typecode": "6", "sido": sido, "sigungu": sgg,
                "scope": "sigungu_summary",
                "seats_total": sum(c["seats"] for c in cands_dist),
                "candidates": cands_dist,
            })

    # 광역의회 (시도 단위) — tc=5 sido_summary + tc=8 비례.
    for sido, party_map in metro.items():
        cands_prop = [{"name": p, "party": p, "seats": v["proportional"], "won": True}
                      for p, v in party_map.items() if v.get("proportional")]
        if cands_prop:
            new_races.append({
                "sg_typecode": "8", "sido": sido, "sigungu": "",
                "scope": "proportional_sido",
                "seats_total": sum(c["seats"] for c in cands_prop),
                "candidates": cands_prop,
            })
        cands_dist = [{"name": p, "party": p, "seats": v["district"], "won": True}
                      for p, v in party_map.items() if v.get("district")]
        if cands_dist:
            new_races.append({
                "sg_typecode": "5", "sido": sido, "sigungu": "",
                "scope": "sido_summary",
                "seats_total": sum(c["seats"] for c in cands_dist),
                "candidates": cands_dist,
            })

    # sigungu chunk에 넣기 (district race도 chunk에 있음).
    sub_d["races"].extend(new_races)
    sub_d["_meta"]["n_rows"] = len(sub_d["races"])

    main_p.write_text(json.dumps(main_d, ensure_ascii=False, indent=2), encoding="utf-8")
    sub_p.write_text(json.dumps(sub_d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"주입: {len(new_races)} race ({len(new_races)//2} 시군구 × 지역구 summary + 비례)")
    # 전국 정당 합계
    from collections import Counter
    prop_total: Counter = Counter()
    dist_total: Counter = Counter()
    for r in new_races:
        for c in r.get("candidates", []):
            if r["scope"] == "proportional_sigungu":
                prop_total[c["party"]] += c["seats"]
            elif r["scope"] == "sigungu_summary":
                dist_total[c["party"]] += c["seats"]
    print(f"전국 기초의원 지역구: {dict(dist_total.most_common(5))} 총 {sum(dist_total.values())}")
    print(f"전국 기초의원 비례:  {dict(prop_total.most_common(5))} 총 {sum(prop_total.values())}")


if __name__ == "__main__":
    main()
