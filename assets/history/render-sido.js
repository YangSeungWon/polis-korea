// history.js sido hex — 시도 17셀 hex (광역단체장·대선·총선 시도 broadcast).

// === 시도 17셀 hex (메인 페이지와 동일 layout) ===

// 회차 date 기준 시도 cell 표시 여부 (시도 신설·통합 처리).
//   세종특별자치시: 2012-07-01 신설 (그 이전 회차에선 cell 자체 없음)
//   전남광주특별시: 2026-06-03 신설 (9회 지선 이전 회차에선 광주·전남 별개)
const SIDO_HEX_SINCE = {
  '부산광역시': '1963-01-01',   // 정부직할시 승격 — 2·3대 대선(1952·56)엔 경남 소속이라 셀 숨김
  '대구광역시': '1981-07-01',   // 직할시 승격 — 이전엔 경북 소속
  '인천광역시': '1981-07-01',   // 직할시 승격 — 이전엔 경기 소속
  '광주광역시': '1986-11-01',   // 직할시 승격 — 이전엔 전남 소속
  '대전광역시': '1989-01-01',   // 직할시 승격 — 13대 대선(1987)·총선엔 충남 소속이라 셀 숨김
  '울산광역시': '1997-07-15',   // 경남에서 광역시 승격 — 1회(1995) 지선엔 경남 소속이라 셀 숨김
  '세종특별자치시': '2012-07-01',
  '전남광주특별시': '2026-06-03',
};
// 9회 이전 layout — 광주·전남 분리. base(parties.js)와 동일하게 row 3에 나란히:
//   row 2: 전북(2) 대전(3) 대구(4) 울산(5)
//   row 3: 전남(1) 광주(2) 경남(3) 부산(4)   ← 광주는 전남 오른쪽(9회+ 전남광주 통합셀과 같은 col2 자리)
//   row 4: 제주(2)
const SIDO_HEX_LAYOUT_LEGACY = {
  '광주광역시':     { col: 2, row: 3, label: '광주' },  // 전남(col1) 오른쪽
  '전라남도':       { col: 1, row: 3, label: '전남' },
};
// 세종 신설 전 layout — row 1 충남·충북·경북 col 2·3·4 가운데 정렬 (빈 자리 0).
const SIDO_HEX_LAYOUT_PRE_SEJONG = {
  '충청남도': { col: 2, row: 1, label: '충남' },
  '충청북도': { col: 3, row: 1, label: '충북' },
  '경상북도': { col: 4, row: 1, label: '경북' },
};

function getActiveSidoLayout(electionDate) {
  let layout = { ...SIDO_HEX_LAYOUT };
  if (electionDate && electionDate >= HONAM_MERGE_DATE) {
    // 9회+ — 광주·전남 통합 '전남광주' 한 셀(광역단체장 1선거)
    layout = honamMergedLayout(layout);
  } else if (electionDate && electionDate < '2026-06-03') {
    // 9회 이전 — 광주·전남 별개
    layout = { ...layout, ...SIDO_HEX_LAYOUT_LEGACY };
  }
  // 세종 신설 전 — row 1 가운데 정렬, 세종 cell 자체 제거
  if (electionDate && electionDate < '2012-07-01') {
    layout = { ...layout, ...SIDO_HEX_LAYOUT_PRE_SEJONG };
    delete layout['세종특별자치시'];
  }
  return layout;
}

// 시도 1위색 hex — 공용 캐논 Archive.governorHex로 위임(폴·아카이브와 동일 렌더러).
//   history 고유: 회차 레이아웃(getActiveSidoLayout)·신설 전 숨김(SIDO_HEX_SINCE)을 opts로 주입.
function renderSidoHex() {
  const svg = $('#hex');
  if (!svg || !window.Archive || !window.Archive.governorHex) return;
  const el = (state.elections[state.type]?.elections || []).find((x) => x.n === state.n);
  const electionDate = el?.date || '';
  window.Archive.governorHex.draw(svg, [], {
    layout: getActiveSidoLayout(electionDate),
    skipSido: (sido) => { const since = SIDO_HEX_SINCE[sido]; return !!(since && electionDate && electionDate < since); },
    winnerOf: (sido) => {
      const result = resultForSido(sido);
      const top = topCandidate(result);
      if (!top) return null;
      const sec = result?.candidates?.length >= 2 ? result.candidates[1] : null;
      return { party: top.party, name: candLabel(top), pct: top.pct, gap: sec ? top.pct - sec.pct : null };
    },
    opacityOf: (w) => gapOpacity(w.gap),
    onSelect: (sido) => { state.selected = { sido }; renderAll(); renderDetail(); },
    selected: (state.selected && !state.selected.name) ? state.selected.sido : null,
  });
}
