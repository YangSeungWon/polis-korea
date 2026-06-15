# assets/polls/

여론조사 페이지(`/polls.html` · `/governor/` · `/mayor/` · `/superintendent/` · `/party/` · per-election `/polls/{id}/`) JS.
per-election 페이지는 `POLL_ELECTION`(build_static가 `__INITIAL_STATE__.election` 주입)으로 대선·총선·지선 분기.

```
core.js           → ELECTION 상수 · state · 카운트다운 · loadData · region/office lookup
render-hex.js     → 17 시도 hex(renderHex=governorHex 위임) + 시군구 hex(period-aware: sigungu_hex_local[회차])
render-map.js     → Leaflet 시도·시군구 chloropleth + 미니맵
result-overlay.js → 출구조사/실제 결과 오버레이(덤벨 등)
chrome.js         → 디테일 패널 · 보기 토글 · 범례
recent-feed.js    → 최근 여론조사 피드(허브)
election-index.js → 선거별 여론조사 디렉터리(ElectionTimeline 3레인 타임라인)
adapter.js        → 여론조사↔실제 결과 어댑터(대선/총선/지선)
climate.js        → 선거 무렵 분위기(국정·정당 지지 12개월 창)
render-pres.js    → 대선 비례 viz(아카이브 render-sido-prop 재사용)
render-gen.js     → 총선 지역구 hex + 정당 지지율 추이(climate가 소유)
main.js           → setOffice/setScope · seg fades · init · entry
```
※ 공유 컴포넌트(ElectionTimeline·LensSwitcher·governorHex·drawSigunguHex)는 `docs/shared-components.md`.

## 로드 순서

```html
<script src="assets/polls/core.js"></script>
<script src="assets/polls/render-hex.js"></script>
<script src="assets/polls/render-map.js"></script>
<script src="assets/polls/chrome.js"></script>
<script src="assets/polls/main.js"></script>
```

`main.js`가 마지막에 `init()` 호출. URL prerender 시 `window.__INITIAL_STATE__`
주입 형태 그대로 유지.

## 의존 관계

```
main           → 모두 (init이 setView/setOffice/setScope dispatch)
chrome         → render-hex/map (setView 가 호출)
render-X       → core (state · regionSidoWinner/regionSigunguWinner — 모드 인식, PollAdapter 위임)
core           → (없음)
```

5개 페이지 (polls·governor·mayor·superintendent·party)가 같은 5 script 태그
세트를 공유.
