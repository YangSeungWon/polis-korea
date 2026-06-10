// 광역단체장 — 시도 hex map (SIDO_HEX_LAYOUT 5×5 격자).
// 각 시도 = 1 hex, 1위 정당 색 + 후보명·득표율 label.

(function () {
  const NS = 'http://www.w3.org/2000/svg';
  // pointy-top hex grid math
  function hexPoints(cx, cy, R) {
    const pts = [];
    for (let i = 0; i < 6; i++) {
      const a = Math.PI / 6 + i * Math.PI / 3;
      pts.push(`${cx + R * Math.cos(a)},${cy + R * Math.sin(a)}`);
    }
    return pts.join(' ');
  }

  // 시도 hex 그리기 (host 엘리먼트 + races). sidoView가 호출.
  function draw(host, races) {
    if (!host) return;
    if (typeof SIDO_HEX_LAYOUT !== 'object') return;
    // 레이아웃 키 = 현 캐노니컬명(강원특별자치도·전북특별자치도). 데이터 시도명(옛 강원도/전라북도 포함)을
    // canonSido로 정규화해 매칭.
    const canon = (typeof canonSido === 'function') ? canonSido : (x) => x;
    const bySido = {};
    for (const r of races) {
      const cs = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      if (cs[0]) bySido[canon(r.sido)] = { name: cs[0].name, party: cs[0].party, pct: cs[0].pct };
    }
    // 전남광주 통합(2026) — 병합 race를 광주·전남 양 셀에 매핑('통합' 표기 변형도 수용).
    const merged = bySido['전남광주특별시'] || bySido['전남광주통합특별시'];

    const COL_W = 80, ROW_H = 70, OFF_X = 50, OFF_Y = 50, R = 36;
    const cells = [];
    const seen = new Set();
    for (const [sido, pos] of Object.entries(SIDO_HEX_LAYOUT)) {
      const key = `${pos.col},${pos.row}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const win = bySido[sido] || ((sido === '광주광역시' || sido === '전라남도') ? merged : undefined);
      const cx = OFF_X + pos.col * COL_W + (pos.row % 2 ? COL_W / 2 : 0);
      const cy = OFF_Y + pos.row * ROW_H * 0.87;
      cells.push({ sido, pos, cx, cy, label: pos.label, win });
    }
    const maxCx = Math.max(...cells.map((c) => c.cx)) + R + 20;
    const maxCy = Math.max(...cells.map((c) => c.cy)) + R + 20;

    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('xmlns', NS);
    svg.setAttribute('viewBox', `0 0 ${maxCx} ${maxCy}`);
    svg.setAttribute('class', 'governor-hex-svg');

    for (const cell of cells) {
      const g = document.createElementNS(NS, 'g');
      const poly = document.createElementNS(NS, 'polygon');
      poly.setAttribute('points', hexPoints(cell.cx, cell.cy, R));
      if (cell.win) {
        poly.setAttribute('fill', (typeof partyColor === 'function') ? partyColor(cell.win.party) : '#888');
        poly.setAttribute('class', 'gov-hex-cell has-data');
      } else {
        poly.setAttribute('class', 'gov-hex-cell no-data');
      }
      g.appendChild(poly);
      const tt = document.createElementNS(NS, 'title');
      tt.textContent = cell.win
        ? `${cell.sido} · ${cell.win.name}(${cell.win.party}) ${(cell.win.pct || 0).toFixed(1)}%`
        : `${cell.sido} · 데이터 없음`;
      g.appendChild(tt);
      // 시도 라벨
      const t1 = document.createElementNS(NS, 'text');
      t1.setAttribute('x', cell.cx); t1.setAttribute('y', cell.cy - 6);
      t1.setAttribute('text-anchor', 'middle');
      t1.setAttribute('font-size', '13');
      t1.setAttribute('font-weight', '700');
      t1.setAttribute('class', cell.win ? 'gov-hex-label on-data' : 'gov-hex-label no-data');
      t1.textContent = cell.label;
      g.appendChild(t1);
      // 후보명
      if (cell.win) {
        const t2 = document.createElementNS(NS, 'text');
        t2.setAttribute('x', cell.cx); t2.setAttribute('y', cell.cy + 9);
        t2.setAttribute('text-anchor', 'middle');
        t2.setAttribute('font-size', '11');
        t2.setAttribute('font-weight', '700');
        t2.setAttribute('class', 'gov-hex-name');
        t2.textContent = cell.win.name;
        g.appendChild(t2);
        const t3 = document.createElementNS(NS, 'text');
        t3.setAttribute('x', cell.cx); t3.setAttribute('y', cell.cy + 22);
        t3.setAttribute('text-anchor', 'middle');
        t3.setAttribute('font-size', '10');
        t3.setAttribute('class', 'gov-hex-pct');
        t3.setAttribute('font-variant-numeric', 'tabular-nums');
        t3.textContent = `${(cell.win.pct || 0).toFixed(1)}%`;
        g.appendChild(t3);
      }
      svg.appendChild(g);
    }
    host.innerHTML = '';
    host.appendChild(svg);
  }

  // opts: {tc='3'(광역단체장)|'1'(대선), hostId='ar-governor-hex'} — 단독 호출용(sidoView 없이).
  function init(ctx, opts) {
    const tc = (opts && opts.tc) || '3';
    const hostId = (opts && opts.hostId) || 'ar-governor-hex';
    const host = document.getElementById(hostId);
    if (!host) return;
    const races = (ctx?.results?.races || []).filter(
      (r) => r.scope === 'sido' && r.sg_typecode === tc
    );
    if (!races.length) {
      host.parentElement?.setAttribute('hidden', '');
      return;
    }
    host.parentElement?.removeAttribute('hidden');
    draw(host, races);
  }

  window.Archive = window.Archive || {};
  window.Archive.governorHex = { init, draw };
})();
