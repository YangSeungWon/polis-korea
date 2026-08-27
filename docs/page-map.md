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
| `/about/` | 1 | 데이터 출처·방법론 |
| `/og/` | — | og 카드 이미지 |

`/share/{회차}/{뷰}/` 402쪽은 2026-08-27에 지웠다 — 뷰 키 재설계로 어차피 전부 다시
만들어야 했고, 그 페이지들이 쓰던 뷰별 og 카드도 함께 사라졌다. 같은 날 `svg-export.js`
(SVG 내려받기 버튼)도 지웠다: 부트스트랩이 share 정리 때 함께 빠져 **이미 죽어 있었고**,
91쪽이 죽은 스크립트 둘을 싣고 있었다. archive 페이지는 이제 `<figure>`로 PNG를 직접
갖는다(우클릭 저장이 그 자리를 대신한다).
고아 페이지와 혼동하지 말 것.

## 알려진 공백

발견 2026-08-04, 같은 날 처리 결과 포함.

**gap-1 · history ↔ archive 단방향** — 해소.
hex 탐색기에서 보던 회차의 심층 자료로 갈 수 없었다. `history.html`에 링크 슬롯을 두고
`updateURL()`이 `archive_index.json`으로 `(type, n)`→slug를 찾아 갱신한다. 프리렌더 66개는
정적 `<a>`를 유지하되 같은 id를 붙여, HTML에 링크가 남으면서 회차 전환 시 JS가 갱신한다.

**gap-2 · '고아'는 오진이었다** — 정정 + 보강.
`/polls/{회차}/`가 사이트 어디서도 링크되지 않는다고 적었으나 **틀렸다**. `polls.html`이
`election-index.js`로 타임라인을 그려 링크하고 있었다. 정적 HTML만 grep해서 JS 생성 링크를
놓친 것이다. 실제 문제는 '고아'가 아니라 **링크가 렌더 후에만 존재**하는 것이었고, 그건
아래 gap-5와 같은 부류다. 지금은 `polls.html`에 정적 시드 목록(build_static이 갱신)이
들어가고, archive 9개도 해당 폴 페이지로 링크한다.

> 교훈: 링크·콘텐츠 유무를 정적 파일 grep으로만 판단하지 말 것. 이 사이트는 상당 부분을
> JS가 만든다. 사용자 도달 가능성과 크롤러 가시성은 **다른 질문**이다.

**gap-3 · 같은 화면의 두 URL** — 남음(성격 변경).
`/history.html?type=local&n=8`과 `/history/local/8/{office}/`가 같은 화면이다. 다만 이제
프리렌더는 회차별 사실(당선인·투표율)을 본문에 갖고 canonical이 자기 자신을 가리키므로
중복 콘텐츠는 아니다. 정리 필요성은 낮아졌다.

**gap-4 · breadcrumb 라벨 불일치** — 해소. '타임라인' → '역대 판세'.

**gap-5 · 렌더 전 본문이 비는 페이지** — 대부분 해소.
2026-07 Search Console이 2,190페이지를 '크롤링됨 - 색인 생성되지 않음'으로 보류했다.
원인은 본문이 HTML에 없다는 것이었다(person 40자, history 프리렌더 66개는 서로 완전 동일).
빌드 시점 정적 렌더로 person 223자·공약 보유자 373자, history 중복 0쌍이 됐고 구조화
데이터(Person·Organization·BreadcrumbList)를 넣었다. 남은 것:
  · `/party/` 100개는 중앙값 228자 — 군소·역사 정당은 데이터 자체가 적어 한계가 있다.
  · og:image가 인물·정당·history에서 공용 이미지다(archive만 회차별).
  · 효과 확인은 색인 재평가까지 몇 주 걸린다. **2026-08 그 확인 경로가 생겼다** —
    GSC Search Analytics를 주간으로 쌓아 층별 '노출된 페이지 수'를 보고, 되돌아가면
    검사가 빨개진다(`docs/seo-coverage.md`). 구조화 데이터 채택 여부도 여기서 갈린다.

## 관련 문서

- `docs/seo-coverage.md` — 색인 수집(GSC)·회귀 검사·결손 모델
- `docs/architecture.md` — 운영 모델·디렉터리
- `docs/archive-content.md` — archive 회차 종류별 섹션 구성
- `docs/cycle-workflow.md` — 선거 생애주기(0~3단계)·active/archive 전환
- `docs/hex-layout.md` — 카토그램 hex 규칙
- `docs/tracker-pipeline.md` — 지지율 추이 데이터
