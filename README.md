# polis-korea

[polis.ysw.kr](https://polis.ysw.kr)

- 9회 지선·재보궐 여론조사 + 역대 대선·총선·지선 개표 결과
- 시각화 단위는 선거별로: 총선=지역구 / 지선=시군구 / 대선=시군구+인구비례
- 앞으로 있을 선거들 계속 추가
- 정적 사이트 (HTML/CSS/JS) + Python 파이프라인

## 페이지

| 페이지 | 첫 화면 |
|---|---|
| **홈** (`/`) | 대시보드 허브 — status 카드(대통령·국회·지방정부) + 활성 9회 지선·재보궐 hex + 역대 그리드 + 검색바 |
| **여론조사** (`/polls.html`) | 선거구별 여론조사 카드 — 시계열·산점도·후보 표 (`/governor` 등 직위 페이지 템플릿) |
| **재·보궐** (`/byelection.html`) | 2026 국회의원 재·보궐 — 선거구별 지도·카드 |
| **지지율 추이** (`/tracker.html`) | 국정평가·정당지지·차기주자 연속 시계열 + house effect 토글 |
| **역대 결과** (`/history.html`) | 1987~ 대선·총선·지선 카토그램 (격자/Dorling·hex/지도 토글) |
| **타임라인** (`/timeline.html`) | 역대 선거 연표 — 회차별 득표율 흐름 |
| **검색** (`/search.html`) | 당선인·지역·정당 통합 검색 |

페이지별 첫 화면·연결·URL 파라미터는 [docs/page-map.md](docs/page-map.md) 참고.

## 시각화 컨셉

**모든 시군구는 같은 크기 한 칸**.  
인구가 많고 적음, 면적이 넓고 좁음에 휘둘리지 않는다. 서울 강남구 한 칸, 강원 양양군 한 칸 — 같은 정치적 단위로 본다. 250개 시군구를 육각형 격자에 snap하고 시도 클러스터 연결성을 보장한다 (`build_sigungu_hex.py`).

- **시군구 카토그램** — 9회 지선 + 역대 결과
- **지역구 카토그램** — 총선 회차별 지역구(약 254개)를 시군구 위에 매핑
- **17셀 시도 격자** — 광역단체장·정당 단위 요약
- **비례대표 픽토그램** — 정당별 한 줄, 의석 1석 = 한 칸

## 데이터 출처

모든 출처는 **[`data/sources.json`](data/sources.json)** 단일 레지스트리에 등록, 각 페이지 하단 출처 패널에도 표시.

- **여론조사**: NESDC(중앙선거여론조사심의위원회) 등록·공표 조사 — [www.nesdc.go.kr](https://www.nesdc.go.kr/)
- **개표 결과·당선인**: 중앙선거관리위원회 — [data.go.kr](https://www.data.go.kr/) OpenAPI · 파일데이터
- **2026 등록 후보**: NEC CndaSrchService API (선관위 후보자검색)

원본(raw)은 저장소에 포함하지 않으며(`data/raw/` gitignore), 가공 결과만 공개한다.

## 법적 사항 — 여론조사 인용

공직선거법에 따라 인용 시 반드시 표시:

1. **의뢰자**
2. **조사기관**
3. **조사기간**
4. **NESDC 원문 링크** (각 카드의 *원문 보기*)

표본수·응답률·접촉률·표본오차도 카드에 함께 표시.  
**공표금지기간(선거 6일 전~선거일 18시)** 에는 신규 조사 노출을 자동 차단.

## 로컬 실행

```bash
# 정적 사이트만 보기
python3 -m http.server 8766    # http://localhost:8766

# 데이터 파이프라인 재실행
python3 -m venv .venv && .venv/bin/pip install pdfplumber pymupdf scipy numpy requests
.venv/bin/python scripts/fetch/scrape_nesdc.py              # NESDC 등록현황 → CSV
.venv/bin/python scripts/fetch/refresh_pending_pdfs.py      # 결과 PDF 후속 첨부 회복
.venv/bin/python scripts/parse/parse_pdf.py "data/raw/pdf/*.pdf" --jobs 4
.venv/bin/python scripts/parse/parse_kr_stats.py            # 통계표 stacked-header 보강
.venv/bin/python scripts/parse/patch_cross_tab.py           # 자체조사 cross-tab 정정
.venv/bin/python scripts/build/patch_byelection.py          # 재보궐 PDF 후보 추출
.venv/bin/python scripts/build/build_polls.py               # → data/polls/aggregated.json
.venv/bin/python scripts/build/build_byelection.py          # → data/polls/byelection.json
.venv/bin/python scripts/build/build_static.py              # → polls.json·history.json·sitemap
.venv/bin/python scripts/build/optimize_data.py             # 정적 자산 압축
```

전체 데이터 흐름·수집 스크립트·빌드 순서: **[`data/README.md`](data/README.md)**.

## 디렉터리

```
.
├── *.html              # 정적 페이지
├── assets/             # 공통 CSS·JS
├── data/
│   ├── polls/          # aggregated·byelection·history 공개 JSON
│   ├── geo/            # 시군구·지역구 hex 좌표
│   ├── sources.json    # 데이터 출처 레지스트리
│   └── raw/            # gitignore (원본 PDF·CSV)
├── scripts/            # 파이프라인 Python
└── tests/              # 골든 baseline (parse 룰 회귀 검출)
```

## 라이선스

- **코드**: MIT
- **데이터**: 각 출처 라이선스(대부분 공공누리·공공데이터). 여론조사 인용은 위 표시 의무 전제.
