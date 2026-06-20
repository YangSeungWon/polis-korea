// 시도 지리 지도 — sido_simple.json 경계로 choropleth. 1위 정당 색 + 시도명 라벨.
// governor-hex와 같은 races(scope=sido) 입력. draw(hostEl, races) 위주, sidoView가 호출.

(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const PAD = 10, W = 520;

  // 특별자치도·옛 명칭 정규화 — 데이터(옛 '제주도'/'강원도')와 geojson(현대명·code2 변환명) 통일.
  function norm(n) {
    return (n || '')
      .replace('강원특별자치도', '강원도')
      .replace('전북특별자치도', '전라북도')
      .replace('제주특별자치도', '제주도');
  }
  // 시도 약칭 (라벨용)
  function shortSido(n) {
    return n
      .replace('특별자치도', '').replace('특별자치시', '')
      .replace('특별시', '').replace('광역시', '')
      .replace('충청', '충').replace('전라', '전').replace('경상', '경')
      .replace('도', '').trim() || n;
  }

  // 시도 2자리 코드 → 시도명 (period geojson은 code2만 있을 수 있음 — geomap.ts와 동기).
  const SIDO_CODE2 = {
    '11': '서울특별시', '21': '부산광역시', '22': '대구광역시', '23': '인천광역시',
    '24': '광주광역시', '25': '대전광역시', '26': '울산광역시', '29': '세종특별자치시',
    '31': '경기도', '32': '강원특별자치도', '33': '충청북도', '34': '충청남도',
    '35': '전북특별자치도', '36': '전라남도', '37': '경상북도', '38': '경상남도', '39': '제주특별자치도',
  };
  // feature → 시도명 (name·SIDO·code2 어느 키든 흡수, norm으로 옛/특별자치 표기 통일).
  function sidoName(props) { return norm(props.name || props.SIDO || SIDO_CODE2[String(props.code2)] || ''); }

  // 회차별 시도 경계 — 세종(2012)·울산(1997)·대전(1989) 신설 등 시점 반영(sido_{year}). 없으면 현대 sido_simple.
  const SIDO_YEARS = new Set([1975, 1985, 1987, 1990, 1995, 2000, 2002, 2006, 2010, 2013, 2026]);
  const PRES_SIDO_YEAR = { 13: 1987, 14: 1990, 15: 2000, 16: 2002, 17: 2006, 18: 2013 };  // 19~21=현대
  const LOCAL_SIDO_YEAR = { 1: 1995, 2: 2000, 3: 2002, 4: 2006, 5: 2010, 9: 2026 };          // 6~8=현대, 9=전남광주 통합
  function sidoGeoFile(n, kind) {
    let y;
    if (kind === 'presidential') y = PRES_SIDO_YEAR[n];
    else if (kind === 'local') y = LOCAL_SIDO_YEAR[n];
    return (y && SIDO_YEARS.has(y)) ? `data/geo/sido_${y}.json` : 'data/geo/sido_simple.json';
  }
  const _geoCache = {};
  function loadGeo(file) {
    file = file || 'data/geo/sido_simple.json';
    if (_geoCache[file]) return Promise.resolve(_geoCache[file]);
    return fetch(file).then((r) => r.json()).then((g) => (_geoCache[file] = g)).catch(() => null);
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
    if (!a) {
      const m = r.reduce((s, p) => [s[0] + p[0], s[1] + p[1]], [0, 0]);
      return [m[0] / r.length, m[1] / r.length];
    }
    return [cx / (6 * a), cy / (6 * a)];
  }
  // 가장 큰 ring 중심 (라벨 위치)
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

  // opts.margin: 승자색에 격차명도(gapOpacity) 적용 — 대선 시도(승자독식 단색 거부, [[no_winner_take_all_pres]]).
  //   flat 단색은 광역장(실제 1명 당선)만; 대선은 명도로 박빙/압승 구분해 영토적 오독 완화.
  async function draw(host, races, opts) {
    if (!host) return;
    const margin = !!(opts && opts.margin);
    const geo = await loadGeo(sidoGeoFile(opts && opts.n, opts && opts.kind));   // 회차별 시도 경계(세종 등 시점)
    if (!geo || !geo.features) { host.parentElement?.setAttribute('hidden', ''); return; }

    // 득표 점수 — 원시 race(votes) / 어댑터 cell(share=votes|pct) / 폴(pct) 모두 호환.
    const score = (c) => (c.votes != null ? c.votes : (c.share != null ? c.share : (c.pct || 0)));
    const bySido = {};
    for (const r of races) {
      const cs = (r.candidates || []).slice().sort((a, b) => score(b) - score(a));
      if (cs[0]) bySido[norm(r.sido)] = { name: cs[0].name, party: cs[0].party, pct: cs[0].pct, gap: cs[1] ? (cs[0].pct || 0) - (cs[1].pct || 0) : null };
    }
    // 전남광주 통합(2026) — geo는 광주·전남 분리 폴리곤이라 병합 못 함 → 두 폴리곤에 통합 결과 칠함.
    const mergedHonam = bySido['전남광주특별시'] || bySido['전남광주통합특별시'];
    if (mergedHonam) { bySido['광주광역시'] = bySido['광주광역시'] || mergedHonam; bySido['전라남도'] = bySido['전라남도'] || mergedHonam; }

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
    svg.setAttribute('class', 'sido-map-svg');

    const labels = [];
    for (const f of feats) {
      const name = sidoName(f.properties);   // name·SIDO·code2 어느 키든 흡수(period geojson은 code2만일 수 있음)
      const win = bySido[name];
      const path = document.createElementNS(NS, 'path');
      path.setAttribute('d', featPath(f.geometry));
      path.setAttribute('fill-rule', 'evenodd');
      if (win) {
        path.setAttribute('fill', (typeof partyFill === 'function') ? partyFill(win.party) : '#888');
        // 대선: 격차명도 (gapOpacity = 박빙 0.55 ~ 압도 0.95). 광역장: flat(명도 없음).
        if (margin) path.setAttribute('fill-opacity', ((typeof gapOpacity === 'function') ? gapOpacity(win.gap) : 1).toFixed(3));
        path.setAttribute('class', 'sido-map-region has-data');
      } else {
        path.setAttribute('class', 'sido-map-region no-data');
      }
      const tt = document.createElementNS(NS, 'title');
      tt.textContent = win
        ? `${name} · ${win.name}(${win.party}) ${(win.pct || 0).toFixed(1)}%`
        : `${name} · 데이터 없음`;
      path.appendChild(tt);
      svg.appendChild(path);
      const c = centroid(f.geometry);
      if (c && name) labels.push({ sido: name, cx: px(c[0]), cy: py(c[1]) });
    }
    // 시도명 외곽 세로줄 라벨 (history 방식) — 중앙 centroid 라벨 대신.
    if (typeof drawSidoEdgeLabels === 'function') drawSidoEdgeLabels(svg, labels);
    host.innerHTML = '';
    host.appendChild(svg);
  }

  // 단독 호출용 (sidoView 없이도 동작)
  function init(ctx, opts) {
    const tc = (opts && opts.tc) || '3';
    const hostId = (opts && opts.hostId) || 'ar-sido-map';
    const host = document.getElementById(hostId);
    if (!host) return;
    const races = (ctx?.results?.races || []).filter((r) => r.scope === 'sido' && r.sg_typecode === tc);
    if (!races.length) { host.parentElement?.setAttribute('hidden', ''); return; }
    return draw(host, races);
  }

  window.Archive = window.Archive || {};
  window.Archive.sidoMap = { init, draw };
})();
