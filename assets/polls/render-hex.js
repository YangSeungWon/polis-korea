// polls.js hex — 17 시도 hex (renderHex) + 시군구 hex (renderSigunguHex).

// === HEX 격자 ===
// hexPoints·nbrs·NBR_TO_EDGE·corner → assets/hexgrid.js (공용)

// 시도 1위색 hex — 공용 캐논 Archive.governorHex로 위임(아카이브 광역장 hex와 동일 렌더러).
//   폴 전용 신뢰도 시각화(불투명도=격차·저신뢰 0.4, 점선=n≤2·저신뢰)는 opts 콜백으로 보존.
function renderHex() {
  const host = $('#hex');
  if (!host || !window.Archive || !window.Archive.governorHex) return;
  window.Archive.governorHex.draw(host, [], {
    winnerOf: (sido) => regionSidoWinner(sido, state.office),
    opacityOf: (w) => (w ? (w.low_recent ? 0.4 : gapOpacity(w.effective_gap != null ? w.effective_gap : w.gap)) : 1),
    dashOf: (w) => ((w && (w.n_polls <= 2 || w.low_recent)) ? '3,2' : null),
    onSelect: (sido) => { state.selectedSido = sido; state.selectedSigungu = null; renderHex(); renderDetail(); },
    selected: state.selectedSido,
  });
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
        ? regionSigunguWinner(d.sido, d.name, state.office)
        : regionSidoWinner(d.sido, state.office);
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
