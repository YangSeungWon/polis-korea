"""8회 지선 시군구의회 정당별 의석 (지역구·비례) wiki scrape.

위키 entry '제8회 전국동시지방선거 {시군구}의회' 본문에
'정당 | 지역구 | 비례대표 | 합계' 표가 있음. parse → JSON 룩업.

Output: data/raw/8th_council_party_seats.json
  { "서울특별시|강남구": { "국민의힘": {"district": 12, "proportional": 2},
                          "더불어민주당": {"district": 8, "proportional": 1}, ... },
    ... }

사용:
  .venv/bin/python scripts/fetch/fetch_8th_council_seats.py
"""
from __future__ import annotations
import argparse
import json
import re
import time
import urllib.parse
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
UA = "Mozilla/5.0 vote-via-data scraper"

# 시도 prefix가 필요한 모호한 sigungu (남구·동구·서구·중구 등 — 여러 시도에 동시 존재)
def candidate_urls(sido: str, sigungu: str, n: int = 8) -> list[str]:
    s = sigungu
    return [
        f"https://ko.wikipedia.org/wiki/{urllib.parse.quote(f'제{n}회 전국동시지방선거 {s}의회')}",
        f"https://ko.wikipedia.org/wiki/{urllib.parse.quote(f'제{n}회 전국동시지방선거 {sido} {s}의회')}",
        f"https://ko.wikipedia.org/wiki/{urllib.parse.quote(f'제{n}회_전국동시지방선거_{s}의회')}",
    ]


# 위키 정당색 테이블 row: "<span>색</span> 정당명 N N N" — N = 지역구, 비례, 합계.
# 정당명은 2-10 한글 (점·중점 허용), 뒤에 숫자 3개 연속.
ROW_RE = re.compile(r'([가-힣][가-힣·]{1,10})\s+(\d+)\s+(\d+)\s+(\d+)')
# 정당명 노이즈 필터 — 합계·계 등 header text 제외
NOT_PARTY = {"합계", "계", "정당", "지역구", "비례대표", "비례", "득표율", "비고",
             "당선인", "후보", "선거구", "구분"}


def parse_party_seats(html: str) -> dict[str, dict]:
    """페이지 내 모든 정당별 의석 row 추출. 합계 = 지역구 + 비례 검증."""
    # plain text 변환
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'&[a-z]+;', ' ', text)  # &nbsp; 등
    text = re.sub(r'\s+', ' ', text)
    out = {}
    seen_keys = set()
    for m in ROW_RE.finditer(text):
        party, dist, prop, total = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
        if party in NOT_PARTY:
            continue
        # 합계 일관성 검증
        if dist + prop != total:
            continue
        # 0/0/0 row 제외 (의석 없는 정당 일부 page에 노출)
        if total == 0:
            continue
        if party in seen_keys:
            continue
        seen_keys.add(party)
        out[party] = {"district": dist, "proportional": prop}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8, help="회차 (5/6/7/8)")
    ap.add_argument("--results", default="data/results/9th-local-2026.json",
                    help="sigungu list 추출용 (9회 sigungu set 기준)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if not args.out:
        args.out = f"data/raw/{args.n}th_council_party_seats.json"
    rp = ROOT / args.results
    out_p = ROOT / args.out
    d = json.loads(rp.read_text(encoding="utf-8"))

    sigungus = sorted(set((r["sido"], r["sigungu"]) for r in d["races"] if r.get("sg_typecode") == "9"))
    existing = json.loads(out_p.read_text(encoding="utf-8")) if out_p.exists() else {}

    result = dict(existing)
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    n_new = n_skip = n_fail = 0
    for i, (sido, sgg) in enumerate(sigungus):
        key = f"{sido}|{sgg}"
        if key in result and result[key]:
            n_skip += 1
            continue
        seats = None
        for url in candidate_urls(sido, sgg, args.n):
            try:
                r = s.get(url, timeout=10)
            except Exception:
                continue
            if r.status_code != 200 or len(r.text) < 10000:
                continue
            parsed = parse_party_seats(r.text)
            if parsed:
                seats = parsed
                break
            time.sleep(0.05)
        if not seats:
            n_fail += 1
            result[key] = None
            print(f"  ! [{i+1}/{len(sigungus)}] {sido} {sgg}: not found")
        else:
            result[key] = seats
            n_new += 1
            if (i + 1) % 20 == 0:
                total_d = sum(v["district"] for v in seats.values())
                total_p = sum(v["proportional"] for v in seats.values())
                print(f"  [{i+1}/{len(sigungus)}] {sido} {sgg}: {len(seats)}당, 지역구 {total_d} 비례 {total_p}")
        time.sleep(0.1)
        if (i + 1) % 50 == 0:
            out_p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n신규 {n_new} · 스킵 {n_skip} · 실패 {n_fail}")
    print(f"→ {out_p}")


if __name__ == "__main__":
    main()
