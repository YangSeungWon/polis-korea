"""data/elections/{id}.json 레지스트리 → archive/{id}/index.html 자동 생성.

archive HTML 4개 (8th-local·9th-local·21st-pres·22nd-general)는 head/footer가
거의 같고 모드별 (hero stats · 섹션 list · source links)만 다름. 단일 출처로
관리하기 위해 메타 + 종류별 템플릿으로 derive.

새 archive 페이지 추가 = data/elections/{id}.json archive 블록 채우고
이 스크립트 1회 실행. 손으로 수정 X.

사용:
  python3 scripts/build/sync_archive_html.py
  python3 scripts/build/sync_archive_html.py --id 21st-pres-2025  # 한 회차만
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from view_registry import THUMB_PRIORITY, PRIMARY_ORDER  # noqa: E402
ELECTIONS_DIR = ROOT / "data" / "elections"
ARCHIVE_DIR = ROOT / "archive"
RESULTS_DIR = ROOT / "data" / "results"
INDEX_HTML = ROOT / "index.html"
AR_LIST_START = "<!-- AR_LIST_START"
AR_LIST_END = "<!-- AR_LIST_END -->"
AR_RECENT_START = "<!-- AR_RECENT_START"
AR_RECENT_END = "<!-- AR_RECENT_END -->"
AR_RECENT_N = 6   # 홈은 최근 몇 개만 — 전체는 /elections.html 허브가 링크한다.

# nav 정본은 sync_nav_html.py — 사본을 들고 있으면 메뉴 변경 때마다 어긋난다.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_nav_html import render_nav, menu_for_path  # noqa: E402


DOW = ["월", "화", "수", "목", "금", "토", "일"]

# kind → 짧은 라벨·history.html type slug·n 단위
# query: 사람이 실제로 검색창에 치는 이름. short('지선')는 우리 내부 약어라 검색어가
# 아니다 — 상위 검색어는 '지방 선거 결과'지 '지선 결과'가 아니다. 제목 앞머리에는
# query를, 본문 라벨에는 short를 쓴다.
KIND_META = {
    "local":              {"short": "지선",  "query": "지방선거",   "history_type": "local",              "n_unit": "회"},
    "presidential":       {"short": "대선",  "query": "대통령선거", "history_type": "presidential",       "n_unit": "대"},
    "general_election":   {"short": "총선",  "query": "총선",       "history_type": "national_assembly",  "n_unit": "대"},
    "byelection":         {"short": "재보궐", "query": "재보궐선거", "history_type": "byelection",         "n_unit": "년"},
}


def _esc(x) -> str:
    return (str(x if x is not None else "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def kday(date_str: str) -> str:
    y, m, d = map(int, date_str.split("-"))
    return f"{date_str} ({DOW[date.fromordinal(date(y, m, d).toordinal()).weekday()]})"


_SUM_CACHE: dict = {}


def result_summary(meta: dict) -> str:
    """결과 파일에서 히어로 한 줄 요약을 뽑는다. 종류마다 '무엇이 결과인가'가 다르다.

        대선   1·2위 후보 득표율
        총선   정당별 의석
        지선   직위별 정당 곳수 (광역단체장·기초단체장)

    없으면 빈 문자열 — 없는 숫자를 만들지 않는다.
    """
    eid = meta.get("id") or ""
    if eid in _SUM_CACHE:
        return _SUM_CACHE[eid]
    rp = (meta.get("archive") or {}).get("results_path") or f"data/results/{eid}.json"
    f = ROOT / rp
    out = ""
    try:
        races = json.loads(f.read_text(encoding="utf-8")).get("races") or []
    except Exception:                                            # noqa: BLE001
        races = []
    kind = meta.get("kind")
    if kind == "presidential":
        nat = next((r for r in races if r.get("scope") == "nation"
                    and r.get("sg_typecode") == "1"), None)
        cs = sorted((nat or {}).get("candidates") or [],
                    key=lambda c: -(c.get("pct") or 0))[:2]
        if cs and cs[0].get("pct") is not None:
            out = " / ".join(f'{c.get("name")}({c.get("party")}) {c["pct"]:.2f}%'
                             for c in cs if c.get("pct") is not None)
    elif kind == "general_election":
        seats: dict = {}
        for r in races:
            if r.get("scope") not in ("district", None):
                continue
            for c in r.get("candidates") or []:
                if c.get("won") and c.get("party"):
                    seats[c["party"]] = seats.get(c["party"], 0) + 1
        for r in races:                       # 비례 의석 합산
            for c in r.get("candidates") or []:
                if (c.get("proportional_seats") or 0) and c.get("party"):
                    seats[c["party"]] = seats.get(c["party"], 0) + c["proportional_seats"]
        top = sorted(seats.items(), key=lambda kv: -kv[1])[:4]
        if top:
            out = " · ".join(f"{p} {n}석" for p, n in top)
    elif kind == "local":
        # 직위별로 1위 정당이 몇 곳인가. 지선은 '한 줄 결과'가 없어 두 직위를 함께 쓴다.
        parts = []
        for tc, label, scope in (("11", "광역단체장", "sido"), ("4", "기초단체장", "sigungu")):
            won: dict = {}
            for r in races:
                if r.get("sg_typecode") != tc or r.get("scope") != scope:
                    continue
                cs = sorted(r.get("candidates") or [],
                            key=lambda c: -(c.get("votes") or 0))
                if cs and cs[0].get("party"):
                    won[cs[0]["party"]] = won.get(cs[0]["party"], 0) + 1
            top = sorted(won.items(), key=lambda kv: -kv[1])[:2]
            if top:
                parts.append(f"{label} " + " · ".join(f"{p} {n}곳" for p, n in top))
        out = " / ".join(parts)
    _SUM_CACHE[eid] = out
    return out


def derive(meta: dict) -> dict:
    """meta + archive 블록 → 템플릿에 박을 변수."""
    kind = meta["kind"]
    km = KIND_META[kind]
    ar = meta["archive"]
    sg_id = meta.get("nec", {}).get("sg_id", "")
    gubun = meta.get("nesdc", {}).get("gubun", "")
    # 히어로의 결과 요약. **손으로 적은 context_note가 우선**이고(편집 맥락이 들어 있다 —
    # "윤석열 탄핵 인용 후 조기 대선" 같은 건 데이터에서 못 나온다), 없으면 결과에서 뽑는다.
    #
    # 이 자리가 비면 검색엔진이 보는 페이지에 **숫자가 하나도 없다**. scorecard는 JS가
    # 채우고 기본값이 hidden이라, 크롤러에는 '—'만 남는다. 9회 지선처럼 최신·최다 검색
    # 회차가 그랬다 — 손으로 적는 필드라 새 회차부터 비어 있었다(16회차).
    context = ar.get("context_note", "") or result_summary(meta)
    date_label = kday(meta["date"])
    if context:
        date_label += f" · {context}"
    # breadcrumb — 재보궐은 역대(history/timeline)에 없으니 '재·보궐'로, 나머지는 타임라인·역대 선거.
    if kind == "byelection":
        breadcrumb = (f'<a href="/byelection/">재·보궐</a> · '
                      f'<span>{meta["n"]}{km["n_unit"]} {km["short"]} 아카이브</span>')
    else:
        breadcrumb = (f'<a href="/timeline.html">역대 판세</a> · '
                      f'<a href="/history.html?type={km["history_type"]}&n={meta["n"]}">역대 선거</a> · '
                      f'<span>{meta["n"]}{km["n_unit"]} {km["short"]} 아카이브</span>')
    # 선거별 결과지도 og 카드(build_og_maps.py 생성). 없으면(지도 없는 옛 회차) 일반 카드.
    _og = ROOT / "og" / f'{meta["id"]}.png'
    og_image = (f'https://polis.ysw.kr/og/{meta["id"]}.png' if _og.exists()
                else "https://polis.ysw.kr/og.png")
    # 화면 breadcrumb과 같은 경로를 기계가 읽을 수 있게 — 검색 결과에 URL 대신 경로가 뜬다.
    if kind == "byelection":
        trail = [("재·보궐", "/byelection/"), (f'{meta["n"]}{km["n_unit"]} {km["short"]} 아카이브', None)]
    else:
        trail = [("역대 판세", "/timeline.html"),
                 ("역대 선거", f'/history.html?type={km["history_type"]}&n={meta["n"]}'),
                 (f'{meta["n"]}{km["n_unit"]} {km["short"]} 아카이브', None)]
    SITE = "https://polis.ysw.kr"
    ld = {"@context": "https://schema.org", "@type": "BreadcrumbList",
          "itemListElement": [
              {"@type": "ListItem", "position": i + 1, "name": nm,
               **({"item": SITE + u} if u else {})}
              for i, (nm, u) in enumerate(trail)]}
    # 회차별 여론조사 페이지(/polls/{id}/)가 있으면 링크. 이 9개는 sitemap에만 있고
    # 사이트 어디서도 링크하지 않아 검색엔진으로만 도달 가능한 고아였다(page-map gap-2).
    polls_page = ROOT / "polls" / meta["id"] / "index.html"
    polls_link = (f'<p class="ar-source-line"><a href="/polls/{meta["id"]}/">'
                  f'{meta["n"]}{km["n_unit"]} {km["short"]} 여론조사 vs 실제 — 조사별 정확도 비교</a></p>'
                  if polls_page.exists() else "")
    return {
        "polls_link": polls_link,
        "breadcrumb_ld": ('<script type="application/ld+json">'
                          + json.dumps(ld, ensure_ascii=False) + '</script>'),
        "breadcrumb": breadcrumb,
        "id": meta["id"],
        "og_image": og_image,
        "name": meta["name"],
        "date": meta["date"],
        "date_label": date_label,
        "n": meta["n"],
        "n_unit": km["n_unit"],
        "kind": kind,
        "kind_short": km["short"],
        "kind_query": km["query"],
        # 제목이 '2025 대통령선거 결과 — 제21대 대통령선거'처럼 같은 말을 두 번 하지
        # 않도록, 정식명이 검색어로 끝나면 그 꼬리만 내부 약어로 줄인다.
        # ('제21대 대통령선거' → '제21대 대선'). 총선·재보궐은 정식명이 검색어로
        # 끝나지 않아 그대로 남는다.
        "name_short": _name_short(meta["name"], km),
        "history_type": km["history_type"],
        "is_active": meta.get("status") == "active",
        "election_id_full": f"002{sg_id}" if sg_id else "",
        "nesdc_gubun_query": f"&pollGubuncd={gubun}" if gubun else "",
        "wiki_url": ar.get("wiki_url", ""),
        "year": meta["date"][:4],
    }



def _name_short(name: str, km: dict) -> str:
    """제목에서 같은 말을 두 번 하지 않도록 정식명을 줄인다.

    '2025 대통령선거 결과 — 제21대 대통령선거'처럼 앞머리 검색어와 정식명이 겹치면
    정식명을 '제21대 대선'으로 줄인다. 꼬리만 잘라내면 '제9회 전국동시지방선거'가
    '제9회 전국동시지선'이 되므로, 회차 표기(제N회·제N대)만 남기고 약어를 붙인다.
    회차 표기가 없거나 겹치지 않는 이름(재보궐의 '2025년 4·2 재·보궐선거',
    총선의 '제22대 국회의원선거')은 그대로 둔다.
    """
    if not name.endswith(km["query"]):
        return name
    m = re.match(r"^(제\d+[회대])", name)
    return f'{m.group(1)} {km["short"]}' if m else name


# --- 공통 chrome ---

HEAD = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<script>try{{var _m=localStorage.getItem('vote-ysw-theme');if(_m==='dark')document.documentElement.setAttribute('data-theme','dark');else if(_m==='light')document.documentElement.setAttribute('data-theme','light');}}catch(_e){{}}</script>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#5b54d6">
<base href="/">
<title>{year} {kind_query} 결과 — {name_short} 개표·득표율 | polis</title>
<meta name="description" content="{year}년 {kind_query}({date}) 결과. {name} 시도·시군구별 개표와 득표율, 여론조사·출구조사 비교까지 한 화면에서.">
<meta property="og:title" content="{year} {kind_query} 결과 — {name_short}">
<meta property="og:description" content="{n}{n_unit} {kind_short} 시도·시군구별 개표와 득표율, 여론조사·출구조사 비교.">
<meta property="og:type" content="website">
<meta property="og:image" content="{og_image}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{og_image}">
<link rel="canonical" href="/archive/{id}/">
{breadcrumb_ld}
<link rel="preconnect" href="https://cdn.jsdelivr.net">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.min.css">
<link rel="stylesheet" href="assets/common.css">
<link rel="stylesheet" href="assets/components.css">
<link rel="stylesheet" href="assets/archive.css">
<script id="archive-meta">window.__ARCHIVE__ = {{ id: '{id}' }};</script>
</head>
<body>
<header class="site-hdr">
  <div class="brand">
    <a href="/" class="logo-link"><span class="logo">polis</span><span class="domain">ysw.kr</span></a>
  </div>
  <nav class="hdr-nav">
{nav}
  </nav>
  <div class="hdr-meta">
    <button id="theme-toggle" class="theme-toggle" type="button" aria-label="테마 토글"></button>
  </div>
</header>

<main class="page">
  <nav class="ar-breadcrumb" aria-label="경로">
    {breadcrumb}
  </nav>
"""

# --- hero 블록 (kind별) ---

HERO_LOCAL = """
  <section class="ar-hero">
    <div class="ar-hero-top"><div class="ar-hero-tag">아카이브</div><div id="lens-switcher-host"></div></div>
    <h1 class="ar-hero-title" id="ar-title">{name}</h1>
    <div class="ar-hero-date" id="ar-date">{date_label}</div>
    <div class="ar-hero-scorecard" id="ar-scorecard" hidden>
      <div class="ar-sc-row ar-sc-head">
        <div class="ar-sc-party ar-sc-p1" id="ar-sc-p1"></div>
        <div class="ar-sc-label"></div>
        <div class="ar-sc-party ar-sc-p2" id="ar-sc-p2"></div>
      </div>
      <div class="ar-sc-row" data-level="3">
        <div class="ar-sc-num ar-sc-num-l" id="ar-sc-3-l">—</div>
        <div class="ar-sc-label">광역단체장</div>
        <div class="ar-sc-num ar-sc-num-r" id="ar-sc-3-r">—</div>
      </div>
      <div class="ar-sc-other" id="ar-sc-3-other" hidden></div>
      <div class="ar-sc-row" data-level="4">
        <div class="ar-sc-num ar-sc-num-l" id="ar-sc-4-l">—</div>
        <div class="ar-sc-label">기초단체장</div>
        <div class="ar-sc-num ar-sc-num-r" id="ar-sc-4-r">—</div>
      </div>
      <div class="ar-sc-other" id="ar-sc-4-other" hidden></div>
      <div class="ar-sc-row" data-level="5">
        <div class="ar-sc-num ar-sc-num-l" id="ar-sc-5-l">—</div>
        <div class="ar-sc-label">광역의원</div>
        <div class="ar-sc-num ar-sc-num-r" id="ar-sc-5-r">—</div>
      </div>
      <div class="ar-sc-other" id="ar-sc-5-other" hidden></div>
      <div class="ar-sc-row" data-level="6">
        <div class="ar-sc-num ar-sc-num-l" id="ar-sc-6-l">—</div>
        <div class="ar-sc-label">기초의원</div>
        <div class="ar-sc-num ar-sc-num-r" id="ar-sc-6-r">—</div>
      </div>
      <div class="ar-sc-other" id="ar-sc-6-other" hidden></div>
    </div>
    <div class="ar-hero-meta" id="ar-hero-meta">
      <span class="ar-hm-item"><span class="ar-hm-label">투표율</span> <span class="ar-hm-value" id="ar-turnout">—</span></span>
      <span class="ar-hm-item" id="ar-hm-close" hidden><span class="ar-hm-label">박빙</span> <span class="ar-hm-value" id="ar-close-count">—</span></span>
      <span class="ar-hm-item" id="ar-hm-exit" hidden><span class="ar-hm-label">출구조사 적중</span> <span class="ar-hm-value" id="ar-exit-hit">—</span></span>
      <span class="ar-hm-item" id="ar-hm-polls" hidden><span class="ar-hm-label">여론조사</span> <span class="ar-hm-value" id="ar-polls-count">—</span></span>
      <span class="ar-hm-item" id="ar-hm-by" hidden><span class="ar-hm-label">동시 재·보궐</span> <span class="ar-hm-value" id="ar-byelection-count">—</span></span>
    </div>
    <p class="ar-hero-status" id="ar-status">{hero_status}</p>
  </section>
"""

HERO_PRES = """
  <section class="ar-hero">
    <div class="ar-hero-top"><div class="ar-hero-tag">아카이브</div><div id="lens-switcher-host"></div></div>
    <h1 class="ar-hero-title" id="ar-title">{name}</h1>
    <div class="ar-hero-date" id="ar-date">{date_label}</div>
    <!-- 대선 히어로: 당선자 강조 + 전체 후보 구도 막대. pres.js renderHero가 채움. -->
    <div class="ar-hero-scorecard ar-pres-sc" id="ar-scorecard" hidden></div>
    <div class="ar-hero-meta" id="ar-hero-meta">
      <span class="ar-hm-item" id="ar-hm-exit" hidden><span class="ar-hm-label">출구조사 적중</span> <span class="ar-hm-value" id="ar-exit-hit">—</span></span>
      <span class="ar-hm-item" id="ar-hm-polls" hidden><span class="ar-hm-label">여론조사</span> <span class="ar-hm-value" id="ar-polls-count">—</span></span>
    </div>
    <p class="ar-hero-status" id="ar-status">{hero_status}</p>
  </section>
"""

HERO_BYELECTION = """
  <section class="ar-hero">
    <div class="ar-hero-top"><div class="ar-hero-tag">아카이브</div><div id="lens-switcher-host"></div></div>
    <h1 class="ar-hero-title" id="ar-title">{name}</h1>
    <div class="ar-hero-date" id="ar-date">{date_label}</div>
    <div class="ar-hero-scorecard" id="ar-scorecard" hidden>
      <div class="ar-sc-row ar-sc-head">
        <div class="ar-sc-party ar-sc-p1" id="ar-sc-p1"></div>
        <div class="ar-sc-label"></div>
        <div class="ar-sc-party ar-sc-p2" id="ar-sc-p2"></div>
      </div>
      <div class="ar-sc-row" data-level="2">
        <div class="ar-sc-num ar-sc-num-l" id="ar-sc-2-l">—</div>
        <div class="ar-sc-label">국회의원</div>
        <div class="ar-sc-num ar-sc-num-r" id="ar-sc-2-r">—</div>
      </div>
      <div class="ar-sc-other" id="ar-sc-2-other" hidden></div>
      <div class="ar-sc-row" data-level="3">
        <div class="ar-sc-num ar-sc-num-l" id="ar-sc-3-l">—</div>
        <div class="ar-sc-label">광역단체장</div>
        <div class="ar-sc-num ar-sc-num-r" id="ar-sc-3-r">—</div>
      </div>
      <div class="ar-sc-other" id="ar-sc-3-other" hidden></div>
      <div class="ar-sc-row" data-level="4">
        <div class="ar-sc-num ar-sc-num-l" id="ar-sc-4-l">—</div>
        <div class="ar-sc-label">기초단체장</div>
        <div class="ar-sc-num ar-sc-num-r" id="ar-sc-4-r">—</div>
      </div>
      <div class="ar-sc-other" id="ar-sc-4-other" hidden></div>
      <div class="ar-sc-row" data-level="5">
        <div class="ar-sc-num ar-sc-num-l" id="ar-sc-5-l">—</div>
        <div class="ar-sc-label">광역의원</div>
        <div class="ar-sc-num ar-sc-num-r" id="ar-sc-5-r">—</div>
      </div>
      <div class="ar-sc-other" id="ar-sc-5-other" hidden></div>
      <div class="ar-sc-row" data-level="6">
        <div class="ar-sc-num ar-sc-num-l" id="ar-sc-6-l">—</div>
        <div class="ar-sc-label">기초의원</div>
        <div class="ar-sc-num ar-sc-num-r" id="ar-sc-6-r">—</div>
      </div>
      <div class="ar-sc-other" id="ar-sc-6-other" hidden></div>
    </div>
    <div class="ar-hero-meta" id="ar-hero-meta">
      <span class="ar-hm-item"><span class="ar-hm-label">실시 사유</span> <span class="ar-hm-value" id="ar-by-reasons-count">—</span></span>
      <span class="ar-hm-item" id="ar-hm-close" hidden><span class="ar-hm-label">박빙</span> <span class="ar-hm-value" id="ar-close-count">—</span></span>
    </div>
    <p class="ar-hero-status" id="ar-status">{hero_status}</p>
  </section>
"""

HERO_GENERAL = """
  <section class="ar-hero">
    <div class="ar-hero-top"><div class="ar-hero-tag">아카이브</div><div id="lens-switcher-host"></div></div>
    <h1 class="ar-hero-title" id="ar-title">{name}</h1>
    <div class="ar-hero-date" id="ar-date">{date_label}</div>
    <!-- 총선 히어로: 의석 반원(전 정당) 헤드라인. general.js renderHero가 채움. 정당별 상세는 '의회 구성' 섹션. -->
    <div class="ar-hero-scorecard ar-parl-sc" id="ar-scorecard" hidden></div>
    <div class="ar-hero-meta" id="ar-hero-meta">
      <span class="ar-hm-item"><span class="ar-hm-label">투표율</span> <span class="ar-hm-value" id="ar-turnout">—</span></span>
      <span class="ar-hm-item" id="ar-hm-close" hidden><span class="ar-hm-label">박빙</span> <span class="ar-hm-value" id="ar-close-count">—</span></span>
      <span class="ar-hm-item" id="ar-hm-exit" hidden><span class="ar-hm-label">출구조사 적중</span> <span class="ar-hm-value" id="ar-exit-hit">—</span></span>
      <span class="ar-hm-item" id="ar-hm-polls" hidden><span class="ar-hm-label">여론조사</span> <span class="ar-hm-value" id="ar-polls-count">—</span></span>
    </div>
    <p class="ar-hero-status" id="ar-status">{hero_status}</p>
  </section>
"""

# --- 섹션 (kind별) — NEC 소스 URL은 derive ---

NEC_RESULTS_URL = "https://info.nec.go.kr/main/showDocument.xhtml?electionId={election_id_full}&topMenuId=VC&secondMenuId=VCCP09"

# 시도/시군구 시각화 진입은 하단 nav 센터 '더 자세히' 셀로 통합 (render_bottom_nav · DETAIL_CELL)

SECTIONS_LOCAL = """
  <div class="ar-group">
    <h2 class="ar-group-title">결과<span class="ar-group-sub">이 선거에서 무슨 일이 있었나</span></h2>

  <section class="ar-section" id="ar-offices" hidden>
    <h2 class="ar-section-title">선출직 정당 분포</h2>
    <p class="ar-source-line">광역단체장 · 기초단체장 · 광역의원 (지역구·비례) · 기초의원 (지역구·비례). 교육감 제외.</p>
    <div class="ar-offices-grid" id="ar-offices-grid"></div>
  </section>

  <section class="ar-section" id="ar-governor-hex-section" hidden>
    <h2 class="ar-section-title">광역단체장 결과</h2>
    <p class="ar-source-line">각 시·도 1위 후보 — 정당색·득표율.</p>
    <div class="ar-governor-hex" id="ar-governor-hex"></div>
  </section>

  <section class="ar-section" id="ar-metro-hex-section" hidden>
    <h2 class="ar-section-title">시·도의회 의석 분포</h2>
    <p class="ar-source-line">시·도의회 광역의원 의석(지역구+비례) — 칸 1개 = 1석, 색 = 정당.</p>
    <div class="ar-metro-hex" id="ar-metro-hex"></div>
    <div class="ar-metro-hex-meta"><span id="ar-metro-hex-total"></span><span id="ar-metro-hex-legend"></span></div>
  </section>

  <section class="ar-section" id="ar-council-hex-section" hidden>
    <h2 class="ar-section-title">시군구의회 의석 분포</h2>
    <p class="ar-source-line">시·군·구의회 의석(지역구+비례) — 칸 1개 = 1석, 색 = 정당.</p>
    <div class="ar-council-hex" id="ar-council-hex"></div>
    <div class="ar-council-hex-meta"><span id="ar-council-hex-total"></span><span id="ar-council-hex-legend"></span></div>
  </section>
  </div>


  <div class="ar-group">
    <h2 class="ar-group-title">무엇이 바뀌었나<span class="ar-group-sub">지난 회차와 견줘서</span></h2>

  <section class="ar-section" id="ar-compare-section" hidden>
    <h2 class="ar-section-title">무엇이 바뀌었나</h2>
    <div id="ar-compare-host"></div>
  </section>
  </div>


  <div class="ar-group">
    <h2 class="ar-group-title">누가 경쟁했나<span class="ar-group-sub">당선인과 후보</span></h2>

  <section class="ar-section" id="ar-winners-section" hidden>
    <h2 class="ar-section-title">시·도의원·시·군·구의원 당선인</h2>
    <p class="ar-source-line">시·도의원·시·군·구의원 모두 NEC 확정 당선인 기준 — 중선거구 정수·무투표 포함.</p>
    <div id="ar-winners-body"></div>
  </section>
  </div>


  <div class="ar-group">
    <h2 class="ar-group-title">선거 전에는 어떻게 보였나<span class="ar-group-sub">여론조사·출구조사와 실제의 거리</span></h2>

  <section class="ar-section" id="ar-exitpoll" hidden>
    <h2 class="ar-section-title">출구조사 vs 실제</h2>
    <p class="ar-source-line">{date} 18:00 발표. <b>KBS·MBC·SBS 방송 3사 공동 출구조사</b>(한국리서치·입소스·코리아리서치 컨소시엄, 1,980개 투표소) — 표본은 공유, <b>의석 예측은 각 사 분석팀이 별도 시뮬레이션</b>이라 값이 다름. JTBC는 별도. 시도별 1위 일치율·평균 오차 자동 계산.</p>
    <div class="ar-exitpoll-grid" id="ar-exitpoll-grid"></div>
  </section>

  <section class="ar-section" id="ar-polls-link" hidden>
    <h2 class="ar-section-title">여론조사</h2>
    {polls_link}
    <div class="ar-polls-link-host" id="ar-polls-link-host"></div>
  </section>
  </div>


  <div class="ar-group">
    <h2 class="ar-group-title">공약<span class="ar-group-sub">NEC에 등록된 선거공약</span></h2>

  <section class="ar-section" id="ar-pledge-realm-section" hidden>
    <h2 class="ar-section-title">공약 분야 분포</h2>
    <p class="ar-source-line">중앙선거관리위원회 선거공약 API. 분야는 원문에 없어 제목·본문으로 자동 분류했습니다.</p>
    <div id="ar-pledge-realm-host"></div>
  </section>
  </div>


  <div class="ar-group">
    <h2 class="ar-group-title">함께 치러진 선거<span class="ar-group-sub">같은 날 실시된 재·보궐</span></h2>

  <section class="ar-section" id="ar-byelection" hidden>
    <h2 class="ar-section-title">재·보궐</h2>
    <div class="ar-byelection-host" id="ar-byelection-host"></div>
  </section>
  </div>

"""

SECTIONS_PRES = """
  <section class="ar-section" id="ar-pres-sido-hex-section" hidden>
    <h2 class="ar-section-title">시도별 결과</h2>
    <p class="ar-source-line">각 시·도 1위 후보 — 정당색·득표율.</p>
    <div class="ar-governor-hex" id="ar-pres-sido-hex"></div>
  </section>

  <section class="ar-section" id="ar-nation" hidden>
    <h2 class="ar-section-title">전국 결과</h2>
    <p class="ar-source-line">데이터 원본: <a href="{nec_url}" target="_blank" rel="noopener">중앙선거관리위원회 선거통계시스템 ↗</a></p>
    <div class="ar-nation-host" id="ar-nation-host"></div>
  </section>

  <section class="ar-section" id="ar-exitpoll" hidden>
    <h2 class="ar-section-title">출구조사 vs 실제</h2>
    <p class="ar-source-line">{date} 18:00 발표. <b>KBS·MBC·SBS 방송 3사 공동 출구조사</b>(한국리서치·입소스·코리아리서치 컨소시엄). 표본은 공유, <b>의석 예측은 각 사 분석팀이 별도 시뮬레이션</b>. JTBC는 별도. 전국 적중·평균 오차 자동 계산.</p>
    <div class="ar-exitpoll-grid" id="ar-exitpoll-grid"></div>
  </section>

  <section class="ar-section" id="ar-polls-link" hidden>
    <h2 class="ar-section-title">여론조사</h2>
    {polls_link}
    <div class="ar-polls-link-host" id="ar-polls-link-host"></div>
  </section>

  <section class="ar-section" id="ar-pledge-realm-section" hidden>
    <h2 class="ar-section-title">공약 분야 분포</h2>
    <p class="ar-source-line">중앙선거관리위원회 선거공약 API. 분야는 원문에 없어 제목·본문으로 자동 분류했습니다.</p>
    <div id="ar-pledge-realm-host"></div>
  </section>

  <section class="ar-section" id="ar-compare-section" hidden>
    <h2 class="ar-section-title">무엇이 바뀌었나</h2>
    <div id="ar-compare-host"></div>
  </section>
"""

SECTIONS_BYELECTION = """
  <section class="ar-section" id="ar-by-sido-section" hidden>
    <h2 class="ar-section-title">광역단체장 결과</h2>
    <p class="ar-source-line">데이터 원본: <a href="{nec_url}" target="_blank" rel="noopener">중앙선거관리위원회 ↗</a></p>
    <div class="ar-by-sido-host" id="ar-by-sido-host"></div>
  </section>

  <section class="ar-section" id="ar-by-supt-section" hidden>
    <h2 class="ar-section-title">교육감 결과</h2>
    <p class="ar-source-line">교육감은 정당의 추천·표방이 금지된 직이라 정당 표시가 없습니다.</p>
    <div class="ar-by-sido-host" id="ar-by-supt-host"></div>
  </section>

  <section class="ar-section" id="ar-by-district-section" hidden>
    <h2 class="ar-section-title">국회의원 재·보궐 결과</h2>
    <div class="ar-by-district-host" id="ar-by-district-host"></div>
  </section>

  <section class="ar-section" id="ar-by-sigungu-section" hidden>
    <h2 class="ar-section-title">기초단체장 결과</h2>
    <div class="ar-by-sigungu-host" id="ar-by-sigungu-host"></div>
  </section>

  <section class="ar-section" id="ar-by-sido-mem-section" hidden>
    <h2 class="ar-section-title">광역의원 결과</h2>
    <p class="ar-source-line">시·도의회 의원 보궐 (선거구별).</p>
    <div class="ar-by-sido-mem-host" id="ar-by-sido-mem-host"></div>
  </section>

  <section class="ar-section" id="ar-by-sigungu-mem-section" hidden>
    <h2 class="ar-section-title">기초의원 결과</h2>
    <p class="ar-source-line">시·군·구의회 의원 보궐 (선거구별).</p>
    <div class="ar-by-sigungu-mem-host" id="ar-by-sigungu-mem-host"></div>
  </section>

  <section class="ar-section" id="ar-by-reasons-section" hidden>
    <h2 class="ar-section-title">실시 사유</h2>
    <p class="ar-source-line">중앙선거관리위원회 재·보궐 실시사유 확정상황 API · 전임자·소속 정당·사유.</p>
    <div class="ar-by-reasons-host" id="ar-by-reasons-host"></div>
  </section>

  <section class="ar-section" id="ar-pledge-realm-section" hidden>
    <h2 class="ar-section-title">공약 분야 분포</h2>
    <p class="ar-source-line">중앙선거관리위원회 선거공약 API. 분야는 원문에 없어 제목·본문으로 자동 분류했습니다.</p>
    <div id="ar-pledge-realm-host"></div>
  </section>
"""

SECTIONS_GENERAL = """
  <section class="ar-section" id="ar-parliament" hidden>
    <h2 class="ar-section-title">의회 구성</h2>
    <p class="ar-source-line">정당별 지역구·비례대표 의석. 데이터 원본: <a href="{nec_url}" target="_blank" rel="noopener">중앙선거관리위원회 ↗</a></p>
    <div class="ar-parliament-table" id="ar-parliament-table"></div>
  </section>

  <section class="ar-section" id="ar-proportional" hidden>
    <h2 class="ar-section-title">비례대표 정당 득표</h2>
    <div class="ar-nation-host" id="ar-proportional-host"></div>
  </section>

  <section class="ar-section" id="ar-exitpoll" hidden>
    <h2 class="ar-section-title">출구조사 vs 실제</h2>
    <p class="ar-source-line">{date} 18:00 발표. <b>KBS·MBC·SBS 방송 3사 공동 출구조사</b>(컨소시엄). 표본은 공유, <b>의석 예측은 각 사 분석팀이 별도 시뮬레이션</b>(기준점·접전구 처리 차이). JTBC는 별도. 범위 안 적중 자동 계산.</p>
    <div class="ar-exitpoll-grid" id="ar-exitpoll-grid"></div>
  </section>

  <section class="ar-section" id="ar-polls-link" hidden>
    <h2 class="ar-section-title">여론조사</h2>
    {polls_link}
    <div class="ar-polls-link-host" id="ar-polls-link-host"></div>
  </section>
"""

FOOT = """
  <footer class="foot">
    <div class="foot-row">
      <span class="ar-foot-src"><a href="https://info.nec.go.kr" target="_blank" rel="noopener">중앙선거관리위원회 선거통계시스템</a>{nec_source_suffix}</span>
      <a href="https://www.nesdc.go.kr/portal/bbs/B0000005/list.do?menuNo=200467{nesdc_gubun_query}" target="_blank" rel="noopener">중앙선거여론조사심의위원회 ({n}{n_unit} {kind_short})</a>{wiki_link}
    </div>
    <p class="fine">본 아카이브는 NEC 개표 결과·NESDC 등록 여론조사·방송사 출구조사를 통합 가공한 회차 단위 영구 보존 페이지입니다.</p>
  </footer>
</main>

<script src="assets/regions.js"></script>
<script src="assets/parties.js"></script>
<script src="assets/utils.js"></script>
<script src="assets/lens-switcher.js"></script>
{extra_scripts}<script src="assets/elections.js"></script>
<script src="assets/svg-viewport.js"></script><!-- SVG 팬·줌 (방식 뷰 공용) -->
<script src="assets/encoding-toggle.js"></script><!-- 인코딩 토글(아이콘+가족) -->
<script src="assets/archive/shared.js"></script>
<script src="assets/archive/local.js"></script>
<script src="assets/archive/render-governor-hex.js"></script>
<script src="assets/archive/render-sido-map.js"></script>
<script src="assets/archive/render-sigungu-map.js"></script><!-- 시군구 지리 코로플레스(대선 시군구 명도 geo) -->
<script src="assets/archive/render-sido-prop.js"></script>
<script src="assets/archive/render-sido-view.js"></script>
<script src="assets/archive/render-metro-hex.js"></script>
<script src="assets/cartogram-util.js"></script>
<script src="assets/hexgrid.js"></script><!-- hexCenter·hexPoints(선거구 hex 의존) -->
<script src="assets/render-sigungu-cartogram.js"></script><!-- 시군구 표비례 카토그램(격자/dorling) -->
<script src="assets/render-district-hex.js"></script><!-- 선거구 hex(공용) -->
<script src="assets/archive/render-district-map.js"></script><!-- 선거구 지리 코로플레스 -->
<script src="assets/trust.js"></script><!-- 신뢰 상태 (docs/trust-states.md) -->
<script src="assets/archive/person-link.js"></script><!-- 후보 → 인물 페이지 -->
<script src="assets/archive/render-comparison.js"></script><!-- 이전 회차 대비 변화 -->
<script src="assets/archive/render-pledge-realms.js"></script><!-- 공약 분야 분포 -->
<script src="assets/archive/render-council-hex.js"></script>
<script src="assets/archive/render-winners.js"></script>
<script src="assets/archive/render-demographics.js"></script><!-- 성연령 득표기여(대선) -->
<script src="assets/archive/pres.js"></script>
<script src="assets/archive/general.js"></script>
<script src="assets/archive/byelection.js"></script>
<script src="assets/archive/core.js"></script>
<script src="assets/view-registry.js"></script>
<script src="assets/svg-export.js"></script>
<script src="assets/theme.js"></script>
<script src="assets/nav.js"></script>
</body>
</html>
"""

KIND_TO_HERO = {"local": HERO_LOCAL, "presidential": HERO_PRES, "general_election": HERO_GENERAL, "byelection": HERO_BYELECTION}

# 제목 아래 깔린 .ar-source-line(TMI 설명)을 제목 옆 정보 ⓘ 팝오버로 이관.

# --- 결과 요약 (빌드 시점 정적 렌더) -----------------------------------------
# archive 77개는 섹션 제목만 HTML에 있고 수치는 전부 JS가 채웠다. 본문이 744자뿐이라
# 검색엔진이 '크롤링됨 - 색인 생성되지 않음'으로 보류하기 좋은 상태였다. 결과 JSON에서
# 회차 핵심을 뽑아 HTML로도 찍는다 — 화면 섹션은 그대로 JS가 채우므로 중복 표시는 없다.

def _fmt_pct(v):
    return f"{float(v):.1f}%" if v is not None else "—"


_PARTY_PAGES = None
_PERSON_LINKS = {}


def party_href(name: str) -> str | None:
    """정당 페이지가 있는 이름만. 무소속·미등록 군소정당은 링크하지 않는다."""
    global _PARTY_PAGES
    if _PARTY_PAGES is None:
        try:
            _PARTY_PAGES = set(json.loads(
                (ROOT / "data/parties/registry.json").read_text(encoding="utf-8"))["parties"])
        except Exception:
            _PARTY_PAGES = set()
    if name in _PARTY_PAGES:
        return f"/party/{quote(name)}/"
    return None


def person_href(eid: str, tc: str, place: str, name: str) -> str | None:
    """build_person_links가 만든 (직|지역|이름) → slug 색인. 동명이인으로 갈리는 키는
    색인에 아예 없으므로 여기서 억지로 잇지 않는다 — 죽은 링크보다 글자가 낫다."""
    if eid not in _PERSON_LINKS:
        fp = ROOT / "data/person-links" / f"{eid}.json"
        try:
            _PERSON_LINKS[eid] = json.loads(fp.read_text(encoding="utf-8")).get("links") or {}
        except Exception:
            _PERSON_LINKS[eid] = {}
    slug = _PERSON_LINKS[eid].get(f"{tc}|{place}|{name}")
    return f"/person/{quote(slug)}/" if slug else None


def comparison_line(eid: str) -> str:
    """'지난 회차 대비' 한 줄 — 첫 화면에서 답해야 할 네 질문 중 마지막.
    (무슨 선거 / 누가 이겼나 / 투표율은 / **지난번과 뭐가 달라졌나**)

    비교 데이터는 21쌍 다 있는데 스크롤을 한참 내려야 나왔다. 요약은 이 선거의
    입구이므로 여기서 한 줄로 답한다 — 자세한 건 아래 비교 섹션이 이어받는다.

    정적 HTML이라 크롤러도 본다. 첫 화면 JS 렌더(hero)는 크롤러가 못 볼 수 있다.
    """
    em = ROOT / "data/elections" / f"{eid}.json"
    if not em.exists():
        return ""
    try:
        prev = (json.loads(em.read_text(encoding="utf-8")).get("archive") or {}
                ).get("compare_previous")
    except Exception:
        return ""
    if not prev:
        return ""
    fp = ROOT / "data/comparisons" / f"{eid}__{prev}.json"
    if not fp.exists():
        return ""
    try:
        d = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return ""

    bits = []
    t = d.get("turnout") or {}
    if t.get("delta") is not None:
        arrow = "▲" if t["delta"] > 0 else "▼" if t["delta"] < 0 else "="
        bits.append(f'투표율 {t["previous"]}% → <b>{t["current"]}%</b> '
                    f'<span class="ar-cmp-d">{arrow}{abs(t["delta"]):.1f}%p</span>')

    # 대선은 전국 득표율 이동이 본론, 그 외는 자리 증감이 본론이다.
    def top_delta(delta: dict, unit: str, n: int = 3):
        if not delta:
            return None
        items = sorted(delta.items(), key=lambda x: -abs(x[1]))[:n]
        return " · ".join(
            f'{_esc(k)} <span class="ar-cmp-d">{v:+g}{unit}</span>' for k, v in items)

    nat = top_delta((d.get("nation") or {}).get("delta") or {}, "%p")
    if nat:
        bits.append(nat)
    else:
        for tc in ("3", "4", "2"):
            o = (d.get("offices") or {}).get(tc)
            if not o:
                continue
            seats = top_delta(o.get("delta_compared_only") or {}, "")
            if seats:
                bits.append(f'{_esc(o.get("label") or "")} {seats}')
                break
    if not bits:
        return ""
    name = _esc((d.get("_meta") or {}).get("previous_name") or prev)
    return (f'<p class="ar-summary-cmp"><span class="ar-cmp-k">{name} 대비</span> '
            + " · ".join(bits) + '</p>')


def results_summary(eid: str, kind: str) -> str:
    rp = RESULTS_DIR / f"{eid}.json"
    if not rp.exists():
        return ""
    try:
        doc = json.loads(rp.read_text(encoding="utf-8"))
    except Exception:
        return ""
    races = doc.get("races", [])

    def top_of(scope, tc=None, n=3):
        rs = [r for r in races if r.get("scope") == scope and (tc is None or r.get("sg_typecode") == tc)]
        if not rs:
            return []
        cs = sorted((rs[0].get("candidates") or []), key=lambda c: -(c.get("votes") or 0))
        return cs[:n]

    # 요약은 이 선거의 **입구**다. 이름만 적어 두면 여기서 더 갈 데가 없다 —
    # archive에서 인물·정당으로 나가는 링크가 하나도 없었다(측정: person 0·party 0).
    # 당선인 목록은 3,967명이라 필터 UI라서 상호작용 전엔 크롤러도 못 본다.
    def party_cell(name: str) -> str:
        h = party_href(name)
        return f'<a href="{h}">{_esc(name)}</a>' if h else _esc(name)

    rows = []
    if kind == "presidential":
        for c in top_of("nation", "1"):
            nm, pty = c.get("name"), c.get("party")
            ph = person_href(eid, "1", "전국", nm)
            nm_html = f'<a href="{ph}">{_esc(nm)}</a>' if ph else _esc(nm)
            rows.append((f'{nm_html} ({party_cell(pty)})', _fmt_pct(c.get("pct"))))
    elif kind == "general_election":
        seats = {}
        for r in races:
            if r.get("scope") != "district" or r.get("sg_typecode") != "2":
                continue
            for c in (r.get("candidates") or []):
                if c.get("won"):
                    seats[c.get("party") or "무소속"] = seats.get(c.get("party") or "무소속", 0) + 1
        for pty, n in sorted(seats.items(), key=lambda x: -x[1])[:5]:
            rows.append((party_cell(pty), f"지역구 {n}석"))
    else:   # local · byelection — 광역단체장(3) 우선, 없으면 기초단체장(4)·국회의원(2)
        # 재보궐은 그 회차에 치러진 직만 있다 — 광역장이 없으면 기초장·국회의원·지방의원
        # 순으로 내려가며 첫 번째로 데이터가 있는 직을 요약한다(2014-10-29는 기초의원뿐).
        for tc, scope, label in (("3", "sido", "광역단체장"), ("4", "sigungu", "기초단체장"),
                                 ("2", "district", "국회의원"), ("5", "district", "광역의원"),
                                 ("6", "district", "기초의원")):
            won = {}
            for r in races:
                if r.get("sg_typecode") != tc or r.get("scope") != scope:
                    continue
                for c in (r.get("candidates") or []):
                    if c.get("won"):
                        won[c.get("party") or "무소속"] = won.get(c.get("party") or "무소속", 0) + 1
            if won:
                for pty, n in sorted(won.items(), key=lambda x: -x[1])[:5]:
                    rows.append((party_cell(pty), f"{label} {n}곳"))
                break
    if not rows:
        return ""

    # 투표율 — 전국 합계가 있으면 그것, 없으면 시도 가중평균.
    # voters가 아예 없는 회차(1~4회 지선)는 계산하지 않고 문구를 뺀다. None을 0으로
    # 더하면 '투표율 0.0%'라는 없던 사실이 만들어진다 — 결손은 0이 아니다.
    top = [r for r in races if r.get("scope") in ("sido", "nation")]
    el = sum(r.get("electors") or 0 for r in top)
    have_vo = [r for r in top if r.get("voters") is not None]
    vo = sum(r["voters"] for r in have_vo)
    # 일부만 있으면 그 합은 전국 투표율이 아니다 — 전부 있을 때만 쓴다.
    turnout = (f" · 투표율 {vo / el * 100:.1f}%"
               if (el and have_vo and len(have_vo) == len(top)) else "")

    items = "".join(f"<li><b>{a}</b> <span>{b}</span></li>" for a, b in rows)
    return (f'<section class="ar-summary"><h2>결과 요약</h2>'
            f'<ul class="ar-summary-list">{items}</ul>'
            + comparison_line(eid)
            + (f'<p class="ar-summary-note">개표 결과 기준{turnout}. '
            f'지역별 상세는 아래 섹션에서 — '
            # archive에서 지역 entity로 나가는 길. 시군구 265곳을 다 나열하지 않고
            # 허브 1-hop으로 둔다(역방향은 이미 강하다 — 지역 페이지가 archive 25개를 링크).
            f'<a href="/region/">내 지역의 역대 기록</a>도 볼 수 있습니다.</p>')
            + '</section>')


# 화면엔 제목만 — 누르면(ⓘ) 설명이 읽기 좋은 크기로 뜬다. (assets/components.css .info-i/.info-pop)
_SRC_RE = re.compile(r'<h2 class="ar-section-title">([^<]*)</h2>\s*<p class="ar-source-line">(.*?)</p>')


def _sourceline_to_info(html: str) -> str:
    def repl(m: "re.Match[str]") -> str:
        title, body = m.group(1), m.group(2)
        return (f'<h2 class="ar-section-title">{title}'
                f'<span class="info-i" tabindex="0" role="button" aria-label="설명">i'
                f'<span class="info-pop">{body}</span></span></h2>')
    return _SRC_RE.sub(repl, html)



# --- 서사 그룹 -----------------------------------------------------------------
# 섹션이 전부 같은 위계로 늘어서면 '무엇에 답하는 묶음인지'가 없어 길게만 느껴진다.
# 섹션을 지우거나 접지 않고 그룹을 얹어 계층을 만든다. 그룹은 trust provenance의
# 상속 단위이기도 하다(같은 데이터 family = 같은 부모).
#
# 회차 종류마다 있는 섹션이 다르므로, 없는 섹션은 조용히 건너뛰고 빈 그룹은 만들지 않는다.

def group_sections(body: str, groups: list) -> str:
    """섹션 블록을 서사 그룹으로 재배열. groups = [(제목, 부제, [section_id...])]"""
    blocks = {}
    for m in re.finditer(r'\n  <section class="ar-section" id="(ar-[a-z0-9-]+)"[\s\S]*?\n  </section>\n',
                         body):
        blocks[m.group(1)] = m.group(0)
    if not blocks:
        return body
    out, seen = [], set()
    for title, sub, ids in groups:
        have = [i for i in ids if i in blocks]
        if not have:
            continue                       # 이 회차에 없는 그룹은 만들지 않는다
        out.append(f'\n  <div class="ar-group">\n    <h2 class="ar-group-title">{title}'
                   f'<span class="ar-group-sub">{sub}</span></h2>')
        for i in have:
            out.append(blocks[i].rstrip('\n'))
            seen.add(i)
        out.append('  </div>\n')
    for k, v in blocks.items():            # 그룹 미지정 섹션도 잃지 않는다
        if k not in seen:
            out.append(v.rstrip('\n'))
    return '\n'.join(out) + '\n'


G_RESULT = ("결과", "이 선거에서 무슨 일이 있었나")
G_CHANGE = ("무엇이 바뀌었나", "지난 회차와 견줘서")
G_WHO = ("누가 경쟁했나", "당선인과 후보")
G_BEFORE = ("선거 전에는 어떻게 보였나", "여론조사·출구조사와 실제의 거리")
# 섹션 이름은 짧고 건조하게 — nav의 "선거 / 인물·정당 / 역사"와 같은 명명법.
# 부제는 링크가 아니라 부제다(다른 그룹과 동일). "당선인·후보의"는 두 집단인지
# 헷갈리게 하고, 회차마다 모집단이 달라(당선인만/등록 후보 전체) 고정 문구로는
# 정확할 수 없다 — 정확한 모집단은 차트 위 note가 말한다.
G_PLEDGE = ("공약", "NEC에 등록된 선거공약")
G_TOGETHER = ("함께 치러진 선거", "같은 날 실시된 재·보궐")

GROUPS_BY_KIND = {
    "presidential": [
        (*G_RESULT, ["ar-nation", "ar-pres-sido-hex-section"]),
        (*G_CHANGE, ["ar-compare-section"]),
        (*G_BEFORE, ["ar-exitpoll", "ar-polls-link"]),
        (*G_PLEDGE, ["ar-pledge-realm-section"]),
    ],
    "general_election": [
        (*G_RESULT, ["ar-parliament", "ar-proportional"]),
        (*G_CHANGE, ["ar-compare-section"]),
        (*G_BEFORE, ["ar-exitpoll", "ar-polls-link"]),
    ],
    "byelection": [
        (*G_RESULT, ["ar-by-sido-section", "ar-by-supt-section", "ar-by-district-section",
                     "ar-by-sigungu-section", "ar-by-sido-mem-section",
                     "ar-by-sigungu-mem-section"]),
        (*G_WHO, ["ar-by-reasons-section"]),
        (*G_PLEDGE, ["ar-pledge-realm-section"]),
    ],
}


KIND_TO_SECTIONS = {
    k: _sourceline_to_info(group_sections(v, GROUPS_BY_KIND[k]) if k in GROUPS_BY_KIND else v)
    for k, v in {
        "local": SECTIONS_LOCAL, "presidential": SECTIONS_PRES,
        "general_election": SECTIONS_GENERAL, "byelection": SECTIONS_BYELECTION,
    }.items()}


def nec_source_suffix(meta: dict) -> str:
    """data_source_note(예 '중앙선거관리위원회 OpenAPI')를 푸터 NEC 링크 옆 인라인 접미로.
    '중앙선거관리위원회'는 링크 텍스트에 이미 있으니 떼고 방식만(예 'OpenAPI') ' · '로 붙임."""
    note = (meta.get("archive") or {}).get("data_source_note", "")
    method = note.replace("중앙선거관리위원회", "").strip().lstrip("·").strip()
    return f' · {method}' if method else ""


def hero_status(d: dict) -> str:
    return "개표 결과 수집 중." if d["is_active"] else "확정 결과."


def counting_title(d: dict) -> str:
    return "개표 진행 · 시도별" if d["is_active"] else "광역단체장 결과 · 시도별"


def render(meta: dict, neighbors: dict | None = None) -> str:
    d = derive(meta)
    d["hero_status"] = hero_status(d)
    d["counting_title"] = counting_title(d)
    d["nec_url"] = NEC_RESULTS_URL.format(election_id_full=d["election_id_full"]) if d["election_id_full"] else "https://info.nec.go.kr"
    d["wiki_link"] = (
        f'\n      <a href="{d["wiki_url"]}" target="_blank" rel="noopener">출구조사 · 위키백과</a>'
        if d["wiki_url"] else ""
    )
    d["extra_scripts"] = '<script src="assets/parliament.js"></script>\n' if d["kind"] == "general_election" else ""
    d["nec_source_suffix"] = nec_source_suffix(meta)   # 푸터 NEC 링크 옆 ' · OpenAPI' 인라인(선거통계시스템과 한 줄)
    hero_html = KIND_TO_HERO[d["kind"]].format(**d)
    nbrs = neighbors or {}

    return (
        HEAD.format(**d, nav=render_nav(menu_for_path(f'archive/{d["id"]}/index.html')))
        + render_tophead(nbrs, hero_html)           # 히어로 제목 좌우에 이전·다음
        + results_summary(d["id"], d["kind"])       # 빌드 시점 정적 요약(검색엔진용)
        + KIND_TO_SECTIONS[d["kind"]].format(**d)
        + render_bottom_nav(nbrs, d)                # 이전 · [더 자세히] · 다음
        + FOOT.format(**d)
    )


# kind → 하단 '더 자세히' 센터 셀 (history.html type, 제목, 보조설명). byelection은 없음 → 센터 비움.
DETAIL_CELL = {
    "general_election": ("national_assembly", "지역구 단위 hex·지도", "시도별 요약보다 세밀 · 역대 회차 비교"),
    "local": ("local", "광역·기초·교육감 지도", "시도별 요약보다 세밀 · 역대 회차 비교"),
    "presidential": ("presidential", "시군구·동 단위 득표 지도", "시도별 요약보다 세밀 · 역대 회차 비교"),
}


def nav_cell(m: dict | None, side: str) -> str:
    """이전·다음 회차 셀 (상·하단 공통)."""
    label = "이전 회차" if side == "prev" else "다음 회차"
    if not m:
        none_txt = "이전 없음" if side == "prev" else "다음 없음"
        return f'<span class="ar-nav-cell ar-nav-{side} ar-nav-empty">{none_txt}</span>'
    date = m.get("date", "")
    name = m.get("name", "")
    page = m.get("archive", {}).get("page", "#")
    arrow = "←" if side == "prev" else "→"
    lbl = f'{arrow} {label}' if side == "prev" else f'{label} {arrow}'
    return (f'<a class="ar-nav-cell ar-nav-{side}" href="{page}">'
            f'<span class="ar-nav-label">{lbl}</span>'
            f'<span class="ar-nav-name">{name}</span>'
            f'<span class="ar-nav-date">{date}</span></a>')


def render_tophead(neighbors: dict, hero_html: str) -> str:
    """상단: 히어로(현재 회차 제목) 좌우에 이전·다음. 양옆 모두 없으면 히어로만."""
    prev_meta = neighbors.get("prev")
    next_meta = neighbors.get("next")
    if not prev_meta and not next_meta:
        return hero_html
    return (f'  <div class="ar-tophead">'
            f'{nav_cell(prev_meta, "prev")}{hero_html}{nav_cell(next_meta, "next")}'
            f'</div>\n')


def render_bottom_nav(neighbors: dict, current: dict) -> str:
    """하단: 이전 · [더 자세히(history 진입)] · 다음. 더 자세히 없으면(재보궐) 센터 비움."""
    prev_meta = neighbors.get("prev")
    next_meta = neighbors.get("next")
    d = DETAIL_CELL.get(current.get("kind"))
    center = ""
    if d:
        htype, name, sub = d
        center = (f'<a class="ar-nav-cell ar-nav-detail" href="/history.html?type={htype}&n={current.get("n")}">'
                  f'<span class="ar-nav-label">더 자세히 ↘</span>'
                  f'<span class="ar-nav-name">{name}</span>'
                  f'<span class="ar-nav-detail-sub">{sub}</span></a>')
    if not prev_meta and not next_meta and not center:
        return ""
    cls = "ar-nav ar-nav-tl ar-nav-bottom" + ("" if center else " ar-nav-nodetail")
    return f'<nav class="{cls}">{nav_cell(prev_meta, "prev")}{center}{nav_cell(next_meta, "next")}</nav>\n'


def render_ar_list(metas: list[dict]) -> str:
    """index.html 회차 아카이브 목록 — 날짜 desc 정렬. 재보궐은 회차가 아니고(날짜 기반)
    결과지도도 없어 빈 썸네일이 됨 → 제외(전용 허브 /byelection/ 가 따로 있음)."""
    rows = []
    for m in sorted(metas, key=lambda x: x["date"], reverse=True):
        if m.get("kind") == "byelection":
            continue
        ar = m["archive"]
        label = ar.get("list_label") or ("진행" if m.get("status") == "active" else "확정")
        # 결과지도 미니 썸네일 — 타입별 대표 뷰 우선순위(라벨은 캡처서 숨김 → 모양만으로 식별).
        #   지선=광역장 hex · 대선=시군구 격차명도 hex(result) · 총선=의석 반원(seats). 없으면 dorling 폴백.
        # 우선순위는 data/view_registry.json이 정본 — 목록 썸네일·og 카드·본문 그림이
        # 같은 뷰를 고르게 하려고 한자리에 뒀다. 여기 사본을 두면 셋이 어긋난다.
        thumb = '<span class="ar-list-thumb is-empty" aria-hidden="true"></span>'
        for v in (THUMB_PRIORITY.get(m.get("kind")) or PRIMARY_ORDER):
            if (ROOT / "og" / "maps" / m["id"] / f"{v}.png").exists():
                thumb = (f'<img class="ar-list-thumb" src="/og/maps/{m["id"]}/{v}.png" '
                         f'alt="" loading="lazy" decoding="async">')
                break
        rows.append(
            f'      <a class="ar-list-row" href="{ar["page"]}">{thumb}'
            f'<span>{m["date"]}</span><span>{m["name"]}</span>'
            f'<span class="ar-list-tag">{label}</span></a>'
        )
    return "\n".join(rows)


def sync_recent_html(metas: list[dict], check: bool) -> bool:
    """홈의 '최근 선거' 몇 개만 갱신. 전체 목록은 /elections.html 허브가 갖는다.

    홈에서 53행을 걷어내되 정적으로 박아 두면 다음 선거 때 낡는다. 마커로 생성한다.
    """
    fp = ROOT / "index.html"
    html = fp.read_text(encoding="utf-8")
    si, ei = html.find(AR_RECENT_START), html.find(AR_RECENT_END)
    if si < 0 or ei < 0:
        return False
    start_end = html.find("\n", si) + 1
    # render_ar_list가 내부에서 정렬·재보궐 제외를 하므로, 자르기 전에 같은 기준을 적용해야
    # 최근 N개가 실제로 N개가 된다(정렬 전에 자르면 재보궐이 섞여 줄어든다).
    recent = [m for m in sorted(metas, key=lambda x: x["date"], reverse=True)
              if m.get("kind") != "byelection"][:AR_RECENT_N]
    new_html = html[:start_end] + render_ar_list(recent) + "\n      " + html[ei:]
    if new_html == html:
        return False
    if not check:
        fp.write_text(new_html, encoding="utf-8")
    return True


def sync_index_html(metas: list[dict], check: bool, target: Path = None) -> bool:
    """AR_LIST 마커 사이 회차 목록 갱신. 변경 여부 반환.

    홈과 '모든 선거' 허브가 같은 목록을 쓴다. 홈에서 목록을 걷어내도 허브가 77개 archive를
    직접 링크하므로 크롤 경로(홈 → 허브 → archive)가 1-hop + 1-hop으로 유지된다.
    """
    INDEX_HTML = target or (ROOT / "index.html")
    html = INDEX_HTML.read_text(encoding="utf-8")
    si = html.find(AR_LIST_START)
    ei = html.find(AR_LIST_END)
    if si < 0 or ei < 0:
        print(f"  ! {INDEX_HTML.name}에 AR_LIST 마커 없음 — 스킵", file=sys.stderr)
        return False
    # marker 줄 끝까지 포함
    start_end = html.find("\n", si) + 1
    new_block = render_ar_list(metas) + "\n      "
    new_html = html[:start_end] + new_block + html[ei:]
    if new_html == html:
        return False
    if not check:
        INDEX_HTML.write_text(new_html, encoding="utf-8")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", help="특정 회차 1건만 (index.html 은 갱신 안 됨)")
    ap.add_argument("--check", action="store_true", help="diff만 출력, 파일 안 씀")
    args = ap.parse_args()

    index = json.loads((ELECTIONS_DIR / "index.json").read_text(encoding="utf-8"))
    all_ids = list(index.get("active", [])) + list(index.get("archive", []))
    if args.id:
        if args.id not in all_ids:
            print(f"ERR: {args.id} index.json 에 없음", file=sys.stderr)
            sys.exit(1)
        all_ids = [args.id]

    # 모든 meta 먼저 로드 (kind별 neighbor 계산 위해)
    all_metas = []
    for eid in (list(index.get("active", [])) + list(index.get("archive", []))):
        mp = ELECTIONS_DIR / f"{eid}.json"
        if mp.exists():
            m = json.loads(mp.read_text(encoding="utf-8"))
            if m.get("archive") and m.get("kind") in KIND_TO_HERO:
                all_metas.append(m)
    # kind별 chronological list
    from collections import defaultdict
    by_kind: dict = defaultdict(list)
    for m in all_metas:
        by_kind[m["kind"]].append(m)
    for k in by_kind:
        by_kind[k].sort(key=lambda x: x.get("date", ""))
    neighbors_of = {}
    for kind, lst in by_kind.items():
        for i, m in enumerate(lst):
            neighbors_of[m["id"]] = {
                "prev": lst[i - 1] if i > 0 else None,
                "next": lst[i + 1] if i < len(lst) - 1 else None,
            }

    # 선거 고르기 디렉터리 인덱스 (대시보드 ElectionTimeline) — 아카이브 있는 대선/총선/지선 전 회차.
    # 단일 출처: 여기서 만든 슬러그(=아카이브 id)는 그대로 archive 링크라 404 없음. 재보궐 제외.
    # party = 역대 정당 지형 요약(노드 색): 대선=당선 정당, 총선=지역구 1당, 지선=광역단체장 다수당.
    if not args.id:
        from collections import Counter as _Counter
        HT = {"presidential": "presidential", "general_election": "national_assembly", "local": "local"}
        _agg = json.loads((ROOT / "data" / "elections.json").read_text(encoding="utf-8"))
        _pres_wp = {e.get("n"): e.get("winner_party") for e in _agg.get("presidential", {}).get("elections", [])}

        def _dominant_party(m):
            kind = m.get("kind")
            if kind == "presidential":
                # 아카이브가 보여주는 archive.results_path의 전국 1위 정당으로(n-keyed elections.json은
                # 4대처럼 같은 n에 2건(3·15 자유당·8월 간선 민주당)이면 충돌). 없으면 fallback.
                rp = (m.get("archive") or {}).get("results_path")
                if rp and (ROOT / rp).exists():
                    try:
                        races = json.loads((ROOT / rp).read_text(encoding="utf-8")).get("races", [])
                        nat = [r for r in races if r.get("scope") == "nation"]
                        cs = sorted((nat[0].get("candidates") if nat else []) or [],
                                    key=lambda x: -(x.get("votes") or 0))
                        if cs and cs[0].get("party"):
                            return cs[0]["party"]
                    except Exception:
                        pass
                return _pres_wp.get(m.get("n"))
            rp = (m.get("archive") or {}).get("results_path")
            if not rp or not (ROOT / rp).exists():
                return None
            try:
                races = json.loads((ROOT / rp).read_text(encoding="utf-8")).get("races", [])
            except Exception:
                return None
            c = _Counter()
            if kind == "general_election":      # 지역구(tc=2) 당선자 1당
                for r in races:
                    if str(r.get("sg_typecode")) == "2" and r.get("scope") == "district":
                        w = [x for x in (r.get("candidates") or []) if x.get("won")]
                        if w and w[0].get("party"):
                            c[w[0]["party"]] += 1
            elif kind == "local":               # 광역단체장(tc=3) 다수당
                for r in races:
                    if str(r.get("sg_typecode")) == "3" and r.get("scope") == "sido":
                        cs = sorted(r.get("candidates") or [], key=lambda x: -(x.get("votes") or 0))
                        if cs and cs[0].get("party"):
                            c[cs[0]["party"]] += 1
            return c.most_common(1)[0][0] if c else None

        dir_list = sorted(
            ({"slug": m["id"], "name": m["name"], "date": m["date"], "n": m["n"],
              "type": HT[m["kind"]], "party": _dominant_party(m)}
             for m in all_metas if m.get("kind") in HT and m.get("date") and m.get("n") is not None),
            key=lambda x: x["date"])
        (ROOT / "data" / "archive_index.json").write_text(
            json.dumps(dir_list, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    n_changed = 0
    n_unchanged = 0
    n_skipped = 0
    archive_metas = []  # index.html 목록용
    for eid in all_ids:
        meta_path = ELECTIONS_DIR / f"{eid}.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        ar = meta.get("archive")
        if not ar or not ar.get("page"):
            n_skipped += 1
            continue
        if meta.get("kind") not in KIND_TO_HERO:
            print(f"  ! {eid}: kind={meta.get('kind')} — 템플릿 없음, 스킵", file=sys.stderr)
            n_skipped += 1
            continue
        archive_metas.append(meta)
        html = render(meta, neighbors_of.get(meta["id"]))
        out = ARCHIVE_DIR / eid / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        current = out.read_text(encoding="utf-8") if out.exists() else ""
        if current == html:
            n_unchanged += 1
            continue
        if args.check:
            print(f"~ {eid} 변경 예정")
            n_changed += 1
            continue
        out.write_text(html, encoding="utf-8")
        print(f"OK {eid}")
        n_changed += 1
    # index.html 회차 목록 — --id 옵션이 아닐 때만 (부분 메타로 list 잘리면 안 됨)
    if not args.id and archive_metas:
        # '모든 선거' 허브도 같은 목록을 쓴다 — 홈에서 목록을 줄여도 크롤 경로가 유지된다.
        sync_index_html(archive_metas, args.check, ROOT / 'elections.html')
        if sync_recent_html(archive_metas, args.check):
            print(("~" if args.check else "OK") + " index.html (최근 선거)")
        if sync_index_html(archive_metas, args.check):
            print(("~" if args.check else "OK") + " index.html (회차 아카이브 목록)")

    print(f"\n변경 {n_changed} · 동일 {n_unchanged} · 스킵 {n_skipped}")


if __name__ == "__main__":
    main()
