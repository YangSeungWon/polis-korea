// history.js 지선 geo chloropleth — 광역장/교육감 시도, 기초장 시군구 (단색 winner).
// 총선 renderGeoMap(render-district.js)의 Leaflet 인프라(geoLeafletMap·mini-map·
// sido outline·_districtStyleFor)를 재사용. 지선 단체장은 1명 당선이라 승자독식 단색이 정확.

let localGeoLayer = null;        // 현재 표시 중 layer
let localGeoSidoData = null;     // sido_simple.json (광역장/교육감)
const localGeoSggCache = {};     // year|'simple' → sigungu GeoJSON (기초장, 회차별 period-correct 경계)

// 기초장 시군구 geo — 회차별 SGIS 시군구 경계 연도(통합전 시군구 반영).
//   1회1995→1995  2회1998→2000(울산 광역시)  3회2002→2002  4회2006→2006  5회2010→2010
//   6~9회→sigungu_simple(2018). 6회는 통합 청주시(2014-07) 당선이라 2018 경계가 맞음.
const LOCAL_SGG_GEO_YEAR = { 1: 1995, 2: 2000, 3: 2002, 4: 2006, 5: 2010 };

async function loadLocalSggGeo(n) {
  const y = LOCAL_SGG_GEO_YEAR[n];
  const key = y || 'simple';
  if (!localGeoSggCache[key]) {
    localGeoSggCache[key] = await loadJson(y ? `data/geo/sigungu_${y}.json` : 'data/geo/sigungu_simple.json');
  }
  return localGeoSggCache[key];
}

// 통계청 시도 2자리 코드 → canon 시도명 (resultForSigungu는 canonSido(data.sido)와 === 비교).
const LOCAL_SIDO_CODE2 = {
  '11': '서울특별시', '21': '부산광역시', '22': '대구광역시', '23': '인천광역시',
  '24': '광주광역시', '25': '대전광역시', '26': '울산광역시', '29': '세종특별자치시',
  '31': '경기도', '32': '강원특별자치도', '33': '충청북도', '34': '충청남도',
  '35': '전북특별자치도', '36': '전라남도', '37': '경상북도', '38': '경상남도',
  '39': '제주특별자치도',
};

function localGeoSupported(unit, n) {
  if (state.type !== 'local') return false;
  return true;   // 시도(전 회차) + 시군구(1~6 회차별 복원경계, 7~9 현재경계) 모두 지원
}

async function renderLocalGeoMap(unit) {
  const isSido = unit === 'sido';
  if (isSido && !localGeoSidoData) localGeoSidoData = await loadJson('data/geo/sido_simple.json');
  await loadSidoGeo();
  const geoData = isSido ? localGeoSidoData : await loadLocalSggGeo(state.n);
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
    style: (f) => _localStyleFor(infoFor(f.properties)),
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

// 지선 단색 스타일 — 당선자 있으면 partyColor(없는당='' → 교육감 #777777, hex와 동일),
// 데이터 없으면 no-data 회색. (_districtStyleFor는 빈 party를 no-data로 처리해 교육감이
// 데이터 없는 곳과 구분 안 됐음 → 별도 스타일.)
function _localStyleFor(info) {
  const fill = info ? partyColor(info.winner?.party || '') : 'rgba(154,163,179,0.65)';
  return { color: 'rgba(10,14,26,0.35)', weight: 0.6, fillColor: fill, fillOpacity: 0.85 };
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
