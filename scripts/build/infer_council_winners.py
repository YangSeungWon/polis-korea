"""기초의원(tc=6) 중선거구 multi-winner 추정. ⚠ FALLBACK 전용 — 확정 명부 우선.

NEC live API는 race당 won=True를 1위에만 자동 부여. 한국 기초의원은 중선거구
(race당 2-4명 당선)이지만 magnitude 정보가 API에 없음. 위키 룩업의 시군구
district 정수 / race 수 = 평균 magnitude. 각 race에 평균값 정수로 top-K 당선.

⚠ 이 추정은 부정확함 — 선거구별 실제 정수가 평균과 ±1 달라, 9회 기준 90개
선거구에서 당선자가 틀렸음(예: 정원 2석을 3석으로 추정 → 낙선자를 당선 처리).
**확정 당선인이 나오면 반드시 교체**:
  - 5~8회: scripts/fetch/fetch_council_winners.py (data.go.kr OpenAPI 당선인)
  - 9회:   scripts/fetch/fetch_council_winners_live.py (NEC 개표방송 EPEI01 명부)
이 스크립트는 명부가 아직 없는 선거 직후 임시 표시용으로만 사용.

사용:
  .venv/bin/python scripts/build/infer_council_winners.py
"""
from __future__ import annotations
import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


N_TO_YEAR = {5: 2010, 6: 2014, 7: 2018, 8: 2022, 9: 2026}
N_TO_ORD = {5: "5th", 6: "6th", 7: "7th", 8: "8th", 9: "9th"}


def load_quota_for_round(n: int) -> dict[str, int]:
    """회차별 시군구 district 정수 룩업.
    9회: sigungu_council_quota.json (위키 8회 baseline)
    5~8회: {n}th_council_party_seats.json — 정당별 의석 합으로 district 총수 계산."""
    if n == 9:
        p = ROOT / "data/raw/sigungu_council_quota.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        return {k: v.get("district") for k, v in d.items() if v and v.get("district")}
    # 5~8회: party_seats 합산
    p = ROOT / f"data/raw/{N_TO_ORD[n]}_council_party_seats.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for key, party_map in d.items():
        if not party_map:
            continue
        total = sum(v.get("district", 0) for v in party_map.values() if isinstance(v, dict))
        if total > 0:
            out[key] = total
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=9, help="회차 (5/6/7/8/9)")
    ap.add_argument("--results", default=None)
    args = ap.parse_args()
    year = N_TO_YEAR[args.n]
    ord_ = N_TO_ORD[args.n]
    # 결과 파일: 9회는 main, 5~8회는 sigungu chunk (tc=6 race가 거기 있음)
    if not args.results:
        if args.n == 9:
            args.results = f"data/results/{ord_}-local-{year}.json"
        else:
            args.results = f"data/results/{ord_}-local-{year}.sigungu.json"
    rp = ROOT / args.results
    d = json.loads(rp.read_text(encoding="utf-8"))
    quota_map = load_quota_for_round(args.n)
    if not quota_map:
        print(f"! {args.n}회 quota 룩업 없음 (no party_seats data)")
        return

    # 시도명 alias (옛 회차)
    SIDO_ALIAS = {
        "강원도": "강원특별자치도",
        "전라북도": "전북특별자치도",
    }
    # tc=6 race의 시군구 추출 — sigungu 비어있으면 district에서 '...선거구' 제거
    DISTRICT_SUFFIX = re.compile(r"(?:제\d+|[가-하])선거구$")

    def sigungu_of(race):
        if race.get("sigungu"):
            return race["sigungu"]
        return DISTRICT_SUFFIX.sub("", race.get("district") or "")

    # 통합시 일반구(수원시장안구 등)는 quota가 parent 시(수원시)로 키잉됨 → parent로 묶어
    # 그 시 전체 일반구 race에 시 총정수를 배분. (안 그러면 통합시 일반구가 통째로 skip→과소.)
    PARENT_GU = re.compile(r"^([가-힣]+시)[가-힣]+구$")

    def quota_sigungu(sg):
        m = PARENT_GU.match(sg)
        return m.group(1) if m else sg

    # tc=6 race per (sido, quota-sigungu) — 통합시는 parent 시로 그룹
    races_by_sgg: dict[tuple, list] = {}
    for r in d.get("races", []):
        if r.get("sg_typecode") != "6" or r.get("scope") != "district":
            continue
        sd = SIDO_ALIAS.get(r["sido"], r["sido"])
        sg = quota_sigungu(sigungu_of(r))
        if not sg:
            continue
        races_by_sgg.setdefault((sd, sg), []).append(r)

    # district 정수 lookup — 회차별 quota_map (load_quota_for_round) 사용
    def district_seats(sido, sigungu):
        key = f"{sido}|{sigungu}"
        n = quota_map.get(key)
        if n: return n
        # 구가 있는 시(수원시 등) — prefix 합산은 9회에서만 처리 (5~8회 race도 동일 패턴)
        for k, v in quota_map.items():
            if k.startswith(f"{sido}|{sigungu}"):
                return v
        return None

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
