# hex 격자 layout 규칙

한반도 시·군·구 / 선거구를 hex 격자로 시각화하는 layout 알고리즘 문서.
`scripts/build/build_zone_hex.py` 가 모든 회차 hex 좌표를 생성한다.

## 전체 구조 — 3 zone

```
┌─────────────────────────────────────┐
│  N zone (수도권 + 강원)              │
│  인천 │ 서울 │ 경기 wrap │ 강원      │
├─────────────────────────────────────┤
│  S zone (충청 + 호남 + 영남)         │
│  ┌──────────────────┬──────────┐   │
│  │  충청 (top)      │          │   │
│  ├──────────────────┤  영남    │   │
│  │  호남            │          │   │
│  └──────────────────┴──────────┘   │
├─────────────────────────────────────┤
│  P zone (제주, 호남 아래 1 row gap) │
└─────────────────────────────────────┘
```

회차마다 셀 수 변동 → 시도별 W·H 동적 계산.

## 정렬 원칙 (전 시도 공통)

- **row = -lat** (북 → 남, top row = 가장 북쪽)
- **col = lon** (서 → 동, col 0 = 가장 서쪽)
- 육각 grid offset: odd row가 가로 0.5칸 shift (geographic 시각 영향)

### `fill_rect` 2-pass 정렬

`sort_key=None` (기본) 이면 자동 2-pass:
1. cells을 -lat sort (북 먼저)
2. H 단위 row 분배
3. row 내 lon sort (서 먼저) → col 0..count-1 배치

명시 sort_key 호출은 1-pass (backward compat).

### Column-major 정렬 (전북·인천 등)

특정 시도는 column-major:
1. lon 큰 → 작은 (east first) sort, H씩 batch로 col에 분배
2. col 안에서 lat 큰 → 작은 (북 → 남) sort

`from RIGHT`: 동쪽 col 우선 채움, 빈자리는 서쪽 outer col에.
호남 right-align과 일관 (영남과 boundary 깔끔).

---

## N zone (수도권 + 강원)

```
row 0     |  경기 top wrap (서울 위 + 인천 위 좌측 절반)
row 1     |  경기 (인천 위 1 row 추가) | 서울 row 0 | 경기 right
row 2~    |  인천             | 서울 inner | 경기 right | 강원
row inner+|  경기 bot wrap (서울 아래 + 인천 아래 좌측 절반)
```

### 서울

square-ish 직사각형. `h_seoul = max(1, round(√n_seoul))`, factor 우선.
inner_H = h_seoul.

**빈칸 메움** (`inner_holes`): n_seoul이 W×H에 미달하면 마지막 줄 우측이 비어
서울·경기 사이에 갇힌 구멍이 생김(예 14대 44석=7×7, 5칸 빔). 그 빈칸을 경기 **최북단
bot 셀**로 메움 — 서울 바로 아래/안쪽 = 남부 경기 북단이라 지리적으로 자연스럽고 갭 제거.
쓴 셀만큼 bot wrap 서측이 외곽 notch로 빔(갇힌 구멍 아님). 정확 직사각(예 17대 8×6,
21대 7×7)이면 미작동.

### 인천

- **위치**: 서울 좌측, **한 칸 아래로 내려** rows `top_h+1 .. top_h+inner_H-1`.
- **모양**: `h_in_pref = ceil(√(n×1.5))` (살짝 세로). inner_H 초과 시 wider.
- **이유**: row top_h (인천 top row) 자리를 경기 북부에 양보.
- **column-major from RIGHT** (동쪽 = 서울 가까움).
  - (1) lon 큰 → 작은 (east first)로 H씩 batch, col `w_in-1 .. 0` 채움.
  - (2) col 안에서 lat 큰 → 작은 (북 → 남).
- **partial col = 서쪽 outermost (col 0), top-aligned**.
  - 셀이 H로 안 나눠지면 leftmost col이 미달 — 북쪽(top)에 붙임.
  - 결과: **좌하단이 빔** (서남 바다 쪽). 옹진군·강화군 같은 단일/소수 cell은 col 0 top.
  - 인천 본토 아래쪽 = 경기 bot wrap 위쪽 빈자리와 매끄럽게 이어짐.

### 경기도 wrap (top + right + bot)

서울을 둘러쌈. **top은 인천 우측 절반**(`ceil(w_in/2)`)까지, **bot은 인천 전체 폭**(`w_in`)까지 확장.
(top은 extra row가 인천 위 가득 덮어주므로 절반만으로 충분, bot은 비대칭 해소를 위해 full width.)

**Cap 계산**:
```
top_extra = ceil(w_in_est / 2)
bot_extra = w_in_est
top_w = top_extra + w_seoul + right_w
bot_w = bot_extra + w_seoul + right_w
cap = top_h × top_w + in_extra_top_row + right_w × inner_H + bot_h × bot_w
```

**점수** (작을수록 선택):
```
score = (waste + east_penalty + top_heavy × 10 - bot_h × 4, top_h + bot_h)
top_heavy = max(0, top_h - bot_h)   # top > bot 회피
east_penalty = right_w × 5          # 동부 비중 줄임 (실제 경기 동부 시군 적음)
```

→ 결과: **남부 압도적 > 북부 ≈ 동부** (실제 인구 분포 반영).

**Bridge 조건**: bot_cells ≥ bot_h (동쪽 col 1개는 full → bot 최남단 row 동쪽 채움 + right wrap 직접 연결).

**분배**:
- top (가장 -lat 큰 cells) → top wrap rows 0..top_h-1, cols (row-major)
- right (중간 lat) → col 우측 strip
- bot (가장 lat 작은) → bot wrap **column-major from RIGHT**.
  - 동쪽 col (강원 옆)부터 full bot_h 채움, 빈자리는 westmost col 위쪽.
  - partial col bot-aligned → bot 최남단 row 항상 가득 (잘린 느낌 X).
  - 빈자리는 인천 본토 아래쪽 notch로 자연 흡수.

### 강원

- **모양**: `w_gw = ceil(n_gw / H_N)`, `h_gw = ceil(n_gw / w_gw)`.
  - 필요시 **1×N strip (지렁이)** 허용. 강원은 남북 매우 긴 권역이라 자연.
- **위치**: 경기 right 우측 col strip. **bot-align** to N zone 끝.
  - → S zone 경북 top과 **직접 접촉** (지리 일치).

---

## S zone (충청 + 호남 + 영남)

### 충청 (W×H — 하우스 높이 4행 우선)

`find_chungcheong_wh(n_ch, prefer_h=4)`: 정사각보다 **회차 간 높이 통일(4행)**을 우선.
정확 인수쌍이 없어도 빈칸 ≤ 3 허용 (이전엔 "빈자리 0"이라 27석=9×3, 충청만 3행으로
납작했음 — 13·20대). 이제 24=4×6, 27=4×7(빈칸1), 28=4×7 모두 **4행**.

**빈칸(waste) = 충남 남서(col 0 bottom) 외곽 notch**: column-major bot-anchor 충남이
서해안 코너만 비움 → 갇힌 구멍 아님. (서울 inner_holes는 경기로 메우지만, 충청은 좌측이
서해안 외곽이라 notch로 충분.)

**구조**:
```
충남 좌 cols (column-major bot_anchor, 남서 notch) → 세종+대전 중앙 → 충북 우 cols
```

**대전 P자 (2-col compact)**:
- 1-col 지렁이 회피
- 세종+대전 통합 영역 = 충남 last col top 빈자리 + 추가 col(들)
- 정렬: top-left부터 (row, col) ascending → 세종 N개, 대전 N개
- 충북: 모든 남은 cells (우측부터 fill)

**충청 right-align** (`ch_col_shift = w_left - w_ch`): 호남과 동일하게 우측(영남
boundary) 정렬. W_ch < W_left일 때 좌측정렬하면 충북이 영남에서 1칸 떨어져(충북 왼쪽
밀림) T경계가 어긋남 → 충청도 우측정렬해 충북이 영남과 직접 접촉. 좌측 notch는 외곽(서해안).

예 sigungu_hex 대전 5셀: `(4,0)(5,0)(4,1)(5,1)(4,2)` = 2×2 + (4,2) P자.

### 호남 (전북 top + 광주 inner + 전남 wrap + 광주 빈자리 메움)

**W·H 설계** (`design_honam(target_W, target_H)`):
- 점수: `waste + w_penalty(|W-target_W|×5) + h_penalty(|H-target_H|×10)`
- `target_W = w_ch` (충청 W와 매칭 → 좌측 큰 notch 방지)
- `target_H = 영남 H - h_ch` (Left H = 영남 H stretch)

**Layout**:
1. **전북 column-major from RIGHT**: 동쪽 col부터 채움.
2. **광주 inner block** (h_gj × w_gj). 직사각형 안 못 채우면 빈자리.
3. **전남 wrap (left + right + bot)** + **광주 빈자리 메움** (extra_positions).
   - 광주가 5셀이고 2×3=6 slots면 1셀 비는데, 그 자리를 전남 cell이 채움.
   - 지리: 광주는 전남 안 enclave.

**호남 right-align**: W_ho < W_left이면 좌측 비고 우측이 영남 boundary와 일치.

**전북 partial 우측 정렬** (`right_top`): top row 끝까지 채워 충청과 연속.

**Bridge 조건**: 좌·우 wrap 둘 다 있으면 bot 첫 row 가득 채워야 단절 안 됨.

### 영남 blob mode

```
경북 (북 wrap)
  대구 (좌 직사각)  울산 (우 blob/L자)
            ↓  bot-aligned, 직접 접촉  ↓
경남 (서 cols)   부산 (동 cols)
```

**대구 + 울산 좌·우 인접**:
- 대구 직사각형 — **near-square** (빈칸 최소 + 정사각 가까이). 셀 수가 소수(13·11 등)여도
  1×N 기둥(영남 길쭉) 회피. 정확 약수면 빈칸 0. 빈칸은 배정부가 가장자리로 비움.
  단, top_taken은 **직사각 면적(빈칸 포함)**으로 계산해야 경북 공간이 모자라지 않음.
- 울산 L자는 **5셀 전용**. 그 외 빈칸은 울산 영역으로 둠(경북 corner bridge로 두면 위쪽
  빈칸과 만나 경북이 고립됨). L-corner는 그 위 col을 채워 row 0 경북과 직접 연결.
- **bot row 일치** → 둘 다 경남·부산과 직접 접촉.

> ⚠️ 소선거구(13대~)는 위 near-square로 시도 단일 cluster + 합리적 종횡비 보장.
> 중선거구(9~12대)는 선거구가 적어(70~90) zone 배치가 sparse → district_hex_cartogram.py
> (지리 비닝) 유지. 둘 중 선택은 회차별.

**경북 north wrap 우선순위**:
1. row 0 (T-boundary top)
2. col 0 (T-boundary left, rows 1..H_top-1)
3. bridge above 울산 (h_dg > h_us 경우)
4. L-corner (n_us=5)
5. 나머지 top region cells

**경남·부산 bot stack**: 경남 서 cols, 부산 동 cols + col W-1 east coast strip (옵션).

**w_gn 결정**: 부산이 east coast 잡으면 경남이 cols 0..w_gn-1, 부산이 cols w_gn..W-1.

---

## P zone (제주)

- **셀 수**: district 3 (제주시갑·을, 서귀포), sigungu 2 (제주시, 서귀포).
- **모양**: 1 row strip (가로).
- **위치**: 호남 actual bot row + 2 = **호남으로부터 1 row gap**.
  - allocated H_ho 대신 호남 cells 실제 max row 사용.
  - 영남 길이 무관 → 전 회차 갭 1 row 통일.
- **col**: 호남 leftmost col과 정렬 (`s_col_offset + ho_shift`).
  - ho_shift = `w_left - W_ho` (호남 right-align 시 shift).

---

## Cluster 보장 가드

`fill_wrap_left_right_bot` (전남 wrap):

```python
# 좌·우 wrap 둘 다 있는데 bot이 못 connect 시 skip:
if left_w > 0 and right_w > 0 and bot_used < total_w:
    continue
```

bot이 첫 row 가득 못 채우면 좌·우 wrap 단절 → 후보 제외.

`fill_wrap_top_right_bot` (경기):

```python
# Bridge 조건 (column-major bot)
bot_cells_actual = n_gg - top_h × top_w - right_w × inner_H
if bot_cells_actual < bot_h:  # 동쪽 col 1개는 full 채워야 right wrap 연결
    continue
```

---

## 디자인 결정 요약

| 항목 | 결정 | 이유 |
|---|---|---|
| 인천 1 row 내림 | row top_h은 경기 북부로 | 경기 북부 셀 보충 |
| 경기 top 인천 절반 확장 | ceil(w_in/2) + extra row 가득 | 인천 위 공간 활용 |
| 경기 bot 인천 전체 폭 확장 | w_in (full) | 인천 본토 아래까지 경기로 메움 (비대칭 해소) |
| 경기 bot column-major from RIGHT | 동쪽 col 우선 full, partial westmost bot-align | 마지막 row 가득 유지, 빈자리 westmost col 위쪽 (인천 아래 notch 흡수) |
| 강원 1×N strip 허용 | H_N 채움 우선 | 강원 남북으로 긴 권역 |
| 강원 bot-align | N zone 끝 = S zone 경북 top - 1 | 지리적 접촉 |
| 호남 right-align | W_ho < W_left일 때 | 영남 boundary 깔끔 |
| 전북·인천 column-major from RIGHT | 동쪽 col 우선 | east edge 깨끗 |
| 대전 2-col P자 | 1-col 지렁이 방지 | 시각 compact |
| 영남 blob bot 정렬 | 대구·울산 bot row 일치 | 경남·부산과 직접 접촉 |
| 제주 호남 실제 bot + 2 | allocated 무시 | 영남 길이 무관 갭 1 통일 |

## ⚠️ 생성 뒤 구멍 메우기 — 두 단계다

`build_zone_hex.py`는 **내부 빈칸 0을 보장하지 않는다.** 독스트링에 오래 그렇게 적혀
있었지만 사실이 아니었다. 영남 70셀을 이 구조(대구 3×3 · 울산 3×2 L · 경북 wrap ·
경남/부산 bot)로 놓으면 **빈칸 0인 후보가 탐색 공간에 아예 없고 최소가 2다.** 그중
하나가 바깥으로 못 나가고 `sigungu_hex` `(12,10)`에 갇혔다 — 이웃이 대구 동구·울산
북구·경북 영천시·청송군이라, 지도에서 대구와 경북 사이가 뚫려 보였다. 회차별 지선
hex는 5~9회에 같은 이유로 구멍이 있었다(5~8회는 각 4~6칸).

경북이 공간을 더 받은 게 아니다 — 22칸으로 실제 시군구 수와 정확히 같다. 모양의
문제이고, 그래서 재배치가 아니라 **slide-fill**로 고친다:

```bash
python scripts/build/build_zone_hex.py          # 배치
python scripts/build/build_local_period_hex.py  # 회차별 배치
python scripts/build/fill_district_hex_holes.py --apply --path data/geo/sigungu_hex.json
python scripts/build/fill_district_hex_holes.py --apply --path data/geo/sigungu_hex_local.json
python scripts/build/fill_district_hex_holes.py --apply          # 지역구 hex 전체
```

hole→외곽 최단경로 위 셀을 1칸씩 밀어 닫는다. 셀 수·시도 소속은 그대로고 좌표만
움직인다(9회는 청송군·울진군 2칸). **셀에 `sido`가 있으면 그 묶음을 더 쪼개는 이동은
고르지 않는다** — 이 필터가 없던 첫 판이 포항시를 `(13,10)→(12,10)`으로 밀어
`(13,11)` 경북 셀을 울산·빈칸 사이에 고립시켰다. 구멍은 사라졌고 검사도 없었으니
그대로 나갈 뻔했다. `tests/test_hex_holes.py`가 둘 다 잡는다(CI 포함).

## 검증

```bash
python3 scripts/build/build_zone_hex.py
python tests/test_hex_holes.py    # 갇힌 빈칸 0 · 시도 분절 회귀 없음
```

- 모든 회차 cluster 단일성 (시도 cells 끊김 없음)
- T-boundary 보존 (충청-호남 직선, 호남-영남 직선)
- 지리 정확 (row=lat, col=lon, hex offset 고려)

ASCII 점검:

```python
import json
LABEL = {'서울특별시':'S','인천광역시':'I','경기도':'경','강원특별자치도':'W',
         '충청남도':'남','충청북도':'북','세종특별자치시':'세','대전광역시':'대',
         '전북특별자치도':'전','전라남도':'전','광주광역시':'광',
         '경상북도':'B','경상남도':'M','대구광역시':'D','울산광역시':'U','부산광역시':'F',
         '제주특별자치도':'P'}
cells = json.load(open('data/geo/sigungu_hex.json'))
grid = {(x['c'],x['r']): LABEL.get(x['sido'],'?') for x in cells}
# ... render grid
```

## 데이터 파일

- `data/geo/sigungu_hex.json` — 현행(2026) 시군구 hex (250여 셀)
- `data/geo/sigungu_hex_legacy.json` — 옛 행정구역 시군구 hex
- `data/geo/sigungu_hex_local.json` — **회차별 지선 시군구 hex** (키=회차 `"1"`…`"9"`, 아래 참조)
- `data/geo/district_hex_{17..22}.json` — 17~22대 총선 지역구 hex

각 파일: `[{code, name, sido, c, r}, ...]` 배열(period 파일은 회차→배열 맵). `c`·`r`은 hex offset 좌표.
`sigungu_hex_local.json` 회차 셀엔 `code`가 없을 수 있음(이름 기반 매칭) — `drawSigunguHex`는 `code` 불필요.

### 회차별(period-aware) 지선 시군구 hex — `sigungu_hex_local.json`
지선은 회차마다 그 시점 시군구 행정구역을 썼어야 하므로 현행 레이아웃을 옛 회차에 그대로 쓰면 팬텀 셀이
빈칸으로 뜬다(예: 군위는 2023-07 경북→대구 이동, 영종/제물포/검단은 2026 인천 신설). `build_local_period_hex.py`가
각 회차 기초단체장 결과에서 그 시점 시군구 셀을 만들어 회차별로 저장. 사용처 둘:
- **history 회차 지도**(`assets/history/render-sigungu.js`) — `state.hexLocal[회차]`, `effectiveCell`로 옛 이름 alias.
- **폴 per-election 시군구 hex**(`assets/polls/render-hex.js` `loadSigunguHex()`) — `POLL_ELECTION.kind==='local'`이면
  `sigungu_hex_local.json[n]` 사용, 없으면 현행 `sigungu_hex.json` 폴백. (7·8회 군위=경북·인천 중/동/서구,
  9회=대구 군위·영종/제물포/검단구.)

## 페이지에서 사용

- `history.html` — 역대 선거 결과 hex 시각화 (`assets/history.js`)
- `byelection.html` — 재보궐선거 여론조사 (`assets/byelection.js`)
- `governor/`·`mayor/`·`superintendent/` — 지선 여론조사
