"""sitemap 완전성·유효성.

새 페이지 유형이 생기면 sitemap 생성기에 손으로 붙여야 한다. /region/ 366개도
그랬다. 안 붙이면 색인이 안 되는데 화면은 멀쩡해서 아무도 모른다 —
nav 가드가 경로 allowlist라 363개를 놓쳤던 것과 같은 구조의 사고다.

제외는 **여기에 이유와 함께** 적는다. 목록에 없으면 실패다.

실행: .venv/bin/python tests/test_sitemap.py
"""
from __future__ import annotations
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://polis.ysw.kr"

# sitemap에 넣지 않는 것 — 각각 이유가 있어야 한다.
EXCLUDE_PREFIX = {
    # 지역 연표 미리보기·UI 감사용 독립 문서. 아직 사이트에 얹지 않았고 nav·링크도
    # 없다. 실제 지역 페이지에 삽입할 때 이 줄을 지우고 sitemap에 넣어야 한다.
    "region-timeline/",
    # 지도 타임랩스 미리보기·UI 감사용 독립 문서. 같은 이유로 아직 사이트 밖이다.
    "map-timelapse/",
    # OG/공유 카드 캡처용 페이지. 사람이 읽을 화면이 아니고 헤더도 없다.
    "share/",
}
EXCLUDE_EXACT = {
    # ?name=·?q= 파라미터를 받는 도구 껍데기. canonical이 자기 자신이지만 정적 본문이
    # 130자 안팎이라 넣으면 '크롤링됨-미색인'이 된다(2026-07 사고와 같은 형태).
    # 실제 내용은 /person/{slug}/ 4,300여 개가 따로 색인된다.
    "person.html",
    "search.html",
}

fails = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def main():
    sm = ROOT / "sitemap.xml"
    raw = sm.read_text(encoding="utf-8")

    # ── 형식 ────────────────────────────────────────────────────────────────
    try:
        ET.fromstring(raw)
        ok_xml = True
    except Exception as e:
        ok_xml, err = False, str(e)
    ck("XML이 유효하다", ok_xml, "" if ok_xml else err)

    locs = re.findall(r"<loc>([^<]+)</loc>", raw)
    ck(f"URL {len(locs):,}개 · 5만 한도 이내", len(locs) <= 50000, str(len(locs)))
    ck("파일 50MB 이내", sm.stat().st_size <= 50 * 1024 * 1024,
       f"{sm.stat().st_size / 1024 / 1024:.1f}MB")
    ck("중복 URL 없음", len(locs) == len(set(locs)), str(len(locs) - len(set(locs))))
    rel = [u for u in locs if not u.startswith(SITE + "/")]
    ck("전부 절대 URL", not rel, str(rel[:3]))
    ck("전부 lastmod가 있다", raw.count("<lastmod>") == len(locs),
       f"{raw.count('<lastmod>')}/{len(locs)}")

    # ── 완전성: 실제 페이지가 전부 들어 있는가 ──────────────────────────────
    listed = {unquote(u[len(SITE):]) for u in locs}
    out = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files", "-z", "*.html"],
        cwd=ROOT, capture_output=True, text=True, timeout=60).stdout
    pages, excluded = [], 0
    for f in [x for x in out.split("\0") if x]:
        if any(f.startswith(p) for p in EXCLUDE_PREFIX) or f in EXCLUDE_EXACT:
            excluded += 1
            continue
        u = "/" if f == "index.html" else "/" + (
            f[: -len("index.html")] if f.endswith("/index.html") else f)
        pages.append((f, u))
    missing = [u for _, u in pages if u not in listed]
    ck(f"실제 페이지 {len(pages):,}개가 전부 sitemap에 있다 (제외 {excluded})",
       not missing, f"{len(missing)}개 누락: {missing[:4]}")

    # ── 유령 URL: sitemap에만 있고 파일이 없는 것 ───────────────────────────
    ghost = []
    for u in listed:
        p = "index.html" if u == "/" else u.lstrip("/")
        if p.endswith("/"):
            p += "index.html"
        if not (ROOT / p).exists():
            ghost.append(u)
    ck("sitemap의 모든 URL이 실재한다", not ghost, f"{len(ghost)}개: {ghost[:4]}")

    # ── robots ──────────────────────────────────────────────────────────────
    rb = (ROOT / "robots.txt").read_text(encoding="utf-8")
    ck("robots.txt가 sitemap을 가리킨다", "sitemap.xml" in rb.lower())
    ck("robots.txt가 사이트를 막고 있지 않다",
       not re.search(r"^\s*Disallow:\s*/\s*$", rb, re.M | re.I))

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
