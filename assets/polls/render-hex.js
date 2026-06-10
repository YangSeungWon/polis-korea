// polls.js hex — 17 시도 hex (renderHex) + 시군구 hex (renderSigunguHex).

// === HEX 격자 ===
// hexPoints·nbrs·NBR_TO_EDGE·corner → assets/hexgrid.js (공용)

function renderHex() {
  const svg = $('#hex');
  svg.innerHTML = '';
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');
  const r = 56; // hex radius — 6행 4컬럼 그리드
  const colW = r * Math.sqrt(3);  // ≈ 97
  const rowH = r * 1.5;            // = 84
  // col 1~4 사용. col 1을 x ≈ 75에 배치.
  const offsetX = 75 - colW;
  const offsetY = 70;

  // 빈 자리 dummy 먼저 (z-order 하단)
  for (const blank of (SIDO_HEX_BLANKS || [])) {
    const [cx, cy] = hexCenter(blank.col, blank.row, colW, rowH, offsetX, offsetY);
    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('class', 'hex-cell no-data');
    poly.setAttribute('points', hexPoints(cx, cy, r - 2));
    svg.appendChild(poly);
  }

  for (const [sido, pos] of Object.entries(SIDO_HEX_LAYOUT)) {
    const [cx, cy] = hexCenter(pos.col, pos.row, colW, rowH, offsetX, offsetY);
    const result = sidoLastWinningParty(sido, state.office);
    const fill = result ? partyColor(result.party) : 'var(--bg3, #e6e9ef)';
    const cls = result ? 'hex-cell has-data' : 'hex-cell no-data';
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('data-sido', sido);
    g.setAttribute('transform', `translate(0,0)`);

    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('class', cls + (state.selectedSido === sido ? ' is-selected' : ''));
    poly.setAttribute('points', hexPoints(cx, cy, r - 2));
    poly.setAttribute('fill', fill);
    poly.setAttribute('stroke', 'var(--ink, #0a0e1a)');
    poly.setAttribute('stroke-width', '1.2');
    const fillOp = result ? (result.low_recent ? 0.4 : gapOpacity(result.effective_gap ?? result.gap)) : 1;
    poly.setAttribute('fill-opacity', fillOp);
    if (result && (result.n_polls <= 2 || result.low_recent)) poly.setAttribute('stroke-dasharray', '3,2');
    g.appendChild(poly);

    const textCol = result ? pickTextColor(fill, fillOp) : 'var(--ink, #1b2237)';
    const t1 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    t1.setAttribute('class', 'hex-label');
    t1.setAttribute('x', cx);
    t1.setAttribute('y', cy + 2);
    t1.setAttribute('fill', textCol);
    t1.textContent = pos.label;
    g.appendChild(t1);

    if (result) {
      const t2 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t2.setAttribute('class', 'hex-pct');
      t2.setAttribute('x', cx);
      t2.setAttribute('y', cy + 20);
      t2.setAttribute('fill', textCol);
      const lbl = result.name || result.party || '';
      // 긴 정당명·후보명일 때 폰트 동적 축소 (시도 hex radius 56 안에 맞춤)
      const total = lbl.length + String(result.pct).length + 2;
      const fs = total >= 14 ? '7px' : total >= 11 ? '9px' : '11px';
      t2.style.fontSize = fs;  // CSS .hex-pct 덮음
      t2.textContent = `${lbl} ${result.pct}%`;
      g.appendChild(t2);
    }

    g.style.cursor = result ? 'pointer' : 'default';
    g.addEventListener('click', () => {
      state.selectedSido = sido;
      state.selectedSigungu = null;
      renderHex();
      renderDetail();
    });
    svg.appendChild(g);
  }
}


// === 시군구 hex (시군구 모드) ===

let sigunguHexData = null;
async function loadSigunguHex() {
  if (sigunguHexData) return sigunguHexData;
  try {
    const r = await fetch('data/geo/sigungu_hex.json');
    sigunguHexData = await r.json();
  } catch (e) {
    sigunguHexData = [];
  }
  return sigunguHexData;
}

async function renderSigunguHex() {
  const svg = $('#hex2');
  const data = await loadSigunguHex();
  svg.innerHTML = '';
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');
  if (!data.length) return;
  const cs = data.map((d) => d.c);
  const rs = data.map((d) => d.r);
  const minC = Math.min(...cs);
  const minR = Math.min(...rs);
  const maxC = Math.max(...cs);
  const maxR = Math.max(...rs);
  const r = 22; // hex radius — 라벨 공간 확보
  const colW = r * Math.sqrt(3);
  const rowH = r * 1.5;
  // SVG viewBox 자동 맞춤
  const w = (maxC - minC + 2) * colW;
  const h = (maxR - minR + 2) * rowH;
  svg.setAttribute('viewBox', `0 0 ${Math.ceil(w)} ${Math.ceil(h)}`);
  const offX = -minC * colW + colW / 2;
  const offY = -minR * rowH + rowH;

  // 시군구별 마지막 기초단체장 조사 1위
  for (const d of data) {
    const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
    const result =
      isSigunguMode()
        ? sigunguLastWinningParty(d.sido, d.name, state.office)
        : sidoLastWinningParty(d.sido, state.office);
    const fill = result ? partyColor(result.party) : 'var(--bg3, #e6e9ef)';
    const cls = result ? 'hex-cell has-data' : 'hex-cell no-data';
    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('class', cls + (state.selectedSido === d.sido && state.selectedSigungu === d.name ? ' is-selected' : ''));
    poly.setAttribute('points', hexPoints(cx, cy, r - 0.7));
    poly.setAttribute('fill', fill);
    poly.setAttribute('stroke', 'var(--ink, #0a0e1a)');
    poly.setAttribute('stroke-width', '0.7');
    const fillOpS = result ? (result.low_recent ? 0.4 : gapOpacity(result.effective_gap ?? result.gap)) : 1;
    poly.setAttribute('fill-opacity', fillOpS);
    if (result && (result.n_polls <= 2 || result.low_recent)) poly.setAttribute('stroke-dasharray', '2,1.5');
    poly.style.cursor = 'pointer';
    poly.addEventListener('click', () => {
      state.selectedSido = d.sido;
      // 일반구 클릭 시 모도시로 (통합도시 1 race) — polls는 모도시 단위
      const sgName = isSigunguMode() ? d.name : null;
      state.selectedSigungu = sgName ? (parentSigungu(sgName) || sgName) : null;
      renderSigunguHex();
      renderDetail();
    });
    // 툴팁
    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    const lbl = result ? (result.name || result.party || '') : '';
    title.textContent = result
      ? `${d.sido} ${d.name} · ${lbl}${result.name && result.party ? ' (' + result.party + ')' : ''} ${result.pct}% · ${fmtDate(result.period)}`
      : `${d.sido} ${d.name} · 조사 없음`;
    poly.appendChild(title);
    svg.appendChild(poly);

    // 라벨 — prefix 있으면 두 줄
    const label = shortSigunguLabel(d.name, d.sido);
    if (label.short) {
      const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      txt.setAttribute('x', cx);
      txt.setAttribute('text-anchor', 'middle');
      txt.setAttribute('font-weight', '600');
      txt.setAttribute('fill', result ? pickTextColor(fill, fillOpS) : 'var(--ink, #0a0e1a)');
      txt.setAttribute('pointer-events', 'none');
      txt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
      if (label.prefix) {
        // 두 줄: prefix 위 (작게·옅게), short 아래
        const tp1 = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
        tp1.setAttribute('x', cx);
        tp1.setAttribute('y', cy - 2);
        tp1.setAttribute('font-size', '6');
        tp1.setAttribute('opacity', '0.75');
        tp1.textContent = label.prefix;
        txt.appendChild(tp1);
        const tp2 = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
        tp2.setAttribute('x', cx);
        tp2.setAttribute('y', cy + 8);
        tp2.setAttribute('font-size', label.short.length > 3 ? '7' : '9');
        tp2.textContent = label.short;
        txt.appendChild(tp2);
      } else {
        txt.setAttribute('y', cy + 3);
        txt.setAttribute('font-size', label.short.length > 3 ? '7' : '9');
        txt.textContent = label.short;
      }
      svg.appendChild(txt);
    }
  }

  // 시도 경계 굵은 선 + 한반도 외곽 — drawHexBorders (hexgrid.js)
  const cellAt = new Map();
  for (const d of data) cellAt.set(`${d.c},${d.r}`, d);
  drawHexBorders(svg, data, cellAt, colW, rowH, offX, offY, r, '1.6', true);
}
