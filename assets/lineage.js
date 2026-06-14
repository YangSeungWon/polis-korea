// 정당사 계보도 (세로형) — data/parties/registry.json.
// 가로축 = 정치 스펙트럼(진보 좌 → 보수 우, 계열 컬럼), 세로축 = 시간(위=현재, 아래로 과거).
// 막대=존속기간, 선=계승(merge/split/rename 색). 막대 클릭 → /party/{정식명}/. 색은 parties.js.

(function () {
  const NOW = 2026.5;
  const REL_COLOR = { merge: '#d08700', split: '#2c82c9', rename: '#8a8f98', new: '#8a8f98', dissolve: '#8a8f98' };
  const COLS = ['진보', '민주', '중도', '충청', '보수', '기타'];  // 좌→우 스펙트럼
  const PXY = 9.5;       // 1년당 px (세로)
  const BAR_W = 11;
  const LANE_W = 98;     // 서브레인 폭(막대 + 라벨)
  const COL_GAP = 16;
  const PAD_T = 50, PAD_L = 44, PAD_B = 28;

  function pyear(s) {
    if (!s) return null;
    const m = String(s).match(/^(\d{4})(?:-(\d{2}))?/);
    return m ? +m[1] + (m[2] ? (+m[2] - 1) / 12 : 0) : null;
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  const color = (n) => (typeof partyColor === 'function' ? partyColor(n) : '#888');

  async function main() {
    const host = document.getElementById('lin-graph');
    let reg;
    try {
      reg = (await (await fetch('data/parties/registry.json')).json()).parties;
    } catch (e) {
      host.innerHTML = '<p class="lin-loading">계보 데이터를 불러오지 못했습니다.</p>';
      return;
    }
    const names = Object.keys(reg);
    const nameSet = new Set(names);

    const node = {};
    for (const name of names) {
      const info = reg[name];
      let f = pyear(info.founded);
      let d = info.dissolved ? pyear(info.dissolved) : NOW;
      if (f == null) f = d != null ? d : NOW;
      if (d == null) d = NOW;
      if (d < f) d = f;
      node[name] = { name, info, f, d, stream: info.stream || '기타' };
    }

    // 엣지(전신→후신)
    const edges = []; const seenE = new Set();
    const addEdge = (a, b) => {
      if (!nameSet.has(a) || !nameSet.has(b) || a === b) return;
      const k = a + '>' + b; if (seenE.has(k)) return; seenE.add(k);
      edges.push([a, b]);
    };
    for (const name of names) {
      (reg[name].successors || []).forEach((s) => addEdge(name, s));
      (reg[name].predecessors || []).forEach((p) => addEdge(p, name));
    }

    // 시간축(세로, 위=현재)
    const ys = names.flatMap((n) => [node[n].f, node[n].d]);
    const minY = Math.floor(Math.min(...ys) / 5) * 5;
    const maxY = NOW;
    const plotH = (maxY - minY) * PXY;
    const yScale = (yr) => PAD_T + (maxY - yr) * PXY;   // 현재→위, 과거→아래

    // 계열 컬럼 + 서브레인(시간 겹침 회피) 패킹, x 배치
    const colMembers = {};
    for (const name of names) (colMembers[node[name].stream] || (colMembers[node[name].stream] = [])).push(name);
    const cols = COLS.filter((s) => colMembers[s]);
    let xCur = PAD_L;
    const colInfo = [];
    for (const s of cols) {
      const sorted = colMembers[s].slice().sort((a, b) => node[a].f - node[b].f);
      const laneEnd = [];
      for (const nm of sorted) {
        const n = node[nm];
        let lane = laneEnd.findIndex((e) => e <= n.f + 0.01);
        if (lane < 0) { lane = laneEnd.length; laneEnd.push(0); }
        laneEnd[lane] = n.d; n.lane = lane;
      }
      const nLanes = laneEnd.length || 1;
      const w = nLanes * LANE_W;
      colInfo.push({ stream: s, x: xCur, w });
      for (const nm of colMembers[s]) node[nm].x = xCur + node[nm].lane * LANE_W;
      xCur += w + COL_GAP;
    }
    const W = xCur + 8;
    const H = PAD_T + plotH + PAD_B;

    const out = [`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="lin-svg" xmlns="http://www.w3.org/2000/svg">`];

    // 연도 가로 그리드
    for (let yr = Math.ceil(minY / 10) * 10; yr <= maxY; yr += 10) {
      const y = yScale(yr);
      out.push(`<line x1="${PAD_L - 8}" y1="${y.toFixed(1)}" x2="${W}" y2="${y.toFixed(1)}" class="lin-grid"/>`);
      out.push(`<text x="6" y="${(y + 4).toFixed(1)}" class="lin-year">${yr}</text>`);
    }

    // 컬럼 배경 + 계열 헤더
    colInfo.forEach((c, i) => {
      if (i % 2 === 1) out.push(`<rect x="${(c.x - COL_GAP / 2).toFixed(1)}" y="${PAD_T - 6}" width="${(c.w + COL_GAP).toFixed(1)}" height="${(plotH + 12).toFixed(1)}" class="lin-band"/>`);
      out.push(`<text x="${(c.x + c.w / 2).toFixed(1)}" y="${PAD_T - 24}" class="lin-col-label">${esc(c.stream)}</text>`);
    });

    // 엣지 — pred 끝(위) → succ 시작(아래보다 위). 세로 베지어.
    for (const [a, c] of edges) {
      const na = node[a], nc = node[c];
      const x1 = na.x + BAR_W / 2, y1 = yScale(na.d);
      const x2 = nc.x + BAR_W / 2, y2 = yScale(nc.f);
      const col = REL_COLOR[nc.info.relation] || '#8a8f98';
      const dy = Math.max(12, Math.abs(y1 - y2) * 0.4);
      out.push(`<path d="M${x1.toFixed(1)},${y1.toFixed(1)} C${x1.toFixed(1)},${(y1 - dy).toFixed(1)} ${x2.toFixed(1)},${(y2 + dy).toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)}" class="lin-edge" stroke="${col}"/>`);
    }

    // 막대(세로) + 라벨(오른쪽)
    for (const name of names) {
      const n = node[name];
      const yT = yScale(n.d), h = Math.max(yScale(n.f) - yT, 4);
      const col = color(name);
      out.push(`<a href="/party/${encodeURIComponent(name)}/" class="lin-node">`);
      out.push(`<rect x="${n.x.toFixed(1)}" y="${yT.toFixed(1)}" width="${BAR_W}" height="${h.toFixed(1)}" rx="4" fill="${col}" class="lin-bar"><title>${esc(name)}${n.info.abbr ? ' (' + esc(n.info.abbr) + ')' : ''} · ${esc(n.info.founded || '')}~${esc(n.info.dissolved || '현재')}</title></rect>`);
      out.push(`<text x="${(n.x + BAR_W + 4).toFixed(1)}" y="${(yT + 10).toFixed(1)}" class="lin-bar-label">${esc(name)}</text>`);
      out.push(`</a>`);
    }

    out.push('</svg>');
    host.innerHTML = out.length > 1 ? out.join('') : '<p class="lin-loading">표시할 계보가 없습니다.</p>';
  }

  document.addEventListener('DOMContentLoaded', main);
  let rt = null;
  window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(main, 200); });
})();
