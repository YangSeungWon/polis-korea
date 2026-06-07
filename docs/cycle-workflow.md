# 새 선거 사이클 워크플로

선거 사이클당 1회 ~30분 작업. 메타 파일 작성·active 등록·운영 전환.

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
