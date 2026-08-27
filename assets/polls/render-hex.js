// polls.js hex — 17 시도 hex (renderHex) + 시군구 hex (renderSigunguHex).

// === HEX 격자 ===
// hexPoints·nbrs·NBR_TO_EDGE·corner → assets/hexgrid.js (공용)

// 직위 → 캡처 키의 host 토큰(build_og_maps --pages polls). 교육감은 정당을 표방하지
// 않아 '조사 1위 vs 실제 1위'를 비교할 것이 없으므로 안 찍는다.
const POLL_HOST = { '광역단체장': 'pollgov', '기초단체장': 'pollmayor' };

// 시도 1위색 hex — 공용 캐논 Archive.governorHex로 위임(아카이브 광역장 hex와 동일 렌더러).
//   폴 전용 신뢰도 시각화(불투명도=격차·저신뢰 0.4, 점선=n≤2·저신뢰)는 opts 콜백으로 보존.
function renderHex() {
  const host = $('#hex');
  if (!host || !window.Archive || !window.Archive.governorHex) return;
  // 이 지도가 무엇인지 **여기서 선언한다** — 캡처(build_og_maps --pages polls)가 읽는다.
  // ⚠️ #hex는 <div>가 아니라 <svg> 자체다. 그리고 archive와 달리 한 컨테이너에
  // 직위(광역단체장·교육감·기초단체장) × 자료(여론조사 1위·실제 1위) × 방식(균등·지도)이
  // 겹쳐 있다. 전부 찍으면 회차당 12장이 되므로 **기본 직위·기본 방식**만 찍고,
  // 자료 토글만 돈다(그게 이 페이지의 요점 — 조사가 실제와 얼마나 같았나).
  // data-map-toggle은 '모드를 바꾸는 버튼이 data-mode를 쓴다'는 선언이다.
  // 매핑이 없는 직위(교육감 — 정당을 표방하지 않아 비교할 것이 없다)는 **선언하지
  // 않는다**. 빈 문자열을 찍으면 '정체를 밝혔는데 이름이 없는' 호스트가 생겨 캡처와
  // 검사가 헷갈린다(2026-08-27 /superintendent/에서 실제로 그랬다).
  const _tok = POLL_HOST[state.office];
  if (_tok) {
    host.dataset.mapHost = _tok;
    host.dataset.mapToggle = 'mode';
    host.dataset.mode = state.mode || 'polls';
  } else {
    delete host.dataset.mapHost;
    delete host.dataset.mapToggle;
  }
  // 전남광주 통합(2026-06-03 신설)은 **한 선거**다. 두 칸으로 그리면 같은 값이 두 번
  // 찍혀 유권자 규모가 두 배로 보인다. archive는 데이터에 통합 race가 있으면 병합
  // 레이아웃을 쓰는데, 여기선 draw에 빈 배열을 넘기고 winnerOf 콜백을 쓰므로 그 판단이
  // 안 된다 — 그래서 **적중률 데이터가 통합 셀을 판정했는지**로 정한다(날짜·직위를
  // 손으로 적으면 다음 통합 때 또 어긋난다).
  const _merged = (typeof honamMergedLayout === 'function'
    && PollAdapter.hitOf(state.office, '전남광주특별시') !== null);
  const meta = window.Archive.governorHex.draw(host, [], {
    layout: _merged ? honamMergedLayout(SIDO_HEX_LAYOUT) : undefined,
    winnerOf: (sido) => regionSidoWinner(sido, state.office),
    opacityOf: (w) => (w ? (w.low_recent ? 0.4 : gapOpacity(w.effective_gap != null ? w.effective_gap : w.gap)) : 1),
    dashOf: (w) => ((w && (w.n_polls <= 2 || w.low_recent)) ? '3,2' : null),
    // 실제 모드: 막판 여론조사 1위 ≠ 실제 당선이면 '여론조사 1위 정당색' 반환 → 점선 테두리색.
    missOf: state.mode === 'result' ? (sido) => {
      const p = PollAdapter.missPartyOf(state.office, sido);
      return p ? partyColor(p) : null;
    } : null,
    onSelect: (sido) => { state.selectedSido = sido; state.selectedSigungu = null; renderHex(); renderDetail(); },
    selected: state.selectedSido,
  });
  // 팬·줌 (Phase 1) — draw가 viewBox를 base로 리셋하므로 매 렌더 후 현재 줌 복원. 리스너는 1회만.
  if (window.SvgViewport && meta) window.SvgViewport.attach(host, { baseViewBox: meta.viewBox, cells: meta.cells });
  // 시도 hex도 시군구 hex와 같은 인코딩을 쓴다 — 키가 한쪽에만 있으면 더 헷갈린다.
  // #hex는 <div>가 아니라 <svg> **자체**다. querySelector('svg')로 찾으면 null이라
  // 범례가 아예 안 붙는다(실제로 안 붙어 있었다 — UI 감사에서 0개로 잡혔다).
  //
  // 단, '실제' 모드는 확정 결과라 gap=99 sentinel이 들어가 모든 칸이 같은 명도다.
  // 거기에 '색 진하기 = 격차'를 붙이면 범례가 설명하지 않는 걸 설명한다고 말한다.
  mountOrClearGapLegend(host);
}

// 명도가 값을 나르는 모드에서만 키를 붙이고, 아니면 걷는다.
function mountOrClearGapLegend(hostSvg) {
  if (!hostSvg) return;
  const encodes = state.mode !== 'result';   // 여론조사 모드에서만 격차 명도가 산다
  if (encodes && typeof mountGapLegend === 'function') {
    mountGapLegend(hostSvg, { extra: ['점선·흐림 = 최근 조사 부족'] });
  } else if (typeof removeGapLegend === 'function') {
    removeGapLegend(hostSvg);
  }
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
  // 기초단체장 지도. #hex(시도)와 다른 svg라 따로 선언한다 — 안 하면 /mayor/ 페이지가
  // 지도를 그리는데 캡처에는 아무것도 안 잡힌다.
  if (svg && state.office === '기초단체장') {
    svg.dataset.mapHost = 'pollmayor';
    svg.dataset.mapToggle = 'mode';
    svg.dataset.mode = state.mode || 'polls';
  } else if (svg) {
    delete svg.dataset.mapHost;
    delete svg.dataset.mapToggle;
  }
  const data = await loadSigunguHex();
  // 지도가 비면 키도 걷는다 — svg.innerHTML만 비우면 형제인 범례가 남는다.
  if (!data.length) {
    svg.innerHTML = '';
    if (typeof removeGapLegend === 'function') removeGapLegend(svg);
    return;
  }
  const meta = drawSigunguHex(svg, data,
    (sido, name) => (isSigunguMode() ? regionSigunguWinner(sido, name, state.office) : regionSidoWinner(sido, state.office)),
    {
      selected: { sido: state.selectedSido, name: state.selectedSigungu },
      opacityOf: (w) => (w.low_recent ? 0.4 : gapOpacity(w.effective_gap != null ? w.effective_gap : w.gap)),
      dashOf: (w) => ((w.n_polls <= 2 || w.low_recent) ? '2,1.5' : null),
      // 실제 모드: 막판 조사 1위 ≠ 실제 당선이면 조사 1위 정당색 반환 → 점선 테두리색.
      missOf: (state.mode === 'result' && isSigunguMode()) ? (sido, name) => {
        const p = PollAdapter.missPartyOf(state.office, sido, name);
        return p ? partyColor(p) : null;
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
  // 팬·줌 (Phase 3a) — 시군구 hex. 재렌더 후 현재 줌 복원, 리스너 1회.
  if (window.SvgViewport && meta) window.SvgViewport.attach(svg, { baseViewBox: meta.viewBox, cells: meta.cells });
  // 여론 hex는 명도에 두 가지가 실린다 — 격차와 '최근 조사 부족'. 키에 둘 다 적는다.
  // '실제' 모드는 명도가 균일하므로 키를 걷는다(위 mountOrClearGapLegend 참고).
  mountOrClearGapLegend(svg);
}
