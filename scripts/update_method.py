"""기존 nesdc_9th_polls.csv의 빈 method 필드만 채움.

NESDC 목록 페이지를 페이지별로 fetch해서 (ntt_id → method) 매핑 만들고
csv update. 전체 재스크레이프(50분+) 안 하고 method만 빠르게 채움.
"""
from __future__ import annotations
import csv
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "raw" / "nesdc_9th_polls.csv"
LIST_URL = "https://www.nesdc.go.kr/portal/bbs/B0000005/list.do"


def fetch(url, params, delay=1.0):
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{q}", headers={"User-Agent": "Mozilla/5.0"})
    time.sleep(delay)
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8")


def parse_page(html):
    """{ntt_id → (method, sample_frame)} 매핑."""
    soup = BeautifulSoup(html, "lxml")
    out = {}
    for a in soup.select("a.row.tr"):
        href = a.get("href", "")
        import re
        m = re.search(r"nttId=(\d+)", href)
        if not m:
            continue
        ntt = m.group(1)
        cells = [c.get_text(strip=True) for c in a.select("span.col")]
        # [0]=reg_no [1]=agency [2]=requester [3]=method [4]=sample_frame [5]=poll_name [6]=reg_date [7]=sido_label
        method = cells[3] if len(cells) > 3 else ""
        sample_frame = cells[4] if len(cells) > 4 else ""
        out[ntt] = (method, sample_frame)
    return out


def main():
    if not CSV.exists():
        print("csv 없음", file=sys.stderr); return
    rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
    fieldnames = list(rows[0].keys()) if rows else []
    blank = [r for r in rows if not (r.get("method", "") or "").strip()]
    print(f"전체 {len(rows)} / method 빈 row {len(blank)}", file=sys.stderr)
    if not blank:
        print("채울 게 없음", file=sys.stderr); return

    # 페이지 끝 알아내기 (1페이지 fetch + last 버튼)
    html = fetch(LIST_URL, {"menuNo": "200467", "pollGubuncd": "VT026", "pageIndex": 1})
    import re
    # "page cont last" 버튼 onclick에 pageIndex={N} 들어있음
    last_match = re.search(r'class="page cont last"[^>]*pageIndex=(\d+)', html)
    if last_match:
        last_page = int(last_match.group(1))
    else:
        nums = re.findall(r'pageIndex=(\d+)', html)
        last_page = max((int(n) for n in nums), default=1)
    last_page += 2
    print(f"목록 페이지 최대 ~{last_page}", file=sys.stderr)

    ntt_to_method = {}
    for page in range(1, last_page + 1):
        try:
            html = fetch(LIST_URL, {"menuNo": "200467", "pollGubuncd": "VT026", "pageIndex": page})
        except Exception as e:
            print(f"  ! page {page}: {e}", file=sys.stderr)
            continue
        page_map = parse_page(html)
        if not page_map:
            print(f"  page {page}: 빈 결과 — 끝", file=sys.stderr)
            break
        ntt_to_method.update(page_map)
        if page % 20 == 0:
            print(f"  진행 {page}/{last_page}, 누적 ntt {len(ntt_to_method)}", file=sys.stderr)

    n_filled = 0
    for r in rows:
        nid = r.get("ntt_id", "")
        if nid in ntt_to_method:
            method, frame = ntt_to_method[nid]
            if method and not (r.get("method", "") or "").strip():
                r["method"] = method
                n_filled += 1
            if frame and not (r.get("sample_frame", "") or "").strip():
                r["sample_frame"] = frame

    with open(CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"완료: method {n_filled}건 채움 → {CSV}", file=sys.stderr)


if __name__ == "__main__":
    main()
