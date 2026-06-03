# hex 격자 layout 규칙

한반도 시·군·구 / 선거구를 hex 격자로 시각화하는 layout 알고리즘 문서.
`scripts/build_zone_hex.py` 가 모든 회차 hex 좌표를 생성한다.

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

### 인천

- **위치**: 서울 좌측, **한 칸 아래로 내려** rows `top_h+1 .. top_h+inner_H-1`.
- **모양**: `h_in_pref = ceil(√(n×1.5))` (살짝 세로). inner_H 초과 시 wider.
- **이유**: row top_h (인천 top row) 자리를 경기 북부에 양보.
- **column-major from RIGHT** (동쪽 = 서울 가까움).
- partial_align `right_bot` (마지막 row 우측, 서울 쪽 부착).

### 경기도 wrap (top + right + bot)

서울을 둘러쌈. top·bot은 인천 절반(`ceil(w_in/2)`)까지 확장.

**Cap 계산**:
```
top_w = extra + w_seoul + right_w  # 인천 좌측 절반
bot_w = extra + w_seoul + right_w
extra = ceil(w_in_est / 2)
cap = top_h × top_w + right_w × inner_H + bot_h × bot_w
```

**점수** (작을수록 선택):
```
score = (waste + east_penalty + top_heavy × 10 - bot_h × 4, top_h + bot_h)
top_heavy = max(0, top_h - bot_h)   # top > bot 회피
east_penalty = right_w × 5          # 동부 비중 줄임 (실제 경기 동부 시군 적음)
```

→ 결과: **남부 압도적 > 북부 ≈ 동부** (실제 인구 분포 반영).

**Bridge 조건**: bot 첫 row가 bot_w 전체 채워야 right wrap과 cluster 연결.

**분배**:
- top (가장 -lat 큰 cells) → top wrap rows 0..top_h-1, cols
- right (중간 lat) → col 우측 strip
- bot (가장 lat 작은) → bot wrap rows. partial `right_bot` (강원 옆 정렬).

### 강원

- **모양**: `w_gw = ceil(n_gw / H_N)`, `h_gw = ceil(n_gw / w_gw)`.
  - 필요시 **1×N strip (지렁이)** 허용. 강원은 남북 매우 긴 권역이라 자연.
- **위치**: 경기 right 우측 col strip. **bot-align** to N zone 끝.
  - → S zone 경북 top과 **직접 접촉** (지리 일치).

---

## S zone (충청 + 호남 + 영남)

### 충청 (perfect-fit W×H = n_total)

빈자리 0 보장.

**구조**:
```
충남 좌 cols (bot_anchor) → 세종+대전 중앙 → 충북 우 cols
```

**대전 P자 (2-col compact)**:
- 1-col 지렁이 회피
- 세종+대전 통합 영역 = 충남 last col top 빈자리 + 추가 col(들)
- 정렬: top-left부터 (row, col) ascending → 세종 N개, 대전 N개
- 충북: 모든 남은 cells (우측부터 fill)

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
- 대구 직사각형 (h_dg ≥ w_dg 선호).
- 울산 blob (2×3) 또는 L자 (5셀): h_us = h_dg와 bot row 정렬.
- **bot row 일치** → 둘 다 경남·부산과 직접 접촉.

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
# Bridge 조건
bot_cells_actual = n_gg - top_h × top_w - right_w × inner_H
if bot_cells_actual < bot_w:
    continue
```

---

## 디자인 결정 요약

| 항목 | 결정 | 이유 |
|---|---|---|
| 인천 1 row 내림 | row top_h은 경기 북부로 | 경기 북부 셀 보충 |
| 경기 top·bot 인천 절반 확장 | ceil(w_in/2) | 인천 outer 공간 활용 |
| 경기 bot partial 우측 | `right_bot` | 강원 옆 채워 시각 깔끔 |
| 강원 1×N strip 허용 | H_N 채움 우선 | 강원 남북으로 긴 권역 |
| 강원 bot-align | N zone 끝 = S zone 경북 top - 1 | 지리적 접촉 |
| 호남 right-align | W_ho < W_left일 때 | 영남 boundary 깔끔 |
| 전북·인천 column-major from RIGHT | 동쪽 col 우선 | east edge 깨끗 |
| 대전 2-col P자 | 1-col 지렁이 방지 | 시각 compact |
| 영남 blob bot 정렬 | 대구·울산 bot row 일치 | 경남·부산과 직접 접촉 |
| 제주 호남 실제 bot + 2 | allocated 무시 | 영남 길이 무관 갭 1 통일 |

## 검증

```bash
python3 scripts/build_zone_hex.py
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

- `data/geo/sigungu_hex.json` — 현재 시군구 hex (230여 셀)
- `data/geo/sigungu_hex_legacy.json` — 옛 행정구역 시군구 hex
- `data/geo/district_hex_{17..22}.json` — 17~22대 총선 지역구 hex

각 파일: `[{code, name, sido, c, r}, ...]` 배열. `c`·`r`은 hex offset 좌표.

## 페이지에서 사용

- `history.html` — 역대 선거 결과 hex 시각화 (`assets/history.js`)
- `byelection.html` — 재보궐선거 여론조사 (`assets/byelection.js`)
- `governor/`·`mayor/`·`superintendent/` — 지선 여론조사
