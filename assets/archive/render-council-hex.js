// 9회·8회 archive — 시군구 hex cluster 위에 의석 정당별 spiral.
// 부모 hex = sigungu_hex.json 좌표 / 자식 = 의석 수 N spiral (render-sigungu 패턴 reuse).
// 데이터: races[] tc=6(지역구) + tc=9(비례). 8회는 sigungu_summary scope, 9회는 race winner count.

(function () {
  const NS = 'http://www.w3.org/2000/svg';
  // hexgrid.js 헬퍼
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
  // 표준 axial hex 이웃 (pointy-top, 시계방향).
  const NEIGHBORS = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]];
  // 거리 layer의 ring 6L 개 cells 생성. 시작 = layer steps in NEIGHBORS[4] direction = (-L, L).
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
  // Compact cluster — 중심(0,0) + 완전 ring 1..L-1 + partial ring L 둘레 균등 sample.
  function hexSpiral(N) {
    if (N <= 0) return [];
    const out = [[0, 0]];
    let layer = 0;
    while (out.length < N) {
      layer += 1;
      const ring = hexRing(layer);
      const ringSize = ring.length;  // 6 * layer
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

  // sigungu별 의석 (지역구·비례) by party.
  // 구가 있는 시(부천시·용인시·수원시 등): tc=6 race.sigungu가 '부천시원미구' 등 →
  // hex의 '부천시' key와 매칭 위해 부모 sigungu 추출 (시·군·구 suffix 직전).
  function parentSigungu(sd, sg) {
    if (!sg) return sg;
    // '수원시장안구' → '수원시', '청주시상당구' → '청주시', '천안시동남구' → '천안시'
    const m = sg.match(/^(.+?[시군])(.+[구])$/);
    return m ? m[1] : sg;
  }
  function aggregateSigunguSeats(races) {
    const byKey = new Map();
    function add(sd, sg, party, n) {
      if (!n) return;
      const parent = parentSigungu(sd, sg);
      const k = `${sd}|${parent}`;
      const m = byKey.get(k) || new Map();
      m.set(party, (m.get(party) || 0) + n);
      byKey.set(k, m);
    }
    for (const r of races) {
      const sd = r.sido || '';
      const sg = r.sigungu || '';
      if (r.sg_typecode === '6') {
        if (r.scope === 'sigungu_summary') {
          for (const c of r.candidates || []) add(sd, sg, c.party || '무소속', c.seats || 0);
        } else if (r.scope === 'district') {
          // 중선거구 — 당선자(won) 전원 = 의석. won 없으면 1위만(fallback).
          const won = (r.candidates || []).filter((c) => c.won);
          if (won.length) {
            for (const c of won) add(sd, sg, c.party || '무소속', 1);
          } else {
            const top = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0))[0];
            if (top) add(sd, sg, top.party || '무소속', 1);
          }
        }
      } else if (r.sg_typecode === '9' && r.scope === 'proportional_sigungu') {
        for (const c of r.candidates || []) add(sd, sg, c.party || '무소속', c.seats || 0);
      }
    }
    return byKey;
  }

  // sigungu hex 위치 + 이름 (legacy 회차는 sigungu_hex_legacy도 시도)
  async function loadHexLayout() {
    const main = await fetch('data/geo/sigungu_hex.json').then((r) => r.json()).catch(() => []);
    return main;
  }

  // 데이터 키 정규화 — 통합특별시·과거 행정명 매핑
  function normalizeKey(sido, sigungu) {
    // 전남광주통합특별시 / 전남광주특별시 → 광주광역시·전라남도 분리 매칭 위해 그대로 둠
    return `${sido}|${sigungu}`;
  }

  function render(svg, hexCells, sigunguSeats) {
    const maxC = Math.max(...hexCells.map((c) => c.c));
    const maxR = Math.max(...hexCells.map((c) => c.r));
    const w = OFF_X * 2 + (maxC + 1) * COL_W;
    const h = OFF_Y * 2 + (maxR + 1) * ROW_H;
    const EM = (typeof SIDO_EDGE_MARGIN !== 'undefined') ? SIDO_EDGE_MARGIN : 78;  // 좌우 외곽 라벨 여백
    svg.setAttribute('viewBox', `${-EM} 0 ${w + 2 * EM} ${h}`);
    svg.setAttribute('width', w + 2 * EM);
    svg.setAttribute('height', h);

    // 부모 hex 격자 콜리전 — pointy-top tiling spacing 정확:
    //   colW = R * sqrt(3),  rowH = R * 1.5.
    // COL_W=24 → R ≤ 24/sqrt(3) ≈ 13.86. ROW_H=21 → R ≤ 14.
    const PARENT_R = 13.85;
    const SMALL_R = 2.4;  // 모든 시군구 공통 hex 크기 (1석 = 1 hex 동일)

    // 시도명은 중앙 워터마크 대신 좌우 외곽 세로줄 라벨(history 방식)로 — 아래 hex 뒤 drawSidoEdgeLabels.

    let totalSeats = 0;
    const partyTotal = new Map();

    for (const cell of hexCells) {
      const seats = sigunguSeats.get(normalizeKey(cell.sido, cell.name));
      const [cx, cy] = hexCenter(cell.c, cell.r);
      const g = document.createElementNS(NS, 'g');
      // 클릭 → 아래 당선인 섹션을 그 시군구 기초의원으로 필터·스크롤(의석 있는 셀만).
      if (seats && seats.size) {
        g.style.cursor = 'pointer';
        g.addEventListener('click', () => window.Archive?.winners?.focus?.({ sido: cell.sido, q: cell.name, level: '기초의원' }));
      }
      // 부모 outline
      const outline = document.createElementNS(NS, 'polygon');
      outline.setAttribute('points', hexPoints(cx, cy, PARENT_R));
      outline.setAttribute('class', 'council-outline');
      outline.setAttribute('stroke-width', '0.8');
      g.appendChild(outline);
      // 시군구명 hover tooltip
      const tt = document.createElementNS(NS, 'title');
      const seatsStr = seats ? Array.from(seats.entries()).sort((a, b) => b[1] - a[1])
        .map(([p, n]) => `${p} ${n}`).join(' · ') : '데이터 없음';
      tt.textContent = `${cell.sido} ${cell.name} · ${seatsStr}`;
      g.appendChild(tt);
      // single-tier (세종·제주시·서귀포 등) — 회색 X
      if (cell.single_tier || !seats || seats.size === 0) {
        outline.setAttribute('class', 'council-outline no-data');
        svg.appendChild(g);
        continue;
      }
      const sorted = Array.from(seats.entries()).sort((a, b) => b[1] - a[1]);
      const N = sorted.reduce((s, [, n]) => s + n, 0);
      totalSeats += N;
      for (const [p, n] of sorted) partyTotal.set(p, (partyTotal.get(p) || 0) + n);
      const fills = [];
      for (const [p, n] of sorted) {
        for (let k = 0; k < n; k++) fills.push((typeof partyColor === 'function') ? partyColor(p) : '#999');
      }
      // small hex radius — N이 클수록 작게
      const smallR = SMALL_R;
      const spiral = hexSpiral(N);
      for (let i = 0; i < spiral.length; i++) {
        const [q, ar] = spiral[i];
        const dx = smallR * Math.sqrt(3) * (q + ar / 2);
        const dy = smallR * 1.5 * ar;
        const sx = cx + dx, sy = cy + dy;
        const poly = document.createElementNS(NS, 'polygon');
        poly.setAttribute('points', hexPoints(sx, sy, smallR * 0.95));
        poly.setAttribute('fill', fills[i] || '#e6e9ef');
        poly.setAttribute('stroke', 'rgba(255,255,255,0.5)');
        poly.setAttribute('stroke-width', '0.3');
        g.appendChild(poly);
      }
      svg.appendChild(g);
    }
    // 시도명 외곽 세로줄 라벨 (history 방식) — 헥스 위(여백)에.
    if (typeof drawSidoEdgeLabels === 'function') {
      const pts = hexCells.map((c) => { const [cx, cy] = hexCenter(c.c, c.r); return { sido: c.sido, cx, cy }; });
      drawSidoEdgeLabels(svg, pts);
    }
    return { totalSeats, partyTotal };
  }

  async function init(ctx) {
    const host = document.getElementById('ar-council-hex');
    if (!host) return;
    const races = ctx?.results?.races || [];
    const hexCells = await loadHexLayout();
    if (!hexCells.length) return;
    const seats = aggregateSigunguSeats(races);
    if (seats.size === 0) {
      host.parentElement?.setAttribute('hidden', '');
      return;
    }
    host.parentElement?.removeAttribute('hidden');
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('xmlns', NS);
    svg.setAttribute('class', 'council-hex-svg');
    const { totalSeats, partyTotal } = render(svg, hexCells, seats);
    host.innerHTML = '';
    host.appendChild(svg);
    // 범례 — 정당별 합계
    const legend = document.getElementById('ar-council-hex-legend');
    if (legend) {
      const sorted = Array.from(partyTotal.entries()).sort((a, b) => b[1] - a[1]);
      legend.innerHTML = sorted.map(([p, n]) => {
        const col = (typeof partyColor === 'function') ? partyColor(p) : '#999';
        return `<span class="ch-leg" style="color:${col}"><b>${n}</b> ${p}</span>`;
      }).join(' · ');
      const tot = document.getElementById('ar-council-hex-total');
      if (tot) tot.textContent = `${totalSeats}석 (시군구 의회) · hex 클릭 → 당선인`;
    }
  }

  // archive/local.js render 끝나면 호출. window.Archive 네임스페이스 attach.
  window.Archive = window.Archive || {};
  window.Archive.councilHex = { init };
})();
