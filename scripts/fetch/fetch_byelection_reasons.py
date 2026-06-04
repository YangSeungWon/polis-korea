"""NEC 역대 재보궐선거 실시사유 → data/byelection_reasons.json.

ScgnRpbeExctRsnService — 누가 왜(사망/사직/당선무효 등) 공석되어
재·보궐선거 실시됐는지.

산출: data/byelection_reasons.json
  {
    "rows": [
      {
        "elctYmd": "재보궐 실시일",
        "elctKndCd": "선거종류 (2=국회, 4=기초장, ...)",
        "elctNm": "선거명",
        "seNm": "재" | "보궐",
        "ctpvNm": "시도",
        "cmtNm": "시군구",
        "elpcNm": "선거구",
        "plprNm": "정당",
        "trprNm": "이름",
        "rsn": "사유 (사망·사직·당선무효 등)",
        "rsnOcrnYmd": "사유 발생일",
        "rsnCfmtnYmd": "사유 확정일"
      }
    ]
  }

사용:
  python3 scripts/fetch/fetch_byelection_reasons.py [--years 2020,2021,...]
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_BASE = "https://apis.data.go.kr/9760000"
API_REASONS = f"{API_BASE}/ScgnRpbeExctRsnService/getScgnRpbeElctExctRsnInqire"
API_RESULTS = f"{API_BASE}/ScgnRpbeElctExctSttnService/getScgnRpbeElctExctSttnInqire"
# 향후 endpoint base path 이중 service name 주의 (NEC 명세상 그렇게 등록됨)
API_UPCOMING = f"{API_BASE}/RpbeExctRsnInqireService/RpbeExctRsnInqireService/getRpbeExctRsnCfmtnInfoInqire"


def fetch_year(api_url: str, year: int, key: str) -> list[dict]:
    """한 해 모든 row 페이지네이션 자동."""
    out = []
    page = 1
    while True:
        qs = urllib.parse.urlencode({
            "serviceKey": key, "elctYear": year,
            "numOfRows": 100, "pageNo": page, "resultType": "json",
        }, safe="%")
        url = f"{api_url}?{qs}"
        try:
            r = urllib.request.urlopen(url, timeout=20)
        except Exception as e:
            print(f"  ! year={year} page={page}: {e}", file=sys.stderr)
            break
        try:
            d = json.loads(r.read().decode("utf-8", errors="replace"))
        except Exception as e:
            break
        header = d.get("response", {}).get("header", {})
        if header.get("resultCode") != "INFO-00":
            break
        body = d.get("response", {}).get("body", {})
        items = body.get("items", {})
        # NEC API quirk — single item은 dict, multi는 list
        item_list = items.get("item", []) if isinstance(items, dict) else []
        if isinstance(item_list, dict):
            item_list = [item_list]
        out.extend(item_list)
        total = body.get("totalCount", 0) or 0
        if len(out) >= total or not item_list:
            break
        page += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2010,2011,2012,2013,2014,2015,2016,2017,2018,2019,2020,2021,2022,2023,2024,2025,2026")
    ap.add_argument("--out", default="data/byelection_reasons.json")
    args = ap.parse_args()
    key = os.environ.get("NEC_API_KEY")
    if not key:
        # .env fallback
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("NEC_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    # 새 API key (사용자 추가) — 기존 NEC_API_KEY 시도 후 새 키 fallback
    keys = [key] if key else []
    keys.append("ea8d67c30e01efef34e5b65dfe95cc7449d321bf9b6bbfd8e853ab6c42d0d697")
    years = [int(y) for y in args.years.split(",")]
    reasons, results, upcoming = [], [], []
    for k in keys:
        if not k:
            continue
        for y in years:
            r = fetch_year(API_REASONS, y, k)
            print(f"  reasons {y}: {len(r)}", file=sys.stderr)
            reasons.extend(r)
            s = fetch_year(API_RESULTS, y, k)
            print(f"  results {y}: {len(s)}", file=sys.stderr)
            results.extend(s)
        # 향후 사유 — sgExctDate 없이 호출 (전체 예정 반환)
        upcoming = fetch_upcoming(API_UPCOMING, k)
        print(f"  upcoming: {len(upcoming)}", file=sys.stderr)
        if reasons or results or upcoming:
            break
    out_path = ROOT / args.out
    out_path.write_text(json.dumps({
        "reasons": reasons,
        "results": results,
        "upcoming": upcoming,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {out_path.name}: {len(reasons)} reasons, {len(results)} results, {len(upcoming)} upcoming")


def fetch_upcoming(api_url: str, key: str) -> list[dict]:
    """향후 재보궐 사유 확정 — sgExctDate 없이 호출하면 전체 향후 예정."""
    out = []
    page = 1
    while True:
        qs = urllib.parse.urlencode({
            "serviceKey": key, "numOfRows": 100, "pageNo": page, "resultType": "json",
        }, safe="%")
        url = f"{api_url}?{qs}"
        try:
            r = urllib.request.urlopen(url, timeout=20)
            d = json.loads(r.read().decode("utf-8", errors="replace"))
        except Exception as e:
            break
        header = d.get("response", {}).get("header", {})
        if header.get("resultCode") != "INFO-00":
            break
        body = d.get("response", {}).get("body", {})
        items = body.get("items", {})
        item_list = items.get("item", []) if isinstance(items, dict) else []
        if isinstance(item_list, dict):
            item_list = [item_list]
        out.extend(item_list)
        total = body.get("totalCount", 0) or 0
        if len(out) >= total or not item_list:
            break
        page += 1
    return out


if __name__ == "__main__":
    main()
