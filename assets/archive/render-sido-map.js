// 시도 지리 지도 — sido_simple.json 경계로 choropleth. 1위 정당 색 + 시도명 라벨.
// governor-hex와 같은 races(scope=sido) 입력. draw(hostEl, races) 위주, sidoView가 호출.

(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const PAD = 10, W = 520;

  // 강원/전북 특별자치도 ↔ GeoJSON 옛 명칭 정규화
  function norm(n) {
    return (n || '')
      .replace('강원특별자치도', '강원도')
      .replace('전북특별자치도', '전라북도');
  }
  // 시도 약칭 (라벨용)
  function shortSido(n) {
    return n
      .replace('특별자치도', '').replace('특별자치시', '')
      .replace('특별시', '').replace('광역시', '')
      .replace('충청', '충').replace('전라', '전').replace('경상', '경')
      .replace('도', '').trim() || n;
  }

  let GEO = null;
  function loadGeo() {
    if (GEO) return Promise.resolve(GEO);
    return fetch('data/geo/sido_simple.json')
      .then((r) => r.json())
      .then((g) => (GEO = g))
      .catch(() => null);
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

  async function draw(host, races) {
    if (!host) return;
    const geo = await loadGeo();
    if (!geo || !geo.features) { host.parentElement?.setAttribute('hidden', ''); return; }

    const bySido = {};
    for (const r of races) {
      const cs = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      if (cs[0]) bySido[norm(r.sido)] = { name: cs[0].name, party: cs[0].party, pct: cs[0].pct };
    }

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
    svg.setAttribute('viewBox', `0 0 ${W} ${H.toFixed(1)}`);
    svg.setAttribute('class', 'sido-map-svg');

    const labels = [];
    for (const f of feats) {
      const name = norm(f.properties.name);
      const win = bySido[name];
      const path = document.createElementNS(NS, 'path');
      path.setAttribute('d', featPath(f.geometry));
      path.setAttribute('fill-rule', 'evenodd');
      if (win) {
        path.setAttribute('fill', (typeof partyColor === 'function') ? partyColor(win.party) : '#888');
        path.setAttribute('class', 'sido-map-region has-data');
      } else {
        path.setAttribute('class', 'sido-map-region no-data');
      }
      const tt = document.createElementNS(NS, 'title');
      tt.textContent = win
        ? `${f.properties.name} · ${win.name}(${win.party}) ${(win.pct || 0).toFixed(1)}%`
        : `${f.properties.name} · 데이터 없음`;
      path.appendChild(tt);
      svg.appendChild(path);
      const c = centroid(f.geometry);
      if (c) labels.push({ x: px(c[0]), y: py(c[1]), text: shortSido(f.properties.name) });
    }
    // 라벨은 path 위에
    for (const l of labels) {
      const t = document.createElementNS(NS, 'text');
      t.setAttribute('x', l.x.toFixed(1)); t.setAttribute('y', l.y.toFixed(1));
      t.setAttribute('class', 'sido-map-label');
      t.textContent = l.text;
      svg.appendChild(t);
    }
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
