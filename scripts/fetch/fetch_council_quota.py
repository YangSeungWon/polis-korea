"""ko.wikipedia.org에서 시군구의회 정원·비례정원 scrape → 룩업 JSON.

각 시군구 entry "X의회" 또는 "시도_시군구의회" 형태. wiki infobox '정원'
필드에서 숫자 추출. 지역구 정수는 NEC race 수에서 계산 (tc=6) →
비례 = 총정원 - 지역구.

사용:
  .venv/bin/python scripts/fetch/fetch_council_quota.py
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

# wiki entry 후보 URL 패턴 — 모호한 sigungu name(예: '중구', '동구', '서구')는
# 시도 prefix 필요. exact match 시도순.
def candidate_urls(sido: str, sigungu: str) -> list[str]:
    s = sigungu  # 예: "강남구"
    sd_short = sido.replace("특별시", "").replace("광역시", "").replace("특별자치도", "").replace("특별자치시", "").replace("도", "")
    return [
        f"https://ko.wikipedia.org/wiki/{urllib.parse.quote(f'{s}의회')}",
        f"https://ko.wikipedia.org/wiki/{urllib.parse.quote(f'{sido}_{s}의회')}",
        f"https://ko.wikipedia.org/wiki/{urllib.parse.quote(f'{sd_short}_{s}의회')}",
        f"https://ko.wikipedia.org/wiki/{urllib.parse.quote(f'{sido} {s}의회')}",
    ]


# infobox에서 "정원" 추출.
# 위키 source는 HTML 엔티티로 escape됨: '&quot;정원&quot;:{&quot;wt&quot;:&quot;23석&quot;}'.
QUOTA_RE = re.compile(r'정원&quot;:\{&quot;wt&quot;:&quot;(\d+)\s*석')
QUOTA_RE2 = re.compile(r'"정원"\s*:\s*\{\s*"wt"\s*:\s*"(\d+)\s*석')
# fallback — HTML <td>23석</td> 인접
QUOTA_FALLBACK_RE = re.compile(r'정원[^<]*</th>\s*<td[^>]*>\s*(\d+)\s*석')


def fetch_quota(sido: str, sigungu: str, session: requests.Session) -> int | None:
    for url in candidate_urls(sido, sigungu):
        try:
            r = session.get(url, timeout=10)
        except Exception:
            continue
        if r.status_code != 200 or len(r.text) < 5000:
            continue
        # disambiguation check — page가 모호 처리 페이지면 skip
        if "동음이의" in r.text and len(r.text) < 30000:
            continue
        for rx in (QUOTA_RE, QUOTA_RE2, QUOTA_FALLBACK_RE):
            m = rx.search(r.text)
            if m:
                return int(m.group(1))
        time.sleep(0.05)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="data/results/9th-local-2026.json")
    ap.add_argument("--out", default="data/raw/sigungu_council_quota.json")
    args = ap.parse_args()
    rp = ROOT / args.results
    out_p = ROOT / args.out
    d = json.loads(rp.read_text(encoding="utf-8"))

    # tc=4 (기초장) sigungus — 단층 제외 모든 시군구. tc=9는 NEC 누락(부천·용인)
    # 가능성. tc=4가 가장 안정적.
    tc9 = sorted(set((r["sido"], r["sigungu"]) for r in d["races"]
                     if r.get("sg_typecode") == "4" and r.get("sigungu")))
    from collections import Counter
    tc6 = Counter()
    for r in d["races"]:
        if r.get("sg_typecode") == "6":
            tc6[(r["sido"], r["sigungu"])] += 1

    def district_count(sido: str, sigungu: str) -> int:
        n = tc6.get((sido, sigungu), 0)
        if n == 0:
            # 구가 있는 시 prefix 합산 (수원시 ← 수원시장안구 등)
            for (sd2, sgg2), c in tc6.items():
                if sd2 == sido and sgg2.startswith(sigungu):
                    n += c
        return n

    existing = {}
    if out_p.exists():
        existing = json.loads(out_p.read_text(encoding="utf-8"))

    result = dict(existing)
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    n_new = n_skip = n_fail = 0
    for i, (sido, sgg) in enumerate(tc9):
        key = f"{sido}|{sgg}"
        if key in result and result[key].get("total"):
            n_skip += 1
            continue
        total = fetch_quota(sido, sgg, s)
        dist = district_count(sido, sgg)
        if total is None:
            n_fail += 1
            result[key] = {"total": None, "district": dist, "proportional": None}
            print(f"  ! [{i+1}/{len(tc9)}] {sido} {sgg}: not found (지역구 {dist})")
        else:
            prop = max(0, total - dist)
            result[key] = {"total": total, "district": dist, "proportional": prop}
            n_new += 1
            if (i + 1) % 20 == 0:
                print(f"  [{i+1}/{len(tc9)}] {sido} {sgg}: 총 {total} − 지역구 {dist} = 비례 {prop}")
        time.sleep(0.1)
        # 매 50건마다 중간 save
        if (i + 1) % 50 == 0:
            out_p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n신규 {n_new} · 스킵 {n_skip} · 실패 {n_fail}")
    print(f"→ {out_p}")


if __name__ == "__main__":
    main()
