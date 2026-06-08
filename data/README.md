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
| **NESDC (nesdc.go.kr)** | 9회 지선 여론조사 (메인) | 공시 PDF/HTML | `scripts/fetch/scrape_nesdc.py` |
| **위키백과 + 수동 patch** | PDF·기타 누락 보정 | manual | `data/raw/parsed/` |
| **위키백과 ‘제N회 전국동시지방선거 X의회’** | 5~8회 기초의회 정당별 의석 | HTML scrape | `scripts/fetch/fetch_8th_council_seats.py` → `data/raw/{5,6,7,8}th_council_party_seats.json` |
| **open.assembly.go.kr 국회정보 일괄 다운로드** | 13~22대 국회의원 unique ID(한자명·생년월일·정당이력) | xlsx 묶음 (수동 다운로드) | `data/raw/assembly/`. parse → `data/raw/assembly_member_map.json` (4,587명·9,486 careers) |
| **data.nec.go.kr LOD (SPARQL)** | 14·15·16대 총선 **선거구별 후보·득표**(OpenAPI·다운로드가 못 미치는 옛 총선) | SPARQL RDF/XML | `scripts/fetch/fetch_lod_assembly.py` → `results/{14,15,16}th-general-*.json` district race. 아래 전용 섹션 |

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

## data.nec.go.kr LOD (SPARQL) — 옛 총선 백필

NEC 국가선거정보 개방포털의 **Linked Open Data**. OpenAPI(당선인·투개표)는 17대(지역구)·
16대(전국구)에서, info.nec 일괄다운로드·data.go.kr 파일셋은 19대에서 끊기지만, **LOD는
14대까지** 선거구별 후보·득표를 보유. 13대 이전은 LOD에도 후보 데이터 없음(선거 메타뿐).

- **SPARQL 엔드포인트**: `http://data.nec.go.kr/sparql/` — 온톨로지 `http://data.nec.go.kr/ontology/`.
- **접근 제약**: ① **국내 IP 전용**(해외/CI에선 TCP 차단) ② **세션 쿠키 필요**(브라우저에서
  `SESSION_DATA_1` 복사) ③ `format` 파라미터 무시하고 **항상 SPARQL RDF/XML 결과셋** 반환
  ④ **결과 100행 캡** → `LIMIT 100 OFFSET` 페이징 필수.
  → CI 자동화 불가, **일회성 수기 백필**용. (자동 파이프라인은 OpenAPI/NESDC.)
- **온톨로지 핵심**: `Election` —`hasCandidate`→ `Candidate`(`name`·`pollingScoreCount`=득표·
  `electionSymbol`=기호·`positionPoliticalParty`→`PoliticalParty.name`·`hasElectionDistrict`→
  `ElectionDistrict`). `ElectionDistrict`: `name`·`numberOfElection`=의원정수·`electorCount`·
  `validityVoteCount`·`cityAndProvinces`→시도. 선거 URI = `Elec_2{YYYYMMDD}`(2=국회의원).
- **당선 도출**: 당선 플래그 없음 → 선거구 내 최다 득표(소선거구 정수=1). 전국구(비례)는 별도
  투표가 아니라 배분이라 LOD 지역구엔 없음 → 기존 nation total − 지역구 으로 `proportional_seats` 도출.
- **회수**: `NEC_LOD_COOKIE='...' python scripts/fetch/fetch_lod_assembly.py` (curl 경유 — urllib은 500).
- **정당명 시대차**: LOD 지역구명 ≠ 기존 nation total명일 때 합산 분리됨(예: 15대 통합민주당↔민주당)
  → 스크립트 `PARTY_ALIAS`로 정규화.

## 수집 스크립트 (`scripts/`)

| 스크립트 | 입력 | 출력 | 비고 |
|---|---|---|---|
| `poll_terms.py` | — | — | 공유 어휘·분류기(정당명·`PARTY_CANON` 약칭맵·헤더어·`detect_office`·`is_metric_title`·`_is_noise_name`). 모든 파서가 import |
| `audit_parse.py` | `raw/grids`·`raw/parsed`·메타 CSV | funnel 요약 / `--json` 리포트 | **파싱 품질 하네스**. 이미지/파싱실패/누출/정상 4분류 + `--baseline` diff. 파서 변경 전후 측정 기준 |
| `parse_pdf_v2.py` | grids 캐시 | questions | 격자 기반 파서(classify/extract). 기본 lines + 실패 시 tuned(text) 재추출 자가치유 |
| `ocr_hybrid.py` + `run_ocr_batch.py` | CID폰트 PDF | `parsed/` | 텍스트층이 `(cid:..)`로 깨진 PDF(여론조사꽃 등): **숫자는 pdfplumber 좌표(소수점 보존), 후보명은 PaddleOCR**, x좌표 정렬. 느림(페이지당 ~17s) |
| `parse_words.py` | 표선 없는 텍스트 PDF | `parsed/` | `extract_tables`=0이지만 텍스트 정상인 PDF: `extract_words` 좌표로 후보·정당·% 정렬. **OCR 불필요·빠름** |
| `redownload_orphans.py` | 메타 `pdf_files` 토큰 | `raw/pdf/` | 결과 PDF 미수집(orphan) 재다운로드. NESDC 부하 줄이려 딜레이 |
| `parse_district_nec.py` | `raw/nec_district/*.xlsx` | `parsed/`, `results/national_assembly_*.json` | 19~22대 총선 xlsx parser |
| `parse_local_xlsx.py` | `raw/results_csv/local_*.csv` | `results/local_*.json` | 5~8 지선 (3 office) |
| `ingest_wwolf.py` | `raw/wwolf/*.tsv` | `results/*.json` patch | WWolf TSV 통합 |
| `backfill_uncontested.py` | 무투표선거구 API → `raw/nec_uncontested/{n}.json` 캐시 | `results/*.json`·`geo/district_{n}_centroid.json` 병합 | 무투표 당선구(개표 소스 누락분) 자동 추가. 캐시 있으면 키 불필요 |
| `scrape_nesdc.py` | NESDC 공시 | `raw/parsed/`, `polls/` | 9회 polls |
| `build_polls.py` | `raw/parsed/`, `raw/nec_candidate_party.json` | `polls/aggregated.json` | polls 집계 + 빈 정당 보완(조사 간 다수결 → NEC 캐시 순) |
| `backfill_candidate_party.py` | 후보자 통합검색 API → `raw/nec_candidate_party.json` 캐시 | (캐시만; `build_polls`가 사용) | 어느 조사에도 정당이 안 적힌 후보(회색 셀)의 공식 정당을 이름 기반 조회. **현존 정당만 신뢰**(폐지 정당=동명이인/옛 이력→버림). 캐시 있으면 키 불필요 |

## 인물·검색 인덱스 (`assets/`)

UI fetch용 인물·검색 통합 인덱스. results/*.json → 후가공.

| 파일 | 생성 | 비고 |
|---|---|---|
| `assets/search-index.json` | `scripts/build/build_search_index.py` | 모든 회차 당선인 5,011건. `/search.html`에서 fetch (~700KB) |
| `assets/person-index.json` | `scripts/build/build_person_index.py` → `enrich_person_index.py` | 이름 기준 cluster 10,152명. assembly_id 매칭 시 동명이인 split. `/person.html?name=` dynamic fetch (~3.8MB) |
| `person/{name}-{dob}/index.html` × 807 | `scripts/build/build_person_pages.py` | 의원(assembly 매칭) 한정 정적 prerender. inline JSON으로 fetch 없이 즉시 렌더 |

### 인물 인덱스 빌드 파이프라인

```
data/raw/assembly/*.xlsx                 # 국회 일괄 다운로드 (수동)
    ↓ parse_assembly_members.py
data/raw/assembly_member_map.json        # 한자명·생년월일 기반 unique ID
    ↓ build_person_index.py
assets/person-index.json (초안)          # results/*.json의 모든 candidate → 이름 cluster
    ↓ enrich_person_index.py
assets/person-index.json (assembly_id 부착)  # 의원 매칭 + 동명이인 split
    ↓ build_person_pages.py
person/{slug}/index.html × 807           # SEO 정적 페이지
    ↓ build_sitemap.py
sitemap.xml (person URL 통합)
```

비의원 후보(시·군·구의원·낙선자 9,345명)는 정적 페이지 없음 — `/person.html?name=` dynamic fallback 사용.

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
    │   scripts/_legacy/extract_grids.py — pdfplumber.extract_tables
data/raw/grids/*.json             # 격자 캐시 (cells matrix + page_text)
    ↓ Step B+C: 격자 → questions (분류 + 후보·정당·pct 추출)   [가벼움: <1s/PDF]
    │   parse_pdf_v2.parse_from_grids
    │   (격자가 비거나 빈약하면 v1 word-based parser로 fallback)
data/raw/parsed/*.json            # questions list
    ↓ Step D: parsed + meta → polls (normalize·merge·dedup)
    │   scripts/build/build_polls.py
data/polls/aggregated.json        # UI fetch
```

룰 한 줄 바꿔도 1867 PDF reparse가 1~2분에 끝남 — `parse_from_grids`만 다시 돌리면 됨.
새 PDF 추가 시 `--skip-existing`으로 그것만 Step A.

### PDF 양식별 파싱 경로 (parsed/ 단일 namespace)

`parsed/{stem}.json`은 PDF 양식에 따라 **다른 파서가 채운다**:
- **격자 있음** (대부분) → `parse_pdf` (Step A/B/C, 위).
- **CID 폰트 깨짐** (여론조사꽃 등, 텍스트가 `(cid:..)` 또는 한글이 잘못 매핑) →
  먼저 `scripts/parse/cid_decode.py`(`repair_text`)로 NotoSansCJK cmap 기반 복구 시도. 격자 자체는
  정상이고 한글만 깨진 케이스(여론조사꽃 result PDF)는 OCR 없이 복구됨. 글리프 자체가
  이미지인 경우만 `run_ocr_batch`(ocr_hybrid) fallback.
- **표 선 없는 텍스트** (`extract_tables`=0이나 텍스트 정상) → `parse_words`.

세 파서가 같은 파일을 쓰므로 **덮어쓰기 가드**가 있다: `parse_pdf`가 후보 0을 뽑았는데
기존 parsed에 후보가 있으면(=OCR/words 결과) 덮지 않는다. 그래서 `parse_pdf 'data/raw/pdf/*.pdf'`
전체 재실행해도 OCR/words 회복분이 안 날아간다. (단 OCR/words 룰을 바꾸면 그 배치를 다시 돌려야 반영됨.)

### gotcha (디버깅하다 발견)

- **`RESULT_KEYWORDS`에 "집계" 필수** — 빠지면 `집계표`(가장 흔한 결과 PDF명)를 스킵해 등록이 orphan이 됨.
- **정당 약칭 "국힘"** — 헤더가 `국힘이근수`처럼 약칭+이름. `PARTY_NAMES`에 "국힘" 두고 `PARTY_CANON`으로 국민의힘 정규화해 후보명(이근수) 복구. 약칭을 노이즈로 드롭하면 그 후보 결과가 통째로 사라지니 주의.
- **직무평가 leak** — 리얼미터 "제2장.조사결과"는 한 페이지에 후보지지+직무평가가 섞여 "잘못함" 응답이 후보로 새던 것 → `_is_noise_name`에서 평가응답(잘함/잘못함/매우/대체로) 차단.
- **시군구별 등록** — 한 조사를 시군구마다 따로 등록(도지사 결과에 sigungu가 붙음). `build_polls`가 광역단체장·교육감 + sigungu면 부분표본으로 보고 drop.

## 빌드 순서

```bash
# 0. (폴) Step A — PDF → 격자 캐시. 처음 한 번만 (또는 새 PDF 추가 시 --skip-existing)
.venv/bin/python scripts/_legacy/extract_grids.py 'data/raw/pdf/*.pdf' --jobs 8

# 0.5. (폴) Step B+C — 격자 → parsed JSON. 룰 변경 시 마다 다시
.venv/bin/python scripts/parse/parse_pdf.py 'data/raw/pdf/*.pdf' --jobs 8

# 1. 결과 데이터 (수집 → 정제 → results/)
# (raw 다운로드는 수동)
.venv/bin/python scripts/parse/parse_local_xlsx.py
.venv/bin/python scripts/parse/parse_district_nec.py
.venv/bin/python scripts/build/ingest_wwolf.py

# 1.2. (폴) 후보 정당 백필 — 조사에 정당 안 적힌 후보의 공식 정당을 캐시.
#       build_polls 전에 한 번. 키 있을 때만 갱신, 캐시는 커밋됨(키 없이 재현).
NEC_API_KEY=... .venv/bin/python scripts/build/backfill_candidate_party.py   # 신규 후보 있을 때만
.venv/bin/python scripts/build/build_polls.py                               # 캐시로 빈 정당 보완

# 1.5. 무투표 당선구 백필 (개표 소스에 없는 단독출마 당선구)
.venv/bin/python scripts/build/backfill_uncontested.py 17,18,19,20,21,22

# 2. hex layout (geo/)
.venv/bin/python scripts/_legacy/build_sigungu_hex.py
for n in 19 20 21 22; do .venv/bin/python scripts/_legacy/build_district_hex_v2.py $n; done

# 3. 정적 HTML + sitemap (prerender)
.venv/bin/python scripts/build/build_static.py

# 4. fetch 데이터 최적화 (반드시 마지막 — 빌드는 indent=2로 쓰므로)
#    sigungu 분리·좌표 6자리 절삭·minify. fetch 무게 ~44%↓
.venv/bin/python scripts/build/optimize_data.py
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
