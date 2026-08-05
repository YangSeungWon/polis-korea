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

## 첫 vertical slice — 포항 (구현됨)

`scripts/build/map_timelapse.py` → `data/map_timelapse/포항.json` →
`scripts/build/render_map_timelapse.py` → `map-timelapse/포항.html`.

다섯 상태를 낸다: 선거 직전 / 선거 / 사건 직전 / 사건 직후 / 다음 선거.

### 슬라이스가 실제로 찾아낸 것

**같은 사건, 같은 날짜인데 series에 따라 답이 다르다.**

| series | 1992 snapshot 단위 | 1995 통합 경계로 | 왜 |
|---|---|---|---|
| `president:national` | 포항시 · 영일군 | **aggregated** | 두 단위가 통합 포항시를 정확히 이룬다 |
| `general:district` | 포항시 · 영일군**·울릉군** | **unavailable** | 선거구가 울릉군까지 포함한다 — 뺄 하위 실측이 없다 |

대선은 시군구로 집계돼 지도 단위와 집계 단위가 같지만, 총선은 선거구라 한 겹이 더
있다. `series를 먼저 고른다`가 취향이 아니라 **정확성 요건**인 이유가 이것이다.
기본 series도 이 이유로 정한다(coverage가 높아서가 아니다).

실제 합산(김영삼): 포항시 97,780 + 영일군 58,962 = 156,742 / 250,836 = **62.49%**.
포항시만 보면 62.14%, 영일군만 보면 63.08%다. 어느 쪽도 통합 경계의 값이 아니다.

1997 대선은 포항시남구·북구로 집계돼 지도 단위(포항시)보다 잘다. 이건 승계가 아니라
**포함관계**여서 `data/geography/containment.json`에 따로 둔다 — `from/to`로 적으면
entity 파생기가 포항시를 1995년에 소멸시킨다. `exhaustive: true`(관할구역을 남김없이
나눈다)일 때만 합산을 허용한다.

### 검증

- `tests/test_map_timelapse.py` — 다섯 상태, 이산 전환, **합산이 원자료의 정확한 합인지**,
  unavailable에 색·후보·구성이 새지 않는지, 이름이 아니라 id로 세는지
- **면적 보존** — `territorial_continuity: same_total`이면 사건 전후 면적 합이 보존돼야
  한다. 이게 없으면 옛 폴리곤에 새 이름만 붙여도 테스트가 통과한다(실제로 통과했다)
- `tests/ui/test_map_timelapse.mjs` — 3뷰포트 + JS 없는 경우. 렌더 회귀는 픽셀이 아니라
  **SVG path·채움 골든**(`tests/golden/map_timelapse/`)으로 잡는다 — 폰트에 흔들리지
  않으면서 좌표·투영·색이 바뀌면 반드시 걸린다

## 두 번째 slice — 하남 (분구, 선거구 namespace)

**namespace를 섞지 않는다.** 행정구역 지도와 선거구 지도는 다른 지도다. 하남시갑은
하남시의 후신이 아니라 선거구이고, 같은 폴리곤 위에 겹쳐 그리면 두 ontology가 하나로
보인다. 그래서 경계 파일도 `sigungu_YYYY` / `district_N`으로 갈린다.

### 여섯째 상태가 필요했던 이유

선거구 획정은 **선거일에 발효된다**. 그래서 `사건 직후`가 곧 새 선거이고, 다섯 상태
만으로는 분구의 투영 가능성이 한 번도 시험되지 않는다 — 하남이 전부 `direct`로 나왔다.

그래서 `previous_on_new_boundary`(**경계는 새것, 결과는 그 이전**)를 넣었다. 설계
문서가 말한 비교 모드가 이 조합이고, 여기서만 다음이 드러난다:

> 제21대 결과 · 이 경계 기준 **수준값은 낼 수 없습니다** (정당별 변화량은 별도 비교에서 가능)

읍면동 실측으로 재집계는 됐지만 `inference_to_full_result.level.allowed = false`
(`excluded_votes_change_winner`)다. **지도는 수준값을 칠하는 화면**이므로 색을 주지
않는다. 재집계 엔진의 capability가 지도 claim을 그대로 제한한다.

`delta`는 열려 있고 정당별로 갈린다(더불어민주당 허용 / 국민의힘 `candidacy_
configuration_changed`). 막힌 것만 말하고 끝내지 않고 그 사실도 같이 싣는다 —
다른 화면(비교 모드)이 쓸 수 있어야 한다.

### 합과 쪼개기는 방향만 다른 게 아니다

합은 그냥 더하면 되지만 쪼개기는 하위 실측이 없으면 성립하지 않는다. `footprint()`는
되짚어 올라간 사건 중 **여럿으로 갈라진 것**을 따로 돌려주고, 그때는 합산 경로를
타지 않는다. 이게 없으면 하남시(2020) 표가 하남시갑에 통째로 `aggregated`로 붙는다.

## 화면에서 걸린 것 (데이터가 맞아도 화면이 틀린다)

- 하남 표가 한글을 **한 글자씩 세로로** 흘렸다. 가로 넘침은 없어서 넘침 검사로는
  안 잡혔다 → `th[scope=row]` 폭을 직접 잰다
- 같은 채움(둘 다 표시 불가)이면 두 단위가 한 덩어리로 읽힌다 → 단위 이름표를 넣고
  개수를 검사한다
- 명도 3단계 범례를 `currentColor`로 두니 세 칸이 전부 흐린 회색이었다 → 실제 계열색
  하나로 예시를 든다

## 다음

`reaggregated`가 실제로 성립하는 사례(level 허용)로 확장, 그다음 전국.
지금은 그 분기를 함수에 직접 물려서 동작만 확인한다 — **있는 것처럼 데이터를 만들지
않는다**.

## 커밋 전

`bash scripts/audit/full_gate.sh` — 부분 테스트 성공을 커밋 허가로 보지 않는다.
