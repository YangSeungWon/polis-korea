# CSS 구조

`assets/*.css` 8개 파일, 총 ~1690 LOC. 페이지 종류에 따라 필요한 것만 로드.

## 파일별 역할

| 파일 | LOC | 로드 페이지 | 역할 |
|---|---|---|---|
| `common.css` | 175 | 전 페이지 | 토큰 (`:root --bg --ink`) · reset · 다크 테마 · 사이트 chrome (헤더·푸터·테마 토글) · Leaflet 배경 |
| `components.css` | 343 | polls·history·timeline·byelection·archive | 공유 UI 컴포넌트 — `.controls`·`.seg`·`.lede`·`.intro`·`.detail-pane`·`.hex-pane`·`.map-pane`·`.viz`·`.loading-overlay`·`.spin`·상태(`.is-active`·`.fade-*`)·범례(`.leg-*`)·`.scatter-wrap`·`@keyframes spin` |
| `dashboard.css` | 458 | index + archive 4 | 대시보드 (status overview · dash-section · dash-grid · 정당 범례 · parliament chart mini · timeline strip · ar-list) |
| `polls.css` | 81 | polls·governor·mayor·superintendent·party | 폴 카드 (`.poll-card`·`.pc-*`) 전용 |
| `history.css` | 186 | history + history sub | 회차 결과 chrome (`.rc-*`·`.ns-*`·`.parl-seats-legend`·아카이브 banner) |
| `archive.css` | 287 | archive 4 | 아카이브 페이지 (`.ar-*` 전부 — hero·hero stats·sections·exit poll grid·seat rows…) |
| `timeline.css` | 132 | timeline.html | 타임라인 (`.tl-*`) 전용 |
| `byelection.css` | 27 | byelection.html | 재·보궐 지도 라벨 (`.boe-*`·`.byelection-viz`) 전용 |

## 페이지별 CSS 세트

```
index.html                                common + dashboard
polls.html · governor · mayor · …          common + components + polls
history.html · history/*                   common + components + history
timeline.html                              common + components + timeline
byelection.html                            common + components + byelection
archive/{id}/                              common + components + dashboard + archive
```

## 로드 순서

1. **common.css** — 토큰·reset·chrome (변수 정의가 다른 모든 CSS의 기반)
2. **components.css** — 공유 컴포넌트 (`.seg` 등 — 페이지 전용 CSS가 override 가능)
3. **페이지 전용** — `polls.css`·`history.css`·`archive.css` 등

## 이력

- 이전: `polls.css` 459 LOC가 36 페이지에 박혀있었음 — 그 안에 공유 chrome + 폴 features 섞여 있어 모든 페이지가 459 LOC fetch
- 변환: 공유 chrome → `components.css` 추출, 폴 features만 `polls.css`에 남김. byelection 룰은 `byelection.css`로 분리
- 결과: 비-폴 페이지의 CSS 부담 ~150 LOC↓, 의미적 분리 명확

## 신규 룰 어디 추가?

- 여러 페이지가 쓰는 UI 컴포넌트 → `components.css`
- 특정 페이지 전용 → 그 페이지 CSS (`polls.css`·`history.css`·…)
- 사이트 전역 chrome (헤더·푸터) → `common.css`
- 토큰 (`--bg` 등) → `common.css :root`

## 점검

```bash
# brace 균형
for f in assets/*.css; do python3 -c "s=open('$f').read(); assert s.count('{')==s.count('}'), '$f'"; done

# dead selector 감사 — 이전 PR로 44개 룰 제거. 동일 명령 재실행으로 신규 dead 검출
# (스크립트는 docs/css.md 작성 시점 inline; 영구화하려면 scripts/audit/css_dead.py로)
```
