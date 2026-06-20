"""리얼미터 자체발표(realmeter.net) 주간통계표 PDF 수집 → data/raw/realmeter_self/.

배경: 리얼미터는 NESDC에 **정당지지도만** 등록하고, **대통령 국정수행평가는
NESDC에 안 올린다**(선거여론조사 아니라 등록 의무 없음 — 자체 사이트·언론으로만 발표).
그래서 NESDC-only 파이프라인엔 리얼미터 국정평가가 2023년 이후 안 들어온다.
이 fetcher가 그 공백을 realmeter.net **'보도용' 전체 PDF**(국정수행 표 포함)로 메운다.

소스: http://www.realmeter.net/category/pdf/ (+ /page/N). 각 글이 PDF 직링크 +
title 속성에 주차·조사기간이 들어있어 메타를 목록에서 바로 얻는다.

산출:
  data/raw/realmeter_self/*.pdf          — 다운로드한 보도용 PDF (raw, gitignore)
  data/raw/realmeter_self/index.json     — [{url,file,title,week,period_start,period_end}]
                                            extract_approval_realmeter.py --source self 가 소비.

사용:
  python3 scripts/fetch/fetch_realmeter_self.py              # 최근 3페이지(증분·daily)
  python3 scripts/fetch/fetch_realmeter_self.py --all        # 전체 아카이브 백필
  python3 scripts/fetch/fetch_realmeter_self.py --max-pages 10
"""
from __future__ import annotations
import argparse
import json
import re
import ssl
import sys
import time
import urllib.request
from urllib.parse import quote
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data/raw/realmeter_self"
INDEX = OUT_DIR / "index.json"
BASE = "http://www.realmeter.net/category/pdf/"
UA = "Mozilla/5.0 (compatible; polis-data/1.0)"

# realmeter.net은 https self-signed → http + 미검증 컨텍스트로 접근.
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# 글 a태그: href=보도용 PDF, title="[리얼미터] 주간통계표 (26년 6월 2주, 6월 8일 ~ 6월 12일)"
_POST = re.compile(
    r'href="(http://www\.realmeter\.net/wp-content/uploads/\d{4}/\d{2}/[^"#]+?\.pdf)[^"]*"'
    r'\s+title="([^"]*주간통계표[^"]*)"')
# title → 연(2자리)·주차월·주차번호·기간(시작월/일 ~ 종료월/일)
_TITLE = re.compile(
    r'(\d{2})년\s*(\d{1,2})월\s*(\d)주.*?'
    r'(\d{1,2})월\s*(\d{1,2})일\s*[~∼\-]?\s*(\d{1,2})월\s*(\d{1,2})일')


def fetch(url: str, timeout: float = 30) -> bytes:
    # 한글 파일명 URL → percent-encode (URL 구조문자는 보존).
    url = quote(url, safe="%/:=?#&+~()")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        return r.read()


def parse_title(title: str) -> dict | None:
    """title → {week, period_start, period_end}. 연도 롤오버(12월~1월) 보정."""
    m = _TITLE.search(title)
    if not m:
        return None
    yy, wmon, wno, sm, sd, em, ed = map(int, m.groups())
    year = 2000 + yy
    ey = year + 1 if em < sm else year   # 12월~1월 주는 종료가 다음 해
    try:
        ps = f"{year:04d}-{sm:02d}-{sd:02d}"
        pe = f"{ey:04d}-{em:02d}-{ed:02d}"
    except ValueError:
        return None
    return {"week": f"{yy}년{wmon}월{wno}주", "period_start": ps, "period_end": pe}


def list_page(page: int) -> list[tuple[str, str]]:
    url = BASE if page == 1 else f"{BASE}page/{page}/"
    try:
        html = fetch(url).decode("utf-8", "replace")
    except Exception as e:
        print(f"  ! page {page} 실패: {e}", file=sys.stderr)
        return []
    seen, out = set(), []
    for u, t in _POST.findall(html):
        if u not in seen:
            seen.add(u)
            out.append((u, t))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=3, help="순회할 목록 페이지 수 (기본 3=증분)")
    ap.add_argument("--all", action="store_true", help="빈 페이지 나올 때까지 전체(백필)")
    ap.add_argument("--delay", type=float, default=0.6)
    ap.add_argument("--limit", type=int, default=None, help="다운로드 건수 상한(테스트)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index = []
    if INDEX.exists():
        index = json.loads(INDEX.read_text(encoding="utf-8"))
    have = {e["url"] for e in index}

    max_pages = 999 if args.all else args.max_pages
    new = 0
    for page in range(1, max_pages + 1):
        posts = list_page(page)
        if not posts:
            if args.all:
                print(f"  page {page} 비어있음 — 종료", file=sys.stderr)
            break
        print(f"page {page}: {len(posts)}개 글", file=sys.stderr)
        for url, title in posts:
            if url in have:
                continue
            meta = parse_title(title)
            if not meta:
                print(f"  ? 기간 파싱 실패 skip: {title}", file=sys.stderr)
                continue
            fname = url.rsplit("/", 1)[-1]
            dest = OUT_DIR / fname
            if not dest.exists():
                try:
                    dest.write_bytes(fetch(url))
                except Exception as e:
                    print(f"  ! 다운로드 실패 {fname}: {e}", file=sys.stderr)
                    continue
                time.sleep(args.delay)
            index.append({"url": url, "file": fname, "title": title, **meta})
            have.add(url)
            new += 1
            print(f"  + {meta['period_end']} {meta['week']} ({fname[:40]})", file=sys.stderr)
            if args.limit and new >= args.limit:
                break
        if args.limit and new >= args.limit:
            break

    index.sort(key=lambda e: e["period_end"])
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {INDEX.relative_to(ROOT)}: 총 {len(index)}건 (신규 {new})", file=sys.stderr)


if __name__ == "__main__":
    main()
