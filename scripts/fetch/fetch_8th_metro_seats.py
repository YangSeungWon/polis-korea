"""8회 광역의회 정당별 의석 (지역구·비례) wiki scrape — 17개 시도.

위키 '제8회 전국동시지방선거 {시도}의회' 본문에 정당별 의석 표.

Output: data/raw/8th_metro_party_seats.json
사용: .venv/bin/python scripts/fetch/fetch_8th_metro_seats.py
"""
from __future__ import annotations
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/fetch"))
from fetch_8th_council_seats import parse_party_seats  # noqa: E402

UA = "Mozilla/5.0 vote-via-data scraper"

# 17 시도 (8회 이름; 강원 일반→특별자치도 2023, 전북→특별자치도 2024 변경 후 wiki entry 명)
SIDOS = [
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시",
    "경기도", "강원도", "충청북도", "충청남도", "전라북도", "전라남도",
    "경상북도", "경상남도", "제주특별자치도",
]


def main():
    out_p = ROOT / "data/raw/8th_metro_party_seats.json"
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    result = {}
    for sd in SIDOS:
        url = f"https://ko.wikipedia.org/wiki/{urllib.parse.quote(f'제8회 전국동시지방선거 {sd}의회')}"
        try:
            r = s.get(url, timeout=10)
        except Exception as e:
            print(f"  ! {sd}: {e}")
            continue
        if r.status_code != 200 or len(r.text) < 10000:
            print(f"  ! {sd}: http {r.status_code} len {len(r.text)}")
            continue
        seats = parse_party_seats(r.text)
        if not seats:
            print(f"  ! {sd}: no party rows")
            continue
        result[sd] = seats
        td = sum(v["district"] for v in seats.values())
        tp = sum(v["proportional"] for v in seats.values())
        print(f"  {sd}: {len(seats)}당, 지역구 {td} + 비례 {tp} = {td + tp}")
        time.sleep(0.15)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out_p}  ({len(result)} 시도)")


if __name__ == "__main__":
    main()
