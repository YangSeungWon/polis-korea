// polls.js hex — 17 시도 hex (renderHex) + 시군구 hex (renderSigunguHex).

// === HEX 격자 ===
// hexPoints·nbrs·NBR_TO_EDGE·corner → assets/hexgrid.js (공용)

// 시도 1위색 hex — 공용 캐논 Archive.governorHex로 위임(아카이브 광역장 hex와 동일 렌더러).
//   폴 전용 신뢰도 시각화(불투명도=격차·저신뢰 0.4, 점선=n≤2·저신뢰)는 opts 콜백으로 보존.
function renderHex() {
  const host = $('#hex');
  if (!host || !window.Archive || !window.Archive.governorHex) return;
  const merge = (typeof SIDO_MERGE !== 'undefined') ? SIDO_MERGE : null;
  window.Archive.governorHex.draw(host, [], {
    winnerOf: (sido) => regionSidoWinner(sido, state.office),
    opacityOf: (w) => (w ? (w.low_recent ? 0.4 : gapOpacity(w.effective_gap != null ? w.effective_gap : w.gap)) : 1),
    dashOf: (w) => ((w && (w.n_polls <= 2 || w.low_recent)) ? '3,2' : null),
    // 실제 모드: 막판 여론조사 1위 ≠ 실제 당선인 시도 표시(점선).
    missOf: state.mode === 'result' ? (sido) => {
      const poll = PollAdapter.localSidoWinner(state.data.polls, sido, state.office, merge);
      const actual = regionSidoWinner(sido, state.office);
      return !!(poll && actual && poll.party && actual.party && poll.party !== actual.party);
    } : null,
    onSelect: (sido) => { state.selectedSido = sido; state.selectedSigungu = null; renderHex(); renderDetail(); },
    selected: state.selectedSido,
  });
}


// === 시군구 hex (시군구 모드) ===

let sigunguHexData = null;
async function loadSigunguHex() {
  if (sigunguHexData) return sigunguHexData;
  // 지선 per-election은 그 회차 시점 시군구 레이아웃(period-aware)을 써야 함 — 안 그러면
  // 현행(2026) 셀이 옛 회차에 팬텀으로 떠서 빈칸이 됨(예: 7·8회의 대구 군위[당시 경북]·
  // 인천 영종/제물포[2026 신설]). sigungu_hex_local.json[회차]에 그 시점 이름·소속으로 들어있음.
  const n = POLL_ELECTION.kind === 'local' ? (POLL_ELECTION.n || 9) : null;
  if (n) {
    try {
      const r = await fetch('data/geo/sigungu_hex_local.json');
      const byRound = await r.json();
      const cells = byRound[String(n)];
      if (Array.isArray(cells) && cells.length) { sigunguHexData = cells; return sigunguHexData; }
    } catch (e) { /* 폴백: 현행 레이아웃 */ }
  }
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
      // 실제 모드: 막판 조사 1위 ≠ 실제 당선 시군구 표시.
      missOf: (state.mode === 'result' && isSigunguMode()) ? (sido, name) => {
        const poll = PollAdapter.localSigunguWinner(state.data.polls, sido, name, state.office);
        const actual = regionSigunguWinner(sido, name, state.office);
        return !!(poll && actual && poll.party && actual.party && poll.party !== actual.party);
      } : null,
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
