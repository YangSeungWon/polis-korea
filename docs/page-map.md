# 페이지 지도 (IA) — 첫 화면·연결

사이트(polis.ysw.kr)의 7개 메인 페이지가 **진입 시 무엇을 먼저 보여주는지**, **서로 어떻게
연결되는지** 정리. 정적 서브페이지(build로 프리렌더)도 함께.

## 헤더 nav — 전 페이지 공통

모든 페이지 상단에 동일하게 inline(`sync_nav_html.py`가 동기화). 7개 evergreen 링크 +
긴급 chip 슬롯(`nav.js`가 active 선거 phase 따라 채움 — BLACKOUT/ELECTION/POST/RECENT일 때만).

| 라벨 | 경로 |
|---|---|
| 홈 | `/` |
| 여론조사 | `/polls.html` |
| 재·보궐 | `/byelection.html` |
| 지지율 추이 | `/tracker.html` |
| 역대 결과 | `/history.html` |
| 타임라인 | `/timeline.html` |
| 검색 | `/search.html` |

→ 어느 페이지에서든 7개로 직접 이동 가능. 아래 "나가는 링크"는 nav 외 **콘텐츠 링크**만.

## 메인 페이지 7개

### 홈 `/` (index.html) — 대시보드 허브
- **첫 화면**: ① 상단 통합 검색바 ② status 카드 3개(대통령·국회·지방정부 현황) ③ 활성
  선거 대시보드(9회 지선+재보궐: 광역단체장 17셀 hex·기초단체장 시군구 hex·재보궐 목록)
  ④ 역대 결과 archive 그리드.
- **URL 파라미터**: 없음.
- **나가는 링크**:
  - status 카드 → `history.html?type=presidential` · `?type=national_assembly` · `?type=local`
  - 대시보드 패널 → `/governor/` · `/mayor/` · `/archive/9th-local-2026/`
  - 역대 그리드 → `/archive/{election-id}/` (회차별)
  - 검색바 → `search.html?q=…`
- **들어오는 링크**: nav '홈', 로고.

### 여론조사 `/polls.html`
- **첫 화면**: 선거구별 여론조사 카드 — 후보 지지 막대·시계열 산점도·조사기관/기간/표본.
  `/governor/` `/mayor/` `/superintendent/` `/party/` 의 **템플릿**이기도 함(build_static).
- **URL 파라미터**: 없음(직위 페이지는 경로로 구분).
- **나가는 링크**: `/governor/`, `/archive/9th-local-2026/` 등.

### 재·보궐 `/byelection.html`
- **첫 화면**: 2026 국회의원 재·보궐 선거구별 지도(Leaflet)+여론조사 카드.
- **나가는 링크**: `/byelection/`(선거구 상세 프리렌더).

### 지지율 추이 `/tracker.html`
- **첫 화면**: 선거 무관 연속 시계열 — ① 대통령 국정평가(5소스 통합) ② 정당지지(VT012)
  ③ 차기주자 선호. 커널 평활선+밴드+원자료 점, **house effect 보정 토글**·기관별 lean 표.
- **데이터·파이프라인**: [[tracker-pipeline]] (`docs/tracker-pipeline.md`).

### 역대 결과 `/history.html` — 카토그램 뷰어
- **첫 화면**: 1987년 이후 대선·총선·지선 결과를 hex 카토그램으로. 기본 = 대통령선거 최신
  회차, 시군구 단위 **격자 hex**. 좌측 셋업(seg) 토글:
  - `type`: 대통령선거 / 국회의원선거 / 지방선거
  - `n`(회차), `office`(지선 직위: 광역·기초·교육감)
  - `sizing`: 격자 hex(기본·득표 비례) / Dorling 원(파이) — `docs/hex-layout.md`, 시도 17셀
  - `display`: Hex / 지도(Leaflet)
  - 셀 클릭 → 우측 detail pane(그 지역 결과).
- **URL 파라미터**: `type`·`n`·`office`·`sizing` (`assets/history/core.js`가 파싱·URL 동기화).
- **들어오는 링크**: 홈 status 카드(`?type=…`), 검색 결과, 타임라인.
- **프리렌더**: `/history/presidential/{n}/` 등(SEO용 정적 — 같은 화면).

### 타임라인 `/timeline.html`
- **첫 화면**: 역대 선거 연표 — 회차별 득표율 흐름.
- **나가는 링크**: 각 회차 → history/archive.

### 검색 `/search.html`
- **첫 화면**: 당선인·지역·정당 통합 검색.
- **URL 파라미터**: `q`(`assets/search.js`).
- **들어오는 링크**: 홈·전 페이지 검색바, nav '검색'.

## 정적 서브페이지 (build가 프리렌더)

| 경로 | 생성 | 템플릿/내용 |
|---|---|---|
| `/governor/` `/mayor/` `/superintendent/` `/party/` | `build_static.py` | polls.html 템플릿 — 9회 지선 직위별 |
| `/history/presidential/{n}/`·`/national-assembly/{n}/`·`/local/{n}/{office}/` | `build_static.py` | history.html 프리렌더(SEO) |
| `/archive/{election-id}/` | `sync_archive_html.py` | 회차별 아카이브 랜딩(역대 그리드 타깃) |
| `/byelection/` | byelection 빌드 | 재보궐 선거구 상세 |

## 연결 다이어그램

```
                         ┌─────────────── 헤더 nav (전 페이지 공통 7링크) ───────────────┐
                         ↓        ↓         ↓          ↓          ↓         ↓        ↓
        ┌────────────[ 홈 / ]  여론조사  재·보궐  지지율추이  역대결과  타임라인  검색
        │  (대시보드 허브)  polls    byelection  tracker    history   timeline  search
        │     │  │  │                                          ↑                   ↑
        │     │  │  └── status 카드 ──→ history.html?type=… ────┘                   │
        │     │  └───── 검색바 ──────────────────────────────────────→ search?q=… ──┘
        │     └──────── 대시보드 패널 ──→ /governor/ /mayor/ /archive/9th-local-2026/
        └────────────── 역대 그리드 ───→ /archive/{election-id}/

  프리렌더(정적·SEO): /governor·/mayor·/superintendent·/party (←polls 템플릿)
                     /history/{type}/{n}/ (←history 템플릿)  /archive/{id}/  /byelection/
```

- **홈이 허브**: status 카드→역대결과, 패널→직위 페이지, 그리드→아카이브, 검색바→검색.
- **나머지 6개는 nav로 상호 평면 연결** + 콘텐츠별 deep-link(history `?type/n/office/sizing`, search `?q`).

## 관련 문서

- `docs/architecture.md` — 운영 모델·디렉터리.
- `docs/tracker-pipeline.md` — 지지율 추이 데이터.
- `docs/hex-layout.md` — 카토그램 hex 규칙.
- `docs/cycle-workflow.md` — 선거 사이클 active/archive 전환.
