# 페이지 지도 (IA) — 무엇이 어디에 있고, 어디로 이어지는가

polis.ysw.kr의 화면 전체 지도. **"같은 선거를 여러 페이지가 다루는데 접근법이 다르다"**가
이 사이트 구조의 핵심이라 그것부터 정리한다.

마지막 확인: 2026-08-04.

## 한 선거를 보는 네 가지 화면

역대 선거 하나(예: 8회 지선)를 다루는 화면이 넷이다. 중복이 아니라 **묻는 질문이 다르다**.

| 화면 | 답하는 질문 | 축 | 개수 |
|---|---|---|---|
| `/history.html` | **어디가 어느 정당을 찍었나** | 공간 (hex 카토그램) | 1 (+프리렌더 66) |
| `/timeline.html` | **판세가 회차마다 어떻게 움직였나** | 시간 × 시도 | 1 |
| `/chronology.html` | **그 선거는 어떤 정치사 국면이었나** | 시간 (정변·개헌·항쟁 포함) | 1 |
| `/archive/{회차}/` | **그 선거에서 실제로 무슨 일이 있었나** | 회차 1개 심층 | 77 |

앞의 셋은 **여러 선거를 가로지르는** 뷰(탐색·비교·맥락)고, archive는 **한 선거를 파고드는**
뷰다. 그래서 출구조사·여론조사 대조·공약 분야 분포처럼 회차 고유 자료는 archive에만 있다.

`/history/{type}/{n}/` 66개는 history.html의 **프리렌더**다. 화면은 같고 SEO·직접 링크용 —
사용자에겐 같은 것이 두 URL로 존재한다는 뜻이기도 하다.

### 지금의 연결 (한 방향으로 끊겨 있음)

```
  chronology ──┐
  timeline ────┼──→ history.html          archive/{회차} ──prev/next──→ archive/{회차}
               │        ↑                        │
               └────────┘                        │ breadcrumb
                        └────────────────────────┘
       홈 역대 그리드 ───────────────────────────→ archive/{회차}
```

**`history.html` → `archive/{회차}/` 링크가 없다.** archive는 breadcrumb으로 history를
가리키는데 역방향이 없어서, hex 탐색기에서 8회 지선을 보던 사람이 그 회차의 출구조사·공약으로
넘어갈 수 없다. 홈 그리드로 되돌아가야 한다. → [gap-1](#알려진-공백)

## 헤더 nav — 전 페이지 공통

`sync_nav_html.py`가 정본(MENU)을 갖고 생성기들이 그 함수를 호출한다. 라벨을 바꾸려면 MENU만
고치고 생성기를 다시 돌린다. CI(`checks.yml`)가 사본 발생을 막는다.

| 라벨 | 경로 | 성격 |
|---|---|---|
| (로고) | `/` | 허브 |
| 지지율 추이 | `/tracker.html` | 선거 무관 상시 지표 |
| 여론조사 | `/polls.html` | 선거 여론 |
| 재·보궐 | `/byelection/` | 선거 결과·여론 |
| 역대 결과 | `/history.html` | 결과 (공간) |
| 역대 판세 | `/timeline.html` | 결과 (시간) |
| 근현대사 | `/chronology.html` | 맥락 |
| 정당사 | `/parties.html` | 정당 계보 |

`data-nav-urgent` 슬롯은 `nav.js`가 active 선거 phase(BLACKOUT/ELECTION/POST/RECENT)일
때만 채운다. `/search.html`은 nav에 없고 **헤더 우측 검색창**(nav.js 주입)으로 들어간다.

## 화면 전체

### 허브·진입

| 경로 | 첫 화면 | 나가는 곳 |
|---|---|---|
| `/` | 통합 검색바 · status 카드 3(대통령·국회·지방정부) · active 선거 대시보드 · 역대 결과 그리드 | `history.html?type=…` · `/governor/` `/mayor/` · `/archive/{회차}/` |
| `/search.html` | 당선인·지역·정당 통합 검색 (`?q=`) | `/person/…` · `/party/…` · archive |

### 선거 결과

| 경로 | 내용 | 파라미터 |
|---|---|---|
| `/history.html` | hex 카토그램 뷰어. 셀 클릭 → 우측 detail | `type`·`n`·`office`·`sizing`·`display` |
| `/history/{type}/{n}/` | 위 화면 프리렌더 66개 | — |
| `/timeline.html` | 1987~ 시도별 1위 정당 흐름 | — |
| `/archive/{회차}/` | 회차 심층 77개 | — |
| `/byelection/` · `/byelection.html` | 재보궐 선거구별 지도·여론조사 | — |

archive 섹션(9회 지선 기준): 선출직 정당 분포 · 광역단체장 결과 · 시도의회 의석 ·
시군구의회 의석 · 지방의원 당선인 · 출구조사 vs 실제 · 여론조사 · 재보궐 · 공약 분야 분포.
회차 종류(local/pres/general/byelection)마다 섹션 구성이 다르다 → `docs/archive-content.md`.

### 여론조사

| 경로 | 내용 |
|---|---|
| `/polls.html` | 여론조사 허브. `/governor/` `/mayor/` `/superintendent/` `/party/`의 템플릿이기도 함 |
| `/governor/` `/mayor/` `/superintendent/` `/party/` | active 지선 직위별 여론조사 (build_static) |
| `/polls/{회차}/` | 회차별 '여론조사 vs 실제' 9개 — **진입 경로 없음** → [gap-2](#알려진-공백) |
| `/tracker.html` | 선거 무관 연속 시계열(국정평가·정당지지·차기주자). house effect 보정 토글 |

> `/party/index.html`은 **정당지지 여론조사** 페이지이고 `/party/{정당명}/`은 **정당 프로필**이다.
> 경로가 한 단계 차이인데 성격이 전혀 다르니 주의 — nav의 is-current 매핑도 이 둘을 갈라 놨다.

### 개체(entity) 페이지

| 경로 | 개수 | 내용 |
|---|---|---|
| `/person/{이름}-{생년월일}/` | 4,022 | 출마 이력 타임라인 · 정당 변천 · 선거공약 |
| `/person.html?name=` | — | 정적 페이지가 없는 인물용 동적 fallback |
| `/party/{정당명}/` | 100 | 창당·합당·해산, 소속 인물, 선거 성적 |
| `/parties.html` | 1 | 정당 계보 전체 시간축 |

인물 페이지는 **의원 이력이 있는 4,022명만 프리렌더**한다. 공약 보유 905명 중 정적 페이지가
있는 건 63명뿐이고 나머지 842명은 `?name=` 동적 경로로 들어간다 — 지방선거 당선인 다수가
여기 해당한다.

### 생성물·부속

| 경로 | 개수 | 용도 |
|---|---|---|
| `/share/{회차}/{뷰}/` | 288 | SVG 내보내기 공유 랜딩. `svg-export.js`가 URL 생성, 뷰별 og:image |
| `/about/` | 1 | 데이터 출처·방법론 |
| `/og/` | — | og 카드 이미지 |

share는 sitemap에도 없고 내부 링크도 없지만 **의도된 설계**다(공유된 링크로만 도달).
고아 페이지와 혼동하지 말 것.

## 알려진 공백

작업 대상으로 남겨 둔 것. 발견 2026-08-04.

**gap-1 · `history.html` → `archive/{회차}/` 링크 없음.**
hex 탐색기에서 회차를 보다가 그 회차의 심층 자료로 갈 수 없다. archive → history는
breadcrumb으로 이미 있으니 역방향만 뚫으면 된다. history의 선택 상태(`type`·`n`)가 곧
archive id로 매핑되므로 링크 하나면 된다.

**gap-2 · `/polls/{회차}/` 9개가 고아.**
sitemap에는 있으나 사이트 어디서도 링크하지 않아 검색엔진으로만 도달 가능하다.
`polls/index.html` 허브도 없다. archive의 '여론조사' 섹션과 내용이 겹치므로
① archive에서 링크 ② polls.html에 회차 목록 ③ archive로 흡수하고 페이지 폐기 — 중 택일.

**gap-3 · 같은 화면의 두 URL.**
`/history.html?type=local&n=8`과 `/history/local/8/{office}/`가 같은 것을 보여준다.
프리렌더는 SEO 목적이니 canonical 정리 상태를 점검할 여지가 있다.

**gap-4 · archive breadcrumb 라벨이 nav와 불일치.**
breadcrumb '타임라인' vs nav '역대 판세' — 같은 페이지를 두 이름으로 부른다.
`sync_archive_html.py`의 `derive()` 한 줄.

## 관련 문서

- `docs/architecture.md` — 운영 모델·디렉터리
- `docs/archive-content.md` — archive 회차 종류별 섹션 구성
- `docs/cycle-workflow.md` — 선거 생애주기(0~3단계)·active/archive 전환
- `docs/hex-layout.md` — 카토그램 hex 규칙
- `docs/tracker-pipeline.md` — 지지율 추이 데이터
