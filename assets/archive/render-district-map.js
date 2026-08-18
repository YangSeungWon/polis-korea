// 선거구(지역구) 지리 지도 — district_{n}_geojson 경계로 코로플레스. 1위 후보 정당색(승자독식 1명 = flat).
//   sidoMap/sigunguMap의 선거구판. archive 총선 지역구 맵에서 호출. leaflet 없이 SVG.
//   매칭: 결과(sido|district) → name_to_sgg_code(district_{n}_geojson_map) → SGG_Code → feature.
//   draw(host, { n, races, onSelect, selected, valueFn, valueLabel, range }).
//   valueFn(race)→숫자면 **값 코로플레스**(정당색 대신 teal 그라데이션, 이 지도 최저~최고 상대화).
//   투표율처럼 승자가 아니라 연속값을 그릴 때. 반환값에 {lo,hi,shown}이 실려 호출부가 범례를 단다.

(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const PAD = 10, W = 560;

  const geoCache = {};   // n → {geo, code} | null
  function loadGeo(n) {
    if (geoCache[n] !== undefined) return Promise.resolve(geoCache[n]);
    return Promise.all([
      fetch(`data/geo/district_${n}_geojson.json`).then((r) => r.json()).catch(() => null),
      fetch(`data/geo/district_${n}_geojson_map.json`).then((r) => r.json()).catch(() => null),
    ]).then(([geo, mp]) => {
      const code = (mp && mp.name_to_sgg_code) || null;
      geoCache[n] = (geo && geo.features && code) ? { geo, code } : null;
      return geoCache[n];
    }).catch(() => { geoCache[n] = null; return null; });
  }

  function bbox(features) {
    let mnX = Infinity, mnY = Infinity, mxX = -Infinity, mxY = -Infinity;
    const scan = (rings) => rings.forEach((r) => r.forEach(([x, y]) => {
      if (x < mnX) mnX = x; if (x > mxX) mxX = x; if (y < mnY) mnY = y; if (y > mxY) mxY = y;
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
    for (let i = 0; i < r.length - 1; i++) { const [x0, y0] = r[i], [x1, y1] = r[i + 1]; const f = x0 * y1 - x1 * y0; a += f; cx += (x0 + x1) * f; cy += (y0 + y1) * f; }
    a *= 0.5;
    if (!a) { const m = r.reduce((s, p) => [s[0] + p[0], s[1] + p[1]], [0, 0]); return [m[0] / r.length, m[1] / r.length]; }
    return [cx / (6 * a), cy / (6 * a)];
  }
  function centroid(g) {
    const rings = g.type === 'Polygon' ? [g.coordinates[0]] : g.type === 'MultiPolygon' ? g.coordinates.map((p) => p[0]) : [];
    let best = null, bestA = -1;
    for (const r of rings) { let a = 0; for (let i = 0; i < r.length - 1; i++) a += r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1]; a = Math.abs(a); if (a > bestA) { bestA = a; best = r; } }
    return best ? ringCentroid(best) : null;
  }

  async function draw(host, opts) {
    if (!host) return null;
    opts = opts || {};
    const data = await loadGeo(opts.n);
    if (!data) { host.innerHTML = '<p class="ar-empty">선거구 경계 없음</p>'; return null; }
    const { geo, code } = data;
    const canon = (typeof canonSido === 'function') ? canonSido : (x) => x;
    const pcol = (typeof partyFill === 'function') ? partyFill : () => '#888';

    // SGG_Code → 1위 {party,name,pct} · (값 모드면) SGG_Code → 숫자
    const winBySgg = {};
    const valBySgg = {};
    for (const r of opts.races || []) {
      if (r.scope !== 'district') continue;
      const key = `${canon(r.sido)}|${r.district || r.name || ''}`;
      const sgg = code[key];
      if (!sgg) continue;
      if (opts.valueFn) {
        const v = opts.valueFn(r);
        if (v != null) valBySgg[sgg] = v;
        continue;                       // 값 모드에선 정당색을 아예 안 쓴다
      }
      const cs = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      if (cs[0] && cs[0].party) winBySgg[sgg] = { party: cs[0].party, name: cs[0].name, pct: cs[0].pct };
    }
    // 상대 스케일 — 기본은 이 지도의 최저~최고. opts.range를 주면 그걸 쓴다: 같은 자료를
    // 균등 hex로도 그릴 때 두 방식의 색이 같은 자를 써야 탭을 오가며 비교할 수 있다.
    const vals = Object.values(valBySgg);
    const lo = opts.range ? opts.range[0] : (vals.length ? Math.min(...vals) : 0);
    const hi = opts.range ? opts.range[1] : (vals.length ? Math.max(...vals) : 1);
    // 이름을 valueOf로 지으면 안 된다 — Object.prototype.valueOf가 상속돼 옵션을 안 넘겨도
    // 항상 truthy다(실제로 결과 지도가 값 모드로 잘못 들어갔다).
    const vcol = (window.Archive && window.Archive.turnout && window.Archive.turnout.color) || (() => '#88a');
    const vlabel = opts.valueLabel || ((v) => v.toFixed(1));

    const feats = geo.features;
    const { mnX, mnY, mxX, mxY } = bbox(feats);
    const kx = Math.cos(((mnY + mxY) / 2) * Math.PI / 180);
    const scale = (W - 2 * PAD) / ((mxX - mnX) * kx);
    const H = (mxY - mnY) * scale + 2 * PAD;
    const px = (lng) => PAD + (lng - mnX) * kx * scale;
    const py = (lat) => PAD + (mxY - lat) * scale;
    const ringPath = (r) => r.map(([x, y], i) => (i ? 'L' : 'M') + px(x).toFixed(1) + ' ' + py(y).toFixed(1)).join(' ') + ' Z';
    const polyPath = (rings) => rings.map(ringPath).join(' ');
    const featPath = (g) => g.type === 'Polygon' ? polyPath(g.coordinates) : g.type === 'MultiPolygon' ? g.coordinates.map(polyPath).join(' ') : '';

    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('xmlns', NS);
    const EM = (typeof SIDO_EDGE_MARGIN !== 'undefined') ? SIDO_EDGE_MARGIN : 78;
    svg.setAttribute('viewBox', `${-EM} 0 ${(W + 2 * EM).toFixed(1)} ${H.toFixed(1)}`);
    svg.setAttribute('width', (W + 2 * EM).toFixed(1)); svg.setAttribute('height', H.toFixed(1));
    // 값 모드는 og·공유에서 1위 지도와 다른 키여야 한다(같은 키면 서로를 덮어쓴다).
    svg.setAttribute('class', 'district-map-svg' + (opts.valueFn ? ' district-turnout-geo' : ''));

    const sel = opts.selected || null;
    const labels = [], cells = [];
    for (const f of feats) {
      const sgg = String(f.properties.SGG_Code || '');
      const win = winBySgg[sgg];
      const val = opts.valueFn ? valBySgg[sgg] : undefined;
      const sido = f.properties.SIDO || '';
      const name = f.properties.SGG || '';
      const where = f.properties.SIDO_SGG || (sido + ' ' + name);
      const path = document.createElementNS(NS, 'path');
      path.setAttribute('d', featPath(f.geometry));
      path.setAttribute('fill-rule', 'evenodd');
      if (val != null) { path.setAttribute('fill', vcol(val, lo, hi)); path.setAttribute('class', 'district-map-region has-data'); }
      else if (win) { path.setAttribute('fill', pcol(win.party)); path.setAttribute('class', 'district-map-region has-data'); }
      else { path.setAttribute('class', 'district-map-region no-data'); }
      if (sel && sel.sgg === sgg) path.classList.add('is-selected');
      const tt = document.createElementNS(NS, 'title');
      tt.textContent = val != null ? `${where} · ${vlabel(val)}`
        : win ? `${where} · ${win.name || ''}(${win.party}) ${fmtPct(win.pct, { digits: 1 })}`
          : `${f.properties.SIDO_SGG || ''} · 데이터 없음`;
      path.appendChild(tt);
      if (opts.onSelect && win) { path.style.cursor = 'pointer'; path.addEventListener('click', () => opts.onSelect(sido, name, sgg)); }
      svg.appendChild(path);
      const c = centroid(f.geometry);
      if (c) { labels.push({ sido: canon(sido), cx: px(c[0]), cy: py(c[1]) }); cells.push({ region: sgg, cx: px(c[0]), cy: py(c[1]) }); }
    }
    if (typeof drawSidoEdgeLabels === 'function') drawSidoEdgeLabels(svg, labels);
    host.innerHTML = '';
    host.appendChild(svg);
    return { cells, lo, hi, shown: vals.length };
  }

  window.Archive = window.Archive || {};
  window.Archive.districtMap = { draw };
})();
