// history.js sido hex — 시도 17셀 hex (광역단체장·대선·총선 시도 broadcast).

// === 시도 17셀 hex (메인 페이지와 동일 layout) ===

// 회차 date 기준 시도 cell 표시 여부 (시도 신설·통합 처리).
//   세종특별자치시: 2012-07-01 신설 (그 이전 회차에선 cell 자체 없음)
//   전남광주특별시: 2026-06-03 신설 (9회 지선 이전 회차에선 광주·전남 별개)
const SIDO_HEX_SINCE = {
  '세종특별자치시': '2012-07-01',
  '전남광주특별시': '2026-06-03',
};
// 9회 이전 layout — 5 row, row 2가 5 cell (광주 추가), row 3 3 cell (전남 추가).
//   row 2: 광주(1) 전북(2) 대전(3) 대구(4) 울산(5)
//   row 3: 전남(1) 경남(2) 부산(3)
//   row 4: 제주(2)
// parties.js 9회 active에 광주(전남광주 자리)·전남(전남광주 자리) cell 추가, row 3 부산 그대로.
const SIDO_HEX_LAYOUT_LEGACY = {
  '광주광역시':     { col: 1, row: 2, label: '광주' },  // 전북 col 2 좌측 추가
  '전라남도':       { col: 1, row: 3, label: '전남' },  // 9회 전남광주 자리에 전남 (광주는 row 2로)
};
// 세종 신설 전 layout — row 1 충남·충북·경북 col 2·3·4 가운데 정렬 (빈 자리 0).
const SIDO_HEX_LAYOUT_PRE_SEJONG = {
  '충청남도': { col: 2, row: 1, label: '충남' },
  '충청북도': { col: 3, row: 1, label: '충북' },
  '경상북도': { col: 4, row: 1, label: '경북' },
};

function getActiveSidoLayout(electionDate) {
  let layout = { ...SIDO_HEX_LAYOUT };
  // 9회 이전 — 광주·전남 별개
  if (electionDate && electionDate < '2026-06-03') {
    layout = { ...layout, ...SIDO_HEX_LAYOUT_LEGACY };
    delete layout['전남광주특별시'];
  }
  // 세종 신설 전 — row 1 가운데 정렬, 세종 cell 자체 제거
  if (electionDate && electionDate < '2012-07-01') {
    layout = { ...layout, ...SIDO_HEX_LAYOUT_PRE_SEJONG };
    delete layout['세종특별자치시'];
  }
  return layout;
}

function renderSidoHex() {
  const svg = $('#hex');
  svg.innerHTML = '';
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');
  const r = 56;
  const colW = r * Math.sqrt(3);
  const rowH = r * 1.5;
  const offsetX = 75 - colW;
  const offsetY = 70;

  const el = (state.elections[state.type]?.elections || []).find((x) => x.n === state.n);
  const electionDate = el?.date || '';
  const layout = getActiveSidoLayout(electionDate);

  for (const [sido, pos] of Object.entries(layout)) {
    if (sido === '전라북도') continue; // 전북특별자치도와 중복 alias
    const since = SIDO_HEX_SINCE[sido];
    if (since && electionDate && electionDate < since) continue;
    const [cx, cy] = hexCenter(pos.col, pos.row, colW, rowH, offsetX, offsetY);
    const result = resultForSido(sido);
    const top = topCandidate(result);
    const sec = result?.candidates?.length >= 2 ? result.candidates[1] : null;
    const gap = top && sec ? top.pct - sec.pct : null;
    const fill = top ? partyColor(top.party) : '#e6e9ef';
    const opacity = top ? gapOpacity(gap) : 1;
    const isSelected = state.selected?.sido === sido && !state.selected?.name;

    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.style.cursor = result ? 'pointer' : 'default';
    g.addEventListener('click', () => {
      state.selected = { sido };
      renderAll();
      renderDetail();
    });

    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('class', 'hex-cell ' + (top ? 'has-data' : 'no-data') + (isSelected ? ' is-selected' : ''));
    poly.setAttribute('points', hexPoints(cx, cy, r - 2));
    poly.setAttribute('fill', fill);
    poly.setAttribute('stroke', '#0a0e1a');
    poly.setAttribute('stroke-width', isSelected ? '2.2' : '1.2');
    poly.setAttribute('fill-opacity', opacity);
    g.appendChild(poly);

    const t1 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    t1.setAttribute('class', 'hex-label');
    t1.setAttribute('x', cx);
    t1.setAttribute('y', cy + 2);
    t1.setAttribute('text-anchor', 'middle');
    const txtCol = top ? pickTextColor(fill, opacity) : 'var(--ink)';
    t1.setAttribute('fill', txtCol);
    t1.setAttribute('font-weight', '700');
    t1.setAttribute('font-size', '15');
    t1.setAttribute('pointer-events', 'none');
    t1.textContent = pos.label;
    g.appendChild(t1);

    if (top) {
      const t2 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t2.setAttribute('class', 'hex-pct');
      t2.setAttribute('x', cx);
      t2.setAttribute('y', cy + 20);
      t2.setAttribute('text-anchor', 'middle');
      t2.setAttribute('fill', txtCol);
      t2.setAttribute('font-size', '11');
      t2.setAttribute('pointer-events', 'none');
      const lbl = candLabel(top);
      // 라벨+pct 총 길이로 폰트 동적 축소 (CSS 덮기 위해 style 사용)
      const total = lbl.length + (top.pct?.toFixed(1) || '').length + 2;
      t2.style.fontSize = total >= 14 ? '7px' : total >= 11 ? '9px' : '11px';
      t2.textContent = `${lbl} ${top.pct?.toFixed(1)}%`;
      g.appendChild(t2);
    }
    svg.appendChild(g);
  }
}
