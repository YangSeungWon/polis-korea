// polls.js Leaflet 지도 — 시도·시군구 chloropleth + 미니맵.

// === 지리 지도 (Leaflet) ===

let leafletMap = null;
let sidoLayer = null;
let sigunguLayer = null;
let sidoOutlineLayer = null;  // 시군구 모드에서 위에 오버레이되는 시도 외곽선 전용
let miniMapCtrl = null;
let initialZoom = null;  // sidoLayer 로드 후 fitBounds로 결정
// 한국 경계 — 제주(33) ~ 강원북 (39), 백령(124) ~ 독도(132). 패닝 제한.
const KOREA_BOUNDS = [[32.5, 123.5], [39.5, 132.5]];

function setupMiniMap(sidoData) {
  if (miniMapCtrl || typeof L.Control.MiniMap === 'undefined') return;
  const miniLayer = L.geoJSON(sidoData, {
    style: { color: 'var(--ink-mute, #999)', weight: 0.6, fillColor: 'var(--bg3, #e0e3ea)', fillOpacity: 0.85 },
    interactive: false,
  });
  // 한반도 본토 위주 — 독도/울릉 등 동쪽 outlier 제외해 세로 비율 유지.
  const MAINLAND = L.latLngBounds([32.8, 125.6], [38.8, 130.0]);
  const TARGET_H = 170;
  let miniZoom = initialZoom;
  let sw, ne, miniW, miniH;
  for (let i = 0; i < 8; i++) {
    sw = leafletMap.project(MAINLAND.getSouthWest(), miniZoom);
    ne = leafletMap.project(MAINLAND.getNorthEast(), miniZoom);
    miniH = sw.y - ne.y;
    if (miniH > TARGET_H * 1.4 && miniZoom > 0) { miniZoom--; continue; }
    if (miniH < TARGET_H * 0.7) { miniZoom++; continue; }
    break;
  }
  miniW = Math.ceil(ne.x - sw.x) + 12;
  miniH = Math.ceil(miniH) + 12;
  miniMapCtrl = new L.Control.MiniMap(miniLayer, {
    position: 'bottomleft',
    width: miniW,
    height: miniH,
    toggleDisplay: false,
    zoomLevelFixed: miniZoom,
    centerFixed: MAINLAND.getCenter(),
    aimingRectOptions: {
      color: '#e61e2b',
      weight: 2,
      fillColor: '#e61e2b',
      fillOpacity: 0.15,
    },
  }).addTo(leafletMap);
  // 미니맵 자체는 늘 표시. 빨간 viewport rect은 확대 시에만 노출.
  const updateMini = () => {
    const path = miniMapCtrl._aimingRect && miniMapCtrl._aimingRect._path;
    if (!path) return;
    path.style.display = leafletMap.getZoom() > initialZoom ? '' : 'none';
  };
  leafletMap.on('zoomend', updateMini);
  leafletMap.on('moveend', updateMini);
  setTimeout(updateMini, 0);
}

async function renderMap() {
  if (!leafletMap) {
    leafletMap = L.map('map', {
      zoomControl: true,
      attributionControl: false,
      maxBounds: KOREA_BOUNDS,
      maxBoundsViscosity: 1.0,        // 경계 밖으로 못 끌리게
    });
    // setView는 일단 임시값. sidoLayer 로드 후 fitBounds로 진짜 초기 뷰 잡음.
    leafletMap.setView([35.9, 127.8], 6);
    window.leafletMap = leafletMap;  // debug
  }
  const sigungu = isSigunguMode();

  // GeoJSON 로드 (시도·시군구) — 제주·울릉·서해5도 포함 전체
  if (!sidoLayer) {
    const sidoData = await (await fetch('data/geo/sido_simple.json')).json();
    sidoLayer = L.geoJSON(sidoData, {
      style: (f) => sidoStyle(f),
      onEachFeature: (f, l) => attachSidoClick(f, l),
    });
    // fitBounds → maxBounds 자동 보정까지 다 끝난 뒤 zoom 확정.
    leafletMap.invalidateSize();
    leafletMap.fitBounds(sidoLayer.getBounds(), { padding: [12, 12] });
    const finalize = () => {
      leafletMap.off('moveend', finalize);
      initialZoom = leafletMap.getZoom();
      leafletMap.setMinZoom(initialZoom);
      setupMiniMap(sidoData);
    };
    leafletMap.on('moveend', finalize);
  }
  if (!sigunguLayer) {
    const sigunguData = await (await fetch('data/geo/sigungu_simple.json')).json();
    sigunguLayer = L.geoJSON(sigunguData, {
      style: (f) => sigunguStyle(f),
      onEachFeature: (f, l) => attachSigunguClick(f, l),
    });
  }

  // 시도 외곽 전용 layer (시군구 모드 오버레이용) — 한 번만 생성
  if (!sidoOutlineLayer) {
    const sidoData = sidoLayer.toGeoJSON();
    sidoOutlineLayer = L.geoJSON(sidoData, { style: sidoOutlineStyle, interactive: false });
  }

  // 레이어 swap
  if (sigungu) {
    if (leafletMap.hasLayer(sidoLayer)) leafletMap.removeLayer(sidoLayer);
    if (!leafletMap.hasLayer(sigunguLayer)) sigunguLayer.addTo(leafletMap);
    sigunguLayer.setStyle((f) => sigunguStyle(f));
    sigunguLayer.eachLayer(updateSigunguTooltip);
    if (!leafletMap.hasLayer(sidoOutlineLayer)) sidoOutlineLayer.addTo(leafletMap);
    sidoOutlineLayer.bringToFront();
  } else {
    if (leafletMap.hasLayer(sigunguLayer)) leafletMap.removeLayer(sigunguLayer);
    if (leafletMap.hasLayer(sidoOutlineLayer)) leafletMap.removeLayer(sidoOutlineLayer);
    if (!leafletMap.hasLayer(sidoLayer)) sidoLayer.addTo(leafletMap);
    sidoLayer.setStyle((f) => sidoStyle(f));
    sidoLayer.eachLayer(updateSidoTooltip);
  }

  setTimeout(() => leafletMap.invalidateSize(), 50);
}

function attachSidoClick(feat, layer) {
  const sido = canonSido((feat.properties.name || '').trim());
  layer.on('click', () => {
    state.selectedSido = sido;
    state.selectedSigungu = null;
    renderMap();
    renderDetail();
  });
}

function attachSigunguClick(feat, layer) {
  const code = feat.properties.code || '';
  const sido = sigunguSidoFromCode(code);
  const name = feat.properties.name || '';
  layer.on('click', () => {
    state.selectedSido = sido;
    state.selectedSigungu = name;
    renderMap();
    renderDetail();
  });
}

function updateSidoTooltip(layer) {
  const sido = canonSido((layer.feature.properties.name || '').trim());
  const result = sidoLastWinningParty(sido, state.office);
  const lbl = result ? (result.name || result.party || '') : '';
  const tip = result
    ? `<b>${sido}</b><br>${lbl}${result.name && result.party ? ' (' + result.party + ')' : ''} ${result.pct}%<br>${fmtDate(result.period)} 조사`
    : `<b>${sido}</b><br>조사 없음`;
  layer.bindTooltip(tip, { className: 'sigungu-tooltip', sticky: true });
}

function updateSigunguTooltip(layer) {
  const code = layer.feature.properties.code || '';
  const sido = sigunguSidoFromCode(code);
  const name = layer.feature.properties.name || '';
  const result = sigunguLastWinningParty(sido, name, state.office);
  const tip = result
    ? `<b>${sido} ${name}</b><br>${result.name} (${result.party}) ${result.pct}%<br>${fmtDate(result.period)} 조사`
    : `<b>${sido} ${name}</b><br>조사 없음`;
  layer.bindTooltip(tip, { className: 'sigungu-tooltip', sticky: true });
}

function sidoStyle(feat) {
  const sido = canonSido((feat.properties.name || '').trim());
  const result = sidoLastWinningParty(sido, state.office);
  const sel = state.selectedSido === sido && !state.selectedSigungu;
  const low = result && result.n_polls <= 2;
  return {
    fillColor: result ? partyColor(result.party) : 'var(--bg3, #d8dce4)',
    fillOpacity: result ? gapOpacity(result.effective_gap ?? result.gap) : 0.55,
    color: sel ? 'var(--ink, #0a0e1a)' : 'var(--ink-soft, #2a2f3c)',
    weight: sel ? 2.5 : 1.4,
    opacity: sel ? 1 : 0.7,
    dashArray: low ? '4,3' : null,
  };
}

function sigunguStyle(feat) {
  const code = feat.properties.code || '';
  const sido = sigunguSidoFromCode(code);
  const name = feat.properties.name || '';
  const result = sigunguLastWinningParty(sido, name, state.office);
  const selected = state.selectedSido === sido && state.selectedSigungu === name;
  const low = result && result.n_polls <= 2;
  return {
    fillColor: result ? partyColor(result.party) : 'var(--bg3, #d8dce4)',
    fillOpacity: result ? gapOpacity(result.effective_gap ?? result.gap) : 0.55,
    color: selected ? 'var(--ink, #0a0e1a)' : 'var(--ink-mute, #7a8090)',
    weight: selected ? 2.5 : 0.6,
    dashArray: low ? '3,2' : null,
  };
}

// 시도 외곽선 전용 스타일 (시군구 모드에서 위에 오버레이) — fill 없이 굵은 line
function sidoOutlineStyle() {
  return { fill: false, color: 'var(--ink-soft, #3a4050)', weight: 1.6, opacity: 0.55, interactive: false };
}
