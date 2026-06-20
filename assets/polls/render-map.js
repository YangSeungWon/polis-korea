// polls.js Leaflet 지도 — 시도·시군구 chloropleth + 미니맵.

// === 지리 지도 (Leaflet) ===

let leafletMap = null;
let sidoLayer = null;
let sigunguLayer = null;
let sidoOutlineLayer = null;  // 시군구 모드에서 위에 오버레이되는 시도 외곽선 전용
let miniMapCtrl = null;
let initialZoom = null;  // sidoLayer 로드 후 fitBounds로 결정
// 줌·포커스 인프라(viewport-focus) — 시도 centroid·기준 줌·준비 플래그·대기 포커스.
let sidoCentroids = null;     // Map(canonSido → LatLng)
let sigunguCentroids = null;  // Map('canonSido|시군구명' → LatLng)
let focusBaseZoom = null;   // scale=1 기준 줌(getBoundsZoom, finalize 무관하게 일찍 확정)
let mapReady = false;       // 첫 finalize(초기 줌·미니맵) 완료 후 true
let pendingFocus = null;    // finalize 전에 들어온 포커스는 보류 후 적용(initialZoom 기준 안 틀어지게)
// 한국 경계 — 제주(33) ~ 강원북 (39), 백령(124) ~ 독도(132). 패닝 제한.
const KOREA_BOUNDS = [[32.5, 123.5], [39.5, 132.5]];

// 현재 모드(시도/시군구)에 맞는 centroid·fit 레이어 — region 키 네임스페이스가 달라(시도 vs 시도|구) 안 겹침.
function focusCents() { return (typeof isSigunguMode === 'function' && isSigunguMode()) ? sigunguCentroids : sidoCentroids; }
function focusFitLayer() { return (typeof isSigunguMode === 'function' && isSigunguMode()) ? (sigunguLayer || sidoLayer) : sidoLayer; }

// region 앵커 포커스 적용 — region centroid로 setView(배율→줌). 없으면 현 모드 전체 fit.
function mapApplyFocus(region, scale) {
  if (!leafletMap) return;
  const iz = (focusBaseZoom != null) ? focusBaseZoom : (initialZoom != null ? initialZoom : leafletMap.getZoom());
  const cents = focusCents();
  const ll = region && cents && cents.get(region);
  if (ll) leafletMap.flyTo(ll, iz + Math.log2(Math.max(1, scale || 1)), { duration: 0.45 });   // 부드러운 전환
  else { const lyr = focusFitLayer(); if (lyr) leafletMap.fitBounds(lyr.getBounds(), { padding: [12, 12] }); }
}

// leaflet 뷰포트 어댑터 — report/focusOn(viewport-focus 규약). 모드별 centroid 사용.
window.__mapViewport = {
  report() {
    const cents = focusCents();
    if (!leafletMap || !cents) return { region: null, scale: 1 };
    const c = leafletMap.getCenter();
    const iz = (focusBaseZoom != null) ? focusBaseZoom : leafletMap.getZoom();
    const scale = Math.pow(2, leafletMap.getZoom() - iz);
    let best = null, bd = Infinity;
    cents.forEach((ll, nm) => {
      const d = (ll.lat - c.lat) ** 2 + (ll.lng - c.lng) ** 2;
      if (d < bd) { bd = d; best = nm; }
    });
    return { region: best, scale };
  },
  focusOn(region, scale) {
    if (!leafletMap) return;
    if (!mapReady) { pendingFocus = { region, scale }; return; }  // finalize 후 적용
    mapApplyFocus(region, scale);
  },
};

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
    // 시도 region → centroid·기준 줌(포커스 전환용). getBoundsZoom은 맵을 안 움직이는 순수 계산이라
    // finalize(moveend) 전에 일찍 확정 — 포커스 setView가 initialZoom 산정을 방해하지 않게.
    sidoCentroids = new Map();
    sidoLayer.eachLayer((l) => {
      const nm = (typeof canonSido === 'function') ? canonSido((l.feature?.properties?.name || '').trim()) : (l.feature?.properties?.name || '').trim();
      if (nm && l.getBounds) sidoCentroids.set(nm, l.getBounds().getCenter());
    });
    try { focusBaseZoom = leafletMap.getBoundsZoom(sidoLayer.getBounds(), false, L.point(12, 12)); } catch (e) { focusBaseZoom = null; }
    // fitBounds → maxBounds 자동 보정까지 다 끝난 뒤 zoom 확정.
    leafletMap.invalidateSize();
    leafletMap.fitBounds(sidoLayer.getBounds(), { padding: [12, 12] });
    const finalize = () => {
      leafletMap.off('moveend', finalize);
      initialZoom = leafletMap.getZoom();
      leafletMap.setMinZoom(initialZoom);
      setupMiniMap(sidoData);
      mapReady = true;
      if (pendingFocus) { const pf = pendingFocus; pendingFocus = null; mapApplyFocus(pf.region, pf.scale); }
    };
    leafletMap.on('moveend', finalize);
  }
  if (!sigunguLayer) {
    const sigunguData = await (await fetch('data/geo/sigungu_simple.json')).json();
    sigunguLayer = L.geoJSON(sigunguData, {
      style: (f) => sigunguStyle(f),
      onEachFeature: (f, l) => attachSigunguClick(f, l),
    });
    // 시군구 region(시도|구) → centroid (포커스 전환용). hex는 일반구를 시 한 칸으로 합치므로
    // (수원시장안구→수원시) leaflet도 부모 시로 롤업·평균해 입도를 맞춤(키 양방향 일치).
    const acc = new Map();
    sigunguLayer.eachLayer((l) => {
      const code = l.feature?.properties?.code || '';
      let nm = l.feature?.properties?.name || '';
      const sd0 = periodSido(nm, sigunguSidoFromCode(code));
      const sd = (typeof canonSido === 'function') ? canonSido(sd0) : sd0;
      const parent = (typeof parentSigungu === 'function') ? parentSigungu(nm) : null;
      if (parent) nm = parent;   // 일반구→시 롤업(다른 시군구는 그대로)
      if (!sd || !nm || !l.getBounds) return;
      const ctr = l.getBounds().getCenter();
      const a = acc.get(sd + '|' + nm) || { lat: 0, lng: 0, n: 0 };
      a.lat += ctr.lat; a.lng += ctr.lng; a.n += 1; acc.set(sd + '|' + nm, a);
    });
    sigunguCentroids = new Map();
    acc.forEach((a, key) => sigunguCentroids.set(key, L.latLng(a.lat / a.n, a.lng / a.n)));
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

// 시도 이동 보정 — geo는 현행 경계(군위=대구)지만 회차 시점엔 경북(2023.7.1 전입). 폴 회차 날짜로 보정.
//   (균등 hex는 회차별 sigungu_hex_local 레이아웃이라 이미 그 시점 sido. geo만 현행이라 어긋남.)
function periodSido(name, sido) {
  if (name === '군위군' && (POLL_ELECTION.date || '9999') < '2023-07-01') return '경상북도';
  return sido;
}

function attachSigunguClick(feat, layer) {
  const code = feat.properties.code || '';
  const name = feat.properties.name || '';
  const sido = periodSido(name, sigunguSidoFromCode(code));
  layer.on('click', () => {
    state.selectedSido = sido;
    state.selectedSigungu = name;
    renderMap();
    renderDetail();
  });
}

function updateSidoTooltip(layer) {
  const sido = canonSido((layer.feature.properties.name || '').trim());
  const result = regionSidoWinner(sido, state.office);
  const lbl = result ? (result.name || result.party || '') : '';
  const tip = result
    ? `<b>${sido}</b><br>${lbl}${result.name && result.party ? ' (' + result.party + ')' : ''} ${result.pct}%<br>${fmtDate(result.period)} 조사`
    : `<b>${sido}</b><br>조사 없음`;
  layer.bindTooltip(tip, { className: 'sigungu-tooltip', sticky: true });
}

function updateSigunguTooltip(layer) {
  const code = layer.feature.properties.code || '';
  const name = layer.feature.properties.name || '';
  const sido = periodSido(name, sigunguSidoFromCode(code));
  const result = regionSigunguWinner(sido, name, state.office);
  const tip = result
    ? `<b>${sido} ${name}</b><br>${result.name} (${result.party}) ${result.pct}%<br>${fmtDate(result.period)} 조사`
    : `<b>${sido} ${name}</b><br>조사 없음`;
  layer.bindTooltip(tip, { className: 'sigungu-tooltip', sticky: true });
}

// 여론조사 빗나감 점선 테두리는 지도(geo)에선 미표시 — 윤곽선을 가려 이상함. 균등 hex(render-sigungu-hex 등)에서만 표시.

function sidoStyle(feat) {
  const sido = canonSido((feat.properties.name || '').trim());
  const result = regionSidoWinner(sido, state.office);
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
  const name = feat.properties.name || '';
  const sido = periodSido(name, sigunguSidoFromCode(code));
  const result = regionSigunguWinner(sido, name, state.office);
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
