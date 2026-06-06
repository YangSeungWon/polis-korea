"""기초의원(tc=6) 중선거구 multi-winner 추정.

NEC live API는 race당 won=True를 1위에만 자동 부여. 한국 기초의원은 중선거구
(race당 2-4명 당선)이지만 magnitude 정보가 API에 없음. 위키 룩업의 시군구
district 정수 / race 수 = 평균 magnitude. 각 race에 평균값 정수로 top-K 당선.

caveat: race마다 실제 magnitude는 ±1 차이 있을 수 있음 (인구 분배에 따라).
대략 95%+ 정확 추정. 정확값은 NEC 사후 PDF에서 회수해야.

사용:
  .venv/bin/python scripts/build/infer_council_winners.py
"""
from __future__ import annotations
import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="data/results/9th-local-2026.json")
    ap.add_argument("--quota", default="data/raw/sigungu_council_quota.json")
    args = ap.parse_args()
    rp = ROOT / args.results
    qp = ROOT / args.quota
    d = json.loads(rp.read_text(encoding="utf-8"))
    quota = json.loads(qp.read_text(encoding="utf-8"))

    # tc=6 race per sigungu
    races_by_sgg: dict[tuple, list] = {}
    for r in d.get("races", []):
        if r.get("sg_typecode") != "6" or r.get("scope") != "district":
            continue
        sg_key = (r["sido"], r["sigungu"])
        races_by_sgg.setdefault(sg_key, []).append(r)

    # district 정수 (sigungu_council_quota — 'district' 필드)
    def district_seats(sido, sigungu):
        key = f"{sido}|{sigungu}"
        ent = quota.get(key)
        if not ent:
            return None
        return ent.get("district")

    total_won = 0
    sigungu_count = 0
    for (sido, sgg), races in races_by_sgg.items():
        seats = district_seats(sido, sgg)
        if not seats:
            continue
        n_race = len(races)
        # 평균 magnitude — round
        avg_mag = seats / n_race
        # 정수 배분 — 큰 race가 더 많은 magnitude (인구 비례 근사로 votes 합 사용)
        # 각 race의 magnitude = floor(avg) or ceil(avg) 비례 분배
        floors = [int(avg_mag)] * n_race
        remaining = seats - sum(floors)
        if remaining > 0:
            # 잔여 의석 → 등록 후보 많은 race 우선 (큰 선거구 의석 더 많음)
            order = sorted(range(n_race), key=lambda i: -len(races[i].get("candidates", [])))
            for i in order[:remaining]:
                floors[i] += 1

        for race, K in zip(races, floors):
            cands = race.get("candidates") or []
            # votes 순 정렬 후 top-K won 부여
            sorted_c = sorted(cands, key=lambda c: -(c.get("votes") or 0))
            for i, c in enumerate(sorted_c):
                c["won"] = (i < K)
                if i < K:
                    total_won += 1
            race["seats_total"] = K
        sigungu_count += 1

    rp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"기초의원 winner 추정: {sigungu_count}개 시군구, 총 {total_won}명")
    # 정당별 합계
    from collections import Counter
    by_party = Counter()
    for races in races_by_sgg.values():
        for r in races:
            for c in r.get("candidates") or []:
                if c.get("won"):
                    by_party[c.get("party") or "무소속"] += 1
    print("정당별 당선:")
    for p, n in by_party.most_common(10):
        print(f"  {p}: {n}")


if __name__ == "__main__":
    main()
