// 정당사 계보도 (세로형) — data/parties/registry.json.
// 가로축 = 정치 스펙트럼(진보 좌 → 보수 우, 계열 컬럼), 세로축 = 시간(위=현재, 아래로 과거).
// 막대=존속기간, 선=계승(merge/split/rename 색). 막대 클릭 → /party/{정식명}/. 색은 parties.js.

(function () {
  const NOW = 2026.5;
  const REL_COLOR = { merge: '#d08700', split: '#2c82c9', rename: '#8a8f98', new: '#8a8f98', dissolve: '#8a8f98' };
  const COLS = ['진보', '중도진보', '중도', '중도보수', '보수'];  // 좌→우 이념 스펙트럼 (기타는 그래프 밖 텍스트)
  const PXY = 12;        // 1년당 px (세로) — 세로 라벨 공간 확보 위해 키움
  const COL_GAP = 10;
  const PAD_T = 50, PAD_L = 40, PAD_R = 14, PAD_B = 28;

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

    // 계열 컬럼 + 서브레인(시간 겹침 회피) 패킹
    const colMembers = {};
    for (const name of names) (colMembers[node[name].stream] || (colMembers[node[name].stream] = [])).push(name);
    const cols = COLS.filter((s) => colMembers[s]);
    let totalLanes = 0;
    const colInfo = [];
    for (const s of cols) {
      // lane 좌우 = 이념순(info.order, 낮을수록 왼쪽). 없으면(중도·보수 등) 창당연도순.
      // order 오름차순 처리 + 같은 order lane만 시간겹침 없을 때 재사용 → 다른 이념과 안 섞여
      // 좌우 단조 보장(낮은 order가 항상 왼쪽). 새 order는 뒤에 append되어 자연히 좌→우 정렬.
      const ord = (x) => (node[x].info.order != null ? node[x].info.order : 1e3);
      const sorted = colMembers[s].slice().sort((a, b) => (ord(a) - ord(b)) || (node[a].f - node[b].f));
      const laneEnd = [], laneOrd = [];
      for (const nm of sorted) {
        const n = node[nm], o = ord(nm);
        let lane = -1;
        for (let i = 0; i < laneEnd.length; i++) {
          if (laneOrd[i] === o && laneEnd[i] <= n.f + 0.01) { lane = i; break; }
        }
        if (lane < 0) { lane = laneEnd.length; laneEnd.push(0); laneOrd.push(o); }
        laneEnd[lane] = n.d; n.lane = lane;
      }
      const nLanes = laneEnd.length || 1;
      colInfo.push({ stream: s, nLanes, startLane: totalLanes });
      totalLanes += nLanes;
    }
    // 컨테이너 폭에 맞춰 lane 폭 산출 — 항상 진보↔보수 한 화면에. 라벨은 폭 여유 시만.
    const W = Math.max(host.clientWidth || 900, 320);
    const laneW = Math.max((W - PAD_L - PAD_R - (cols.length - 1) * COL_GAP) / totalLanes, 6);
    const BAR_W = Math.max(3, Math.min(10, laneW * 0.55));
    // 세로(회전) 라벨 — 정당명을 막대 따라 위→아래 업라이트 스택. 가로폭 부족·세로 여유를 활용해
    // PC 라벨 겹침·모바일 미표시를 동시 해소. 폰트는 lane 안에 글자열이 들어가도록 적응.
    const labelFS = Math.max(7, Math.min(11, laneW - BAR_W - 2));
    const showLabels = labelFS >= 7;
    colInfo.forEach((c, i) => {
      c.x = PAD_L + c.startLane * laneW + i * COL_GAP;
      for (const nm of colMembers[c.stream]) node[nm].x = c.x + node[nm].lane * laneW;
    });
    const etc = colMembers["기타"] || [];   // 그래프 밖(분류불가) — 아래 텍스트로.
    const H = PAD_T + plotH + PAD_B;

    const out = [`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="lin-svg" xmlns="http://www.w3.org/2000/svg">`];

    // 연도 가로 그리드
    for (let yr = Math.ceil(minY / 10) * 10; yr <= maxY; yr += 10) {
      const y = yScale(yr);
      out.push(`<line x1="${PAD_L - 8}" y1="${y.toFixed(1)}" x2="${W}" y2="${y.toFixed(1)}" class="lin-grid"/>`);
      out.push(`<text x="12" y="${y.toFixed(1)}" transform="rotate(-90 12 ${y.toFixed(1)})" text-anchor="middle" class="lin-year">${yr}</text>`);
    }

    // 스펙트럼 양 끝(진보/보수)만 표시 — 중도 위치는 주관적이라 중간 라벨·구획 생략.
    const ay = PAD_T - 22;
    out.push(`<line x1="${(PAD_L + 48).toFixed(1)}" y1="${ay - 4}" x2="${(W - 60).toFixed(1)}" y2="${ay - 4}" class="lin-axis"/>`);
    out.push(`<text x="${PAD_L}" y="${ay}" class="lin-pole" text-anchor="start">◀ 진보</text>`);
    out.push(`<text x="${W - 8}" y="${ay}" class="lin-pole" text-anchor="end">보수 ▶</text>`);

    // 엣지 — pred 끝(위) → succ 시작(아래보다 위). 세로 베지어.
    for (const [a, c] of edges) {
      const na = node[a], nc = node[c];
      // 분당(split): 모정당이 존속하므로 분당 시점(자식 창당년)에서 가지치기.
      // 합당·개명: 모정당이 끝나며 이어지므로 모정당 종료점에서.
      const isSplit = nc.info.relation === 'split';
      const x1 = na.x + BAR_W / 2, y1 = yScale(isSplit ? Math.min(nc.f, na.d) : na.d);
      const x2 = nc.x + BAR_W / 2, y2 = yScale(nc.f);
      const col = REL_COLOR[nc.info.relation] || '#8a8f98';
      const dy = Math.max(12, Math.abs(y1 - y2) * 0.4);
      out.push(`<path d="M${x1.toFixed(1)},${y1.toFixed(1)} C${x1.toFixed(1)},${(y1 - dy).toFixed(1)} ${x2.toFixed(1)},${(y2 + dy).toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)}" class="lin-edge" stroke="${col}"/>`);
    }

    // 막대(세로) + 라벨(폭 여유 시) — 스펙트럼 컬럼만
    for (const name of names) {
      const n = node[name];
      if (n.stream === "기타") continue;
      const yT = yScale(n.d), h = Math.max(yScale(n.f) - yT, 4);
      const col = color(name);
      out.push(`<a href="/party/${encodeURIComponent(name)}/" class="lin-node">`);
      out.push(`<rect x="${n.x.toFixed(1)}" y="${yT.toFixed(1)}" width="${BAR_W.toFixed(1)}" height="${h.toFixed(1)}" rx="3" fill="${col}" class="lin-bar"><title>${esc(name)}${n.info.abbr ? ' (' + esc(n.info.abbr) + ')' : ''} · ${esc(n.info.founded || '')}~${esc(n.info.dissolved || '현재')}</title></rect>`);
      // 세로 라벨 — 막대 높이(h)로 들어가는 글자수(cap)만큼만. 넘치면 들어가는 만큼만(막대 밖 overflow 방지).
      // 이름과 동음이의 연도괄호 분리 — '민중당(2017)' → 이름 세로스택 + '(2017)' 통회전.
      const mp = name.match(/^(.+?)\s*(\([^)]*\))\s*$/);
      const base = mp ? mp[1] : name, paren = mp ? mp[2] : '';
      const baseCh = [...base];
      const cap = Math.floor((h + labelFS * 0.5) / labelFS);   // 막대에 들어갈 글자수(약간만 여유)
      if (showLabels && cap >= 1) {
        const lxN = n.x + BAR_W + 1, lx = lxN.toFixed(1);
        const showCh = baseCh.slice(0, cap);   // 넘치면 들어가는 만큼만(생략부호 없이 — 짧으면 한두 글자)
        const tsp = showCh.map((ch, i) => `<tspan x="${lx}" dy="${i ? '1em' : '0'}">${esc(ch)}</tspan>`).join('');
        out.push(`<text x="${lx}" y="${(yT + labelFS).toFixed(1)}" class="lin-bar-label" style="font-size:${labelFS.toFixed(1)}px">${tsp}</text>`);
        // 연도괄호: 이름이 다 들어가고 + 막대에 연도 들어갈 여유까지 있을 때만(짧으면 생략 — 호버 툴팁으로 확인).
        const yearLines = Math.ceil(paren.length * 0.45);   // 회전 연도의 세로 줄수 근사
        if (paren && cap >= baseCh.length + yearLines) {
          const py = yT + (baseCh.length + 0.4) * labelFS;   // 이름 바로 아래(간격 최소화)
          const pfs = labelFS * 0.82;
          out.push(`<text x="${lx}" y="${py.toFixed(1)}" transform="rotate(90 ${lx} ${py.toFixed(1)})" class="lin-bar-label" style="font-size:${pfs.toFixed(1)}px">${esc(paren)}</text>`);
        }
      }
      out.push(`</a>`);
    }

    out.push('</svg>');
    // 분류 외(기타) — 그래프 밖 텍스트로
    let etcHtml = '';
    if (etc.length) {
      const links = etc.sort((a, b) => node[a].f - node[b].f)
        .map((nm) => `<a href="/party/${encodeURIComponent(nm)}/">${esc(nm)}</a>`).join(' · ');
      etcHtml = `<p class="lin-etc-note"><span>분류 외</span> ${links}</p>`;
    }
    host.innerHTML = out.length > 1 ? out.join('') + etcHtml : '<p class="lin-loading">표시할 계보가 없습니다.</p>';
  }

  document.addEventListener('DOMContentLoaded', main);
  let rt = null;
  window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(main, 200); });
})();
