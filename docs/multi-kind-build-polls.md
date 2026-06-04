# build_polls.py 회차 종류 일반화 (대선·총선 지원)

`scripts/build/build_polls.py`가 현재 **지선 전용** 로직으로 짜여 있어, 21대 대선 폴 build 시 후보지지 race가 거의 모두 reject됨 (499건 메타 → emit 17건, 전부 정당지지). 대선·총선용 build path를 추가하기 위한 설계 문서.

## 현재 상태

- **9회 지선** (`data/raw/nesdc_9th_polls.csv` 1886건 → `aggregated.json` 1703건): 정상 동작.
- **8회 지선** (`nesdc_8th_polls.csv` 1886건 → `aggregated_8th.json` 846건): 정상 동작.
- **21대 대선** (`nesdc_21pres_polls.csv` 499건 → `aggregated_21pres.json` **17건**): 거의 다 reject.

PDF·CSV는 다 확보됨 (`data/raw/pdf/`에 4400+ PDF, `data/raw/parsed/`에 5500+ JSON). 마지막 build 단계만 막힘.

## 원인 — 지선 가드가 대선을 reject

`scripts/build/build_polls.py:417-419`:

```python
# 대선 회상 투표 reject — "21대 대선 투표 후보" 같은 회상 질문이 기초단체장으로
# 잘못 승격되는 걸 막음 (9회 지선 폴에 섞임)
if re.search(r"(대선|대통령)\s*(투표|선거|후보)|\d+대\s*대선|회상\s*투표", title):
    continue
```

지선용 build에선 필요한 가드. 대선용 build에선 정작 핵심 race를 제거.

또 `classify_office` (line 119)도 광역단체장/기초단체장/교육감/광역의원/기초의원/비례/기타만 출력. **'대통령'·'국회의원'·'비례대표 국회의원' 분기 없음**.

## 구현됨 (2026-06-04) — 옵션 B (대선 전용 스크립트)

대선은 지선 build의 ~700줄 후처리(광역/기초/교육감 office 분류·단일정당 경선·column-bleed
등)와 구조가 근본적으로 달라(race 1개=대통령, scope=전국/시도, 후보군 시간변동) `--kind`
분기로 끼우기보다 **`scripts/build/build_polls_pres.py` 별도 스크립트**로 구현. 지선 build의 순수
helper(`parse_survey_period`·`to_float`·`is_self_poll`·`canon_sido`·`SIDO_CANONICAL`)만 import해
재사용. 총선 build(`build_polls_gen.py`)도 같은 skeleton에서 roster/accept 규칙만 교체 예정.

핵심 로직:
- **ROSTER anchor**: 본선 5인(이재명·김문수·이준석·권영국·송진호) + 경선·단일화 국면 주요
  주자(한덕수·홍준표·한동훈·안철수·오세훈·이낙연·김동연·김경수·김부겸 등) name→party map.
  parsed에 정당 비면 roster로 backfill (no-party 0건 달성).
- **horse-race accept**: roster 후보 3~6인 + 이재명 포함 + 합 [40,110]. 적합도·양자·단일화·
  가상대결·비호감·역선택·성향·정책 류 title은 `REJECT_TITLE`로 제거. ballot 7인+는
  "차기주자 선호도" 매트릭스라 제외(`MAX_BALLOT=6`).
- **단일정당 drop**: 후보 전원 한 정당이면 당내 경선("더불어민주당 차기 후보"·"범진보 선호도")
  → distinct party <2 면 drop.
- **campaign window**: 윤 탄핵 점화일 `2024-12-03`(CAMPAIGN_START) 이전 정례 사운딩 제외
  (NESDC가 같은 gubun으로 등록한 22대 총선기·2022 조사 오염 차단).
- **정당지지**: 민주+국힘 동시 등장 + 경선/단일화 title 제외.
- **후처리**: record 내 dedup → pct-일치 split표만 merge → (ntt,metric,sido) 카드 1개
  (후보지지는 '다자' title·합 100근접·표본 우선) → 최종 sanity(ballot 3~6·합 40~110·정당 2+).

결과: 메타 499 → emit **364건** (후보지지 107 national+시도 / 정당지지 257). 검증 통과:
suspect_names 0, zero_cand 0, weird_pct 0%, no-party 0. 월별 트렌드 실제 선거 서사와 일치
(이재명 40~47 선두, 김문수 5월 급등, 한덕수 4~5월 단일화 국면만 등장). 출력
`data/polls/aggregated_21pres.json`. 실행: `python3 scripts/build/build_polls_pres.py`.

## 총선 build (2026-06-04) — `scripts/build/build_polls_gen.py`

대선 골격 재사용. 총선은 race 단위가 **선거구(254)**라 고정 roster 불가 → NEC 선거구별 명부
(`nec_roster_22gen.json`, `build_roster_gen.py` 생성)로 anchor. 3 metric:
- **후보지지(지역구)** → `국회의원`: region을 선거구 key로 정규화(중복토큰·압축갑을·오타 보정)
  후 그 선거구 roster에 있는 후보명만 채택(≥2). 여론조사꽃류 깨진 race는 roster 미매칭으로
  자연 탈락.
- **비례대표** → 전국 정당투표: `proportional_parties` ∪ 모정당명(민주/국힘) anchor,
  민주계+국힘계 둘 다 + ≥3 정당.
- **정당지지** → 일반 정당지지(민주+국힘).

결과(22대): 메타 1993 → emit **833** (정당지지 787·후보지지 39·비례 7, 지역구 31). zero/weird 0%.
출력 `data/polls/aggregated_22nd.json` (메타 archive.polls_path 일치). 샘플 검증 정확
(하남갑 추미애 51/이용 38, 화성을 공영운/이준석28 등).

> **한계 — parse 품질**: 후보지지/비례가 적은 건 build 로직이 아니라 parse 블로커. 22대
> PDF의 **여론조사꽃 391개(후보 race 파일의 52%)**가 괘선없는 cross-tab이라 pdfplumber가
> 인접 숫자컬럼을 병합("36.042.70.41")·후보명을 라벨에 묻어 추출 실패. cid는 이미 정상
> (parse_pdf_v2가 `(cid:N)` 복구). 해결하려면 **단어 x좌표 클러스터링 기반 cross-tab 추출기**가
> 필요(후속 과제). 갤럽·한국리서치류 0-클린(~13%)도 별개 레이아웃 문제. 현재는 클린 기관
> (리서치뷰·케이스탯·코리아정보·리얼미터 등)만 커버.

> 아래는 작업 전 설계 옵션 분석 — 기록용. 실제 채택은 옵션 B.

## 설계 옵션

### 옵션 A: `--kind {local,presidential,general}` 인자 + 분기 로직

build_polls.py에 회차 종류 인자 추가. 가드·classify_office가 종류별로 분기:

```python
ap.add_argument("--kind", choices=["local","presidential","general"], default="local")
```

- `kind="local"`: 현재 로직 (대선 회상 reject + 광역/기초/교육감 classify).
- `kind="presidential"`: 대선 회상 reject **안 함**. classify_office가 모두 "대통령" race로 인식 (시도별/전국별만 구분, 시군구 X).
- `kind="general"`: 총선 회상 reject 안 함. classify_office가 "국회의원" race로 인식 (선거구별, 비례 분리).

장점: 단일 스크립트, 진입점 단일.
단점: 분기가 늘어나 가독성 ↓. classify_office가 거대해짐.

### 옵션 B: 회차별 별도 스크립트 (`build_polls_pres.py`, `build_polls_gen.py`)

공통 helper(`_polls_common.py`)에 PDF 매칭·CSV 파싱·후보 정규화 같은 종류 독립 로직 추출. 각 build_*는 classify_office·가드·candidates 필터만 자기 종류용.

장점: 회차별 로직 명확 분리, 변경 영향 격리.
단점: helper 추출 작업이 큼. 공통 코드 중복 위험.

### 옵션 C: 메타 파일 기반 (`data/elections/{id}.json`)

`9th-local-2026.json` 메타가 이미 office_list·sido_merge 등 보유. `build_polls.py`가 메타의 type·office_list 보고 classify·가드 분기.

```python
ap.add_argument("--election-id", required=True)
# meta = load_election_meta(args.election_id)
# kind = meta["type"]   # presidential/local/general
# offices = meta["offices"]  # ["광역단체장", "기초단체장", ...] / ["대통령"] / ["국회의원","비례대표 국회의원"]
```

장점: 사이트 전체 메타 시스템(architecture.md)과 정합. 향후 회차 추가 시 메타만 작성.
단점: 메타 schema 보완 필요. 일부 회차 메타가 부분만 있음(대선·총선 메타 아직 적음).

## 추천 — 옵션 C (메타 우선) + 옵션 A 보강

1. 메타 파일 schema 확장: `type`, `offices` (이미 있는 곳도 있음).
2. `build_polls.py`에 `--election-id` 인자. 메타에서 `kind` 읽어 분기 로직 적용.
3. fallback: 메타 미존재 시 `--kind {local,presidential,general}` 인자.

## 작업 단계

### 1. 메타 확인 + 보강

```
data/elections/9th-local-2026.json     ← type:"local", offices: [...]
data/elections/21st-pres-2025.json     ← 신규 또는 보강
data/elections/22nd-general-2024.json  ← 신규 또는 보강
```

각 메타에 최소: `id`, `type`, `date`, `offices`, `nec.sg_id`, `nesdc.gubun`.

### 2. classify_office 분기

```python
def classify_office(title, sido, sigungu, kind, offices):
    if kind == "presidential":
        # 대통령 race만. office_label = "대통령". sigungu 무시.
        if re.search(r"(대선|대통령|후보지지)", title):
            return ("대통령", "대통령")
        return (None, None)  # 그 외 race reject (정당지지·국정평가 등은 metric으로)
    if kind == "general":
        # 국회의원 race: 지역구 선거구 분류 + 비례 분리
        if re.search(r"비례", title):
            return ("비례대표 국회의원", "비례")
        if re.search(r"(국회의원|총선|당선)", title):
            return ("국회의원", "지역구")
        return (None, None)
    # kind == "local": 현재 로직
    ...
```

### 3. 대선 회상 가드 conditional

```python
if kind == "local" and re.search(r"대선|대통령선거|회상", title):
    continue
# 대선·총선용 build에선 위 가드 안 건너뜀
```

### 4. 후보 정당 매핑

대선·총선은 NEC roster가 다름. `data/raw/nec_roster_{id}.json` 구조 통일 또는 회차별 분리.

예: `data/raw/nec_roster_21pres.json` 신규 생성 — 21대 대선 후보 5명 (이재명·김문수·이준석·권영국·송진호) party 매핑.

### 5. 출력 path 분리

`data/polls/aggregated_21pres.json`, `aggregated_22gen.json` 등 회차별. 9회 지선용 `aggregated.json`은 그대로 유지 (polls 페이지 운영).

## 핸드오버 후 다음 단계

1. **archive 페이지에 통합**: 21대 대선 archive 만들면서 `aggregated_21pres.json` 사용.
2. **출구조사 데이터**: `data/exit_polls/21st-pres-2025.json` 수기 입력 + 9회 archive와 동일 schema.
3. **NEC API polling 재검토**: 21대 대선 결과는 `data/results/21st-pres-2025.json` 이미 정상.

## 참고 위치

- `scripts/build/build_polls.py:417` — 대선 회상 reject 가드 (대선 build엔 빼야).
- `scripts/build/build_polls.py:119` — `classify_office` 함수 (대선·총선 분기 추가).
- `scripts/build/build_polls.py:267` — `metric_type` 결정 ("정당지지"·"국정평가"·"투표의향"·"적합도" 등).
- `data/elections/index.json` — active/archive 회차 list.
- `docs/architecture.md` — 메타 기반 운영 모델.

## 현재 데이터 상태 (작업 시작 시점)

- `data/raw/nesdc_21pres_polls.csv` 499건 (헤더 포함 500줄).
- `data/raw/pdf/`에 21대 대선 PDF 다 다운 (parse 완료 5500+ JSON 누적).
- 결과 데이터 `data/results/21st-pres-2025.json` 정상 (NEC OpenAPI fetch 완료).

## 검증 기준

각 회차 build 후:

```python
total = len(polls)
suspect_names = sum(1 for p in polls for c in p.get('candidates',[])
                    if any(c.get('name','').startswith(k) for k in ISSUE_KEYWORDS))
zero_cand = sum(1 for p in polls if not p.get('candidates'))
weird_pct = sum(1 for p in polls if p.get('candidates') and
                (sum(c.get('pct',0) for c in p['candidates']) < 50
                 or sum(...) > 105))
```

- `suspect_names == 0`
- `zero_cand == 0`
- `weird_pct / total < 5%`
- `office_level` 분포에 "대통령"(대선 build) 또는 "국회의원"·"비례대표 국회의원"(총선 build) 다수
