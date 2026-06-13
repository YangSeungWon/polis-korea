// history.js 지선·대선 geo chloropleth.
//   지선: 광역장/교육감 시도, 기초장 시군구 (단색 winner — 단체장 1명 당선이라 정확).
//   대선: 시군구 margin 명도 (박빙 옅게·압승 진하게 — 승자독식 단색 회피, [[no_winner_take_all_pres]]).
// 총선 renderGeoMap(render-district.js)의 Leaflet 인프라(geoLeafletMap·mini-map·sido outline)를 재사용.

let localGeoLayer = null;        // 현재 표시 중 layer
let localGeoSidoData = null;     // sido_simple.json (광역장/교육감)
const localGeoSggCache = {};     // year|'simple' → sigungu GeoJSON (회차별 period-correct 경계)

// 기초장 시군구 geo — 회차별 SGIS 시군구 경계 연도(통합전 시군구 반영).
//   1회1995→1995  2회1998→2000(울산 광역시)  3회2002→2002  4회2006→2006  5회2010→2010
//   6~9회→sigungu_simple(2018). 6회는 통합 청주시(2014-07) 당선이라 2018 경계가 맞음.
const LOCAL_SGG_GEO_YEAR = { 1: 1995, 2: 2000, 3: 2002, 4: 2006, 5: 2010 };

// 대선 시군구 geo — 16대(2002)부터만(13~15대는 전국 합산만 있어 지도 불가).
//   16대2002→2002  17대2007→2006  18대2012→2013(세종 출범·당진시 승격 후, 청주통합 전)
//   19대2017·20대2022·21대2025→2025(SGIS 2025-2Q 동→시군구 dissolve, 상세 80m급).
// 이전엔 19~21이 sigungu_simple(과단순화 30정점/폴리곤)을 써 해안선이 엉기설기했음.
// 시-단위 250유닛은 2018~2025 안정 → 한 파일로 19~21 공용. 일반구는 reverse-merge로 집계.
const PRES_SGG_GEO_YEAR = { 16: 2002, 17: 2006, 18: 2013, 19: 2025, 20: 2025, 21: 2025 };
const PRES_GEO_ROUNDS = [16, 17, 18, 19, 20, 21];   // 21대=2025 조기대선(sigungu_simple 경계)

async function loadSggGeoByYear(y) {
  const key = y || 'simple';
  if (!localGeoSggCache[key]) {
    localGeoSggCache[key] = await loadJson(y ? `data/geo/sigungu_${y}.json` : 'data/geo/sigungu_simple.json');
  }
  return localGeoSggCache[key];
}
const loadLocalSggGeo = (n) => loadSggGeoByYear(LOCAL_SGG_GEO_YEAR[n]);

function presGeoSupported(n) {
  return state.type === 'presidential' && PRES_GEO_ROUNDS.includes(n);
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
  const labelFor = (props) => isSido
    ? props.name
    : `${LOCAL_SIDO_CODE2[String(props.code).slice(0, 2)] || ''} ${props.name}`.trim();
  _mountSggGeo(geoData, infoFor, _localStyleFor, labelFor);
}

// 대선 시군구 geo — margin 명도(16~21). 13~15대는 시군구 미수집 → 시도 hex(margin 명도)로 표시(activeUnit).
async function renderPresGeoMap() {
  await loadSidoGeo();
  const geoData = await loadSggGeoByYear(PRES_SGG_GEO_YEAR[state.n]);
  if (!geoData?.features?.length) return;
  const el = (state.elections[state.type]?.elections || []).find((x) => x.n === state.n);
  const electionDate = el?.date || '';
  const infoFor = (props) => {
    const sidoName = LOCAL_SIDO_CODE2[String(props.code).slice(0, 2)];
    if (!sidoName) return null;
    const eff = effectiveCell({ sido: sidoName, name: props.name }, electionDate);
    if (!eff) return null;
    const r = resultForSigungu(eff.sido, eff.name);
    if (!r?.candidates?.length) return null;
    return { sido: eff.sido, name: eff.name, winner: r.candidates[0], second: r.candidates[1] || null,
             race: { sido: eff.sido, name: eff.name, candidates: r.candidates, scope: 'sigungu' } };
  };
  const labelFor = (props) => `${LOCAL_SIDO_CODE2[String(props.code).slice(0, 2)] || ''} ${props.name}`.trim();
  _mountSggGeo(geoData, infoFor, _presStyleFor, labelFor);
}

// Leaflet 마운트 공유 — layer 교체·시도 외곽선·fit·minimap. (지선/대선 공통)
function _mountSggGeo(geoData, infoFor, styleFor, labelFor) {
  if (!geoLeafletMap) {
    geoLeafletMap = L.map('geomap', {
      zoomControl: true, attributionControl: false,
      maxBounds: KOREA_BOUNDS_GEO, maxBoundsViscosity: 1.0,
    });
    geoLeafletMap.setView([35.9, 127.8], 6);
  } else {
    geoLeafletMap.invalidateSize();
  }
  // 다른 layer(총선 지역구 / 이전 layer) 제거
  if (geoDistrictLayer && geoLeafletMap.hasLayer(geoDistrictLayer)) geoLeafletMap.removeLayer(geoDistrictLayer);
  if (localGeoLayer && geoLeafletMap.hasLayer(localGeoLayer)) geoLeafletMap.removeLayer(localGeoLayer);

  localGeoLayer = L.geoJSON(geoData, {
    style: (f) => styleFor(infoFor(f.properties)),
    onEachFeature: (f, l) => _attachLocalInteraction(f, l, infoFor(f.properties), labelFor(f.properties)),
  });
  localGeoLayer.addTo(geoLeafletMap);
  // 선택 강조 재적용 (office/회차 전환 시 stale ref 제거 + 같은 지역 재강조)
  _geoReapplySelection(localGeoLayer, (p) => {
    const info = infoFor(p);
    if (!info) return false;
    return info.race.scope === 'sido'
      ? (info.sido === state.selected?.sido && !state.selected?.name)
      : (info.sido === state.selected?.sido && info.name === state.selected?.name);
  });

  // 시도 외곽선 overlay
  if (!geoSidoOutlineLayer && state.geoSido) {
    geoSidoOutlineLayer = L.geoJSON(state.geoSido, {
      style: { color: 'rgba(10,14,26,0.85)', weight: 1.4, fill: false, lineJoin: 'round' },
      interactive: false,
    });
  }
  if (geoSidoOutlineLayer && !geoLeafletMap.hasLayer(geoSidoOutlineLayer)) geoSidoOutlineLayer.addTo(geoLeafletMap);
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

// 대선 margin 명도 — 1위 정당색을 격차(1위-2위 %p)에 따라 흰색쪽으로 옅게.
// 박빙(0%p)≈옅음, 압승(40%p+)=원색. 승자독식 단색 착시 회피(미국 purple-map 방식).
function _hex2rgb(h) {
  h = String(h).replace('#', '');
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
function _mixWhite(hex, t) {       // t=0 → 흰색, t=1 → 원색
  const [r, g, b] = _hex2rgb(hex);
  const m = (c) => Math.round(255 + (c - 255) * t);
  return `rgb(${m(r)},${m(g)},${m(b)})`;
}
function _presStyleFor(info) {
  if (!info) return { color: 'rgba(10,14,26,0.25)', weight: 0.5, fillColor: 'rgba(154,163,179,0.4)', fillOpacity: 0.55 };
  const margin = (info.winner?.pct || 0) - (info.second?.pct || 0);
  const t = Math.max(0.18, Math.min(1, margin / 40));   // 0~40%p → 0.18~1.0
  return { color: 'rgba(10,14,26,0.3)', weight: 0.5, fillColor: _mixWhite(partyColor(info.winner?.party || ''), t), fillOpacity: 0.92 };
}

function _attachLocalInteraction(feature, layer, info, label) {
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
