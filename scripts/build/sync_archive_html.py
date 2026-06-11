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
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ELECTIONS_DIR = ROOT / "data" / "elections"
ARCHIVE_DIR = ROOT / "archive"
INDEX_HTML = ROOT / "index.html"
AR_LIST_START = "<!-- AR_LIST_START"
AR_LIST_END = "<!-- AR_LIST_END -->"

DOW = ["월", "화", "수", "목", "금", "토", "일"]

# kind → 짧은 라벨·history.html type slug·n 단위
KIND_META = {
    "local":              {"short": "지선",  "history_type": "local",              "n_unit": "회"},
    "presidential":       {"short": "대선",  "history_type": "presidential",       "n_unit": "대"},
    "general_election":   {"short": "총선",  "history_type": "national_assembly",  "n_unit": "대"},
    "byelection":         {"short": "재보궐", "history_type": "byelection",         "n_unit": "년"},
}


def kday(date_str: str) -> str:
    y, m, d = map(int, date_str.split("-"))
    return f"{date_str} ({DOW[date.fromordinal(date(y, m, d).toordinal()).weekday()]})"


def derive(meta: dict) -> dict:
    """meta + archive 블록 → 템플릿에 박을 변수."""
    kind = meta["kind"]
    km = KIND_META[kind]
    ar = meta["archive"]
    sg_id = meta.get("nec", {}).get("sg_id", "")
    gubun = meta.get("nesdc", {}).get("gubun", "")
    context = ar.get("context_note", "")
    date_label = kday(meta["date"])
    if context:
        date_label += f" · {context}"
    return {
        "id": meta["id"],
        "name": meta["name"],
        "date": meta["date"],
        "date_label": date_label,
        "n": meta["n"],
        "n_unit": km["n_unit"],
        "kind": kind,
        "kind_short": km["short"],
        "history_type": km["history_type"],
        "is_active": meta.get("status") == "active",
        "election_id_full": f"002{sg_id}" if sg_id else "",
        "nesdc_gubun_query": f"&pollGubuncd={gubun}" if gubun else "",
        "wiki_url": ar.get("wiki_url", ""),
        "year": meta["date"][:4],
    }


# --- 공통 chrome ---

HEAD = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<base href="/">
<title>polis · {name} ({date})</title>
<meta name="description" content="{name}({date}) 결과·여론조사·출구조사 비교 아카이브.">
<meta property="og:title" content="polis · {n}{n_unit} {kind_short} 아카이브">
<meta property="og:description" content="{n}{n_unit} {kind_short} 결과·여론조사·출구조사 비교.">
<meta property="og:type" content="website">
<link rel="canonical" href="/archive/{id}/">
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
    <!-- NAV_START — scripts/build/sync_nav_html.py 자동 갱신. 손수정 X. -->
    <span data-nav-urgent></span>
    <a href="/polls.html" class="hdr-link">여론조사</a>
    <a href="/byelection/" class="hdr-link">재·보궐</a>
    <a href="/tracker.html" class="hdr-link">지지율 추이</a>
    <a href="/history.html" class="hdr-link is-current">역대 결과</a>
    <a href="/timeline.html" class="hdr-link">타임라인</a>
    <!-- NAV_END -->
  </nav>
  <div class="hdr-meta">
    <button id="theme-toggle" class="theme-toggle" type="button" aria-label="테마 토글"></button>
  </div>
</header>

<main class="page">
  <nav class="ar-breadcrumb" aria-label="경로">
    <a href="/timeline.html">타임라인</a> ·
    <a href="/history.html?type={history_type}&n={n}">역대 선거</a> · <span>{n}{n_unit} {kind_short} 아카이브</span>
  </nav>
"""

# --- hero 블록 (kind별) ---

HERO_LOCAL = """
  <section class="ar-hero">
    <div class="ar-hero-tag">아카이브</div>
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
    <div class="ar-hero-tag">아카이브</div>
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
    <div class="ar-hero-tag">아카이브</div>
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
    <div class="ar-hero-tag">아카이브</div>
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

HISTORY_LINK_PRES = """
  <section class="ar-history-link">
    <a href="/history.html?type=presidential&n={n}" class="ar-history-link-btn">
      <span class="ar-history-link-label">시도·시군구 시각화</span>
      <span class="ar-history-link-sub">/history 에서 hex·지도로 →</span>
    </a>
  </section>
"""

HISTORY_LINK_LOCAL = """
  <section class="ar-history-link">
    <a href="/history.html?type=local&n={n}" class="ar-history-link-btn">
      <span class="ar-history-link-label">시도·시군구 시각화</span>
      <span class="ar-history-link-sub">/history 에서 광역·기초·교육감 hex로 →</span>
    </a>
  </section>
"""

HISTORY_LINK_GENERAL = """
  <section class="ar-history-link">
    <a href="/history.html?type=national_assembly&n={n}" class="ar-history-link-btn">
      <span class="ar-history-link-label">지역구·시도 시각화</span>
      <span class="ar-history-link-sub">/history 에서 254 지역구 hex·지도로 →</span>
    </a>
  </section>
"""

SECTIONS_LOCAL = HISTORY_LINK_LOCAL + """
  <section class="ar-section" id="ar-offices" hidden>
    <h2 class="ar-section-title">선출직 정당 분포</h2>
    <p class="ar-source-line">광역단체장 · 기초단체장 · 광역의원 (지역구·비례) · 기초의원 (지역구·비례). 교육감 제외.</p>
    <div class="ar-offices-grid" id="ar-offices-grid"></div>
  </section>

  <section class="ar-section" id="ar-governor-hex-section" hidden>
    <h2 class="ar-section-title">광역단체장 결과</h2>
    <p class="ar-source-line">시·도 hex — 1위 후보·득표율. 정당별 색.</p>
    <div class="ar-governor-hex" id="ar-governor-hex"></div>
  </section>

  <section class="ar-section" id="ar-metro-hex-section" hidden>
    <h2 class="ar-section-title">시·도의회 의석 분포</h2>
    <p class="ar-source-line">각 시도 cluster — 광역의원 지역구(tc=5) + 비례(tc=8). 정당별 색.</p>
    <div class="ar-metro-hex" id="ar-metro-hex"></div>
    <div class="ar-metro-hex-meta"><span id="ar-metro-hex-total"></span><span id="ar-metro-hex-legend"></span></div>
  </section>

  <section class="ar-section" id="ar-council-hex-section" hidden>
    <h2 class="ar-section-title">시군구의회 의석 분포</h2>
    <p class="ar-source-line">각 시군구 hex 안에 의석 spiral — 정당별 색. 지역구(tc=6) + 비례(tc=9) 합산.</p>
    <div class="ar-council-hex" id="ar-council-hex"></div>
    <div class="ar-council-hex-meta"><span id="ar-council-hex-total"></span><span id="ar-council-hex-legend"></span></div>
  </section>

  <section class="ar-section" id="ar-winners-section" hidden>
    <h2 class="ar-section-title">시·도의원·시·군·구의원 당선인</h2>
    <p class="ar-source-line">광역의원(tc=5)·기초의원(tc=6) 모두 NEC 확정 당선인 명부 기준 — 중선거구 정수·무투표 포함.</p>
    <div id="ar-winners-body"></div>
  </section>

  <section class="ar-section" id="ar-exitpoll" hidden>
    <h2 class="ar-section-title">출구조사 vs 실제</h2>
    <p class="ar-source-line">{date} 18:00 발표. <b>KBS·MBC·SBS 방송 3사 공동 출구조사</b>(한국리서치·입소스·코리아리서치 컨소시엄, 1,980개 투표소) — 표본은 공유, <b>의석 예측은 각 사 분석팀이 별도 시뮬레이션</b>이라 값이 다름. JTBC는 별도. 시도별 1위 일치율·평균 오차 자동 계산.</p>
    <div class="ar-exitpoll-grid" id="ar-exitpoll-grid"></div>
  </section>

  <section class="ar-section" id="ar-polls-link" hidden>
    <h2 class="ar-section-title">여론조사</h2>
    <div class="ar-polls-link-host" id="ar-polls-link-host"></div>
  </section>

  <section class="ar-section" id="ar-byelection" hidden>
    <h2 class="ar-section-title">재·보궐</h2>
    <div class="ar-byelection-host" id="ar-byelection-host"></div>
  </section>
"""

SECTIONS_PRES = HISTORY_LINK_PRES + """
  <section class="ar-section" id="ar-pres-sido-hex-section" hidden>
    <h2 class="ar-section-title">시도별 결과</h2>
    <p class="ar-source-line">시·도 hex — 1위 후보·득표율. 정당별 색.</p>
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
"""

SECTIONS_BYELECTION = """
  <section class="ar-section" id="ar-by-sido-section" hidden>
    <h2 class="ar-section-title">광역단체장 결과</h2>
    <p class="ar-source-line">데이터 원본: <a href="{nec_url}" target="_blank" rel="noopener">중앙선거관리위원회 ↗</a></p>
    <div class="ar-by-sido-host" id="ar-by-sido-host"></div>
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
"""

SECTIONS_GENERAL = HISTORY_LINK_GENERAL + """
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
"""

FOOT = """
  <footer class="foot">
    <div class="foot-row">
      <a href="https://info.nec.go.kr" target="_blank" rel="noopener">중앙선거관리위원회 선거통계시스템</a>
      <a href="https://www.nesdc.go.kr/portal/bbs/B0000005/list.do?menuNo=200467{nesdc_gubun_query}" target="_blank" rel="noopener">중앙선거여론조사심의위원회 ({n}{n_unit} {kind_short})</a>{wiki_link}
    </div>
    <p class="fine">본 아카이브는 NEC 개표 결과·NESDC 등록 여론조사·방송사 출구조사를 통합 가공한 회차 단위 영구 보존 페이지입니다.</p>
  </footer>
</main>

<script src="assets/regions.js"></script>
<script src="assets/parties.js"></script>
<script src="assets/utils.js"></script>
{extra_scripts}<script src="assets/elections.js"></script>
<script src="assets/archive/shared.js"></script>
<script src="assets/archive/local.js"></script>
<script src="assets/archive/render-governor-hex.js"></script>
<script src="assets/archive/render-sido-map.js"></script>
<script src="assets/archive/render-sido-prop.js"></script>
<script src="assets/archive/render-sido-view.js"></script>
<script src="assets/archive/render-metro-hex.js"></script>
<script src="assets/archive/render-council-hex.js"></script>
<script src="assets/archive/render-winners.js"></script>
<script src="assets/archive/pres.js"></script>
<script src="assets/archive/general.js"></script>
<script src="assets/archive/byelection.js"></script>
<script src="assets/archive/core.js"></script>
<script src="assets/theme.js"></script>
<script src="assets/nav.js"></script>
</body>
</html>
"""

KIND_TO_HERO = {"local": HERO_LOCAL, "presidential": HERO_PRES, "general_election": HERO_GENERAL, "byelection": HERO_BYELECTION}
KIND_TO_SECTIONS = {"local": SECTIONS_LOCAL, "presidential": SECTIONS_PRES, "general_election": SECTIONS_GENERAL, "byelection": SECTIONS_BYELECTION}


def source_caveat_block(meta: dict) -> str:
    note = (meta.get("archive") or {}).get("data_source_note", "")
    if not note:
        return ""
    return (
        '\n  <p class="ar-source-caveat">'
        f'<span class="ar-source-caveat-tag">source</span> {note}'
        '</p>\n'
    )


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
    d["nav_block"] = render_nav_block(neighbors or {})

    return (
        HEAD.format(**d)
        + KIND_TO_HERO[d["kind"]].format(**d)
        + source_caveat_block(meta)
        + d["nav_block"]
        + KIND_TO_SECTIONS[d["kind"]].format(**d)
        + d["nav_block"]
        + FOOT.format(**d)
    )


def render_nav_block(neighbors: dict) -> str:
    """이전·다음 회차 nav. neighbors = {'prev': meta or None, 'next': meta or None}."""
    prev_meta = neighbors.get("prev")
    next_meta = neighbors.get("next")
    if not prev_meta and not next_meta:
        return ""
    def cell(m, side):
        if not m:
            return f'<span class="ar-nav-cell ar-nav-empty">—</span>'
        date = m.get("date", "")
        name = m.get("name", "")
        page = m.get("archive", {}).get("page", "#")
        arrow = "←" if side == "prev" else "→"
        label = "이전 회차" if side == "prev" else "다음 회차"
        align = "left" if side == "prev" else "right"
        return (f'<a class="ar-nav-cell ar-nav-{side}" href="{page}">'
                f'<span class="ar-nav-label">{arrow if side == "prev" else ""} {label} {arrow if side == "next" else ""}</span>'
                f'<span class="ar-nav-name">{name}</span>'
                f'<span class="ar-nav-date">{date}</span></a>')
    return f'<nav class="ar-nav">{cell(prev_meta, "prev")}{cell(next_meta, "next")}</nav>\n'


def render_ar_list(metas: list[dict]) -> str:
    """index.html 회차 아카이브 목록 — 날짜 desc 정렬."""
    rows = []
    for m in sorted(metas, key=lambda x: x["date"], reverse=True):
        ar = m["archive"]
        label = ar.get("list_label") or ("진행" if m.get("status") == "active" else "확정")
        rows.append(
            f'      <a class="ar-list-row" href="{ar["page"]}">'
            f'<span>{m["date"]}</span><span>{m["name"]}</span>'
            f'<span class="ar-list-tag">{label}</span></a>'
        )
    return "\n".join(rows)


def sync_index_html(metas: list[dict], check: bool) -> bool:
    """index.html 회차 목록 markers 사이 갱신. 변경 여부 반환."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    si = html.find(AR_LIST_START)
    ei = html.find(AR_LIST_END)
    if si < 0 or ei < 0:
        print(f"  ! index.html에 AR_LIST 마커 없음 — 스킵", file=sys.stderr)
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
        if sync_index_html(archive_metas, args.check):
            print(("~" if args.check else "OK") + " index.html (회차 아카이브 목록)")

    print(f"\n변경 {n_changed} · 동일 {n_unchanged} · 스킵 {n_skipped}")


if __name__ == "__main__":
    main()
