# 데이터 디렉터리 — 출처와 수집 흐름

vote.ysw.kr의 모든 데이터셋·원본·생성물 정리.

## 디렉터리 구조

```
data/
├── elections.json          # 회차 메타 (날짜·label·당선자) - 수동 관리
├── geo/                    # 지리·hex layout - 생성물 (scripts/build_*)
├── raw/                    # 원본 다운로드 (수집 스크립트 입력)
├── parsed/                 # 중간 산출물 (raw → 정제)
├── results/                # 최종 결과 JSON (UI fetch 대상)
└── polls/                  # 9회 지선 여론조사 (NESDC)
```

## results/ — 역대 선거 결과 (UI fetch)

`/history` 페이지가 fetch. 파일명 `{type}_{n}.json`:
- `presidential_{16..21}.json`
- `national_assembly_{17..22}.json`
- `local_{5..8}.json`

스키마는 `data/results/README.md`.

`manifest.json` — 회차 인덱스. prerender (build_static.py)가 이거 읽고 페이지 생성.

## polls/ — 9회 지선 여론조사 (메인 페이지 fetch)

`index.html` (메인) + `byelection.html`이 fetch. 출처는 NESDC.

- `aggregated.json` — 다자대결 1 문항 = 1 record. office_level 별 분류.
- `byelection.json` — 재·보궐 폴

자세한 흐름·스키마·법적 의무는 `data/polls/README.md`.

## 원본 데이터 출처

| 출처 | 활용 | 형식 | 비고 |
|---|---|---|---|
| **info.nec.go.kr / data.nec.go.kr 게시판** | 19~22대 총선 지역구 xlsx | xlsx (dataId=9) | `data/raw/nec_district/` |
| **data.go.kr (NEC 공공데이터)** | 5~8회 지선 개표결과 | xlsx (rename .csv) | `data/raw/results_csv/local_{5,6,7,8}.csv` |
| **github.com/WWolf/korea-election** | 17~21대 비례·후보별, 16·20대 대선 | TSV | `data/raw/wwolf/` |
| **vuski/admdongkor** | 시군구·시도 GeoJSON 경계 | GeoJSON | `data/geo/sigungu_simple.json` 등 |
| **github.com/vuski/...** (20대 대선) | 시군구 단위 대선 결과 | CSV | `data/raw/wwolf/vuski_20p.csv` |
| **NESDC (nesdc.go.kr)** | 9회 지선 여론조사 (메인) | 공시 PDF/HTML | `scripts/scrape_nesdc.py` |
| **위키백과 + 수동 patch** | PDF·기타 누락 보정 | manual | `data/raw/parsed/` |

## data.go.kr OpenAPI (NEC) — 활성

발급일 2026-05-26, 활용기간 ~2028-05-26. 일반 인증키 환경변수 `NEC_API_KEY`.

| 키 | 엔드포인트 | 용도 | 우선순위 |
|---|---|---|---|
| **당선인 정보** | `https://apis.data.go.kr/9760000/WinnerInfoInqireService2/getWinnerInfoInqire` | 모든 선거 당선자 (정당·이름·득표) — 17·18대 미수집 백필, 분할구 매핑 | ★★★ 핵심 |
| **무투표선거구 정보** | `https://apis.data.go.kr/9760000/WtvtelpcInfoInqireService/getWtvtelpcsccnInfoInqire` | 무투표 당선 시군구 (raw xlsx 누락분) | ★★★ 핵심 |
| **후보자 통합검색** | `https://apis.data.go.kr/9760000/CndaSrchService/getCndaSrchInqire` | 이름 기반 후보 명부(당락 무관) → 조사에 정당 안 적힌 후보의 공식 정당 백필 (`backfill_candidate_party.py`) | ★★ 보조 |
| 역대 대통령선거 실시상황 | `https://apis.data.go.kr/9760000/ScgnPresElctExctSttnService/getScgnPresElctExctSttnInqire` | 대선 시도/시군구 통계 | ★ 보조 (results JSON과 중복) |

호출 예 (8회 지선 기초단체장 무투표 당선자):
```
GET /WtvtelpcInfoInqireService/getWtvtelpcsccnInfoInqire
  ?serviceKey={KEY}
  &sgId=20220601           # 선거ID = 선거일 YYYYMMDD
  &sgTypecode=4            # 4=구시군의장(기초단체장), 3=시도지사, 1=대통령, 2=국회의원
  &pageNo=1&numOfRows=100
```

## 수집 스크립트 (`scripts/`)

| 스크립트 | 입력 | 출력 | 비고 |
|---|---|---|---|
| `poll_terms.py` | — | — | 공유 어휘·분류기(정당명·헤더어·`detect_office`·`is_metric_title`·`_is_noise_name`). v1·v2 둘 다 import (v2→v1 의존 제거용) |
| `audit_parse.py` | `raw/grids`·`raw/parsed`·메타 CSV | funnel 요약 / `--json` 리포트 | **파싱 품질 하네스**. 이미지/파싱실패/누출/정상 4분류 + `--baseline` diff. 파서 변경 전후 측정 기준 |
| `parse_district_nec.py` | `raw/nec_district/*.xlsx` | `parsed/`, `results/national_assembly_*.json` | 19~22대 총선 xlsx parser |
| `parse_local_xlsx.py` | `raw/results_csv/local_*.csv` | `results/local_*.json` | 5~8 지선 (3 office) |
| `ingest_wwolf.py` | `raw/wwolf/*.tsv` | `results/*.json` patch | WWolf TSV 통합 |
| `backfill_uncontested.py` | 무투표선거구 API → `raw/nec_uncontested/{n}.json` 캐시 | `results/*.json`·`geo/district_{n}_centroid.json` 병합 | 무투표 당선구(개표 소스 누락분) 자동 추가. 캐시 있으면 키 불필요 |
| `scrape_nesdc.py` | NESDC 공시 | `raw/parsed/`, `polls/` | 9회 polls |
| `build_polls.py` | `raw/parsed/`, `raw/nec_candidate_party.json` | `polls/aggregated.json` | polls 집계 + 빈 정당 보완(조사 간 다수결 → NEC 캐시 순) |
| `backfill_candidate_party.py` | 후보자 통합검색 API → `raw/nec_candidate_party.json` 캐시 | (캐시만; `build_polls`가 사용) | 어느 조사에도 정당이 안 적힌 후보(회색 셀)의 공식 정당을 이름 기반 조회. **현존 정당만 신뢰**(폐지 정당=동명이인/옛 이력→버림). 캐시 있으면 키 불필요 |

## 생성물 (`geo/`)

| 파일 | 생성 | 비고 |
|---|---|---|
| `sigungu_hex.json` | `build_sigungu_hex.py` | 250 시군구 17×17 직사각 hex |
| `district_hex_{19..22}.json` | `build_district_hex_v2.py` | 회차별 지역구 hex (sigungu_hex 기반) |
| `sigungu_adjacency.json`, `sigungu_coastal.json` | `build_sigungu_*` | 시군구 그래프 메타 |
| `*_simple.json` | `vuski/admdongkor` raw 다운로드 + `mapshaper` 단순화 | 폴 지도 |

## 폴 (여론조사) 파이프라인 — 단계 분리

NESDC PDF는 양식이 매우 다양해 parse 룰이 자주 바뀜. 단계별 중간결과물을 캐시해서
룰 변경 시 비용 큰 PDF 열기를 건너뛰도록 분리.

```
data/raw/pdf/*.pdf                # 원본 (불변)
    ↓ Step A: PDF → 표 격자                                   [무거움: 30s/PDF]
    │   scripts/extract_grids.py — pdfplumber.extract_tables
data/raw/grids/*.json             # 격자 캐시 (cells matrix + page_text)
    ↓ Step B+C: 격자 → questions (분류 + 후보·정당·pct 추출)   [가벼움: <1s/PDF]
    │   parse_pdf_v2.parse_from_grids
    │   (격자가 비거나 빈약하면 v1 word-based parser로 fallback)
data/raw/parsed/*.json            # questions list
    ↓ Step D: parsed + meta → polls (normalize·merge·dedup)
    │   scripts/build_polls.py
data/polls/aggregated.json        # UI fetch
```

룰 한 줄 바꿔도 1867 PDF reparse가 1~2분에 끝남 — `parse_from_grids`만 다시 돌리면 됨.
새 PDF 추가 시 `--skip-existing`으로 그것만 Step A.

## 빌드 순서

```bash
# 0. (폴) Step A — PDF → 격자 캐시. 처음 한 번만 (또는 새 PDF 추가 시 --skip-existing)
.venv/bin/python scripts/extract_grids.py 'data/raw/pdf/*.pdf' --jobs 8

# 0.5. (폴) Step B+C — 격자 → parsed JSON. 룰 변경 시 마다 다시
.venv/bin/python scripts/parse_pdf.py 'data/raw/pdf/*.pdf' --jobs 8

# 1. 결과 데이터 (수집 → 정제 → results/)
# (raw 다운로드는 수동)
.venv/bin/python scripts/parse_local_xlsx.py
.venv/bin/python scripts/parse_district_nec.py
.venv/bin/python scripts/ingest_wwolf.py

# 1.2. (폴) 후보 정당 백필 — 조사에 정당 안 적힌 후보의 공식 정당을 캐시.
#       build_polls 전에 한 번. 키 있을 때만 갱신, 캐시는 커밋됨(키 없이 재현).
NEC_API_KEY=... .venv/bin/python scripts/backfill_candidate_party.py   # 신규 후보 있을 때만
.venv/bin/python scripts/build_polls.py                               # 캐시로 빈 정당 보완

# 1.5. 무투표 당선구 백필 (개표 소스에 없는 단독출마 당선구)
.venv/bin/python scripts/backfill_uncontested.py 17,18,19,20,21,22

# 2. hex layout (geo/)
.venv/bin/python scripts/build_sigungu_hex.py
for n in 19 20 21 22; do .venv/bin/python scripts/build_district_hex_v2.py $n; done

# 3. 정적 HTML + sitemap (prerender)
.venv/bin/python scripts/build_static.py

# 4. fetch 데이터 최적화 (반드시 마지막 — 빌드는 indent=2로 쓰므로)
#    sigungu 분리·좌표 6자리 절삭·minify. fetch 무게 ~44%↓
.venv/bin/python scripts/optimize_data.py
```

> `optimize_data.py`는 **빌드 후 마지막에** 돌린다. 빌드 스크립트들이 가독성용 indent=2로
> 쓰기 때문에, 최적화는 그 뒤 minify/절삭하는 후처리 단계. 멱등이라 여러 번 돌려도 안전.
> 분리된 `national_assembly_*_sigungu.json`(비례 시군구 득표)은 보존되지만 페이지가 fetch하지 않음.

## 알려진 누락

- **17·18대 총선 지역구**: NEC 스크레이프 시도 후 포기. data.go.kr API로 백필 가능.
- ~~**20대 통영시고성군**~~: 무투표 당선(이군현·새누리당)이라 WWolf TSV에 없었음 → `backfill_uncontested.py`로 자동 해결.
- **5~8회 지선 무투표 당선 시군구** (예: 8회 광주 광산구·대구 달서·중구·군위, 경북 예천, 전남 보성·해남): NEC xlsx에 row 없음 → `backfill_uncontested.py`에 sgTypecode 추가하면 동일 처리 가능.
- **세종 5회**: 출범 전. 정상.
- **제주 기초단체장**: 폐지 (특별자치도). 정상.
