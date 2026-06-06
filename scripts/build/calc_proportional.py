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


def compute_sigungu_quota(results: dict) -> dict[tuple, int]:
    """기초의원 비례정원 = max(1, round(지역구 의원수 / 10)) per 시군구.
    공직선거법 제23조 기준.

    구가 있는 시(수원시·청주시 등)는 tc=6의 sigungu가 '수원시장안구' 식으로
    구 포함이지만 tc=9 비례는 '수원시' 단위. tc=9 키별로 tc=6 count를
    prefix 매칭해 합산."""
    from collections import Counter
    tc6 = Counter()
    tc9_keys = set()
    for r in results.get("races", []):
        tc = r.get("sg_typecode")
        if tc == "6":
            tc6[(r.get("sido", ""), r.get("sigungu", ""))] += 1
        elif tc == "9":
            tc9_keys.add((r.get("sido", ""), r.get("sigungu", "")))
    quota = {}
    for sido, sgg in tc9_keys:
        # exact match 우선
        n = tc6.get((sido, sgg), 0)
        if n == 0:
            # prefix 합산 (예: '수원시' ← '수원시장안구'·'수원시권선구'…)
            for (sd2, sgg2), c in tc6.items():
                if sd2 == sido and sgg2.startswith(sgg):
                    n += c
        if n > 0:
            quota[(sido, sgg)] = max(1, round(n / 10))
    return quota


def process(results: dict) -> tuple[int, int]:
    """tc=8/9 race에 seats 부여. (광역_n, 기초_n) 반환."""
    metro_n = local_n = 0
    sigungu_quota = compute_sigungu_quota(results)
    for race in results.get("races", []):
        tc = race.get("sg_typecode")
        if tc == "8":
            sido = race.get("sido", "")
            seats = GWANGYK_BIRYE_QUOTA.get(sido)
            label = sido
            counter_idx = "metro"
        elif tc == "9":
            sido, sgg = race.get("sido", ""), race.get("sigungu", "")
            # NEC가 race shell에 seats_total을 MAXHUBOSU에서 직접 줌. fallback
            # = round(tc=6 지역구 / 10) (구가 있는 시는 prefix 합산).
            seats = race.get("seats_total") or sigungu_quota.get((sido, sgg))
            label = f"{sido} {sgg}"
            counter_idx = "local"
        else:
            continue
        if seats is None:
            print(f"  ! 비례정원 미정의: {label}")
            continue
        votes = {c["party"]: c.get("votes", 0) for c in race.get("candidates", []) if c.get("party")}
        alloc = hare_niemeyer(seats, votes)
        for cand in race["candidates"]:
            cand["seats"] = alloc.get(cand["party"], 0)
            cand["won"] = cand["seats"] > 0
        race["seats_total"] = seats
        if counter_idx == "metro": metro_n += 1
        else: local_n += 1
    return metro_n, local_n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="data/results/9th-local-2026.json")
    args = ap.parse_args()
    path = ROOT / args.results if not Path(args.results).is_absolute() else Path(args.results)
    d = json.loads(path.read_text(encoding="utf-8"))
    metro_n, local_n = process(d)

    def summarize(tc, label):
        total: dict[str, int] = {}
        for r in d.get("races", []):
            if r.get("sg_typecode") != tc:
                continue
            for c in r.get("candidates", []):
                s = c.get("seats", 0)
                if s:
                    total[c["party"]] = total.get(c["party"], 0) + s
        print(f"\n{label}:")
        for party, s in sorted(total.items(), key=lambda x: -x[1]):
            print(f"  {party}: {s}")
        print(f"  총: {sum(total.values())}")

    print(f"광역의원 비례: {metro_n}개 시도 / 기초의원 비례: {local_n}개 시군구")
    summarize("8", "광역의원 비례 전국 합계")
    summarize("9", "기초의원 비례 전국 합계")
    # 저장 — pretty (다른 results와 동일 포맷)
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"→ {path}")


if __name__ == "__main__":
    main()
