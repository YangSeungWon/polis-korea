# korea-election-hex

한국 선거 데이터를 **hex 카토그램**으로 시각화하는 정적 사이트 — **[vote.ysw.kr](https://vote.ysw.kr)**.

역대 대선·총선·지선 개표 결과와 2026년 9회 지방선거·재보궐선거 여론조사를, 면적 왜곡 없이 모든 시군구·선거구를 같은 크기 육각형으로 보여줍니다. 빌드 도구 없는 순수 HTML/CSS/JS + Python 데이터 파이프라인.

## 페이지

| 페이지 | 내용 |
|---|---|
| **index** (`/`) | 9회 지방선거(2026-06-03) 여론조사 — 시도/시군구 hex + 17셀 시도 격자 |
| **history** (`/history`) | 역대 선거 결과 — 대선 16~21대, 총선 17~22대(지역구 hex + 비례 픽토그램), 지선 5~8회 |
| **byelection** (`/byelection`) | 2026 국회의원 재·보궐선거 여론조사 — 선거구별 지도(Leaflet) + 카드 |

## 시각화

- **시군구 hex 카토그램** — 250개 시군구를 동일 크기 육각형으로. centroid를 격자에 snap + 시도 클러스터 연결성 보장 (`build_sigungu_hex.py`).
- **지역구 hex** — 총선 회차별 지역구(254개 등)를 시군구 hex 위에 매핑.
- **17셀 시도 격자** — 광역단체장·정당 단위 요약용.
- **비례대표 픽토그램** — 정당별 한 줄, 의석 1석 = 육각형 1개. 지역구+비례 합산 총 300석.

## 데이터 출처·라이선스

모든 출처는 **[`data/sources.json`](data/sources.json)** 단일 레지스트리에 등록, 각 페이지 하단 출처 패널에도 표시.

- **개표 결과·당선인**: 중앙선거관리위원회 (data.go.kr 파일데이터·OpenAPI). 공개 사실 + 공공데이터.
- **여론조사**: NESDC(중앙선거여론조사심의위원회) 등록·공표 조사. **공직선거법에 따라 의뢰자·기관·조사기간·표본수·응답률·표본오차·NESDC 출처를 표시**하고, 공표금지기간(선거 6일 전~선거일 18시)에는 신규 조사 표시를 차단합니다.
- 원본 데이터(raw)는 저장소에 포함하지 않으며(`data/raw/` gitignore), 가공 결과(공개 사실)만 공개합니다.

자세한 데이터 흐름·수집 스크립트·빌드 순서: **[`data/README.md`](data/README.md)**.

## 로컬 실행

```bash
python3 -m http.server 8766    # http://localhost:8766
```

데이터 재생성(선택):

```bash
python3 -m venv .venv && .venv/bin/pip install pdfplumber pymupdf scipy numpy
.venv/bin/python scripts/build_sigungu_hex.py
for n in 19 20 21 22; do .venv/bin/python scripts/build_district_hex_v2.py $n; done
```

전체 파이프라인은 `data/README.md`의 "빌드 순서" 참고.

## 라이선스

코드는 자유롭게 활용 가능. 데이터는 각 출처의 라이선스(대부분 공공데이터·공개 사실)를 따르며, 여론조사 인용은 위 표시 의무를 전제로 합니다.
