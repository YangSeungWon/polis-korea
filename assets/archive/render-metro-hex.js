// 시도의회 광역의원 의석 분포 — 시도 중심에 의석 spiral.
// 부모 = sigungu_hex의 시도별 centroid. 자식 = 광역의원 N석 spiral.
// 데이터: tc=5(지역구) + tc=8(비례). 8회+ sido_summary, 9회는 race winner 1로 fallback.

(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const COL_W = 24, ROW_H = 21, OFF_X = 30, OFF_Y = 30;
  function hexCenter(c, r) {
    const x = OFF_X + c * COL_W + (r % 2 ? COL_W / 2 : 0);
    const y = OFF_Y + r * ROW_H;
    return [x, y];
  }
  function hexPoints(cx, cy, R) {
    const pts = [];
    for (let i = 0; i < 6; i++) {
      const a = Math.PI / 6 + i * Math.PI / 3;
      pts.push(`${cx + R * Math.cos(a)},${cy + R * Math.sin(a)}`);
    }
    return pts.join(' ');
  }
  // Compact hex cluster — distance-from-center sort. 동그란 모양 + 중심 채움.
  function hexSpiral(N) {
    if (N <= 0) return [];
    let L = 0; let cap = 1;
    while (cap < N) { L += 1; cap += 6 * L; }
    const positions = [[0, 0]];
    const dirs = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]];
    for (let layer = 1; layer <= L; layer++) {
      let q = layer, ar = -layer;
      for (const [dq, dr] of dirs) {
        for (let k = 0; k < layer; k++) {
          q += dq; ar += dr;
          positions.push([q, ar]);
        }
      }
    }
    const dist = ([q, r]) => Math.max(Math.abs(q), Math.abs(r), Math.abs(q + r));
    positions.sort((a, b) => {
      const da = dist(a), db = dist(b);
      if (da !== db) return da - db;
      return Math.atan2(a[1] + a[0] / 2, a[0]) - Math.atan2(b[1] + b[0] / 2, b[0]);
    });
    return positions.slice(0, N);
  }

  // 시도별 광역의원 (지역구·비례) by party
  function aggregateMetroSeats(races) {
    const bySido = new Map();
    function add(sd, party, n) {
      if (!n) return;
      const m = bySido.get(sd) || new Map();
      m.set(party, (m.get(party) || 0) + n);
      bySido.set(sd, m);
    }
    for (const r of races) {
      const sd = r.sido || '';
      if (r.sg_typecode === '5') {
        if (r.scope === 'sido_summary') {
          for (const c of r.candidates || []) add(sd, c.party || '무소속', c.seats || 0);
        } else if (r.scope === 'district') {
          const top = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0))[0];
          if (top) add(sd, top.party || '무소속', 1);
        }
      } else if (r.sg_typecode === '8' && r.scope === 'proportional_sido') {
        for (const c of r.candidates || []) add(sd, c.party || '무소속', c.seats || 0);
      }
    }
    return bySido;
  }

  // SIDO_HEX_LAYOUT (parties.js) 기반 5×5 격자 좌표 — 시도 cluster 겹침 방지.
  // col,row를 pixel로 변환. SPACING은 cluster radius 보다 크게.
  const SIDO_GAP = 110;  // 시도 hex 간 거리 — outline overlap 방지
  function sidoCentroidsFromLayout() {
    if (typeof SIDO_HEX_LAYOUT !== 'object') return null;
    const out = new Map();
    const seen = new Set();
    for (const [sido, pos] of Object.entries(SIDO_HEX_LAYOUT)) {
      const k = `${pos.col},${pos.row}`;
      if (seen.has(k)) continue;
      seen.add(k);
      const cx = 80 + pos.col * SIDO_GAP + (pos.row % 2) * SIDO_GAP / 2;
      const cy = 60 + pos.row * SIDO_GAP * 0.87;
      out.set(sido, { cx, cy, label: pos.label });
    }
    return out;
  }

  // 시도명 정규화 — 통합특별시 → 분리 sido로 분기 (광주·전남)
  function aliasSido(name) {
    if (name === '전남광주통합특별시' || name === '전남광주특별시') return ['광주광역시', '전라남도'];
    return [name];
  }

  async function loadHex() {
    return fetch('data/geo/sigungu_hex.json').then((r) => r.json()).catch(() => []);
  }

  function render(svg, _hexCells, sidoSeats) {
    const centroids = sidoCentroidsFromLayout();
    if (!centroids) return { totalSeats: 0, partyTotal: new Map() };
    // viewBox — top 라벨 + bottom legend 위해 padding 충분히
    const xs = Array.from(centroids.values()).map((c) => c.cx);
    const ys = Array.from(centroids.values()).map((c) => c.cy);
    const w = Math.max(...xs) + 80;
    const h = Math.max(...ys) + 100;
    svg.setAttribute('viewBox', `0 -10 ${w} ${h + 10}`);
    svg.setAttribute('width', w); svg.setAttribute('height', h + 10);
    let totalSeats = 0;
    const partyTotal = new Map();

    for (const [sd, info] of centroids) {
      // alias 처리 — 통합특별시는 분리 sido 합산 표시
      let seats = sidoSeats.get(sd);
      if (!seats) {
        // 통합특별시 → 광주+전남 합산
        const aliases = aliasSido(sd);
        if (aliases.length > 1) {
          const merged = new Map();
          for (const a of aliases) {
            const m = sidoSeats.get(a);
            if (m) for (const [p, n] of m) merged.set(p, (merged.get(p) || 0) + n);
          }
          if (merged.size) seats = merged;
        }
      }
      if (!seats || seats.size === 0) continue;
      const sorted = Array.from(seats.entries()).sort((a, b) => b[1] - a[1]);
      const N = sorted.reduce((s, [, n]) => s + n, 0);
      totalSeats += N;
      for (const [p, n] of sorted) partyTotal.set(p, (partyTotal.get(p) || 0) + n);

      const g = document.createElementNS(NS, 'g');
      // 시도 outline — SIDO_GAP/2 안 (인접 cluster와 겹침 방지)
      const clusterR = SIDO_GAP * 0.45;
      const outline = document.createElementNS(NS, 'circle');
      outline.setAttribute('cx', info.cx); outline.setAttribute('cy', info.cy);
      outline.setAttribute('r', clusterR);
      outline.setAttribute('fill', 'rgba(255,255,255,0.45)');
      outline.setAttribute('stroke', 'rgba(27,34,55,0.45)');
      outline.setAttribute('stroke-width', '1.2');
      g.appendChild(outline);
      const tt = document.createElementNS(NS, 'title');
      const seatsStr = sorted.map(([p, n]) => `${p} ${n}`).join(' · ');
      tt.textContent = `${sd} 광역의회 ${N}석 · ${seatsStr}`;
      g.appendChild(tt);

      // small hex radius — 외곽 ring radius가 clusterR 안에 수렴.
      // L 레이어 hex의 cluster radius = L * smallR * sqrt(3)/2 * 2 = L * smallR * sqrt(3).
      // L = ceil(sqrt((N-1)/3)). smallR = clusterR / (L * sqrt(3) + 0.5)
      const L_est = Math.ceil(Math.sqrt(Math.max(N - 1, 0) / 3));
      const smallR = Math.max(1.4, clusterR / (L_est * Math.sqrt(3) + 1.2));
      const fills = [];
      for (const [p, n] of sorted) {
        for (let k = 0; k < n; k++) fills.push((typeof partyColor === 'function') ? partyColor(p) : '#999');
      }
      const spiral = hexSpiral(N);
      for (let i = 0; i < spiral.length; i++) {
        const [q, ar] = spiral[i];
        const dx = smallR * Math.sqrt(3) * (q + ar / 2);
        const dy = smallR * 1.5 * ar;
        const sx = info.cx + dx, sy = info.cy + dy;
        const poly = document.createElementNS(NS, 'polygon');
        poly.setAttribute('points', hexPoints(sx, sy, smallR * 0.92));
        poly.setAttribute('fill', fills[i] || '#e6e9ef');
        poly.setAttribute('stroke', 'rgba(255,255,255,0.45)');
        poly.setAttribute('stroke-width', '0.3');
        g.appendChild(poly);
      }
      // 시도 라벨 (위)
      const labelY = info.cy - clusterR - 6;
      const t = document.createElementNS(NS, 'text');
      t.setAttribute('x', info.cx); t.setAttribute('y', labelY);
      t.setAttribute('text-anchor', 'middle');
      t.setAttribute('font-size', '13');
      t.setAttribute('font-weight', '700');
      t.setAttribute('fill', '#0a0e1a');
      t.textContent = info.label || sd;
      g.appendChild(t);
      svg.appendChild(g);
    }
    return { totalSeats, partyTotal };
  }

  async function init(ctx) {
    const host = document.getElementById('ar-metro-hex');
    if (!host) return;
    const races = ctx?.results?.races || [];
    const seats = aggregateMetroSeats(races);
    if (seats.size === 0) {
      host.parentElement?.setAttribute('hidden', '');
      return;
    }
    host.parentElement?.removeAttribute('hidden');
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('xmlns', NS);
    svg.setAttribute('class', 'metro-hex-svg');
    const { totalSeats, partyTotal } = render(svg, null, seats);
    host.innerHTML = '';
    host.appendChild(svg);
    const legend = document.getElementById('ar-metro-hex-legend');
    if (legend) {
      const sorted = Array.from(partyTotal.entries()).sort((a, b) => b[1] - a[1]);
      legend.innerHTML = sorted.map(([p, n]) => {
        const col = (typeof partyColor === 'function') ? partyColor(p) : '#999';
        return `<span class="mh-leg" style="color:${col}"><b>${n}</b> ${p}</span>`;
      }).join(' · ');
      const tot = document.getElementById('ar-metro-hex-total');
      if (tot) tot.textContent = `${totalSeats}석 (시·도의회)`;
    }
  }

  window.Archive = window.Archive || {};
  window.Archive.metroHex = { init };
})();
