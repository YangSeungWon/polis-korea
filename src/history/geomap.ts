// geomap — history.js 지역구 hex + Leaflet geo 지도 (총선·지선·대선) TS 포팅.
// 빌드: esbuild → assets/history/geomap.js (IIFE). render-district.js + render-local-geo.js 통합.
//   두 파일은 가변 Leaflet 상태(geoLeafletMap·레이어·selection·initialZoom)를 공유해 한 모듈이라야 함.
// 공개(globalThis): renderGeoMap·renderDistrictHex(총선) / renderLocalGeoMap·renderPresGeoMap·
//   presGeoSupported·localGeoSupported(지선·대선). 그 외는 전부 모듈 내부 캡슐화.
// 외부 전역 의존: core.js/data.js(state·loadJson·result*·effectiveCell·canonSido·partyColor 등),
//   Leaflet(L), hexgrid.js(hexPoints·hexCenter·nbrs·NBR_TO_EDGE·corner·drawHexBorders).

// ===== 외부 전역 (다른 classic script가 노출) — ambient 선언, 런타임엔 실제 전역 해소 =====
declare const state: any;
declare const L: any;
declare function loadJson(path: string): Promise<any>;
declare function canonSido(s: string): string;
declare const SIDO_HEX_LAYOUT: any;
declare function partyColor(p: string): string;
declare function pickTextColor(hex: string, opacity?: number): string;
declare function resultForDistrict(sido: string, name: string): any;
declare function resultForSido(name: string): any;
declare function resultForSigungu(sido: string, name: string): any;
declare function effectiveCell(cell: { sido: string; name: string }, date: string): any;
declare function topCandidate(result: any): any;
declare function candLabel(cand: any): string;
declare function fmtUnitName(name: string): string;
declare function periodSidoName(sido: string, date: string): string;
declare function loadDistrictHex(n: number): Promise<any[]>;
declare function drawDistrictHex(svg: any, layout: any[], resultFn: (s: string, n: string) => any, opts?: any): any;
declare function renderDetail(): void;
declare function renderAll(): void;
declare function renderHistoryLegend(): void;
declare function $(sel: string): any;
declare function hexPoints(cx: number, cy: number, r: number): string;
declare function hexCenter(col: number, row: number, colW: number, rowH: number, offX: number, offY: number): [number, number];
declare function nbrs(c: number, r: number): Array<[number, number]>;
declare const NBR_TO_EDGE: number[];
declare function corner(cx: number, cy: number, rad: number, i: number): [number, number];
declare function drawHexBorders(svg: any, cells: any[], cellAt: Map<string, any>, colW: number, rowH: number, offX: number, offY: number, r: number, strokeWidth: string | number, includeOutline?: boolean, keyFn?: (d: any) => string | undefined, lineClass?: string): void;
declare function drawSidoEdgeLabels(svg: any, pts: Array<{ sido: string; cx: number; cy: number }>): void;
declare const SIDO_EDGE_MARGIN: number;

const SVGNS = 'http://www.w3.org/2000/svg';

// =====================================================================================
// === 지역구 hex (총선) — 셀 렌더는 공유 drawDistrictHex(assets/render-district-hex.js).
//     이 파일은 wrapper(renderDistrictHex) + 비례 컬럼만. shortDistrictLabel은 공유로 이관.
// =====================================================================================

// === 21·22대 GeoJSON chloropleth (OhmyNews MIT) + 시도 경계 overlay ===
async function loadGeo(n: number): Promise<void> {
  if (state.geoCache[n] && state.geoMapCache[n]) return;
  const [geo, mapj] = await Promise.all([
    loadJson(`data/geo/district_${n}_geojson.json`),
    loadJson(`data/geo/district_${n}_geojson_map.json`),
  ]);
  state.geoCache[n] = geo;
  state.geoMapCache[n] = mapj.name_to_sgg_code;
}

async function loadSidoGeo(): Promise<void> {
  if (state.geoSido) return;
  state.geoSido = await loadJson('data/geo/sido_simple.json');
}

function _geoDisplayName(p: any, _n: number): string {
  // 22대: SIDO_SGG (예: '서울 강서갑'), 21대: SGG_2 (예: '경기도 고양시갑')
  return p.SIDO_SGG || p.SGG_2 || p.SGG || '';
}

// === Leaflet geomap (21·22대 총선 지역구 chloropleth) ===
// 확대·패닝 + 미니맵 지원. polls.js 패턴 재사용.

let geoLeafletMap: any = null;
let geoDistrictLayer: any = null;    // 현재 회차 layer
const geoDistrictByN: Record<string, any> = {};  // n → L.geoJSON layer (캐시, 재방문 시 재생성 안 함)
let geoSidoOutlineLayer: any = null;
const geoSidoByN: Record<string, any> = {};       // 옛총선(1~7대) 회차별 시도 외곽선(당시 영토·이북 포함)
const periodSidoByYear: Record<string, any> = {}; // 대선·지선 연도별 시도 외곽선(sido_{year}) layer 캐시
// sido_{year} 파일이 있는 연도 — 그 외(2025/2026=현재 경계)는 현대 sido_simple 폴백.
const PERIOD_SIDO_YEARS = new Set([1975, 1985, 1987, 1990, 1995, 2000, 2002, 2006, 2010, 2013]);
let geo38Layer: any = null;          // 38선 참조선(1·2대 = 38선이 국경이던 시기)
let geoMiniMapCtrl: any = null;
let geoInitialZoom: number | null = null;

// 방식 전환(균등↔지도) 포커스 전이 — 현재 geo 레이어의 region→centroid. 키는 hex side와 동일
//   (시도 / 시도|시군구). 각 geo render가 마운트 후 setGeoFocus로 채움. report/focusOn은 globalThis.geoFocus.
let geoFocusCentroids = new Map<string, any>();
function setGeoFocus(layer: any, regionOf: (f: any) => string | null): void {
  geoFocusCentroids = new Map();
  if (!layer) return;
  layer.eachLayer((l: any) => {
    if (!l.getBounds) return;
    const reg = regionOf(l.feature);
    if (reg) geoFocusCentroids.set(reg, l.getBounds().getCenter());
  });
}
const infoRegion = (info: any): string | null =>
  info ? (info.name ? canonSido(info.sido) + '|' + info.name : canonSido(info.sido)) : null;
const geoFocus = {
  report() {
    if (!geoLeafletMap || !geoFocusCentroids.size || geoInitialZoom == null) return { region: null, scale: 1 };
    const c = geoLeafletMap.getCenter();
    const scale = Math.pow(2, geoLeafletMap.getZoom() - (geoInitialZoom as number));
    let best: string | null = null, bd = Infinity;
    geoFocusCentroids.forEach((ll: any, nm: string) => {
      const d = (ll.lat - c.lat) ** 2 + (ll.lng - c.lng) ** 2; if (d < bd) { bd = d; best = nm; }
    });
    return { region: best, scale };
  },
  focusOn(region: string, scale: number) {
    if (!geoLeafletMap) return;
    const ll = region && geoFocusCentroids.get(region);
    const iz = geoInitialZoom != null ? (geoInitialZoom as number) : geoLeafletMap.getZoom();
    if (ll) geoLeafletMap.flyTo(ll, iz + Math.log2(Math.max(1, scale || 1)), { duration: 0.45 });   // 부드러운 전환
  },
};

// 모든 geo 오버레이 제거 — 타입(대선↔총선↔지선)·회차 전환 시 이전 지도 잔류 방지.
// 각 geo render가 시작 시 호출 → 필요한 layer만 다시 추가. (한 모듈 내 공유 가변 상태.)
function clearGeoLayers(): void {
  if (typeof geoLeafletMap === 'undefined' || !geoLeafletMap) return;
  const ls = [geoDistrictLayer, geoSidoOutlineLayer, geo38Layer,
    ...Object.values(geoSidoByN || {}), ...Object.values(periodSidoByYear || {})];
  if (typeof localGeoLayer !== 'undefined') ls.push(localGeoLayer);
  for (const l of ls) {
    if (l && geoLeafletMap.hasLayer(l)) geoLeafletMap.removeLayer(l);
  }
}

// === geo 선택 강조 (총선·지선·대선 공통) — 흰 테두리 + 글로우 + 최상위 ===
let geoSelLayer: any = null;
const _GEO_BASE = { weight: 0.6, color: 'rgba(10,14,26,0.35)' };
function _geoDeselect(): void {
  if (geoSelLayer) {
    try { geoSelLayer.setStyle(_GEO_BASE); geoSelLayer._path?.classList.remove('geo-sel'); } catch {}
    geoSelLayer = null;
  }
}
function _geoSelect(layer: any): void {
  _geoDeselect();
  layer.setStyle({ weight: 3, color: '#fff' });
  layer._path?.classList.add('geo-sel');
  layer.bringToFront();
  geoSelLayer = layer;
}
// 회차/office 전환 등 layer 재생성 시 호출 — stale ref 제거 후, state.selected 있으면 재강조.
function _geoReapplySelection(layerGroup: any, matchFn: (p: any) => boolean): void {
  geoSelLayer = null;
  if (!state.selected || !layerGroup) return;
  layerGroup.eachLayer((l: any) => { if (matchFn(l.feature?.properties)) _geoSelect(l); });
}
const KOREA_BOUNDS_GEO = [[32.5, 123.5], [39.5, 132.5]];

// 중선거구(1구 2인) — 두 당선당 색의 대각 줄무늬 패턴. document 전역 <defs>에 lazy 생성.
const _jungPatIds: Record<string, string> = {};
let _jungPatN = 0;
function _jungPattern(parties: [string, string]): string {
  const key = parties[0] + '|' + parties[1];
  if (_jungPatIds[key]) return `url(#${_jungPatIds[key]})`;
  let host: any = document.getElementById('jung-pat-defs');
  if (!host) {
    host = document.createElementNS(SVGNS, 'svg');
    host.id = 'jung-pat-defs';
    host.setAttribute('style', 'position:absolute;width:0;height:0;overflow:hidden');
    host.appendChild(document.createElementNS(SVGNS, 'defs'));
    document.body.appendChild(host);
  }
  const id = 'jp' + (_jungPatN++);
  _jungPatIds[key] = id;
  const p = document.createElementNS(SVGNS, 'pattern');
  p.id = id;
  p.setAttribute('width', '8'); p.setAttribute('height', '8');
  p.setAttribute('patternUnits', 'userSpaceOnUse');
  p.setAttribute('patternTransform', 'rotate(45)');
  p.innerHTML = `<rect width="8" height="8" fill="${partyColor(parties[0])}"/>`
    + `<rect width="4" height="8" fill="${partyColor(parties[1])}"/>`;
  host.querySelector('defs').appendChild(p);
  return `url(#${id})`;
}

function _districtStyleFor(info: any, approx: any): any {
  let fill = info?.winner?.party ? partyColor(info.winner.party) : 'rgba(154,163,179,0.65)';
  const ws = info?.race?.winners;  // 중선거구: 당선당 2개 → 줄무늬
  if (ws && ws.length >= 2) {
    const ps = ws.map((w: any) => w.party);
    fill = (ps[0] !== ps[1]) ? _jungPattern([ps[0], ps[1]]) : partyColor(ps[0]);
  }
  // approx=옛 도시 갑/을 보로노이 추정 경계 → 점선·약간 진하게(실측 아님 표시)
  return {
    color: approx ? 'rgba(10,14,26,0.6)' : 'rgba(10,14,26,0.35)',
    weight: approx ? 1.0 : 0.6,
    dashArray: approx ? '3 3' : null,
    fillColor: fill,
    fillOpacity: 0.85,
  };
}

function _attachDistrictInteraction(_feature: any, layer: any, info: any, label: string): void {
  layer.bindTooltip(
    info ? `${label} — ${info.winner?.name || ''} (${info.winner?.party || ''})` : label,
    { className: 'sigungu-tooltip', sticky: true, direction: 'auto' }
  );
  if (info) {
    layer.on('mouseover', () => { if (layer !== geoSelLayer) layer.setStyle({ weight: 1.8, color: 'rgba(10,14,26,0.85)' }); });
    layer.on('mouseout', () => { if (layer !== geoSelLayer) layer.setStyle(_GEO_BASE); });
    layer.on('click', () => {
      state.selected = { sido: info.race.sido, name: info.race.name, kind: 'district' };
      _geoSelect(layer);
      renderDetail();
    });
  }
}

function _setupGeoMiniMap(sidoData: any): void {
  if (geoMiniMapCtrl || typeof L.Control.MiniMap === 'undefined') return;
  const miniLayer = L.geoJSON(sidoData, {
    style: { color: 'rgba(10,14,26,0.4)', weight: 0.6, fillColor: 'rgba(230,233,239,0.85)', fillOpacity: 0.85 },
    interactive: false,
  });
  const MAINLAND = L.latLngBounds([32.8, 125.6], [38.8, 130.0]);
  const TARGET_H = 170;
  let miniZoom: number = geoInitialZoom as number;
  let sw: any, ne: any, miniW: number, miniH = 0;
  for (let i = 0; i < 8; i++) {
    sw = geoLeafletMap.project(MAINLAND.getSouthWest(), miniZoom);
    ne = geoLeafletMap.project(MAINLAND.getNorthEast(), miniZoom);
    miniH = sw.y - ne.y;
    if (miniH > TARGET_H * 1.4 && miniZoom > 0) { miniZoom--; continue; }
    if (miniH < TARGET_H * 0.7) { miniZoom++; continue; }
    break;
  }
  miniW = Math.ceil(ne.x - sw.x) + 12;
  miniH = Math.ceil(miniH) + 12;
  geoMiniMapCtrl = new L.Control.MiniMap(miniLayer, {
    position: 'bottomleft',
    width: miniW,
    height: miniH,
    toggleDisplay: false,
    zoomLevelFixed: miniZoom,
    centerFixed: MAINLAND.getCenter(),
    aimingRectOptions: { color: '#e61e2b', weight: 2, fillColor: '#e61e2b', fillOpacity: 0.15 },
  }).addTo(geoLeafletMap);
  const updateMini = () => {
    const path = geoMiniMapCtrl._aimingRect && geoMiniMapCtrl._aimingRect._path;
    if (!path) return;
    path.style.display = geoLeafletMap.getZoom() > (geoInitialZoom as number) ? '' : 'none';
  };
  geoLeafletMap.on('zoomend', updateMini);
  geoLeafletMap.on('moveend', updateMini);
  setTimeout(updateMini, 0);
}

async function renderGeoMap(): Promise<void> {
  const n = state.n;
  await Promise.all([loadGeo(n), loadSidoGeo()]);
  const features = state.geoCache[n]?.features || [];
  if (!features.length) return;
  const sggMap = state.geoMapCache[n];
  const sggToWinner: Record<string, any> = {};
  const districts = state.results?.district || [];
  for (const race of districts) {
    // sggMap 키는 새 sido명(전북특별자치도·강원특별자치도) 기준. 옛 race 데이터(전라북도·강원도)는
    // canonSido로 정규화해 매칭.
    const key = `${canonSido(race.sido)}|${race.name}`;
    const sggCode = sggMap[key];
    if (sggCode == null) continue;
    const winner = (race.candidates || []).find((c: any) => c.won || c.rank === 1) || race.candidates?.[0];
    sggToWinner[String(sggCode)] = { race, winner };
  }

  if (!geoLeafletMap) {
    geoLeafletMap = L.map('geomap', {
      zoomControl: true,
      attributionControl: false,
      maxBounds: KOREA_BOUNDS_GEO,
      maxBoundsViscosity: 1.0,
    });
    geoLeafletMap.setView([35.9, 127.8], 6);
  } else {
    geoLeafletMap.invalidateSize();
  }

  // 모든 geo 오버레이 제거(이전 타입/회차 지도 잔류 방지) → 아래서 현재 회차 것만 재추가.
  clearGeoLayers();

  // 회차별 layer 캐시 — winner 색만 재적용
  if (!geoDistrictByN[n]) {
    geoDistrictByN[n] = L.geoJSON(state.geoCache[n], {
      style: (f: any) => _districtStyleFor(sggToWinner[String(f.properties.SGG_Code)], f.properties.approx),
      onEachFeature: (f: any, l: any) => {
        const info = sggToWinner[String(f.properties.SGG_Code)];
        _attachDistrictInteraction(f, l, info, _geoDisplayName(f.properties, n));
      },
    });
  } else {
    // 캐시된 layer는 style/tooltip만 갱신
    geoDistrictByN[n].eachLayer((l: any) => {
      const f = l.feature;
      const info = sggToWinner[String(f.properties.SGG_Code)];
      l.setStyle(_districtStyleFor(info, f.properties.approx));
      l.unbindTooltip();
      _attachDistrictInteraction(f, l, info, _geoDisplayName(f.properties, n));
    });
  }
  geoDistrictLayer = geoDistrictByN[n];
  geoDistrictLayer.addTo(geoLeafletMap);
  setGeoFocus(geoDistrictLayer, (f: any) => {   // 포커스 전이용 — 선거구 region(시도|선거구명)
    const info = sggToWinner[String(f.properties.SGG_Code)];
    return info ? canonSido(info.race.sido) + '|' + info.race.name : null;
  });
  // 선택 강조 재적용 (회차 전환 시 stale ref 제거 + 같은 선거구 재강조)
  _geoReapplySelection(geoDistrictLayer, (p) => {
    const info = sggToWinner[String(p?.SGG_Code)];
    return info && info.race.sido === state.selected?.sido && info.race.name === state.selected?.name;
  });

  // 시도 외곽선 — 옛총선(1~7대)은 그 회차 선거구 dissolve 외곽선(당시 영토·이북 포함, 현대
  // 휴전선 X). 그 외(8~22대, 휴전선 이남)는 현대 sido_simple 공용 외곽선.
  const SIDO_STYLE = { color: 'rgba(10,14,26,0.9)', weight: 2.4, fill: false, lineJoin: 'round' };
  // 회차별 시도 외곽선(district_{n}_sido) — 광역시도 그 회차 승격 기준이라 시대 정합.
  // 파일 없는 회차(21대 등, 현대와 동일)는 현대 sido_simple 폴백.
  let outline: any = null;
  if (geoSidoByN[n] === undefined) {
    geoSidoByN[n] = await loadJson(`data/geo/district_${n}_sido.json`)
      .then((od) => L.geoJSON(od, { style: SIDO_STYLE, interactive: false }))
      .catch(() => null);
  }
  outline = geoSidoByN[n];
  if (!outline) {
    if (!geoSidoOutlineLayer && state.geoSido) {
      geoSidoOutlineLayer = L.geoJSON(state.geoSido, { style: SIDO_STYLE, interactive: false });
    }
    outline = geoSidoOutlineLayer;
  }
  // 회차 전환 시 다른 외곽선 제거 후 현재 것만 표시 (모던 ↔ 회차별)
  for (const l of [geoSidoOutlineLayer, ...Object.values(geoSidoByN)]) {
    if (l && l !== outline && geoLeafletMap.hasLayer(l)) geoLeafletMap.removeLayer(l);
  }
  if (outline && !geoLeafletMap.hasLayer(outline)) outline.addTo(geoLeafletMap);
  if (outline) outline.bringToFront();

  // 38선 참조선 — 1·2대(1948·50)는 38선이 국경이었음. 그 이후는 휴전선이라 미표시.
  if (!geo38Layer) {
    geo38Layer = L.layerGroup([
      L.polyline([[38.0, 124.2], [38.0, 130.9]],
        { color: '#c0392b', weight: 1.5, dashArray: '6 5', opacity: 0.75, interactive: false }),
      L.marker([38.0, 124.5], { interactive: false, icon: L.divIcon({
        className: 'line38-label', html: '38선', iconSize: [34, 16], iconAnchor: [0, 18] }) }),
    ]);
  }
  const show38 = [1, 2].includes(n);
  if (show38 && !geoLeafletMap.hasLayer(geo38Layer)) geo38Layer.addTo(geoLeafletMap);
  else if (!show38 && geoLeafletMap.hasLayer(geo38Layer)) geoLeafletMap.removeLayer(geo38Layer);
  if (show38) geo38Layer.eachLayer((l: any) => l.bringToFront && l.bringToFront());

  // 초기 fitBounds + minimap (한 번만)
  if (geoInitialZoom == null) {
    const bounds = geoDistrictLayer.getBounds();
    geoLeafletMap.fitBounds(bounds, { padding: [12, 12] });
    const finalize = () => {
      geoLeafletMap.off('moveend', finalize);
      geoInitialZoom = geoLeafletMap.getZoom();
      geoLeafletMap.setMinZoom(geoInitialZoom);
      if (state.geoSido) _setupGeoMiniMap(state.geoSido);
    };
    geoLeafletMap.on('moveend', finalize);
  }
  // geo 로드 완료 후 범례 갱신 (옛총선 점선 추정경계 안내 — geoCache 준비된 뒤라야 감지)
  if (typeof renderHistoryLegend === 'function') renderHistoryLegend();
}


async function renderDistrictHex(): Promise<void> {
  const layout = await loadDistrictHex(state.n);
  const svg = $('#hex2');
  // 254 지역구 셀 코어(+중선거구 조랭이떡·시도경계·라벨)는 공유 렌더러 재사용.
  const geom = drawDistrictHex(svg, layout, resultForDistrict, {
    topFn: topCandidate,
    textColor: (fill: string, op?: number) => pickTextColor(fill, op),
    selected: state.selected,
    onSelect: (sido: string, name: string) => { state.selected = { sido, name, kind: 'district' }; renderAll(); },
  });
  if (!geom) return;
  (svg as any)._focusCells = (geom as any).cells;   // 총선 균등↔지도 포커스 전이 앵커
  const { colW, rowH, w, h, r, minR, maxR } = geom;

  // 비례대표 — 정당별 세로 col, 지역구 hex 우측에 배치. 사이즈는 지역구와 동일(r=22).
  // 같은 col 안 vertical pitch = 1.5r (격자 hex 표준, odd col 0.5 row shift로 interlock).
  const propSeats = state.results?.national?.proportional_seats || [];
  if (propSeats.length) {
    const totalProp = propSeats.reduce((s: number, p: any) => s + p.seats, 0);
    const totalSeats = layout.length + totalProp;
    const sorted = [...propSeats].sort((a: any, b: any) => b.seats - a.seats);
    const ns = SVGNS;

    const propGap = colW * 0.8 + SIDO_EDGE_MARGIN;   // 지역구와 비례 영역 사이 여백(+동쪽 시도 라벨 열 공간)
    const propStartX = w + propGap;      // 비례 첫 col 좌측 base
    const labelOffsetY = -rowH * 0.6;    // 정당 라벨 baseline (첫 hex 위쪽)

    // 헤더 (지역구 위쪽 여백, 비례 영역 상단)
    const headerY = labelOffsetY * 2;    // 정당 라벨보다 더 위
    const sectionLabel = document.createElementNS(ns, 'text');
    sectionLabel.setAttribute('x', String(propStartX));
    sectionLabel.setAttribute('y', String(headerY));
    sectionLabel.setAttribute('font-size', '12');
    sectionLabel.setAttribute('font-weight', '700');
    sectionLabel.setAttribute('fill', '#0a0e1a');
    sectionLabel.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
    // 비지역구 의석 명칭 — 시대별(총선): 6~8·11~16대 전국구, 9·10대 유정회, 17대~ 비례대표.
    const propKind = state.type === 'national_assembly'
      ? (state.n === 9 || state.n === 10 ? '유정회' : state.n <= 16 ? '전국구' : '비례대표')
      : '비례대표';
    sectionLabel.textContent = `${propKind} ${totalProp}석 · 총 ${totalSeats}석`;
    svg.appendChild(sectionLabel);

    // 정당당 N col 블록 — 의석 많으면 col 수를 늘려(2~6) 세로 길이를 지역구 hex 높이에 맞춤.
    // (유정회·민정당 전국구 73석을 2열로 하면 37줄로 과도하게 길어짐 → 3·4열로 적응.)
    // flat-top 육각형(30° 회전) — 세로 column 정렬에 벌집처럼 맞물림(지역구는 pointy-top).
    const flatHex = (cx: number, cy: number, rr: number) => {
      const p: string[] = [];
      for (let i = 0; i < 6; i++) {
        const a = (Math.PI / 3) * i;
        p.push(`${(cx + rr * Math.cos(a)).toFixed(1)},${(cy + rr * Math.sin(a)).toFixed(1)}`);
      }
      return p.join(' ');
    };
    const fColPitch = r * 1.5;                       // flat-top 열 간격(폭 2r의 3/4)
    const fRowPitch = r * Math.sqrt(3);              // flat-top 행 간격(높이)
    const hexRows = Math.max(1, maxR - minR + 1);   // 지역구 hex 높이(행) = 비례 블록 목표 높이
    const blockGap = r * 0.7;                        // 정당 블록 사이 여백
    let maxColH = 0;
    let blockX = propStartX;
    sorted.forEach((ps: any) => {
      const cols = Math.min(6, Math.max(2, Math.ceil(ps.seats / hexRows)));
      const blockW = (cols - 1) * fColPitch + 2 * r;
      const color = partyColor(ps.party);
      const labelCx = blockX + blockW / 2;
      // 정당 라벨 (블록 중앙 위)
      const nm = document.createElementNS(ns, 'text');
      nm.setAttribute('x', String(labelCx));
      nm.setAttribute('y', String(labelOffsetY));
      nm.setAttribute('text-anchor', 'middle');
      nm.setAttribute('font-size', '11');
      nm.setAttribute('font-weight', '700');
      nm.setAttribute('fill', color);
      nm.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
      nm.textContent = `${ps.party} ${ps.seats}`;
      svg.appendChild(nm);
      // 의석 flat-top hex — row-major(좌→우 채우고 다음 행), 홀수 col 0.5행 내려 벌집 맞물림.
      for (let j = 0; j < ps.seats; j++) {
        const col = j % cols;
        const row = Math.floor(j / cols);
        const cx = blockX + r + col * fColPitch;
        const cy = row * fRowPitch + r + (col % 2) * (fRowPitch / 2);
        const poly = document.createElementNS(ns, 'polygon');
        poly.setAttribute('points', flatHex(cx, cy, r - 0.7));
        poly.setAttribute('fill', color);
        poly.setAttribute('stroke', '#fff');
        poly.setAttribute('stroke-width', '1');
        const tt = document.createElementNS(ns, 'title');
        tt.textContent = `${propKind} ${ps.party} ${j + 1}/${ps.seats}석`;
        poly.appendChild(tt);
        svg.appendChild(poly);
      }
      const rows = Math.ceil(ps.seats / cols);
      const colH = rows * fRowPitch + fRowPitch / 2 + r;
      if (colH > maxColH) maxColH = colH;
      blockX += blockW + blockGap;
    });

    // viewBox 확장 — 우측 비례 + 위쪽 라벨 영역까지
    const newW = blockX + propGap;
    const topPad = -headerY + 8;
    const newH = Math.max(h, maxColH) + topPad;
    const minY = headerY - 8;
    svg.setAttribute('viewBox', `${-SIDO_EDGE_MARGIN} ${Math.floor(minY)} ${Math.ceil(newW) + SIDO_EDGE_MARGIN} ${Math.ceil(newH)}`);
  }
}

// =====================================================================================
// === 지선·대선 geo chloropleth (render-local-geo.js) ===
//   지선: 광역장/교육감 시도, 기초장 시군구 (단색 winner — 단체장 1명 당선이라 정확).
//   대선: 시군구 margin 명도 (박빙 옅게·압승 진하게 — 승자독식 단색 회피).
//   총선 renderGeoMap의 Leaflet 인프라(geoLeafletMap·mini-map·sido outline)를 재사용.
// =====================================================================================

let localGeoLayer: any = null;        // 현재 표시 중 layer
let localGeoSidoData: any = null;     // sido_simple.json (광역장/교육감)
const localGeoSggCache: Record<string, any> = {};  // year|'simple' → sigungu GeoJSON (회차별 period-correct 경계)

// 기초장 시군구 geo — 회차별 SGIS 시군구 경계 연도(통합전 시군구 반영).
const LOCAL_SGG_GEO_YEAR: Record<number, number> = { 1: 1995, 2: 2000, 3: 2002, 4: 2006, 5: 2010, 6: 2025, 7: 2025, 8: 2025, 9: 2026 };

// 대선 시군구 geo — 15대(1997)부터. (13·14대는 1995 도농통합 전 시군구라 맞는 경계 파일 없음.)
const PRES_SGG_GEO_YEAR: Record<number, number> = {
  2: 1975, 3: 1975, 4: 1975, 5: 1975, 6: 1975, 7: 1975,
  13: 1987, 14: 1990, 15: 2000, 16: 2002, 17: 2006, 18: 2013, 19: 2025, 20: 2025, 21: 2025,
};
const PRES_GEO_ROUNDS = [2, 3, 4, 5, 6, 7, 13, 14, 15, 16, 17, 18, 19, 20, 21];
// HGIS 시간축 경계로 복원된 옛 대선 회차 — sigungu_hgis_{n} + sido_hgis_{n} 사용(그 선거일 실제 경계).
// 그 외(13~21)는 PRES_SGG_GEO_YEAR의 SGIS 연도 경계. (build_sigungu_hgis.py로 회차 추가 시 여기 등록.)
const PRES_HGIS_ROUNDS = new Set([2, 3, 4, 5, 6, 7]);

async function loadSggGeoByYear(y: number | undefined): Promise<any> {
  const key = y || 'simple';
  if (!localGeoSggCache[key]) {
    localGeoSggCache[key] = await loadJson(y ? `data/geo/sigungu_${y}.json` : 'data/geo/sigungu_simple.json');
  }
  return localGeoSggCache[key];
}
// 임의 경계 파일 캐시 로더 (HGIS 회차 등).
async function loadSggGeoFile(cacheKey: string, path: string): Promise<any> {
  if (!localGeoSggCache[cacheKey]) localGeoSggCache[cacheKey] = await loadJson(path);
  return localGeoSggCache[cacheKey];
}
const loadLocalSggGeo = (n: number) => loadSggGeoByYear(LOCAL_SGG_GEO_YEAR[n]);

function presGeoSupported(n: number): boolean {
  return state.type === 'presidential' && PRES_GEO_ROUNDS.includes(n);
}

// 통계청 시도 2자리 코드 → canon 시도명 (resultForSigungu는 canonSido(data.sido)와 === 비교).
const LOCAL_SIDO_CODE2: Record<string, string> = {
  '11': '서울특별시', '21': '부산광역시', '22': '대구광역시', '23': '인천광역시',
  '24': '광주광역시', '25': '대전광역시', '26': '울산광역시', '29': '세종특별자치시',
  '31': '경기도', '32': '강원특별자치도', '33': '충청북도', '34': '충청남도',
  '35': '전북특별자치도', '36': '전라남도', '37': '경상북도', '38': '경상남도',
  '39': '제주특별자치도',
};

function localGeoSupported(_unit: string, _n: number): boolean {
  if (state.type !== 'local') return false;
  return true;   // 시도(전 회차) + 시군구(1~6 회차별 복원경계, 7~9 현재경계) 모두 지원
}

async function renderLocalGeoMap(unit: string): Promise<void> {
  const isSido = unit === 'sido';
  if (isSido && !localGeoSidoData) localGeoSidoData = await loadJson('data/geo/sido_simple.json');
  await loadSidoGeo();
  const geoData = isSido ? localGeoSidoData : await loadLocalSggGeo(state.n);
  if (!geoData?.features?.length) return;

  const el = (state.elections[state.type]?.elections || []).find((x: any) => x.n === state.n);
  const electionDate = el?.date || '';

  // feature props → { winner, race } (없으면 null → 회색)
  const infoFor = (props: any) => {
    if (isSido) {
      const r = resultForSido(props.name);
      if (!r?.candidates?.length) return null;
      return { sido: props.name, name: '', winner: r.candidates[0],
               race: { sido: props.name, name: '', candidates: r.candidates, scope: 'sido' } };
    }
    const sidoName = LOCAL_SIDO_CODE2[String(props.code).slice(0, 2)];
    if (!sidoName) return null;
    // hex와 동일 lifecycle — 신설·폐지·옛이름 alias 적용 후 매칭.
    const eff = effectiveCell({ sido: sidoName, name: props.name }, electionDate);
    if (!eff) return null;
    const r = resultForSigungu(eff.sido, eff.name);
    if (!r?.candidates?.length) return null;
    return { sido: eff.sido, name: eff.name, winner: r.candidates[0],
             race: { sido: eff.sido, name: eff.name, candidates: r.candidates, scope: 'sigungu' } };
  };
  const labelFor = (props: any) => isSido
    ? props.name
    : `${periodSidoName(LOCAL_SIDO_CODE2[String(props.code).slice(0, 2)] || '', electionDate)} ${fmtUnitName(props.name)}`.trim();
  // 시도(광역장) base는 sido_simple 자체 → period 외곽선 불필요(null). 기초장 시군구는 그 회차 연도 경계.
  _mountSggGeo(geoData, infoFor, _localStyleFor, labelFor, isSido ? null : LOCAL_SGG_GEO_YEAR[state.n]);
}

// 대선 시군구 geo — margin 명도(16~21). 13~15대는 시군구 미수집 → 시도 hex(margin 명도)로 표시(activeUnit).
async function renderPresGeoMap(): Promise<void> {
  await loadSidoGeo();
  const n = state.n;
  // HGIS 회차는 그 선거일 실제 경계(sigungu_hgis_{n}), 그 외는 SGIS 연도 경계(sigungu_{year}).
  const useHgis = PRES_HGIS_ROUNDS.has(n);
  const geoData = useHgis
    ? await loadSggGeoFile(`hgis_${n}`, `data/geo/sigungu_hgis_${n}.json`)
    : await loadSggGeoByYear(PRES_SGG_GEO_YEAR[n]);
  const outlineKey = useHgis ? `hgis_${n}` : PRES_SGG_GEO_YEAR[n];
  if (!geoData?.features?.length) return;
  const el = (state.elections[state.type]?.elections || []).find((x: any) => x.n === state.n);
  const electionDate = el?.date || '';
  const infoFor = (props: any) => {
    const sidoName = LOCAL_SIDO_CODE2[String(props.code).slice(0, 2)];
    if (!sidoName) return null;
    const eff = effectiveCell({ sido: sidoName, name: props.name }, electionDate);
    if (!eff) return null;
    const r = resultForSigungu(eff.sido, eff.name);
    if (!r?.candidates?.length) return null;
    return { sido: eff.sido, name: eff.name, winner: r.candidates[0], second: r.candidates[1] || null,
             race: { sido: eff.sido, name: eff.name, candidates: r.candidates, scope: 'sigungu' } };
  };
  const labelFor = (props: any) => `${periodSidoName(LOCAL_SIDO_CODE2[String(props.code).slice(0, 2)] || '', electionDate)} ${fmtUnitName(props.name)}`.trim();
  _mountSggGeo(geoData, infoFor, _presStyleFor, labelFor, outlineKey);
}

const SIDO_OUTLINE_STYLE = { color: 'rgba(10,14,26,0.9)', weight: 2.4, fill: false, lineJoin: 'round' };
// 대선·지선 시도 외곽선 — key가 연도(sido_{year}) 또는 'hgis_{n}'(sido_hgis_{n}, 옛 회차 HGIS 경계)면
// 그 시점 경계로, 없으면(2025/2026=현재) 현대 sido_simple 폴백. 캐시(key 문자열).
async function _sidoOutline(key: string | number | null): Promise<any> {
  const k = key == null ? null : String(key);
  const attempt = k != null && (k.startsWith('hgis_') || PERIOD_SIDO_YEARS.has(Number(k)));
  if (attempt && k) {
    if (periodSidoByYear[k] === undefined) {
      periodSidoByYear[k] = await loadJson(`data/geo/sido_${k}.json`)
        .then((od) => L.geoJSON(od, { style: SIDO_OUTLINE_STYLE, interactive: false }))
        .catch(() => null);
    }
    if (periodSidoByYear[k]) return periodSidoByYear[k];
  }
  if (!geoSidoOutlineLayer && state.geoSido) {
    geoSidoOutlineLayer = L.geoJSON(state.geoSido, { style: SIDO_OUTLINE_STYLE, interactive: false });
  }
  return geoSidoOutlineLayer;
}

// Leaflet 마운트 공유 — layer 교체·시도 외곽선·fit·minimap. (지선/대선 공통)
// outlineKey: 시도 외곽선 소스 — 연도(sido_{year}) 또는 'hgis_{n}'(sido_hgis_{n}); null이면 현대 sido_simple.
async function _mountSggGeo(geoData: any, infoFor: (p: any) => any, styleFor: (info: any) => any, labelFor: (p: any) => string, outlineKey: string | number | null = null): Promise<void> {
  if (!geoLeafletMap) {
    geoLeafletMap = L.map('geomap', {
      zoomControl: true, attributionControl: false,
      maxBounds: KOREA_BOUNDS_GEO, maxBoundsViscosity: 1.0,
    });
    geoLeafletMap.setView([35.9, 127.8], 6);
  } else {
    geoLeafletMap.invalidateSize();
  }
  // 모든 geo 오버레이 제거(총선 지역구·38선·옛 시도외곽선 등 잔류 방지) → 아래서 필요한 것만 재추가.
  clearGeoLayers();

  localGeoLayer = L.geoJSON(geoData, {
    style: (f: any) => styleFor(infoFor(f.properties)),
    onEachFeature: (f: any, l: any) => _attachLocalInteraction(f, l, infoFor(f.properties), labelFor(f.properties)),
  });
  localGeoLayer.addTo(geoLeafletMap);
  setGeoFocus(localGeoLayer, (f: any) => infoRegion(infoFor(f.properties)));   // 포커스 전이용 centroid
  // 선택 강조 재적용 (office/회차 전환 시 stale ref 제거 + 같은 지역 재강조)
  _geoReapplySelection(localGeoLayer, (p) => {
    const info = infoFor(p);
    if (!info) return false;
    return info.race.scope === 'sido'
      ? (info.sido === state.selected?.sido && !state.selected?.name)
      : (info.sido === state.selected?.sido && info.name === state.selected?.name);
  });

  // 시도 외곽선 overlay — period 우선(sido_{year}/sido_hgis_{n}), 없으면 현대 sido_simple.
  const outline = await _sidoOutline(outlineKey);
  // 회차/연도 전환 시 다른 시도 외곽선(현대/타 연도) 제거 후 현재 것만 표시.
  for (const l of [geoSidoOutlineLayer, ...Object.values(periodSidoByYear)]) {
    if (l && l !== outline && geoLeafletMap.hasLayer(l)) geoLeafletMap.removeLayer(l);
  }
  if (outline && !geoLeafletMap.hasLayer(outline)) outline.addTo(geoLeafletMap);
  if (outline) outline.bringToFront();

  if (geoInitialZoom == null) {
    geoLeafletMap.fitBounds(localGeoLayer.getBounds(), { padding: [12, 12] });
    const finalize = () => {
      geoLeafletMap.off('moveend', finalize);
      geoInitialZoom = geoLeafletMap.getZoom();
      geoLeafletMap.setMinZoom(geoInitialZoom);
      if (state.geoSido) _setupGeoMiniMap(state.geoSido);
    };
    geoLeafletMap.on('moveend', finalize);
  }
}

// 지선 단색 스타일 — 당선자 있으면 partyColor(없는당='' → 교육감 #777777, hex와 동일),
// 데이터 없으면 no-data 회색.
function _localStyleFor(info: any): any {
  const fill = info ? partyColor(info.winner?.party || '') : 'rgba(154,163,179,0.65)';
  return { color: 'rgba(10,14,26,0.35)', weight: 0.6, fillColor: fill, fillOpacity: 0.85 };
}

// 대선 margin 명도 — 1위 정당색을 격차(1위-2위 %p)에 따라 흰색쪽으로 옅게.
// 박빙(0%p)≈옅음, 압승(40%p+)=원색. 승자독식 단색 착시 회피(미국 purple-map 방식).
function _hex2rgb(h: string): [number, number, number] {
  h = String(h).replace('#', '');
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
function _mixWhite(hex: string, t: number): string {       // t=0 → 흰색, t=1 → 원색
  const [r, g, b] = _hex2rgb(hex);
  const m = (c: number) => Math.round(255 + (c - 255) * t);
  return `rgb(${m(r)},${m(g)},${m(b)})`;
}
function _presStyleFor(info: any): any {
  if (!info) return { color: 'rgba(10,14,26,0.25)', weight: 0.5, fillColor: 'rgba(154,163,179,0.4)', fillOpacity: 0.55 };
  const margin = (info.winner?.pct || 0) - (info.second?.pct || 0);
  const t = Math.max(0.18, Math.min(1, margin / 40));   // 0~40%p → 0.18~1.0
  return { color: 'rgba(10,14,26,0.3)', weight: 0.5, fillColor: _mixWhite(partyColor(info.winner?.party || ''), t), fillOpacity: 0.92 };
}

function _attachLocalInteraction(_feature: any, layer: any, info: any, label: string): void {
  let tip = label;
  if (info) {
    tip = `${label} — ${candLabel(info.winner)} (${info.winner?.party || ''})`;
    if (info.second) tip += ` +${((info.winner?.pct || 0) - (info.second?.pct || 0)).toFixed(1)}%p`;  // 대선 격차
  }
  layer.bindTooltip(tip, { className: 'sigungu-tooltip', sticky: true, direction: 'auto' });
  if (info) {
    layer.on('mouseover', () => { if (layer !== geoSelLayer) layer.setStyle({ weight: 1.8, color: 'rgba(10,14,26,0.85)' }); });
    layer.on('mouseout', () => { if (layer !== geoSelLayer) layer.setStyle(_GEO_BASE); });
    layer.on('click', () => {
      state.selected = info.race.scope === 'sido'
        ? { sido: info.sido }
        : { sido: info.sido, name: info.name, kind: 'sigungu' };
      _geoSelect(layer);
      renderDetail();
    });
  }
}

// ===== 공개 — 바닐라 main.js·render-sigungu.js가 전역으로 호출 (빌드 IIFE가 노출) =====
Object.assign(globalThis as unknown as Record<string, unknown>, {
  renderGeoMap, renderDistrictHex,
  renderLocalGeoMap, renderPresGeoMap, presGeoSupported, localGeoSupported,
  geoFocus,
});
