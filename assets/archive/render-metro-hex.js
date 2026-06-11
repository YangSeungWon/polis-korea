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
  const NEIGHBORS = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]];
  function hexRing(layer) {
    const ring = [];
    let q = -layer, r = layer;
    for (let side = 0; side < 6; side++) {
      const [dq, dr] = NEIGHBORS[side];
      for (let step = 0; step < layer; step++) {
        ring.push([q, r]);
        q += dq; r += dr;
      }
    }
    return ring;
  }
  function hexSpiral(N) {
    if (N <= 0) return [];
    const out = [[0, 0]];
    let layer = 0;
    while (out.length < N) {
      layer += 1;
      const ring = hexRing(layer);
      const ringSize = ring.length;
      const remaining = N - out.length;
      if (remaining >= ringSize) {
        for (const p of ring) out.push(p);
      } else {
        for (let i = 0; i < remaining; i++) {
          const idx = Math.round(i * ringSize / remaining) % ringSize;
          out.push(ring[idx]);
        }
      }
    }
    return out;
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
          // 당선자 전원 — 전남광주통합 시도의회는 중선거구(1선거구 2~4명). won 없으면 top-1 fallback.
          const wonCs = (r.candidates || []).filter((c) => c.won);
          if (wonCs.length) {
            for (const c of wonCs) add(sd, c.party || '무소속', 1);
          } else {
            const top = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0))[0];
            if (top) add(sd, top.party || '무소속', 1);
          }
        }
      } else if (r.sg_typecode === '8' && r.scope === 'proportional_sido') {
        for (const c of r.candidates || []) add(sd, c.party || '무소속', c.seats || 0);
      }
    }
    return bySido;
  }

  // SIDO_HEX_LAYOUT (parties.js) 기반 5×5 격자 좌표 — 시도 cluster 겹침 방지.
  // col,row를 pixel로 변환. SPACING은 cluster radius 보다 크게.
  const SIDO_GAP = 120;  // 시도 hex 간 거리
  const SMALL_R = 3.5;   // 모든 시도 공통 hex 크기 (1석 = 1 hex 동일 면적)
  function sidoCentroidsFromLayout(layout) {
    const lay = layout || (typeof SIDO_HEX_LAYOUT === 'object' ? SIDO_HEX_LAYOUT : null);
    if (!lay) return null;
    const out = new Map();
    const seen = new Set();
    for (const [sido, pos] of Object.entries(lay)) {
      const k = `${pos.col},${pos.row}`;
      if (seen.has(k)) continue;
      seen.add(k);
      const cx = 80 + pos.col * SIDO_GAP + (pos.row % 2) * SIDO_GAP / 2;
      const cy = 60 + pos.row * SIDO_GAP * 0.87;
      out.set(sido, { cx, cy, label: pos.label });
    }
    return out;
  }

  // 전남광주 통합 셀('전남광주특별시')은 광주 지역구 + 전남 지역구 + 통합 비례를 모두 합산.
  //   (지역구는 광주/전남 라벨 분리, 비례는 '전남광주통합특별시' 한 배분 — 시도의회는 1개.)
  function aliasSido(name) {
    if (name === '전남광주통합특별시' || name === '전남광주특별시') return ['광주광역시', '전라남도', '전남광주통합특별시'];
    return [name];
  }

  async function loadHex() {
    return fetch('data/geo/sigungu_hex.json').then((r) => r.json()).catch(() => []);
  }

  function render(svg, _hexCells, sidoSeats) {
    // 전남광주 통합 배분(비례)이 데이터에 있으면 '전남광주' 한 셀 레이아웃(9회+). 그 전은 분리 유지.
    const hasMerged = sidoSeats.has('전남광주통합특별시') || sidoSeats.has('전남광주특별시');
    const layout = (hasMerged && typeof honamMergedLayout === 'function')
      ? honamMergedLayout(SIDO_HEX_LAYOUT) : null;
    const centroids = sidoCentroidsFromLayout(layout);
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
      // 클릭 → 아래 당선인 섹션을 그 시도 광역의원으로 필터·스크롤.
      g.style.cursor = 'pointer';
      g.addEventListener('click', () => window.Archive?.winners?.focus?.({ sido: sd, level: '광역의원' }));
      // smallR 고정 → cluster 실제 외곽 반경 = L * sqrt(3) * smallR (axial L 레이어).
      const L_est = Math.ceil(Math.sqrt(Math.max(N - 1, 0) / 3));
      const clusterR = Math.max(14, (L_est + 0.6) * Math.sqrt(3) * SMALL_R);
      const outline = document.createElementNS(NS, 'circle');
      outline.setAttribute('cx', info.cx); outline.setAttribute('cy', info.cy);
      outline.setAttribute('r', clusterR);
      outline.setAttribute('class', 'metro-outline');
      outline.setAttribute('stroke-width', '1.2');
      g.appendChild(outline);
      const tt = document.createElementNS(NS, 'title');
      const seatsStr = sorted.map(([p, n]) => `${p} ${n}`).join(' · ');
      tt.textContent = `${sd} 광역의회 ${N}석 · ${seatsStr}`;
      g.appendChild(tt);

      const smallR = SMALL_R;
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
      t.setAttribute('class', 'metro-hex-label');
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
      if (tot) tot.textContent = `${totalSeats}석 (시·도의회) · hex 클릭 → 당선인`;
    }
  }

  window.Archive = window.Archive || {};
  window.Archive.metroHex = { init };
})();
