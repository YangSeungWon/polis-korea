# 줌·포커스 인프라 설계 (방식 전환 시 보던 지역 유지)

## 목표
지도/균등/격자/원형 사이를 전환할 때, **보고 있던 지역을 중심에 그대로 둔다.**
예: leaflet 지도에서 수도권을 확대 → "균등" 누르면 균등 hex도 수도권을 중심에 확대 상태로.
이게 되면 방식 토글을 지도 *안*에 두는 게 비로소 자연스러워진다(같은 대상을 다른 방식으로 변형).

전제: 지금 균등/격자/원형은 **고정 viewBox SVG라 줌이 없다.** 줌 되는 건 leaflet 하나뿐.
→ 두 가지를 새로 만든다. (A) SVG 뷰에 팬·줌, (B) 뷰 간 공유 포커스 상태.

## 핵심 원칙 — 포커스는 "지역 앵커"로 (픽셀·좌표 아님)
지도(위경도)·균등(정육각 격자)·원형(force-pack 원)은 좌표계·배치가 전혀 다르다.
따라서 공유 상태를 픽셀/위경도로 들면 변환이 깨진다. 대신 **지역 식별자로 앵커**한다:

```
Focus = { unit: 'sido' | 'sigungu', region: string | null, scale: number }
```
- `region` = 화면 중앙에 가장 가까운 지역(없으면 null=전국 보기).
- `scale` = 배율. **1 = 전국이 꼭 맞게(fit)**, 3 = 가로 1/3만 보임(3배 확대). 범위 [1, ~8] clamp.
- `unit` = 시도/시군구 — 토글이 단위를 바꾸면(시도hex↔시군구hex) region을 부모/자식으로 변환.

전환 = `다음뷰.focusOn(이전뷰.report().region, 이전뷰.report().scale)`.
이전 뷰가 헐리기 전에 capture → 다음 뷰 렌더 → applyFocus 순서.

## 3개 레이어

### 1) 공유 포커스 (`assets/viewport-focus.js`, 신규)
```js
window.Focus = {
  state: { unit: 'sido', region: null, scale: 1 },
  capture(view) { const r = view.report(); if (r) this.state = { ...this.state, ...r }; },
  apply(view)   { view.focusOn(this.state.region, this.state.scale); },
};
```
모든 "뷰"는 어댑터 2개만 구현하면 된다:
- `report() → { region, scale }`  // 지금 중앙에 뭐가 얼마 배율로
- `focusOn(region, scale)`        // 그 지역을 그 배율로 중앙에

### 2) SVG 뷰포트 헬퍼 (`assets/svg-viewport.js`, 신규) — 균등·격자·원형 공용
viewBox 조작으로 팬/줌. 휠=줌(커서 기준), 드래그=팬, base 경계로 clamp(밖으로 안 나가게), 최소 scale 1.
```js
SvgViewport.attach(svg, {
  baseViewBox: [0, 0, W, H],          // 렌더러가 setAttribute한 그 값
  cells: [{ region, cx, cy }],        // 지역→중심 좌표 (governorHex의 cells에서)
}) → handle
// handle.report():  현재 viewBox 중심에 가장 가까운 cell.region + scale(=W / 현재viewBoxW)
// handle.focusOn(region, scale): cell 찾아 viewBox = [cx - W/2/scale, cy - H/2/scale, W/scale, H/scale], clamp
```
- 줌 애니메이션: viewBox는 CSS transition 불가 → rAF로 300ms 보간(또는 1차는 snap, 애니는 Phase 4).
- **원형(dorling)은 force-pack 후 노드 위치가 확정**되므로 cells를 packCircles 끝난 뒤의 node.cx/cy로 넘긴다(applyFocus는 렌더 후 호출).

### 3) leaflet 어댑터 (`render-map.js`에 추가)
leaflet은 이미 뷰포트 → report/focusOn만 입힌다.
- region centroid: geojson 로드 시 `region → layer.getBounds().getCenter()` 사전계산(Map).
- `report()`: `regionAtCenter(leafletMap.getCenter())` = centroid 최근접(또는 point-in-polygon) + `scale = 2^(getZoom() - initialZoom)`.
- `focusOn(region, scale)`: `leafletMap.setView(centroid[region], initialZoom + log2(scale))` (애니는 flyTo).
- region 없으면 fitBounds(전체) + scale 1.

## 오케스트레이션 (polls 먼저)
`chrome.js setView(v)`를 감싼다:
```
const prev = currentViewHandle();   // 떠나는 뷰
Focus.capture(prev);
... 기존 분기로 renderMap/renderHex/renderSigunguHex ...
Focus.apply(nextViewHandle());      // 새 뷰 (SVG면 렌더 후, dorling이면 pack 후)
```
각 렌더러가 자기 handle을 `window.__viewHandles[v]`에 등록.

## 엣지 케이스
- **단위 전환**(시도hex↔시군구hex): unit 다르면 region 변환 — 시군구→시도는 부모 시도, 시도→시군구는 특정 시군구 못 고르니 시도 중심 유지(scale 보존).
- **대상 레이아웃에 지역 없음**(period 시군구·dorling 탈락): 부모 시도로 폴백, 그래도 없으면 scale 1 전국.
- **aspect 차이**(세로 긴 지도 vs 정사각 hex): 중앙 정렬은 무관, scale은 근사 — 허용.
- **scale 정규화**: 두 좌표계 모두 "가시 폭 / 전체 폭"의 역수로 통일 → 같은 숫자 의미.

## 단계별 롤아웃
1. **Phase 1** — `svg-viewport.js` + 균등(시도 hex) 단독 팬/줌. SVG 줌 인프라 검증(전환 없이).
2. **Phase 2** — `viewport-focus.js` + 균등 ↔ 지도(leaflet) 포커스 보존. **헤드라인 동작.**
3. **Phase 3** — 격자/원형(cartogram)·시군구 뷰로 확장 + archive sido-view/council 토글러.
4. **Phase 4** — 전환 애니메이션(rAF viewBox 보간 / leaflet flyTo).
5. **마무리** — 방식 토글을 다시 지도 *안*으로(이제 포커스 보존되니 제값을 함). [[viz_toggle_model]]

## 변경 안 하는 것
- 내부 키·data-* 값(hex/dorling/grid). 셀 좌표 계산(governorHex COL_W=80·ROW_H=70·R=36 등)은 그대로 읽기만.
- 생성 파일(hexgrid.js 등)은 직접 편집 금지 — .ts 소스 경유.
