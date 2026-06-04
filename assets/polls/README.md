# assets/polls/

여론조사 페이지(`/polls.html` · `/governor/` · `/mayor/` · `/superintendent/` · `/party/`) JS — 5 파일.

```
core.js           → ELECTION 상수 · state · 카운트다운 · loadData · region/office lookup
render-hex.js     → 17 시도 hex (renderHex) + 시군구 hex (renderSigunguHex)
render-map.js     → Leaflet 시도·시군구 chloropleth + 미니맵
chrome.js         → 디테일 패널 · 보기 토글 · 범례
main.js           → setOffice/setScope · seg fades · init · entry
```

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
render-X       → core (state · pollsByRegion · sidoLastWinningParty 등)
core           → (없음)
```

5개 페이지 (polls·governor·mayor·superintendent·party)가 같은 5 script 태그
세트를 공유.
