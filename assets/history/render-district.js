// history.js 지역구 hex + Leaflet geomap — 총선 21·22대.

// === 지역구 hex (총선 전용) ===

// 지역구명 축약: '동해시태백시삼척시정선군' → '동해/태백/삼척/정선' (길면)
// 시도 prefix는 SIDO_HEX_LAYOUT.label에서 추출하여 별도로 추가 (시군구 hex 라벨 패턴과 동일).
function shortDistrictLabel(name, sido) {
  // 분할 suffix 분리
  const m = name.match(/^(.+?)([갑을병정무])$/);
  const base = m ? m[1] : name;
  const suf = m ? m[2] : '';
  // 시/군/구 단위로 split
  const parts = base.match(/[가-힣]+?(?:특별자치시|특별시|광역시|특별자치도|시|군|구)/g) || [base];
  let body;
  if (parts.length === 1) {
    body = parts[0].replace(/(시|군|구)$/, '');
  } else {
    body = parts.map(p => p.replace(/(시|군|구)$/, '').slice(0, 2)).join('/');
  }
  // 갑/을 suffix는 body에 붙임 ('평택갑')
  if (suf) body = body + suf;
  // SIDO_HEX_LAYOUT에 '전라남도'·'광주광역시'는 9회 통합으로 인해 '전남광주특별시' 키만
  // 등록됨. 22대 이전 회차 cells가 '전라남도'·'광주광역시' sido이라 fallback 필요.
  const SIDO_LABEL_FALLBACK = {
    '전라남도': '전남', '광주광역시': '광주',
    '강원도': '강원', '제주도': '제주', '전라북도': '전북',
  };
  const sidoAbbr = sido ? (SIDO_HEX_LAYOUT[sido]?.label || SIDO_LABEL_FALLBACK[sido] || sido.slice(0, 2)) : '';
  return { prefix: sidoAbbr, short: body, fullName: name };
}

// === 21·22대 GeoJSON chloropleth (OhmyNews MIT) + 시도 경계 overlay ===
async function loadGeo(n) {
  if (state.geoCache[n] && state.geoMapCache[n]) return;
  const [geo, mapj] = await Promise.all([
    loadJson(`data/geo/district_${n}_geojson.json`),
    loadJson(`data/geo/district_${n}_geojson_map.json`),
  ]);
  state.geoCache[n] = geo;
  state.geoMapCache[n] = mapj.name_to_sgg_code;
}

async function loadSidoGeo() {
  if (state.geoSido) return;
  state.geoSido = await loadJson('data/geo/sido_simple.json');
}

function _geoDisplayName(p, n) {
  // 22대: SIDO_SGG (예: '서울 강서갑'), 21대: SGG_2 (예: '경기도 고양시갑')
  return p.SIDO_SGG || p.SGG_2 || p.SGG || '';
}

// === Leaflet geomap (21·22대 총선 지역구 chloropleth) ===
// 확대·패닝 + 미니맵 지원. polls.js 패턴 재사용.

let geoLeafletMap = null;
let geoDistrictLayer = null;    // 현재 회차 layer
let geoDistrictByN = {};        // n → L.geoJSON layer (캐시, 재방문 시 재생성 안 함)
let geoSidoOutlineLayer = null;
let geoMiniMapCtrl = null;
let geoInitialZoom = null;
const KOREA_BOUNDS_GEO = [[32.5, 123.5], [39.5, 132.5]];

function _districtStyleFor(info) {
  return {
    color: 'rgba(10,14,26,0.35)',
    weight: 0.6,
    fillColor: info?.winner?.party ? partyColor(info.winner.party) : 'rgba(154,163,179,0.65)',
    fillOpacity: 0.85,
  };
}

function _attachDistrictInteraction(feature, layer, info, label) {
  layer.bindTooltip(
    info ? `${label} — ${info.winner?.name || ''} (${info.winner?.party || ''})` : label,
    { className: 'sigungu-tooltip', sticky: true, direction: 'auto' }
  );
  if (info) {
    layer.on('mouseover', () => layer.setStyle({ weight: 1.8, color: 'rgba(10,14,26,0.85)' }));
    layer.on('mouseout', () => layer.setStyle({ weight: 0.6, color: 'rgba(10,14,26,0.35)' }));
    layer.on('click', () => {
      state.selected = { sido: info.race.sido, name: info.race.name, kind: 'district' };
      renderDetail();
    });
  }
}

function _setupGeoMiniMap(sidoData) {
  if (geoMiniMapCtrl || typeof L.Control.MiniMap === 'undefined') return;
  const miniLayer = L.geoJSON(sidoData, {
    style: { color: 'rgba(10,14,26,0.4)', weight: 0.6, fillColor: 'rgba(230,233,239,0.85)', fillOpacity: 0.85 },
    interactive: false,
  });
  const MAINLAND = L.latLngBounds([32.8, 125.6], [38.8, 130.0]);
  const TARGET_H = 170;
  let miniZoom = geoInitialZoom;
  let sw, ne, miniW, miniH;
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
    path.style.display = geoLeafletMap.getZoom() > geoInitialZoom ? '' : 'none';
  };
  geoLeafletMap.on('zoomend', updateMini);
  geoLeafletMap.on('moveend', updateMini);
  setTimeout(updateMini, 0);
}

async function renderGeoMap() {
  const n = state.n;
  await Promise.all([loadGeo(n), loadSidoGeo()]);
  const features = state.geoCache[n]?.features || [];
  if (!features.length) return;
  const sggMap = state.geoMapCache[n];
  const sggToWinner = {};
  const districts = state.results?.district || [];
  for (const race of districts) {
    // sggMap 키는 새 sido명(전북특별자치도·강원특별자치도) 기준. 옛 race 데이터(전라북도·강원도)는
    // canonSido로 정규화해 매칭.
    const key = `${canonSido(race.sido)}|${race.name}`;
    const sggCode = sggMap[key];
    if (sggCode == null) continue;
    const winner = (race.candidates || []).find((c) => c.won || c.rank === 1) || race.candidates?.[0];
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

  // 기존 회차 layer 제거 (회차 바뀐 경우)
  if (geoDistrictLayer && geoLeafletMap.hasLayer(geoDistrictLayer)) {
    geoLeafletMap.removeLayer(geoDistrictLayer);
  }

  // 회차별 layer 캐시 — winner 색만 재적용
  if (!geoDistrictByN[n]) {
    geoDistrictByN[n] = L.geoJSON(state.geoCache[n], {
      style: (f) => _districtStyleFor(sggToWinner[String(f.properties.SGG_Code)]),
      onEachFeature: (f, l) => {
        const info = sggToWinner[String(f.properties.SGG_Code)];
        _attachDistrictInteraction(f, l, info, _geoDisplayName(f.properties, n));
      },
    });
  } else {
    // 캐시된 layer는 style/tooltip만 갱신
    geoDistrictByN[n].eachLayer((l) => {
      const f = l.feature;
      const info = sggToWinner[String(f.properties.SGG_Code)];
      l.setStyle(_districtStyleFor(info));
      l.unbindTooltip();
      _attachDistrictInteraction(f, l, info, _geoDisplayName(f.properties, n));
    });
  }
  geoDistrictLayer = geoDistrictByN[n];
  geoDistrictLayer.addTo(geoLeafletMap);

  // 시도 외곽선 overlay (한 번만 생성)
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
}


async function renderDistrictHex() {
  const layout = await loadDistrictHex(state.n);
  const svg = $('#hex2');
  svg.innerHTML = '';
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');
  if (!layout?.length) return;
  const cs = layout.map((d) => d.c);
  const rs = layout.map((d) => d.r);
  const minC = Math.min(...cs), minR = Math.min(...rs);
  const maxC = Math.max(...cs), maxR = Math.max(...rs);
  const r = 22;
  const colW = r * Math.sqrt(3);
  const rowH = r * 1.5;
  const w = (maxC - minC + 2) * colW;
  const h = (maxR - minR + 2) * rowH;
  svg.setAttribute('viewBox', `0 0 ${Math.ceil(w)} ${Math.ceil(h)}`);
  const offX = -minC * colW + colW / 2;
  const offY = -minR * rowH + rowH;

  const cellAt = new Map();
  for (const d of layout) cellAt.set(`${d.c},${d.r}`, d);
  // nbrs·NBR_TO_EDGE·corner → assets/hexgrid.js (공용)

  for (const d of layout) {
    const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
    const result = resultForDistrict(d.sido, d.name);
    const top = topCandidate(result);
    const sec = result?.candidates?.length >= 2 ? result.candidates[1] : null;
    const gap = top && sec ? top.pct - sec.pct : null;
    const fill = top ? partyColor(top.party) : '#e6e9ef';
    const opacity = top ? 1 : 1;
    const isSelected = state.selected
      && state.selected.sido === d.sido && state.selected.name === d.name;

    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.style.cursor = result ? 'pointer' : 'default';
    g.addEventListener('click', () => {
      state.selected = { sido: d.sido, name: d.name, kind: 'district' };
      renderAll();
    });

    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('class', 'hex-cell ' + (top ? 'has-data' : 'no-data') + (isSelected ? ' is-selected' : ''));
    poly.setAttribute('points', hexPoints(cx, cy, r - 0.7));
    poly.setAttribute('fill', fill);
    poly.setAttribute('stroke', '#0a0e1a');
    poly.setAttribute('stroke-width', isSelected ? '1.6' : '0.7');
    poly.setAttribute('fill-opacity', opacity);
    g.appendChild(poly);

    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    title.textContent = top
      ? `${d.sido} ${d.name} · ${top.name} (${top.party}) ${result.uncontested ? '무투표 당선' : top.pct?.toFixed(1) + '%'}`
      : `${d.sido} ${d.name} · 데이터 없음`;
    g.appendChild(title);

    const lbl = shortDistrictLabel(d.name, d.sido);
    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txt.setAttribute('x', cx);
    txt.setAttribute('text-anchor', 'middle');
    txt.setAttribute('font-weight', '600');
    txt.setAttribute('fill', top ? '#fff' : '#0a0e1a');
    txt.setAttribute('pointer-events', 'none');
    txt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
    // 시군구 hex와 동일 패턴: prefix(시도, 작게·옅게) 위 + short(지역구+갑) 아래
    if (lbl.prefix) {
      const tp1 = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
      tp1.setAttribute('x', cx);
      tp1.setAttribute('y', cy - 2);
      tp1.setAttribute('font-size', '6');
      tp1.setAttribute('opacity', '0.75');
      tp1.textContent = lbl.prefix;
      txt.appendChild(tp1);
      const tp2 = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
      tp2.setAttribute('x', cx);
      tp2.setAttribute('y', cy + 8);
      tp2.setAttribute('font-size', lbl.short.length > 4 ? '6' : lbl.short.length > 3 ? '7' : '9');
      tp2.textContent = lbl.short;
      txt.appendChild(tp2);
    } else {
      txt.setAttribute('y', cy + 3);
      txt.setAttribute('font-size', lbl.short.length > 4 ? '6' : '8');
      txt.textContent = lbl.short;
    }
    g.appendChild(txt);
    svg.appendChild(g);
  }

  // 시도 경계 굵은 선 + 한반도 외곽 — drawHexBorders (hexgrid.js)
  drawHexBorders(svg, layout, cellAt, colW, rowH, offX, offY, r, '1.8', true);

  // 비례대표 — 정당별 세로 col, 지역구 hex 우측에 배치. 사이즈는 지역구와 동일(r=22).
  // 같은 col 안 vertical pitch = 1.5r (격자 hex 표준, odd col 0.5 row shift로 interlock).
  const propSeats = state.results?.national?.proportional_seats || [];
  if (propSeats.length) {
    const totalProp = propSeats.reduce((s, p) => s + p.seats, 0);
    const totalSeats = layout.length + totalProp;
    const sorted = [...propSeats].sort((a, b) => b.seats - a.seats);
    const ns = 'http://www.w3.org/2000/svg';

    const propGap = colW * 0.8;          // 지역구와 비례 영역 사이 여백
    const propStartX = w + propGap;      // 비례 첫 col 좌측 base
    const propColW = colW;               // 정당 col 폭 = 지역구 colW (snug interlock)
    const propRowH = rowH;               // 세로 pitch = 지역구 rowH (1.5r)
    const labelOffsetY = -rowH * 0.6;    // 정당 라벨 baseline (첫 hex 위쪽)

    // 헤더 (지역구 위쪽 여백, 비례 영역 상단)
    const headerY = labelOffsetY * 2;    // 정당 라벨보다 더 위
    const sectionLabel = document.createElementNS(ns, 'text');
    sectionLabel.setAttribute('x', propStartX);
    sectionLabel.setAttribute('y', headerY);
    sectionLabel.setAttribute('font-size', '12');
    sectionLabel.setAttribute('font-weight', '700');
    sectionLabel.setAttribute('fill', '#0a0e1a');
    sectionLabel.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
    sectionLabel.textContent = `비례대표 ${totalProp}석 · 총 ${totalSeats}석`;
    svg.appendChild(sectionLabel);

    // 정당당 2 col 블록 — 의석 zigzag 배치(좌→우→좌→…)로 세로 길이 절반, 라벨 폭 확보.
    const blockW = 2 * propColW;        // 정당당 2 col 폭
    const blockGap = propColW * 0.35;   // 정당 블록 사이 여백
    let maxColH = 0;
    sorted.forEach((ps, pi) => {
      const color = partyColor(ps.party);
      const blockX = propStartX + pi * (blockW + blockGap);
      const col0Cx = blockX + propColW * 0.5;        // 좌 col 중심
      const col1Cx = blockX + propColW * 1.5;        // 우 col 중심
      const labelCx = blockX + blockW / 2;
      // 정당 라벨 (블록 중앙 위)
      const nm = document.createElementNS(ns, 'text');
      nm.setAttribute('x', labelCx);
      nm.setAttribute('y', labelOffsetY);
      nm.setAttribute('text-anchor', 'middle');
      nm.setAttribute('font-size', '11');
      nm.setAttribute('font-weight', '700');
      nm.setAttribute('fill', color);
      nm.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
      nm.textContent = `${ps.party} ${ps.seats}`;
      svg.appendChild(nm);
      // 의석 hex zigzag: 짝수 j → 좌 col, 홀수 j → 우 col (0.5 row shift).
      for (let j = 0; j < ps.seats; j++) {
        const isRight = j % 2 === 1;
        const rowIdx = Math.floor(j / 2);
        const cx = isRight ? col1Cx : col0Cx;
        const cy = rowIdx * propRowH + r + (isRight ? rowH / 2 : 0);
        const poly = document.createElementNS(ns, 'polygon');
        poly.setAttribute('points', hexPoints(cx, cy, r - 0.7));
        poly.setAttribute('fill', color);
        poly.setAttribute('stroke', '#fff');
        poly.setAttribute('stroke-width', '1');
        const tt = document.createElementNS(ns, 'title');
        tt.textContent = `비례 ${ps.party} ${j + 1}/${ps.seats}석`;
        poly.appendChild(tt);
        svg.appendChild(poly);
      }
      const rows = Math.ceil(ps.seats / 2);
      const colH = rows * propRowH + rowH / 2 + r;
      if (colH > maxColH) maxColH = colH;
    });

    // viewBox 확장 — 우측 비례 + 위쪽 라벨 영역까지
    const newW = propStartX + sorted.length * (blockW + blockGap) + propGap;
    const topPad = -headerY + 8;
    const newH = Math.max(h, maxColH) + topPad;
    const minY = headerY - 8;
    svg.setAttribute('viewBox', `0 ${Math.floor(minY)} ${Math.ceil(newW)} ${Math.ceil(newH)}`);
  }
}
