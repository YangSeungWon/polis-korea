# 지선 의석 데이터 — 출처와 정확성

지선 선출직별 **NEC 확정 당선인** 출처. 메인 status 카드·아카이브 scorecard·당선인 목록이
모두 같은 결과 데이터를 쓰므로 신뢰도도 직위별로 동일하다.

## 한눈에 (전 회차 — 확정 당선인 회수 완료)

| 직위 | tc | 출처 | 신뢰도 |
|---|---|---|---|
| 광역단체장 | 3 | NEC won (1선거구 1명) | ✅ 확정 (명부 16 일치) |
| 교육감 | 11 | NEC won (1시도 1명) | ✅ 확정 (명부 16 일치) |
| **기초단체장** | **4** | **NEC 확정 당선인 명부** | ✅ 확정 (명부 227 일치) |
| **광역의원 지역구** | **5** | **NEC 확정 당선인 명부** | ✅ 확정 (명부 804 일치) |
| **기초의원 지역구** | **6** | **NEC 확정 당선인 명부** | ✅ 확정 (명부 2,650 일치) |
| **기초의원 비례** | **9** | **NEC 확정 당선인 명부** | ✅ 확정 (명부 384 일치) |
| 광역의원 비례 | 8 | calc_proportional 추정 | ⚠️ 추정 (87, 명부 _#8 불명확) |

> 라이브 개표는 무투표 선거구·중선거구 정수를 빼먹어 단일직(tc4 224·tc5 686)도 누락이 있었으나,
> EPEI01 명부 오버레이(`fetch_single_winners_live.py`)로 무투표 보충 + 전남광주통합 시도의회
> 중선거구(남구제1선거구 3인 등)까지 확정. tc4 227·tc5 804로 명부 100% 일치.
>
> ⚠️ **광역의원 비례(tc8)만 미해결**: 명부 EPEI01_#8이 129로 알려진 시도의원 비례 정수(~89)보다
> 부풀려져 있어(서울 15·경기 21·제주 13 — 교육의원 등 혼입 추정) 신뢰 불가 → calc_proportional
> 추정(87) 유지. 정확화하려면 _#8에서 비-시도의원 당선인을 걸러내야 함(미완).

회차별 확정값:

| 회차 | 기초의원 지역구(tc6) | 기초의원 비례(tc9) | 당선인 소스 |
|---|---|---|---|
| 5회(2010) | 2,512 | 376 | OpenAPI 당선인 |
| 6회(2014) | 2,519 | 379 | OpenAPI 당선인 |
| 7회(2018) | 2,541 | 385 | OpenAPI 당선인 |
| 8회(2022) | 2,601 | 386 | OpenAPI 당선인 |
| 9회(2026) | 2,650 | 384 | **EPEI01 라이브 명부** |

모두 NEC 확정 당선인 수와 100% 일치한다(추정 아님).

## 왜 라이브 개표만으론 부족한가 (핵심 gotcha)

NEC 라이브 개표 포털(`info.nec.go.kr`, VCCP09)은 **득표는 주지만 당선 판정에 필요한
정보가 빠져 있다**:

1. **중선거구 정수(magnitude) 없음** — 기초의원 지역구(tc6)는 1선거구 2~4명 당선인데,
   라이브 API는 race당 **1위에게만 won**을 주고 선거구별 정수를 안 준다.
2. **무투표 선거구 누락** — 후보=정수면 무투표(투표 미실시) → 개표 row가 없어 데이터에서
   통째로 빠진다. 9회 tc6에서 **142개 선거구(311명) 누락**(거의 민주·국힘 강세구).
3. **일부 비례 시군구 누락** — 9회 tc9에서 개표방송이 마감 안 한(MAGAM=0) **58개 시군구**가
   빈 row로 와서 빠졌다(성북·노원 등 큰 자치구 포함).

→ 그래서 **확정 당선인 명부로 오버레이**해야 정확하다.

### 과거에 쓰던 추정의 오차 (교체 전)

라이브 개표만으로 채우려고 두 추정 스크립트를 썼고, 둘 다 부정확했다:

- `infer_council_winners.py` (tc6 magnitude 추정): 시군구 총정수 ÷ 선거구 수로 평균 정수를
  배분 → 9회에서 **90개 선거구의 당선자가 틀림**. 예: 용산구가선거구를 3석으로 추정해
  3위(국민주권당 4.54%)를 당선 처리했으나 실제 정수는 2석 → **낙선**.
- `calc_proportional.py` (tc9 비례 헤어식 추정): 8회 baseline 정수 룩업이 부정확 +
  1석 시군구 2/3 상한 cap=int(1×2/3)=0 버그로 1위 의석을 2위에 넘김 → 9회 **298석으로
  과소집계**(실제 384). 8회도 381(실제 386), 5~7회도 5~12석씩 과소.

이 추정들은 이제 **FALLBACK 전용**(명부 미게시 시 선거 직후 임시 표시). 두 스크립트
docstring에 경고 명시.

## 확정 당선인 소스 — 회차별

### 5~8회: data.go.kr OpenAPI (게시됨)

`WinnerInfoInqireService2/getWinnerInfoInqire`:
- `sgTypecode=6` → 기초의원 지역구 당선인 (선거구별 실제 정수·당선인명).
- `sgTypecode=9` → 기초의원 비례 당선인 (시군구·정당별 의석).

스크립트:
- `scripts/fetch/fetch_council_winners.py --n N --rebuild` — tc6 당선인으로 race 재구성.
- `scripts/fetch/fetch_council_prop.py --n N` — tc9 비례 의석을 명부로 교체(+ 누락 시군구 추가).
  통합시 일반구(수원시팔달구)는 모도시(수원시)로 묶고, 군위(경북↔대구) 등 시도이동 매칭.

### 9회: NEC 개표방송 포털 당선인 명부 (OpenAPI 미게시 대체)

선거 직후 OpenAPI는 **미게시(INFO-03)**라, NEC 개표방송 포털의 **당선인 명부**를 쓴다.
`info.nec.go.kr` topMenuId=EP, secondMenuId=**EPEI01**(당선인 명부):
- `statementId=EPEI01_#6` (electionCode 6) → 기초의원 지역구 당선인. K_NAME·JDNAME·SGGNAME(선거구).
- `statementId=EPEI01_#9` (electionCode 9) → 기초의원 비례 당선인. 시군구·정당.
- 무투표 당선인은 DUGSU='무투표당선'으로 표시 → 누락 선거구를 명부에서 보충.

스크립트: `scripts/fetch/fetch_council_winners_live.py`
- tc6: 선거구·이름 매칭으로 won·seats_total 확정 + 무투표 선거구 142곳 추가.
- tc9: 시군구·정당 매칭으로 정당별 seats 확정 + 개표 누락 58곳 추가.
- 결과: tc6 2,650 / tc9 384, 명부와 100% 일치.

OpenAPI 게시(통상 수주 뒤) 후엔 5~8회처럼 OpenAPI로도 회수 가능.

### votes_pending (비례 득표 미게시)

명부엔 **당선·의석은 확정**이나 **정당별 득표수가 없는** 시군구가 있다(개표방송 미마감 +
명부는 득표 미수록). 그런 비례 race는 `"votes_pending": true`로 표시 — **의석은 정확**,
득표만 추후 백필. 회차별: 5회 11곳·6회 6곳·7회 5곳·8회 4곳·9회 58곳.

## 파이프라인

`scripts/build/run_local_pipeline.sh <election-id>` (6단계):
1. NEC 라이브/OpenAPI fetch (개표·득표)
2. **기초의원 당선인 확정** — 9회는 `fetch_council_winners_live.py`,
   5~8회는 `fetch_council_winners.py --rebuild` + `fetch_council_prop.py`
3. 무투표 inject (기초장·광역의원 등 — 기초의원은 2단계 명부가 처리)
4. chunk → 5. timeline → 6. archive sync

## 관련

- `scripts/fetch/fetch_council_winners_live.py` — 9회 EPEI01 명부 (tc6+tc9).
- `scripts/fetch/fetch_council_winners.py` — 5~8회 OpenAPI tc6.
- `scripts/fetch/fetch_council_prop.py` — 5~8회 OpenAPI tc9 비례.
- `scripts/build/infer_council_winners.py` · `calc_proportional.py` — ⚠ FALLBACK 추정(명부 우선).
- `scripts/build/build_timeline.py` — `localCouncilPartyCounts` 카운트(메인 카드).
