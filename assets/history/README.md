# assets/history/

역대 선거 결과 페이지(`/history.html`) JS — 6 파일로 분리.

```
core.js              → state · helpers · 새 schema → 옛 format adapter · URL routing/setters
data.js              → activeOfficeData · 시군구·시도·지역구 결과 lookup · 라벨 helper
render-sido.js       → 시도 17셀 hex (광역단체장·대선·총선 broadcast)
render-district.js   → 지역구 hex + Leaflet geomap (총선 21·22대 OhmyNews GeoJSON)
render-sigungu.js    → 시군구 hex (대선·기초단체장 시군구별)
main.js              → renderHistoryLegend · renderAll · detail pane · init · entry
```

## 로드 순서

```html
<script src="assets/history/core.js"></script>
<script src="assets/history/data.js"></script>
<script src="assets/history/render-sido.js"></script>
<script src="assets/history/render-district.js"></script>
<script src="assets/history/render-sigungu.js"></script>
<script src="assets/history/main.js"></script>
```

`main.js`가 마지막 — bottom에서 `init()` 호출하면 모든 파일이 정의된 함수
참조 가능 (JS 함수 선언은 hoist되지만 const는 안 됨).

## 의존 관계

```
main         → 모두 (renderAll이 render-* dispatch, detail pane이 data 사용)
render-X     → core (state, $, themeVar, 헬퍼) + data (resultForXxx)
data         → core (state, adapter helpers)
core         → (없음)
```

## 모듈 추가

새 render 모드 (예: 시·도 분포 hex별 다른 시각화) 추가 시:
1. `assets/history/render-{kind}.js` 작성 — 전역 함수 `render{Kind}()` 노출
2. `history.html` 에 script 태그 추가
3. `main.js`의 `renderAll()` 분기에 `activeUnit` 케이스 추가

state 객체에 mode 관련 필드가 필요하면 `core.js`의 `state` const 확장.
