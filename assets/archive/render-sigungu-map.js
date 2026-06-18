// 시·군·구 지리 지도 — 회차별 sigungu_{year} 경계로 코로플레스. 1위 정당색 + 격차 명도.
//   sidoMap(시도)의 시군구판. 대선 시군구 1위(council initResult)에서 호출 — flat 단색 아니라
//   격차명도(승자독식 거부, [[no_winner_take_all_pres]]). leaflet 없이 SVG choropleth.
//   draw(host, { year, lookup(sido,name)->{party,margin,pct,name}|null, onSelect, selected }).

(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const PAD = 10, W = 560;

  // 통계청 시도 2자리 코드 → canon 시도명 (geomap.ts LOCAL_SIDO_CODE2와 동기 — lookup이 canonSido와 비교).
  const SIDO_CODE2 = {
    '11': '서울특별시', '21': '부산광역시', '22': '대구광역시', '23': '인천광역시',
    '24': '광주광역시', '25': '대전광역시', '26': '울산광역시', '29': '세종특별자치시',
    '31': '경기도', '32': '강원특별자치도', '33': '충청북도', '34': '충청남도',
    '35': '전북특별자치도', '36': '전라남도', '37': '경상북도', '38': '경상남도',
    '39': '제주특별자치도',
  };

  // 격차 명도 — council renderResult와 동일(0.4 박빙 ~ 1.0 압도). 시군구 단색 hex와 톤 일치.
  function marginOpacity(margin) { return 0.4 + 0.6 * Math.max(0, Math.min(1, (margin || 0) / 40)); }

  const cache = {};
  function loadSgg(year) {
    const key = year || 'simple';
    if (cache[key]) return Promise.resolve(cache[key]);
    const path = year ? `data/geo/sigungu_${year}.json` : 'data/geo/sigungu_simple.json';
    return fetch(path).then((r) => r.json()).then((g) => (cache[key] = g)).catch(() => null);
  }

  function bbox(features) {
    let mnX = Infinity, mnY = Infinity, mxX = -Infinity, mxY = -Infinity;
    const scan = (rings) => rings.forEach((r) => r.forEach(([x, y]) => {
      if (x < mnX) mnX = x; if (x > mxX) mxX = x;
      if (y < mnY) mnY = y; if (y > mxY) mxY = y;
    }));
    for (const f of features) {
      const g = f.geometry; if (!g) continue;
      if (g.type === 'Polygon') scan(g.coordinates);
      else if (g.type === 'MultiPolygon') g.coordinates.forEach(scan);
    }
    return { mnX, mnY, mxX, mxY };
  }

  function ringCentroid(r) {
    let a = 0, cx = 0, cy = 0;
    for (let i = 0; i < r.length - 1; i++) {
      const [x0, y0] = r[i], [x1, y1] = r[i + 1];
      const f = x0 * y1 - x1 * y0; a += f; cx += (x0 + x1) * f; cy += (y0 + y1) * f;
    }
    a *= 0.5;
    if (!a) { const m = r.reduce((s, p) => [s[0] + p[0], s[1] + p[1]], [0, 0]); return [m[0] / r.length, m[1] / r.length]; }
    return [cx / (6 * a), cy / (6 * a)];
  }
  function centroid(g) {
    const rings = g.type === 'Polygon' ? [g.coordinates[0]]
      : g.type === 'MultiPolygon' ? g.coordinates.map((p) => p[0]) : [];
    let best = null, bestA = -1;
    for (const r of rings) {
      let a = 0;
      for (let i = 0; i < r.length - 1; i++) a += r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1];
      a = Math.abs(a);
      if (a > bestA) { bestA = a; best = r; }
    }
    return best ? ringCentroid(best) : null;
  }

  async function draw(host, opts) {
    if (!host) return null;
    opts = opts || {};
    const geo = await loadSgg(opts.year);
    if (!geo || !geo.features || !geo.features.length) {
      host.innerHTML = '<p class="ar-empty">경계 데이터 없음</p>'; return null;
    }
    const lookup = opts.lookup || (() => null);
    const pcol = (typeof partyColor === 'function') ? partyColor : () => '#888';

    const feats = geo.features;
    const { mnX, mnY, mxX, mxY } = bbox(feats);
    const kx = Math.cos(((mnY + mxY) / 2) * Math.PI / 180);
    const scale = (W - 2 * PAD) / ((mxX - mnX) * kx);
    const H = (mxY - mnY) * scale + 2 * PAD;
    const px = (lng) => PAD + (lng - mnX) * kx * scale;
    const py = (lat) => PAD + (mxY - lat) * scale;
    const ringPath = (r) => r.map(([x, y], i) => (i ? 'L' : 'M') + px(x).toFixed(1) + ' ' + py(y).toFixed(1)).join(' ') + ' Z';
    const polyPath = (rings) => rings.map(ringPath).join(' ');
    const featPath = (g) => g.type === 'Polygon' ? polyPath(g.coordinates)
      : g.type === 'MultiPolygon' ? g.coordinates.map(polyPath).join(' ') : '';

    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('xmlns', NS);
    const EM = (typeof SIDO_EDGE_MARGIN !== 'undefined') ? SIDO_EDGE_MARGIN : 78;  // 좌우 외곽 라벨 여백
    svg.setAttribute('viewBox', `${-EM} 0 ${(W + 2 * EM).toFixed(1)} ${H.toFixed(1)}`);
    svg.setAttribute('width', (W + 2 * EM).toFixed(1)); svg.setAttribute('height', H.toFixed(1));
    svg.setAttribute('class', 'sigungu-map-svg');

    const sel = opts.selected || null;
    const labels = [];
    const cells = [];
    for (const f of feats) {
      const code = String(f.properties.code || f.properties.SIG_CD || '');
      const sido = SIDO_CODE2[code.slice(0, 2)];
      const name = f.properties.name || f.properties.SIG_KOR_NM || '';
      if (!sido) continue;
      const win = lookup(sido, name);
      const path = document.createElementNS(NS, 'path');
      path.setAttribute('d', featPath(f.geometry));
      path.setAttribute('fill-rule', 'evenodd');
      if (win) {
        path.setAttribute('fill', pcol(win.party));
        path.setAttribute('fill-opacity', marginOpacity(win.margin).toFixed(2));
        path.setAttribute('class', 'sigungu-map-region has-data');
      } else {
        path.setAttribute('class', 'sigungu-map-region no-data');
      }
      if (sel && sel.sido === sido && sel.name === name) path.classList.add('is-selected');
      const tt = document.createElementNS(NS, 'title');
      tt.textContent = win
        ? `${sido} ${name} · ${win.name || ''}(${win.party}) ${(win.pct || 0).toFixed(1)}% · 격차 ${(win.margin || 0).toFixed(1)}%p`
        : `${sido} ${name} · 데이터 없음`;
      path.appendChild(tt);
      if (opts.onSelect) { path.style.cursor = 'pointer'; path.addEventListener('click', () => opts.onSelect(sido, name)); }
      svg.appendChild(path);
      const c = centroid(f.geometry);
      if (c) { labels.push({ sido, cx: px(c[0]), cy: py(c[1]) }); cells.push({ region: sido + '|' + name, cx: px(c[0]), cy: py(c[1]) }); }
    }
    // 시도명 외곽 세로줄 라벨 (hex·sidoMap과 동일) — 시군구 centroid를 시도별로 묶어.
    if (typeof drawSidoEdgeLabels === 'function') drawSidoEdgeLabels(svg, labels);
    host.innerHTML = '';
    host.appendChild(svg);
    return { cells };
  }

  // 시군구 geo 경계 연도 — geomap.ts와 동기. 대선 PRES_SGG_GEO_YEAR(16~21 SGIS 연도, 13·14대는 도농통합
  //   전이라 파일 없음→undefined), 지선 기초장 LOCAL_SGG_GEO_YEAR(회차별 통합전 시군구). undefined면 호출부 폴백/숨김.
  const PRES_SGG_GEO_YEAR = { 15: 2000, 16: 2002, 17: 2006, 18: 2013, 19: 2025, 20: 2025, 21: 2025 };
  const LOCAL_SGG_GEO_YEAR = { 1: 1995, 2: 2000, 3: 2002, 4: 2006, 5: 2010, 6: 2025, 7: 2025, 8: 2025, 9: 2026 };
  function geoYear(n, kind) {
    if (kind === 'presidential') return PRES_SGG_GEO_YEAR[n];
    if (kind === 'local') return LOCAL_SGG_GEO_YEAR[n];
    return undefined;
  }

  window.Archive = window.Archive || {};
  window.Archive.sigunguMap = { draw, geoYear };
})();
