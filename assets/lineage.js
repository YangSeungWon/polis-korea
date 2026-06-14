// 정당사 계보도 — data/parties/registry.json의 창당/해산·전신/후신을 시간축 간트로.
// 막대=존속기간, 선=계승(합당/분당/개명). 계열=계보 연결성분(union-find) 자동 분리.
// 색은 parties.js partyColor(). 막대 클릭 → /party/{정식명}/.

(function () {
  const NOW = 2026.5;
  const REL_COLOR = { merge: '#d08700', split: '#2c82c9', rename: '#8a8f98', new: '#8a8f98', dissolve: '#8a8f98' };

  function pyear(s) {
    if (!s) return null;
    const m = String(s).match(/^(\d{4})(?:-(\d{2}))?/);
    if (!m) return null;
    return +m[1] + (m[2] ? (+m[2] - 1) / 12 : 0);
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  const color = (name) => (typeof partyColor === 'function' ? partyColor(name) : '#888');

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

    // 노드 — f(창당)·d(해산/현재)
    const node = {};
    for (const name of names) {
      const info = reg[name];
      let f = pyear(info.founded);
      let d = info.dissolved ? pyear(info.dissolved) : NOW;
      if (f == null) f = d != null ? d : NOW;
      if (d == null) d = NOW;
      if (d < f) d = f;
      node[name] = { name, info, f, d, rel: info.relation };
    }

    // 엣지(전신→후신) — 계승 연결선용 (계열 경계 넘는 합당·분당도 그대로 그림)
    const edges = []; const seenE = new Set();
    const addEdge = (a, b) => {
      if (!nameSet.has(a) || !nameSet.has(b) || a === b) return;
      const k = a + '' + b; if (seenE.has(k)) return; seenE.add(k);
      edges.push([a, b]);
    };
    for (const name of names) {
      (reg[name].successors || []).forEach((s) => addEdge(name, s));
      (reg[name].predecessors || []).forEach((p) => addEdge(p, name));
    }

    // 계열(stream) → 밴드. 순서: 진보·민주·충청·보수 인접(3당합당·자민련→한나라 연결선 짧게), 기타 마지막.
    const STREAM_ORDER = ['진보', '민주', '충청', '보수', '기타'];
    const byStream = {};
    for (const name of names) {
      const s = reg[name].stream || '기타';
      (byStream[s] || (byStream[s] = [])).push(name);
    }
    const families = STREAM_ORDER.filter((s) => byStream[s]).map((s) => {
      const members = byStream[s];
      members.label = s;
      return members;
    });

    // 계열 내 레인 패킹(창당순 greedy) — 시간 겹침 회피
    families.forEach((members) => {
      members.sort((a, b) => node[a].f - node[b].f);
      const laneEnd = [];
      for (const nm of members) {
        const n = node[nm];
        let lane = laneEnd.findIndex((end) => end <= n.f + 0.01);
        if (lane < 0) { lane = laneEnd.length; laneEnd.push(0); }
        laneEnd[lane] = n.d;
        n.lane = lane;
      }
      members._lanes = laneEnd.length;
    });

    // 좌표
    const W = Math.max(host.clientWidth || 900, 900);
    const PAD_L = 96, PAD_R = 24, PAD_T = 40, ROW = 30, BAR = 21, FAM_GAP = 16;
    const allF = names.map((n) => node[n].f).concat(names.map((n) => node[n].d));
    const minY = Math.floor(Math.min(...allF) / 5) * 5;
    const maxY = NOW;
    const plotW = W - PAD_L - PAD_R;
    const xs = (y) => PAD_L + (y - minY) / (maxY - minY) * plotW;

    // 각 노드 y 배치
    let yCur = PAD_T;
    const bands = [];
    for (const members of families) {
      const top = yCur;
      const h = members._lanes * ROW;
      for (const nm of members) node[nm].y = top + node[nm].lane * ROW + (ROW - BAR) / 2;
      bands.push({ members, top, h });
      yCur = top + h + FAM_GAP;
    }
    const H = yCur + 10;

    // SVG 조립
    const out = [];
    out.push(`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="lin-svg" xmlns="http://www.w3.org/2000/svg">`);

    // 연도 그리드 (10년 간격)
    for (let yr = Math.ceil(minY / 10) * 10; yr <= maxY; yr += 10) {
      const x = xs(yr);
      out.push(`<line x1="${x}" y1="${PAD_T - 8}" x2="${x}" y2="${H - 6}" class="lin-grid"/>`);
      out.push(`<text x="${x}" y="${PAD_T - 14}" class="lin-year">${yr}</text>`);
    }

    // 계열 밴드 배경 + 대표 라벨
    bands.forEach((b, i) => {
      if (i % 2 === 1) out.push(`<rect x="0" y="${b.top - 4}" width="${W}" height="${b.h}" class="lin-band"/>`);
      out.push(`<text x="10" y="${b.top + b.h / 2}" class="lin-fam-label">${esc(b.members.label)}계</text>`);
    });

    // 엣지 (전신 끝 → 후신 시작), 후신 relation 색
    for (const [a, c] of edges) {
      const na = node[a], nc = node[c];
      const x1 = xs(na.d), y1 = na.y + BAR / 2;
      const x2 = xs(nc.f), y2 = nc.y + BAR / 2;
      const col = REL_COLOR[nc.rel] || '#8a8f98';
      const dx = Math.max(18, Math.abs(x2 - x1) * 0.4);
      out.push(`<path d="M${x1.toFixed(1)},${y1.toFixed(1)} C${(x1 + dx).toFixed(1)},${y1.toFixed(1)} ${(x2 - dx).toFixed(1)},${y2.toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)}" class="lin-edge" stroke="${col}"/>`);
    }

    // 막대 + 라벨
    for (const name of names) {
      const n = node[name];
      const x1 = xs(n.f), x2 = xs(n.d), w = Math.max(x2 - x1, 4);
      const col = color(name);
      const labelInside = w > Math.max(48, (name.length + (n.info.abbr ? 0 : 0)) * 13);
      out.push(`<a href="/party/${encodeURIComponent(name)}/" class="lin-node">`);
      out.push(`<rect x="${x1.toFixed(1)}" y="${n.y}" width="${w.toFixed(1)}" height="${BAR}" rx="5" fill="${col}" class="lin-bar"><title>${esc(name)}${n.info.abbr ? ' (' + esc(n.info.abbr) + ')' : ''} · ${esc(n.info.founded || '')}${n.info.dissolved ? '~' + esc(n.info.dissolved) : '~'}</title></rect>`);
      const lbl = esc(name);
      if (labelInside) {
        out.push(`<text x="${(x1 + 7).toFixed(1)}" y="${n.y + BAR / 2 + 4}" class="lin-bar-label lin-in">${lbl}</text>`);
      } else {
        out.push(`<text x="${(x2 + 5).toFixed(1)}" y="${n.y + BAR / 2 + 4}" class="lin-bar-label lin-out">${lbl}</text>`);
      }
      out.push(`</a>`);
    }

    out.push('</svg>');
    host.innerHTML = out.length > 2 ? out.join('') : '<p class="lin-loading">표시할 계보가 없습니다.</p>';
  }

  document.addEventListener('DOMContentLoaded', main);
  let rt = null;
  window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(main, 200); });
})();
