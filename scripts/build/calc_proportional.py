"""광역의원 비례 (tc=8) 의석 배분 — 헤어식 (largest remainder).

규칙 (공직선거법 제190조의2):
  1. 봉쇄조항: 시도 유효투표총수의 5% 이상 득표 정당만 의석 배분 대상.
  2. 헤어식: 정당별 잠정의석 = (정당득표 / 통과정당총득표) × 정원.
     정수부분 먼저 배분, 잔여 의석은 소수점 큰 순.
  3. 2/3 상한: 한 정당이 비례의석의 2/3 초과 받으면, 초과분은 다른 정당
     (소수점 큰 순)에 재배분.

NEC live API는 시도별 정당 vote만 반환. 시도별 비례정원은 행안부 공시
(사실상 8회와 동일). 이 파일은 race[scope=proportional_sido]의 candidates[].seats
필드를 채워서 results JSON을 in-place 갱신.

사용:
  .venv/bin/python scripts/build/calc_proportional.py [--results data/results/9th-local-2026.json]
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 시도별 광역의원 비례정원 — 9회 지선 (행안부 공시 기준, 8회와 동일).
# 광주·전남은 9회 행정통합으로 'transmgp광주특별시'(NEC: 전남광주통합특별시)
# 한 entity. 비례정원 = 광주(3) + 전남(4) = 7. 추후 NEC 공식 확인 시 보정.
GWANGYK_BIRYE_QUOTA = {
    "서울특별시": 10,
    "부산광역시": 6,
    "대구광역시": 4,
    "인천광역시": 5,
    "대전광역시": 4,
    "울산광역시": 3,
    "세종특별자치시": 2,
    "경기도": 13,
    "강원특별자치도": 5,
    "충청북도": 4,
    "충청남도": 5,
    "전북특별자치도": 4,
    "경상북도": 6,
    "경상남도": 7,
    "제주특별자치도": 2,
    "전남광주특별시": 7,   # 통합 시도 (광주 3 + 전남 4)
    "전남광주통합특별시": 7,  # NEC SDNAME 별칭 가능성 대비
    # 옛 분리 시도 (혹시 NEC가 분리해서 줄 때)
    "광주광역시": 3,
    "전라남도": 4,
}

THRESHOLD_PCT = 5.0
CAP_RATIO = 2 / 3


def hare_niemeyer(seats: int, votes: dict[str, int]) -> dict[str, int]:
    """헤어식 배분. 5% 봉쇄 → 정수 + 잔여 → 2/3 상한.
    반환: {정당: 의석}. 0석 정당도 포함."""
    total = sum(votes.values())
    if total == 0 or seats == 0:
        return {p: 0 for p in votes}
    # 5% 봉쇄 — 시도 유효투표총수 기준
    qualified = {p: v for p, v in votes.items() if v / total * 100 >= THRESHOLD_PCT}
    result = {p: 0 for p in votes}
    if not qualified:
        return result
    qual_total = sum(qualified.values())
    quota = {p: v * seats / qual_total for p, v in qualified.items()}
    floors = {p: int(q) for p, q in quota.items()}
    allocated = sum(floors.values())
    remaining = seats - allocated
    if remaining > 0:
        fracs = sorted(qualified.keys(), key=lambda p: -(quota[p] - floors[p]))
        for p in fracs[:remaining]:
            floors[p] += 1
    # 2/3 상한
    cap = int(seats * CAP_RATIO)  # 2/3 정수부 (예: 10 × 2/3 = 6.67 → 6)
    over = []
    for p, s in floors.items():
        if s > cap:
            over.append((p, s - cap))
            floors[p] = cap
    if over:
        excess = sum(e for _, e in over)
        over_parties = {p for p, _ in over}
        receivers = sorted((p for p in qualified if p not in over_parties),
                           key=lambda p: -(quota[p] - int(quota[p])))
        for p in receivers[:excess]:
            floors[p] += 1
    for p, s in floors.items():
        result[p] = s
    return result


def process(results: dict) -> int:
    """tc=8 race에 seats 부여. 변경된 race 수 반환."""
    changed = 0
    for race in results.get("races", []):
        if race.get("sg_typecode") != "8":
            continue
        sido = race.get("sido", "")
        seats = GWANGYK_BIRYE_QUOTA.get(sido)
        if seats is None:
            print(f"  ! 비례정원 미정의: {sido}")
            continue
        votes = {c["party"]: c.get("votes", 0) for c in race.get("candidates", []) if c.get("party")}
        alloc = hare_niemeyer(seats, votes)
        for cand in race["candidates"]:
            cand["seats"] = alloc.get(cand["party"], 0)
            cand["won"] = cand["seats"] > 0
        race["seats_total"] = seats
        # 1위 정당 기준 sort 유지 (이미 votes 정렬됨).
        changed += 1
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="data/results/9th-local-2026.json")
    args = ap.parse_args()
    path = ROOT / args.results if not Path(args.results).is_absolute() else Path(args.results)
    d = json.loads(path.read_text(encoding="utf-8"))
    n = process(d)
    # 전국 정당별 합계 출력
    party_total: dict[str, int] = {}
    for r in d.get("races", []):
        if r.get("sg_typecode") != "8":
            continue
        for c in r.get("candidates", []):
            s = c.get("seats", 0)
            if s:
                party_total[c["party"]] = party_total.get(c["party"], 0) + s
    print(f"광역의원 비례 의석 배분: {n}개 시도")
    print("전국 정당별 합계:")
    for party, s in sorted(party_total.items(), key=lambda x: -x[1]):
        print(f"  {party}: {s}")
    print(f"  총: {sum(party_total.values())}")
    # 저장 — pretty (다른 results와 동일 포맷)
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"→ {path}")


if __name__ == "__main__":
    main()
