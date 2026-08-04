# 새 선거 사이클 워크플로

선거 사이클당 1회 ~30분 작업. 메타 파일 작성·active 등록·운영 전환.

## 선거 생애주기 — 어느 단계에 무엇이 도는가

| 단계 | 기간 | 데이터 소스 | 자동화 |
|---|---|---|---|
| 0 사전·캡처 | D-180 ~ archive | NESDC 여론조사 · NEC 선거공약 | `daily-refresh.yml` · **`pledge-capture.yml`** |
| 1 개표 | D-day ~ D+7 | info.nec.go.kr 라이브(잠정) | `election-results-poll.yml` |
| 2 확정 대기 | D+7 ~ OpenAPI 게시 | NEC OpenAPI probe | **`election-finalize.yml`** (매일) |
| 3 역사 편입 | 확정 후 | 고정 | 없음 — 자동 잡 금지 |

2단계가 없던 시절 9회 지선 잠정 파일이 두 달 방치됐고, 그 틈에 daily-refresh의 부분
갱신이 기초의원 낙선자 1,737명과 집계값 1,038건을 삭제했다(2026-07-31). 그래서 규칙:

- **확정(`is_final: true`) 회차는 어떤 자동 잡도 건드리지 않는다.**
- **부분 덮어쓰기 금지** — 전면 재fetch만 허용하고, 실패·급감 시 롤백한다.
- 결과 파일을 통째로 교체하는 스크립트는 상시 루프에 넣지 않는다(승격 시 1회만).

```bash
# 2단계 수동 실행 — 게시 전이면 no-op, 게시됐으면 승격까지
python3 scripts/build/finalize_election.py --auto --dry-run
python3 scripts/build/finalize_election.py --auto
```

### 0단계에 시한이 있다 — 낙선자 공약

NEC 선거공약 API의 **낙선자 공약은 시간이 지나면 사라진다.** 문서는 "종료된 선거는
당선인 공약만"이라고 하지만 실제로는 한동안 남아 있다가 없어진다. 2026-08-04 실측:

| 회차 | 경과 | 낙선자 공약 |
|---|---|---|
| 9회 지선 (2026-06) | 2개월 | 살아 있음 |
| 21대 대선 (2025-06) | 14개월 | 없음 |
| 8회·7회 지선 (2022·2018) | — | 없음 |

소멸 시점은 2~14개월 사이고 **한 번 사라지면 복구 수단이 없다.** `pledge-capture.yml`이
active 회차를 매일 훑는 이유다. 새 선거를 active에 올리면 자동으로 캡처가 시작되고,
archive로 내리기 전에 반드시 한 번은 돌았는지 확인할 것.

```bash
python3 scripts/fetch/fetch_pledges.py --active --all-candidates   # 0단계 (전 후보)
python3 scripts/fetch/fetch_pledges.py --election <id>             # 3단계 (당선인 백필)
python3 scripts/build/build_person_pledges.py                      # 인물별 재색인
```

> 지방의원·비례(tc 5·6·8·9)가 있는 회차는 개표 API만으론 무투표·중선거구 당선·비례
> 의석이 빠진다. `finalize_election.py`의 `POST_STEPS`에 그 회차 보정 단계를 등록해야
> 승격이 진행된다 — 등록 전엔 일부러 실패시켜 조용한 결손을 막는다.

## D-180 — 메타 파일 작성

```bash
# 1. {id}.json 작성 — docs/election-meta.md 스키마 참고
cp data/elections/8th-local-2022.json data/elections/10th-local-2030.json
# id, name, date, sg_id, blackout 수정

# 2. 검증
python3 scripts/election_meta.py --id 10th-local-2030
```

체크리스트:
- [ ] `id`·`name`·`type`·`date`
- [ ] `blackout.start` = D-6 00:00 KST
- [ ] `blackout.end` = D-day 18:00 KST
- [ ] `nec.sg_id` = YYYYMMDD
- [ ] `offices` (지선 4~5종, 총선 1종, 대선 1종)
- [ ] `sido_merge` (행정구역 변경 시)
- [ ] `nesdc.gubun` (NESDC 등록 후)

## D-180 — index.json 등록

```json
{
  "active": ["10th-local-2030"],  ← 추가
  "archive": [...]
}
```

active로 추가하면 사이트가 자동으로 다음 선거 모드로 전환.

## D-180 ~ D-1 — 데이터 자동 수집

GitHub Actions cron(`daily-refresh.yml`)이 알아서:
- NESDC 신규 PDF scrape
- parse → patch → build → polls.json
- audit + golden 통과 시 commit·push

> 선거와 무관한 **상시 추이**(국정평가·정당지지·차기주자)는 별개 주간 파이프라인
> `tracker-refresh.yml`이 담당 — `docs/tracker-pipeline.md` 참고.

사람 손길:
- 자체조사 PDF의 새 후보 등장 → `{id}-candidates.json`에 추가
- 사용자 신고 outlier fix

## D-6 — 공표금지 자동 시작

`is_blackout(meta, now)` = True → 신규 PDF 차단·"공표금지" 배너 활성화. 메타의 `blackout` 정의로 자동.

## D-day 18시 — 출구조사·개표 모드

```bash
# 출구조사 결과 (방송 3사 통합)
# UI: 시도별 출구조사 vs 여론조사 비교

# 개표 시작 ~ 새벽:
python3 scripts/fetch/fetch_nec_results.py --election 10th-local-2030
# 30분~1시간마다 호출. cron 추가 가능 (개표 종료 후 비활성화).
```

체크리스트:
- [ ] 메타 `nec.sg_id` 정확
- [ ] `data/results/{id}.json` 생성 확인
- [ ] 잠정 → 확정 전환 (`_meta.is_final`)

## D+1 ~ D+7 — 비교 카드 출시

- 여론조사 vs 개표 비교 카드 생성
- history.html에 미리 archive 자리 준비된 경우 결과 즉시 표시

### ⚠️ 인물·정당 프로필 페이지는 수동 재빌드 (CI 미포함)

daily-refresh CI(`build_static.py`)는 polls·history·sitemap만 재생성한다.
**인물(`/person/`)·정당 프로필(`/party/`) 페이지와 `assets/person-index.json`은
재생성하지 않는다** — 당선이력을 HTML에 정적 임베드하므로, 새 개표 결과가 들어오면
당선자 페이지가 stale 상태로 남는다. 결과 확정 후 로컬에서 빌드·커밋:

```bash
python3 scripts/build/build_person_index.py    # results → assets/person-index.json
python3 scripts/build/enrich_person_index.py   # assembly_id·한자·비례 보강 (빠뜨리면 의원 링크 소실)
python3 scripts/build/build_person_pledges.py  # data/pledges → by-person/ + pledges-index.json
python3 scripts/build/build_person_pages.py    # → person/*/index.html (+ sitemap_person.txt)
python3 scripts/build/build_party_pages.py     # → party/*/index.html (+ sitemap_party.txt)
python3 scripts/build/build_sitemap.py         # sitemap.xml 통합 재생성
```

> `enrich_person_index.py`는 `build_person_index.py` 직후에 반드시 돌린다 — 건너뛰면
> assembly_id 2,617건이 사라지고 인물 id가 바뀌어 정적 페이지 링크가 깨진다.

### nav는 손대지 않아도 된다

nav 정본은 `sync_nav_html.py`(MENU + `menu_for_path`)이고, 페이지 생성기들이 생성
시점에 그 함수를 호출한다. 따라서 재빌드 후 `sync_nav_html.py`를 따로 돌릴 필요가 없다
— 안전망일 뿐이다. 메뉴를 바꿀 때는 `sync_nav_html.py`의 `MENU`만 고치고 생성기를 다시
돌린다.

CI(`checks.yml`)가 매 push마다 `sync_nav_html.py --check`로 검사해, 새 생성기가 nav
사본을 박으면 즉시 실패한다. 로컬에서도 같은 명령으로 확인할 수 있다.

```bash
python3 scripts/build/sync_nav_html.py --check   # 어긋나면 exit 1
```

> 4,000여 페이지를 매일 재생성하는 건 낭비라 CI에서 제외 — 데이터 변경 후 1회만 돌리면 된다.
> 빠뜨리면 조용히 stale 되니, 개표 확정 커밋과 함께 묶을 것.

## D+30 — archive 이동

```json
{
  "active": [],         ← 또는 다음 선거 메타
  "archive": [
    "10th-local-2030",  ← 추가 (시간 역순)
    ...
  ]
}
```

active에서 빠지면 사이트는 자동으로 "선거 사이" 또는 다음 active 모드.

## 분기 1회 — PDF Release 재업로드

```bash
# data/raw/pdf/grids/parsed/ 압축 → polis-korea Release "raw-bundle-v1"에 attach
# 워크플로 cache miss 시 Release zip restore로 base seed 복구
```

## 회차 작명

- 지선: 1991~2026 = 1~9회 (4년 주기)
- 총선: 1948~2024 = 1~22대 (4년 주기, 변동 있음)
- 대선: 1948~2025 = 1~21대 (5년 주기·중간선거 포함)
- 보궐: 직전 정기선거 회차 + "-byelection" (예: 9th-byelection-2026 = 9회 지선 동시 재보궐)

## 데이터 출처 등록

`data/sources.json` + 페이지 출처 패널 + `sitemap.xml`에 새 데이터 등록. 사용자 feedback 기억: `feedback_data_sources.md`.

## 톤·UX 원칙

- 시군구 부정 지표(사고율 등)로 콕 집지 말기 (`feedback_no_local_stigma.md`)
- 사실·수치 위주, AI 비유 피하기
- 인구 1만명당 환산으로 작은 시군구도 공평
