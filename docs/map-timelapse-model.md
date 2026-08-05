# 지도 타임랩스 — 설계 규칙 (구현 전 필독)

정적 연표까지 세운 문법을 그대로 가져오되, 지도에는 **연표에 없던 gate가 하나 더**
필요하다. 이 문서는 그 gate를 잊지 않기 위한 것이다.

## 세 층

```
map_state
  geography_at_date       그 시점의 실제 경계 (사건 날짜에 이산 전환)
  election_snapshot       선택한 series의 선거 시점 결과
  political_projection  = resolve(election_snapshot, geography_at_date)
```

세 번째가 핵심이다. **snapshot이 존재한다 ≠ 지금 polygon에 그 snapshot을 칠할 수 있다.**

`political_projection`의 결과는 넷 중 하나다:

| 값 | 뜻 |
|---|---|
| `direct` | 경계가 그대로다. 그냥 칠한다. |
| `aggregated` | 이전 여러 단위의 표를 **실제로 합산**해 현재 footprint에 투영한다. |
| `reaggregated` | 하위 단위(읍면동) 실측으로 다시 담는다. capability가 허용한 것만. |
| `unavailable` | 칠할 수 없다. polygon은 새 topology로 그리되 **정치색은 중립/미표시**. |

## 왜 이 gate가 필요한가

포항 1995-01-01 도농통합에서 topology는 바뀌지만 그해에 선거는 없다.
직전 snapshot은 1992년이다. 여기서 1992 색을 새 통합 polygon에 그대로 carry-forward하면

> "1992년에 **현재 포항시 기준** A당 득표가 X%였다"

는, 관측하지 않은 새 주장이 된다.

```
1992 snapshot     포항시(구) A당 55% · 영일군 A당 62%
1995 geography    포항시(통합)
```

포항은 `comparison_capability: aggregated`라 두 단위 표를 **실제로 더하면** 투영이
성립한다. 그래서 이렇게 표시할 수 있다:

> 1992년 총선 결과 · 1995년 통합 경계에 합산

반대로 split인데 하위 실측이 없으면 합산할 대상이 없다. 그때는

> 1992년 결과는 이 경계로 표시할 수 없음

으로 두고 색을 칠하지 않는다. **모든 topology change가 aggregated인 것은 아니다.**

## 그 밖 (연표에서 이어지는 규칙)

- **series를 먼저 고른다.** 하나의 연도 scrubber에서 총선·대선·지선을 "그 시점 최신
  선거"라는 이유로 섞지 않는다. `총선` 모드면 2016→2020→2024만 쓴다.
- **선거 사이를 보간하지 않는다.** 관측하지 않은 2022년 정치성향을 만들지 않는다.
  discrete snapshot이 기본. carry-forward한다면 `마지막 총선 결과 기준`을 명시한다.
- **topology를 형태 보간하지 않는다.** 1994-12-31 `포항시(구)+영일군` → 1995-01-01
  `포항시`로 딱 바뀐다. fade는 되지만 없던 중간 geometry는 만들지 않는다.
- **기본 지도는 당시 경계.** `reaggregated`로 현재 경계에 투영하는 건 별도 비교 모드다.
  기본을 현재 경계로 하면 '경계가 변하는 역사'라는 타임랩스의 핵심 가치가 지워진다.
- **계보색은 strict 문법 그대로.** mixed는 중립+패턴(보수/민주로 밀어 넣지 않는다),
  unknown·무소속은 각각 다른 상태. tooltip은 전체 composition과 coverage를 보여준다.
- 색 = 1위 계열, 강도 = 득표 비율 정도로 시작한다. 합성색을 처음부터 만들지 않는다.

## 첫 vertical slice

**포항** — topology 사건(1995 도농통합)과 결과 snapshot이 둘 다 있고, 같은 이름의
다른 entity까지 있어 세 층 분리가 실제로 되는지 확인된다.
scrubber 전후에서 polygon version과 결과가 정확히 바뀌는지 구조 assertion +
스크린샷으로 검증한다.

## 커밋 전

`bash scripts/audit/full_gate.sh` — 부분 테스트 성공을 커밋 허가로 보지 않는다.
