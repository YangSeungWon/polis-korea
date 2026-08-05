// history.js 시군구 hex — 대선·지선 기초단체장 시군구별 결과.
//   격자/dorling은 공용 Archive.drawSigunguCartogram에 위임(종합/폴과 단일 렌더러).
//   시점성(회차별 셀·_borrowed/_fill)은 여기서 데이터로 전처리해 주입 — 렌더러는 받은 셀만 그림.

// === 시군구 hex ===

function renderSigunguHex() {
  const svg = $('#hex2');
  svg.innerHTML = '';
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');
  // 대선만 일반구별 개표 단위 (legacy sigungu hex). 지선은 통합 시장이라 base hex.
  // 총선은 지역구(district_hex_*.json) — renderDistrictHex가 별도 처리.
  // 회차별 그 시점 시군구 레이아웃 — 대선(hexPres 2~18대), 지선 기초장(hexLocal 1~9회: 창원·청주
  // 분리 등). 없으면 현대(대선=legacy 25구, 지선=hexData).
  const periodHex = state.type === 'presidential' ? state.hexPres?.[state.n]
    : state.type === 'local' ? state.hexLocal?.[state.n] : null;
  const useLegacy = state.hexLegacy && state.type === 'presidential';
  let data = periodHex || (useLegacy ? state.hexLegacy : state.hexData);
  if (!data?.length) return;
  // 회차별 자동 hide:
  //   1) lifecycle since/until — 행정구역 신설·폐지 (확장 가능, SIGUNGU_HEX_LIFECYCLE 참조)
  //   2) 데이터 매칭 — 그 회차에 결과 없는 cell 자동 숨김
  const el = (state.elections[state.type]?.elections || []).find((x) => x.n === state.n);
  const electionDate = el?.date || '';
  // 각 cell에 그 시점 effective sido/name 주입 후 매칭 — beforeAs/afterAs 처리 일관.
  data = data.flatMap((d) => {
    const eff = effectiveCell(d, electionDate);
    if (!eff) return [];
    // _borrowed: 그 시점 부모 구로 해석된 셀(예 5대 강남→성동). 같은 구로 묶이는 여러 셀 중
    // 원래 이름이 그 구인 셀(canonical)만 클러스터/원, 나머지는 색만 — 중복카운트 방지.
    const borrowed = eff.sido !== d.sido || eff.name !== d.name;
    if (!resultForSigungu(eff.sido, eff.name)) {
      // 현재 직(office) 데이터 없음 — 그 시점 '존재하는' 시군구(광역단체장 데이터 보유)면
      // 숨기지 말고 no-data 회색 셀로 유지(내부 구멍 방지).
      const gov = state.type === 'local' ? state.results?.offices?.['광역단체장'] : null;
      if (gov && resultForSigungu(eff.sido, eff.name, gov)) {
        return [{ ...d, sido: eff.sido, name: eff.name, _borrowed: borrowed }];
      }
      return [];
    }
    return [{ ...d, sido: eff.sido, name: eff.name, _borrowed: borrowed }];
  });
  if (!data.length) return;  // 매칭 결과 0 → 빈 배열이면 viewBox -Infinity 방지

  // 사이즈 모드: 격자(시군구당 득표 비례 작은 hex·대선 기본) / dorling(원) / 그 외=단일 hex.
  const sizingMode = state.sizing || '동일';
  let maxVoted = 0;
  for (const d of data) {
    const result = resultForSigungu(d.sido, d.name);
    const v = result ? (result.voted != null ? result.voted : (result.voters || 0)) : 0;  // live-count는 voters만
    if (v && !result._fill) maxVoted = Math.max(maxVoted, v);  // 차용 셀 제외
  }

  // 격자/dorling — 공용 카토그램 렌더러(종합/폴과 단일화). 시점 셀·_borrowed/_fill·선택을 opts로 주입.
  if ((sizingMode === '격자' || sizingMode === 'dorling') && maxVoted > 0 && window.Archive?.drawSigunguCartogram) {
    const meta = window.Archive.drawSigunguCartogram(svg, data,
      (sido, name) => resultForSigungu(sido, name),
      {
        mode: sizingMode,
        date: electionDate,
        selected: state.selected ? { sido: state.selected.sido, name: state.selected.name } : null,
        onSelect: (sido, name, result, cell) => { state.selected = { sido, name, code: cell.code }; renderAll(); renderDetail(); },
      });
    if (meta) svg._focusCells = meta.cells;   // 줌은 enablePinchZoom, 셀은 포커스 전이용
    // 카토그램은 두 가지를 동시에 인코딩한다 — 크기와 명도. 둘 다 키에 적는다.
    if (typeof mountGapLegend === 'function') {
      mountGapLegend(svg, { note: '크기 = 투표수 · 색 진하기 = 1·2위 격차' });
    }
    return;
  }

  // 단일 hex (1위 정당색) — 공용 캐논 drawSigunguHex 위임. 시도명 워터마크는 underlay로 셀 뒤에.
  const r = 22;
  const meta = drawSigunguHex(svg, data,
    (sido, name) => {
      const result = resultForSigungu(sido, name);
      const top = topCandidate(result);
      if (!top) return null;
      const sec = result?.candidates?.length >= 2 ? result.candidates[1] : null;
      return { party: top.party, pct: top.pct, label: candLabel(top), uncontested: top.uncontested, gap: sec ? top.pct - sec.pct : null };
    },
    {
      r,
      margin: SIDO_EDGE_MARGIN,
      borderWidth: '1.8',
      selected: state.selected ? { sido: state.selected.sido, name: state.selected.name } : null,
      opacityOf: (w) => gapOpacity(w.gap),
      tooltipOf: (sido, name, w) => (w
        ? `${periodSidoName(sido, electionDate)} ${fmtUnitName(name)} · ${w.label} (${w.party}) ${w.uncontested ? '무투표 당선' : (w.pct != null ? w.pct.toFixed(1) + '%' : '')}`
        : `${periodSidoName(sido, electionDate)} ${fmtUnitName(name)} · 데이터 없음`),
      onSelect: (sido, name, w, cell) => { state.selected = { sido, name, code: cell.code }; renderAll(); renderDetail(); },
      underlay: (svgEl, geom) => {
        // 시도명 — 좌우 외곽 가장자리 라벨(종합결과·카토그램과 통일). 옛 중앙 워터마크 대체.
        if (typeof drawSidoEdgeLabels !== 'function') return;
        const pts = data.map((d) => {
          const [cx, cy] = hexCenter(d.c, d.r, geom.colW, geom.rowH, geom.offX, geom.offY);
          return { sido: d.sido, cx, cy };
        });
        drawSidoEdgeLabels(svgEl, pts);
      },
    });
  if (meta) svg._focusCells = meta.cells;   // 줌은 enablePinchZoom, 셀은 포커스 전이용
  if (typeof mountGapLegend === 'function') mountGapLegend(svg);
}
