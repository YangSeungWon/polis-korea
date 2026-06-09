// history.js 지선 geo chloropleth — 광역장/교육감 시도, 기초장 시군구 (단색 winner).
// 총선 renderGeoMap(render-district.js)의 Leaflet 인프라(geoLeafletMap·mini-map·
// sido outline·_districtStyleFor)를 재사용. 지선 단체장은 1명 당선이라 승자독식 단색이 정확.

let localGeoLayer = null;        // 현재 표시 중 layer
let localGeoSidoData = null;     // sido_simple.json (광역장/교육감)
let localGeoSggData = null;      // sigungu_simple.json (기초장)

// 통계청 시도 2자리 코드 → canon 시도명 (resultForSigungu는 canonSido(data.sido)와 === 비교).
const LOCAL_SIDO_CODE2 = {
  '11': '서울특별시', '21': '부산광역시', '22': '대구광역시', '23': '인천광역시',
  '24': '광주광역시', '25': '대전광역시', '26': '울산광역시', '29': '세종특별자치시',
  '31': '경기도', '32': '강원특별자치도', '33': '충청북도', '34': '충청남도',
  '35': '전북특별자치도', '36': '전라남도', '37': '경상북도', '38': '경상남도',
  '39': '제주특별자치도',
};

// 기초장 시군구 geo 지원 회차 — sigungu_simple(base_year 2018) 경계와 정합한 최근 회차만.
// 옛 회차(1~6회)는 통합전 시군구(마산·진해·여천·청원 등)라 현재 경계로 못 그림 →
// 회차별 SGIS 시군구 경계 복원 필요(총선 선거구 복원과 동형, 후속 작업). 그 전엔 hex 사용.
const LOCAL_SGG_GEO_ROUNDS = [7, 8, 9];

function localGeoSupported(unit, n) {
  if (state.type !== 'local') return false;
  if (unit === 'sido') return true;            // 시도 경계 안정 — 전 회차
  return LOCAL_SGG_GEO_ROUNDS.includes(n);     // 시군구 — 최근 회차만
}

async function renderLocalGeoMap(unit) {
  const isSido = unit === 'sido';
  if (isSido) {
    if (!localGeoSidoData) localGeoSidoData = await loadJson('data/geo/sido_simple.json');
  } else if (!localGeoSggData) {
    localGeoSggData = await loadJson('data/geo/sigungu_simple.json');
  }
  await loadSidoGeo();
  const geoData = isSido ? localGeoSidoData : localGeoSggData;
  if (!geoData?.features?.length) return;

  const el = (state.elections[state.type]?.elections || []).find((x) => x.n === state.n);
  const electionDate = el?.date || '';

  // feature props → { winner, race } (없으면 null → 회색)
  const infoFor = (props) => {
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

  // 다른 layer(총선 지역구 / 이전 지선 layer) 제거
  if (geoDistrictLayer && geoLeafletMap.hasLayer(geoDistrictLayer)) {
    geoLeafletMap.removeLayer(geoDistrictLayer);
  }
  if (localGeoLayer && geoLeafletMap.hasLayer(localGeoLayer)) {
    geoLeafletMap.removeLayer(localGeoLayer);
  }

  localGeoLayer = L.geoJSON(geoData, {
    style: (f) => _districtStyleFor(infoFor(f.properties)),
    onEachFeature: (f, l) => {
      const info = infoFor(f.properties);
      const label = isSido ? f.properties.name : `${LOCAL_SIDO_CODE2[String(f.properties.code).slice(0, 2)] || ''} ${f.properties.name}`;
      _attachLocalInteraction(f, l, info, label.trim());
    },
  });
  localGeoLayer.addTo(geoLeafletMap);

  // 시도 외곽선 overlay (시군구 모드에서 시도 경계 강조)
  if (!geoSidoOutlineLayer && state.geoSido) {
    geoSidoOutlineLayer = L.geoJSON(state.geoSido, {
      style: { color: 'rgba(10,14,26,0.85)', weight: 1.4, fill: false, lineJoin: 'round' },
      interactive: false,
    });
  }
  if (geoSidoOutlineLayer && !geoLeafletMap.hasLayer(geoSidoOutlineLayer)) {
    geoSidoOutlineLayer.addTo(geoLeafletMap);
  }
  if (geoSidoOutlineLayer) geoSidoOutlineLayer.bringToFront();

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

function _attachLocalInteraction(feature, layer, info, label) {
  layer.bindTooltip(
    info ? `${label} — ${candLabel(info.winner)} (${info.winner?.party || ''})` : label,
    { className: 'sigungu-tooltip', sticky: true, direction: 'auto' }
  );
  if (info) {
    layer.on('mouseover', () => layer.setStyle({ weight: 1.8, color: 'rgba(10,14,26,0.85)' }));
    layer.on('mouseout', () => layer.setStyle({ weight: 0.6, color: 'rgba(10,14,26,0.35)' }));
    layer.on('click', () => {
      state.selected = info.race.scope === 'sido'
        ? { sido: info.sido }
        : { sido: info.sido, name: info.name, kind: 'sigungu' };
      renderDetail();
    });
  }
}
