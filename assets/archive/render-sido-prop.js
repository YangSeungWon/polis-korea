// 시도 비례 뷰 — 대선 전용(승자독식 단색 거부). 두 모드:
//   격자(grid): 시도당 작은 hex N개를 후보 득표 비례 배분 (1 hex = 일정 표수)
//   dorling: 투표수 비례 원 + 후보 구성 파이 (force-directed packing)
// render-sigungu.js(history)의 자족 알고리즘 재사용. SIDO_HEX_LAYOUT 위치 사용.

(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const COL_W = 118, ROW_H = 104, OFF_X = 64, OFF_Y = 58;

  const norm = (n) => (n || '')
    .replace('강원특별자치도', '강원도')
    .replace('전북특별자치도', '전라북도');

  function hexPoints(cx, cy, R) {
    const pts = [];
    for (let i = 0; i < 6; i++) {
      const a = Math.PI / 6 + i * Math.PI / 3;
      pts.push(`${(cx + R * Math.cos(a)).toFixed(2)},${(cy + R * Math.sin(a)).toFixed(2)}`);
    }
    return pts.join(' ');
  }
  // axial 스파이럴 — 1..N hex 좌표
  function hexSpiral(N) {
    const out = [[0, 0]];
    if (N <= 1) return out;
    const seen = new Set(['0,0']);
    let frontier = [[0, 0]];
    const DIRS = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]];
    while (out.length < N) {
      const next = [];
      for (const [q, ar] of frontier) {
        for (const [dq, dr] of DIRS) {
          const nq = q + dq, nr = ar + dr;
          const key = nq + ',' + nr;
          if (seen.has(key)) continue;
          seen.add(key); next.push([nq, nr]); out.push([nq, nr]);
          if (out.length >= N) return out;
        }
      }
      frontier = next;
    }
    return out;
  }
  // 후보별 hex 개수 — 큰 정수 잔여(largest remainder)로 N에 정확히 맞춤
  function allocateByVotes(cands, N) {
    const total = cands.reduce((s, c) => s + (c.votes || 0), 0);
    if (!total) return cands.map(() => 0);
    const raw = cands.map((c) => (c.votes || 0) * N / total);
    const floors = raw.map(Math.floor);
    const rem = N - floors.reduce((a, b) => a + b, 0);
    const fracs = raw.map((v, i) => ({ i, f: v - Math.floor(v) })).sort((a, b) => b.f - a.f);
    for (let k = 0; k < rem; k++) floors[fracs[k].i] += 1;
    return floors;
  }
  function pieSlice(cx, cy, rad, a0, a1) {
    const x0 = cx + rad * Math.cos(a0), y0 = cy + rad * Math.sin(a0);
    const x1 = cx + rad * Math.cos(a1), y1 = cy + rad * Math.sin(a1);
    const large = (a1 - a0) > Math.PI ? 1 : 0;
    return `M ${cx.toFixed(2)} ${cy.toFixed(2)} L ${x0.toFixed(2)} ${y0.toFixed(2)} `
      + `A ${rad.toFixed(2)} ${rad.toFixed(2)} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} Z`;
  }
  const pcolor = (p) => (typeof partyColor === 'function') ? partyColor(p) : '#888';

  // races → 셀(위치+후보+투표수)
  function layoutCells(races) {
    if (typeof SIDO_HEX_LAYOUT !== 'object') return [];
    const bySido = {};
    for (const r of races) bySido[norm(r.sido)] = r;
    const cells = [];
    for (const [sido, pos] of Object.entries(SIDO_HEX_LAYOUT)) {
      const race = bySido[sido];
      if (!race) continue;
      const cands = (race.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      const voted = race.valid_votes || cands.reduce((s, c) => s + (c.votes || 0), 0);
      if (!voted) continue;
      cells.push({
        sido, label: pos.label, cands, voted,
        cx: OFF_X + pos.col * COL_W + (pos.row % 2 ? COL_W / 2 : 0),
        cy: OFF_Y + pos.row * ROW_H * 0.87,
      });
    }
    return cells;
  }

  function svgFor(host, cells, extra) {
    const W = Math.max(...cells.map((c) => c.cx)) + OFF_X + extra;
    const H = Math.max(...cells.map((c) => c.cy)) + OFF_Y + extra;
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('xmlns', NS);
    svg.setAttribute('viewBox', `0 0 ${W.toFixed(0)} ${H.toFixed(0)}`);
    svg.setAttribute('class', 'sido-prop-svg');
    return svg;
  }
  function titleText(cell) {
    const t = cell.cands.slice(0, 3)
      .map((c) => `${c.name}(${c.party}) ${(c.pct || 0).toFixed(1)}%`).join(' / ');
    return `${cell.sido} · ${t}`;
  }
  function sidoLabel(svg, cell, dy) {
    const t = document.createElementNS(NS, 'text');
    t.setAttribute('x', cell.cx.toFixed(1));
    t.setAttribute('y', (cell.cy + dy).toFixed(1));
    t.setAttribute('class', 'sido-prop-label');
    t.textContent = cell.label;
    svg.appendChild(t);
  }

  // === 격자 모드 ===
  function drawGrid(host, races) {
    if (!host) return;
    const cells = layoutCells(races);
    if (!cells.length) { host.parentElement?.setAttribute('hidden', ''); return; }
    const maxVoted = Math.max(...cells.map((c) => c.voted));
    // 최대 시도가 ~46개 hex가 되도록 단위 결정 (만 단위로 정리)
    const unit = Math.max(10000, Math.ceil(maxVoted / 46 / 10000) * 10000);
    const smallR = 3.5;
    const svg = svgFor(host, cells, 24);

    for (const cell of cells) {
      const N = Math.max(1, Math.round(cell.voted / unit));
      const alloc = allocateByVotes(cell.cands, N);
      const fills = [];
      for (let i = 0; i < cell.cands.length; i++) for (let k = 0; k < alloc[i]; k++) fills.push(pcolor(cell.cands[i].party));
      while (fills.length < N) fills.push('#e6e9ef');
      const spiral = hexSpiral(N);
      const g = document.createElementNS(NS, 'g');
      const tt = document.createElementNS(NS, 'title'); tt.textContent = titleText(cell); g.appendChild(tt);
      let maxd = 0;
      for (let i = 0; i < spiral.length; i++) {
        const [q, ar] = spiral[i];
        const dx = smallR * Math.sqrt(3) * (q + ar / 2);
        const dy = smallR * 1.5 * ar;
        maxd = Math.max(maxd, Math.abs(dy));
        const poly = document.createElementNS(NS, 'polygon');
        poly.setAttribute('points', hexPoints(cell.cx + dx, cell.cy + dy, smallR - 0.4));
        poly.setAttribute('fill', fills[i] || '#e6e9ef');
        poly.setAttribute('class', 'sido-prop-hex');
        g.appendChild(poly);
      }
      sidoLabel(svg, cell, -(maxd + 9));
      svg.appendChild(g);
    }
    // 단위 범례
    const leg = document.createElementNS(NS, 'text');
    leg.setAttribute('x', '4'); leg.setAttribute('y', '14');
    leg.setAttribute('class', 'sido-prop-legend');
    leg.textContent = `■ 1개 = ${(unit / 10000).toLocaleString()}만표 · 면적=득표, 색=후보`;
    svg.appendChild(leg);
    host.innerHTML = ''; host.appendChild(svg);
  }

  // === dorling 모드 ===
  function drawDorling(host, races) {
    if (!host) return;
    const cells = layoutCells(races);
    if (!cells.length) { host.parentElement?.setAttribute('hidden', ''); return; }
    const maxVoted = Math.max(...cells.map((c) => c.voted));
    const Rmax = 44;
    const nodes = cells.map((c) => ({
      cell: c, cx: c.cx, cy: c.cy, cx0: c.cx, cy0: c.cy,
      radius: Math.max(7, Rmax * Math.sqrt(c.voted / maxVoted)),
    }));
    // force-directed: 겹침 반발 + 원위치 앵커
    for (let iter = 0; iter < 60; iter++) {
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          const dx = b.cx - a.cx, dy = b.cy - a.cy;
          const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
          const overlap = a.radius + b.radius + 2 - dist;
          if (overlap > 0) {
            const push = overlap * 0.5 / dist;
            a.cx -= push * dx; a.cy -= push * dy;
            b.cx += push * dx; b.cy += push * dy;
          }
        }
      }
      for (const n of nodes) { n.cx += (n.cx0 - n.cx) * 0.06; n.cy += (n.cy0 - n.cy) * 0.06; }
    }
    const svg = svgFor(host, nodes.map((n) => ({ cx: n.cx, cy: n.cy })), Rmax + 16);
    for (const n of nodes) {
      const cell = n.cell;
      const g = document.createElementNS(NS, 'g');
      const tt = document.createElementNS(NS, 'title'); tt.textContent = titleText(cell); g.appendChild(tt);
      const cands = cell.cands.filter((c) => (c.votes || 0) > 0);
      const total = cands.reduce((s, c) => s + (c.votes || 0), 0);
      if (total > 0 && cands.length > 1) {
        let a0 = -Math.PI / 2;
        for (const c of cands) {
          const a1 = a0 + (c.votes / total) * 2 * Math.PI;
          const p = document.createElementNS(NS, 'path');
          p.setAttribute('d', pieSlice(n.cx, n.cy, n.radius, a0, a1));
          p.setAttribute('fill', pcolor(c.party));
          g.appendChild(p);
          a0 = a1;
        }
        const ring = document.createElementNS(NS, 'circle');
        ring.setAttribute('cx', n.cx.toFixed(1)); ring.setAttribute('cy', n.cy.toFixed(1));
        ring.setAttribute('r', n.radius.toFixed(1));
        ring.setAttribute('class', 'sido-prop-ring');
        g.appendChild(ring);
      } else {
        const c = document.createElementNS(NS, 'circle');
        c.setAttribute('cx', n.cx.toFixed(1)); c.setAttribute('cy', n.cy.toFixed(1));
        c.setAttribute('r', n.radius.toFixed(1));
        c.setAttribute('fill', cands[0] ? pcolor(cands[0].party) : '#e6e9ef');
        c.setAttribute('class', 'sido-prop-ring');
        g.appendChild(c);
      }
      svg.appendChild(g);
      // 라벨 — 원 중심 (반경 충분할 때만)
      if (n.radius >= 12) {
        const t = document.createElementNS(NS, 'text');
        t.setAttribute('x', n.cx.toFixed(1)); t.setAttribute('y', (n.cy + 3).toFixed(1));
        t.setAttribute('class', 'sido-prop-label on-disc');
        t.textContent = cell.label;
        svg.appendChild(t);
      }
    }
    const leg = document.createElementNS(NS, 'text');
    leg.setAttribute('x', '4'); leg.setAttribute('y', '14');
    leg.setAttribute('class', 'sido-prop-legend');
    leg.textContent = '● 크기=투표수 · 파이=후보 득표 구성';
    svg.appendChild(leg);
    host.innerHTML = ''; host.appendChild(svg);
  }

  window.Archive = window.Archive || {};
  window.Archive.sidoProp = { drawGrid, drawDorling };
})();
