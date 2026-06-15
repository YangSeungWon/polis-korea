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

// 시군구 1위색 hex — 공용 캐논 drawSigunguHex로 위임. 폴 신뢰도·툴팁·선택은 opts로 주입.
async function renderSigunguHex() {
  const svg = $('#hex2');
  const data = await loadSigunguHex();
  if (!data.length) { svg.innerHTML = ''; return; }
  drawSigunguHex(svg, data,
    (sido, name) => (isSigunguMode() ? regionSigunguWinner(sido, name, state.office) : regionSidoWinner(sido, state.office)),
    {
      selected: { sido: state.selectedSido, name: state.selectedSigungu },
      opacityOf: (w) => (w.low_recent ? 0.4 : gapOpacity(w.effective_gap != null ? w.effective_gap : w.gap)),
      dashOf: (w) => ((w.n_polls <= 2 || w.low_recent) ? '2,1.5' : null),
      tooltipOf: (sido, name, w) => (w
        ? `${sido} ${name} · ${w.name || w.party || ''}${w.name && w.party ? ' (' + w.party + ')' : ''} ${w.pct}% · ${fmtDate(w.period)}`
        : `${sido} ${name} · 조사 없음`),
      onSelect: (sido, name) => {
        state.selectedSido = sido;
        const sgName = isSigunguMode() ? name : null;   // 일반구 클릭 시 모도시로(통합도시 1 race)
        state.selectedSigungu = sgName ? (parentSigungu(sgName) || sgName) : null;
        renderSigunguHex();
        renderDetail();
      },
    });
}
