# 줌·포커스 인프라 (방식 전환 시 보던 지역 유지) — 구현 완료

방식(지도/균등/격자/원형) 사이를 전환할 때 **보고 있던 지역을 중심에 그대로 둔다.** 예: 지도에서 수도권을
확대 → "균등" 누르면 균등 hex도 수도권 중심·확대로(flyTo/트윈 애니메이션). 그래서 방식 토글을 지도 *안*
(우상단)에 둔다 — 같은 대상을 다른 방식으로 변형하는 인맵 컨트롤.

## 핵심 원칙 — 포커스는 "지역 앵커"
지도(위경도)·균등(육각격자)·원형(force-pack 원)은 좌표계가 전혀 다르다. 공유 상태를 픽셀/위경도로 들면
변환이 깨지므로 **지역 식별자로 앵커**한다: `{ region, scale }`. region=화면 중앙 최근접 지역(시도 또는
`시도|시군구`), scale=배율(1=전국 fit, 2면 가로 절반). 두 좌표계 모두 "가시폭/전체폭"의 역수로 통일.

각 "뷰"는 어댑터 둘만 구현: `report()→{region,scale}` · `focusOn(region,scale)`.
전환 = 떠나는 뷰 `report()` capture → 새 뷰 렌더 → `focusOn()` apply.

## 줌 시스템은 **두 개**(코드는 둘, UX는 동일)
| | 폴·아카이브 | 역대(history) |
|---|---|---|
| 줌 엔진 | `assets/svg-viewport.js` `SvgViewport` | `assets/history/main.js` `enablePinchZoom` |
| leaflet | `polls/render-map.js` `__mapViewport` | `geomap.ts` `geoFocus`(globalThis, **CI 빌드**) |

history엔 원래 `enablePinchZoom`(핀치·Ctrl+휠·리셋버튼·pan-y)이 있었고 더 나아서, **SvgViewport를 그쪽에
맞춰 수렴**시켰다: Ctrl/⌘+휠만 줌(평소 휠=페이지 스크롤), 안 확대면 `touchAction:pan-y`, 핀치, 더블탭 리셋,
공용 리셋 버튼(`⤢ 전체`, fixed). 둘은 별개 코드지만 조작감 동일. (history에 SvgViewport를 또 붙이면 **충돌**
— 한 번 그 버그를 냈다. history는 native만.)

## 파일별 역할
- **`assets/svg-viewport.js`** — viewBox 팬/줌(커서 앵커 줌은 `getScreenCTM().inverse()`로 letterbox 정확).
  `attach(svg,{baseViewBox,cells})`→handle{report,focusOn,reset,update,isZoomed,detach}. `focusOn`은 rAF
  viewBox 트윈(280ms, 조작 시 취소). **`captureHost/applyHost`**: 글로벌 Focus 없이 host 단위 줌 보존
  (격자↔원형 등 재렌더 토글 — 한 페이지 여러 카토그램 간섭 방지, 보존은 스냅).
- **`assets/viewport-focus.js`** — `window.Focus{state,capture,apply}`. 폴 `chrome.js setView`가 capture→render→apply.
  scale≤1.05면 "전국"으로 보고 no-op(불필요한 포커스 방지).
- **렌더러가 cells/viewBox 반환** → 호출부가 attach/_focusCells. governorHex·drawSigunguHex·
  drawSigunguCartogram·sidoCluster 모두 `{cells:[{region,cx,cy}],viewBox}` 반환. **원형은 force-pack 후
  위치**라 cells도 렌더 뒤 값. history는 `svg._focusCells`에 저장(enablePinchZoom 엔트리가 report/focusOn).
- **leaflet 어댑터** — region centroid 사전계산, `scale=2^(zoom-기준줌)`, `focusOn`은 `flyTo`(0.45s).
  시군구는 일반구→시 롤업·평균(hex 입도와 일치). 폴은 `pendingFocus`로 finalize(초기줌·미니맵) 후 적용.

## 적용 범위(완료)
- 폴: 지도↔균등↔시군구. 종합/폴 시군구 단색↔격자↔원형(council). 대선폴·종합 시도 격자↔원형(sidoCluster).
- 아카이브 시도뷰 균등/격자/원형/투표율 — 탭 교차 포커스 전이(`render-sido-view.js mount`).
- history 균등↔지도(geo 3모드: 총선 지역구·지선 sido/sigungu)·시도·시군구·총선 district hex.

## 엣지 케이스
- 단위 전환(시도↔시군구)은 region 키 네임스페이스가 달라(`서울특별시` vs `서울특별시|종로구`) 자연 분리 —
  안 맞으면 fallback(전국). 대상 레이아웃에 지역 없으면(period·dorling 탈락) 전국 폴백.
- 방식 토글 인맵 오버레이(우상단)는 빽빽한 hex 우상단 셀을 일부 가림 — 줌으로 회피. 이미지 다운/공유
  버튼(`.svg-save-bar`)은 우하단으로 분리.

## 함께 한 것(관련)
- 어휘 통일: hex→**균등**, dorling→**원형**(내부 키 hex/dorling/grid는 보존, 라벨만). 위젯 공용 `.seg`.
- 시군구 카토그램 렌더러 단일화: history `render-sigungu.js`(351→110줄)가 공용 `drawSigunguCartogram`에
  위임. 시점성은 데이터 전처리(`_borrowed`/`_fill`)로 분리. cartogram-util `drawBorders`(구 외곽선 keyFn).
- 대선/총선 지도 클릭→우측 detail 패널(지선 `chrome.renderDetail`/`actualResultFor` 재사용. adapter
  `localActualMaps`에 대선 tc1·비례 tc7·총선 district scope 추가).

## 변경 금지
- 내부 키·data-* 값(hex/dorling/grid/격자). 생성 파일(`assets/history/geomap.js`·`hexgrid.js`)은 직접 편집
  금지 — `src/history/*.ts` 수정 → `npm run build:map`(CI `pages.yml`도 빌드). `.gitignore`가 geomap.js 무시.
