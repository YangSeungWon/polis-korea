"""sitemap 완전성·유효성.

새 페이지 유형이 생기면 sitemap 생성기에 손으로 붙여야 한다. /region/ 366개도
그랬다. 안 붙이면 색인이 안 되는데 화면은 멀쩡해서 아무도 모른다 —
nav 가드가 경로 allowlist라 363개를 놓쳤던 것과 같은 구조의 사고다.

제외는 **여기에 이유와 함께** 적는다. 목록에 없으면 실패다.

실행: .venv/bin/python tests/test_sitemap.py
"""
from __future__ import annotations
import json
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


def check_lastmod_manifest(raw: str) -> None:
    """lastmod가 **내용 해시**에서 나오는가 — git 커밋일에 기대지 않는다.

    예전엔 git 커밋일을 썼는데 CI의 actions/checkout이 기본 shallow(fetch-depth 1)라
    git log가 비었다. 그러면 조용히 오늘로 떨어져 **매일 4,980쪽이 '오늘 수정됨'**이
    됐다 — lastmod를 넣어서 벗어나려던 바로 그 상태다. 로컬은 전체 클론이라 제대로
    나와서 안 보였고, 매일 sitemap 4,981줄이 왕복했다.

    정당 URL은 퍼센트 인코딩돼 나가서 파일을 못 찾아 145쪽이 늘 오늘이었다.
    """
    import hashlib
    urls = dict(re.findall(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", raw))
    man_path = ROOT / "data/sitemap_lastmod.json"
    ck("lastmod 매니페스트가 있다", man_path.exists())
    if not man_path.exists():
        return
    man = json.loads(man_path.read_text(encoding="utf-8"))["pages"]
    ck(f"sitemap URL 전부가 매니페스트에 있다 ({len(man)}쪽)", len(man) >= len(urls) - 80,
       f"매니페스트 {len(man)} vs URL {len(urls)}")
    stale, missing = [], []
    for rel, v in man.items():
        fp = ROOT / rel
        if not fp.exists():
            missing.append(rel)
            continue
        if hashlib.sha1(fp.read_bytes()).hexdigest()[:12] != v["h"]:
            stale.append(rel)
    ck("매니페스트 해시가 실제 파일과 맞는다", not stale, str(stale[:4]))
    ck("매니페스트가 없는 파일을 가리키지 않는다", not missing, str(missing[:4]))
    # 날짜가 한 값으로 뭉쳐 있으면 그건 '오늘로 떨어진' 그 상태다
    days = {v["d"] for v in man.values()}
    ck(f"lastmod가 한 날짜로 뭉쳐 있지 않다 ({len(days)}종)", len(days) >= 2, str(days))
    # sitemap에 적힌 값과 매니페스트가 같은가
    bad = []
    for loc, lm in urls.items():
        rel = unquote(loc.replace(SITE, "")).strip("/")
        rel = rel if rel.endswith(".html") else (rel + "/index.html" if rel else "index.html")
        if rel in man and man[rel]["d"] != lm:
            bad.append(f"{rel}: sitemap {lm} vs 매니페스트 {man[rel]['d']}")
    ck("sitemap의 lastmod가 매니페스트와 같다", not bad, str(bad[:3]))


def main():
    # sitemap.xml은 층별 sitemap을 가리키는 index다. 검사는 index를 따라가 층
    # 파일을 전부 읽는다 — index만 보면 URL이 0개로 보여 아래 검사가 전부 공허하게
    # 통과한다.
    sm = ROOT / "sitemap.xml"
    index_raw = sm.read_text(encoding="utf-8")
    children = [u for u in re.findall(r"<loc>([^<]+)</loc>", index_raw)]
    ck("sitemap.xml이 index다", "<sitemapindex" in index_raw)
    ck(f"층 {len(children)}개를 가리킨다", bool(children), str(children[:3]))

    parts = []
    for u in children:
        f = ROOT / u.rsplit("/", 1)[-1]
        if not f.exists():
            ck(f"{f.name}이 실재한다", False)
            continue
        parts.append(f)
    raw = "\n".join(f.read_text(encoding="utf-8") for f in parts)

    # ── 형식 ────────────────────────────────────────────────────────────────
    bad = []
    for f in [sm] + parts:
        try:
            ET.fromstring(f.read_text(encoding="utf-8"))
        except Exception as e:
            bad.append(f"{f.name}: {e}")
    ck("XML이 유효하다", not bad, "; ".join(bad[:2]))

    locs = re.findall(r"<loc>([^<]+)</loc>", raw)
    ck(f"URL {len(locs):,}개 · 5만 한도 이내", len(locs) <= 50000, str(len(locs)))
    big = [f.name for f in parts if f.stat().st_size > 50 * 1024 * 1024]
    ck("층마다 50MB 이내", not big, str(big))
    ck("중복 URL 없음", len(locs) == len(set(locs)), str(len(locs) - len(set(locs))))
    rel = [u for u in locs if not u.startswith(SITE + "/")]
    ck("전부 절대 URL", not rel, str(rel[:3]))
    ck("전부 lastmod가 있다", raw.count("<lastmod>") == len(locs),
       f"{raw.count('<lastmod>')}/{len(locs)}")
    check_lastmod_manifest(raw)

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

    # ── 자동 잡이 층 파일을 매일 버리지 않는가 ──────────────────────────────
    # 이 저장소에서 두 번 재발한 사고다: 생성기는 돌았는데 git add 범위에 없어
    # 결과가 매일 버려졌다(history/·polls/ 363쪽이 옛 nav로 굳었다). sitemap을
    # 층으로 나누면서 sitemap-{층}.xml이 정확히 그 자리에 놓였다 — index만 add하면
    # lastmod는 갱신되는데 층 내용은 옛것으로 남아, 어긋난 걸 아무도 모른다.
    wf = ROOT / ".github/workflows"
    for name in ("daily-refresh.yml", "tracker-refresh.yml"):
        f = wf / name
        if not f.exists():
            continue
        t = f.read_text(encoding="utf-8")
        adds = " ".join(re.findall(r"git add ([^\n]*)", t))
        ck(f"{name}이 sitemap 층 파일을 add한다", "sitemap-*.xml" in adds,
           "sitemap.xml만 add하면 층 파일이 매일 버려진다")

    # ── robots ──────────────────────────────────────────────────────────────
    rb = (ROOT / "robots.txt").read_text(encoding="utf-8")
    ck("robots.txt가 sitemap을 가리킨다", "sitemap.xml" in rb.lower())
    ck("robots.txt가 사이트를 막고 있지 않다",
       not re.search(r"^\s*Disallow:\s*/\s*$", rb, re.M | re.I))

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
