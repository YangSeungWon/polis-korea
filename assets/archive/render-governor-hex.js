// 광역단체장 — 시도 hex map (SIDO_HEX_LAYOUT 5×5 격자).
// 각 시도 = 1 hex, 1위 정당 색 + 후보명·득표율 label.

(function () {
  const NS = 'http://www.w3.org/2000/svg';
  // pointy-top hex grid math
  function hexPoints(cx, cy, R) {
    const pts = [];
    for (let i = 0; i < 6; i++) {
      const a = Math.PI / 6 + i * Math.PI / 3;
      pts.push(`${cx + R * Math.cos(a)},${cy + R * Math.sin(a)}`);
    }
    return pts.join(' ');
  }

  // 시도 1위색 hex — 사이트 공용 캐논. 아카이브(sidoView)·폴 페이지 모두 호출.
  //   draw(host, races)            아카이브: races[{sido,candidates[votes]}]에서 득표 1위.
  //   draw(host, [], opts)         폴: opts로 1위 출처·신뢰도 시각화·클릭 주입(아래).
  // opts(전부 선택, 미전달 시 아카이브 동작 그대로):
  //   winnerOf(sido)  → {party,name,pct,...} | null  (폴 — 여론조사/실제 1위, 신뢰도 필드 포함)
  //   opacityOf(win)  → fill-opacity   (폴 — 격차·저신뢰 불투명도)
  //   dashOf(win)     → stroke-dasharray | null  (폴 — n≤2·저신뢰 점선)
  //   onSelect(sido)  → 클릭 핸들러     selected → is-selected 강조
  function draw(host, races, opts) {
    if (!host) return;
    if (typeof SIDO_HEX_LAYOUT !== 'object') return;
    opts = opts || {};
    // 레이아웃 키 = 현 캐노니컬명(강원특별자치도·전북특별자치도). 데이터 시도명(옛 강원도/전라북도 포함)을
    // canonSido로 정규화해 매칭.
    const canon = (typeof canonSido === 'function') ? canonSido : (x) => x;
    // opts.layout: 회차별 레이아웃 override(history — 세종 신설 전·전남광주 분리 등 getActiveSidoLayout).
    //   없으면 현 캐노니컬 SIDO_HEX_LAYOUT(+ 데이터에 전남광주 병합 race 있으면 honamMergedLayout).
    const baseLayout = opts.layout || SIDO_HEX_LAYOUT;
    const bySido = {};
    if (opts.winnerOf) {
      // 폴/history: 레이아웃 키만 순회(병합은 opts.layout이 이미 반영). 신뢰도·gap 필드 보존.
      for (const sido of Object.keys(baseLayout)) { const w = opts.winnerOf(sido); if (w) bySido[sido] = w; }
    } else {
      for (const r of races || []) {
        const cs = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
        if (cs[0]) bySido[canon(r.sido)] = { name: cs[0].name, party: cs[0].party, pct: cs[0].pct };
      }
    }
    // 전남광주 통합(2026) — 데이터에 병합 race가 있으면 '전남광주' 한 셀 레이아웃 사용
    // ('통합특별시' 표기 변형 수용). 대선·통합 전 지선은 광주·전남 분리 유지.
    if (!bySido['전남광주특별시'] && bySido['전남광주통합특별시']) bySido['전남광주특별시'] = bySido['전남광주통합특별시'];
    const layout = opts.layout || ((bySido['전남광주특별시'] && typeof honamMergedLayout === 'function')
      ? honamMergedLayout(SIDO_HEX_LAYOUT) : SIDO_HEX_LAYOUT);

    // 아카이브(races 기반): 데이터 없는 시도 = 그 시점에 광역단체로 미존재(세종 2012·울산 1997 등)
    // → 빈 셀을 그리지 않는다. 폴/history(winnerOf)는 '조사 없음' 회색셀을 의도하므로 제외.
    const archiveMode = !opts.winnerOf;
    const COL_W = 80, ROW_H = 70, OFF_X = 50, OFF_Y = 50, R = 36;
    const cells = [];
    const seen = new Set();
    for (const [sido, pos] of Object.entries(layout)) {
      if (opts.skipSido && opts.skipSido(sido)) continue;   // history: 신설(승격) 전 회차엔 셀 숨김
      const key = `${pos.col},${pos.row}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const win = bySido[sido];
      if ((archiveMode || opts.hideEmpty) && !win) continue;   // 미존재 시도 셀 숨김

      const cx = OFF_X + pos.col * COL_W + (pos.row % 2 ? COL_W / 2 : 0);
      const cy = OFF_Y + pos.row * ROW_H * 0.87;
      cells.push({ sido, pos, cx, cy, label: pos.label, win });
    }
    // 좌우 대칭 여백 — 레이아웃 좌단 셀이 0보다 한참 오른쪽이라 viewBox 왼쪽을 0으로 두면 우측 치우침.
    // 실제 셀 x범위에 R+20 대칭 여백(sidoCluster와 동일 정렬). 세로는 위 토글 여유 위해 0부터.
    const minCx = Math.min(...cells.map((c) => c.cx)) - R - 20;
    const maxCx = Math.max(...cells.map((c) => c.cx)) + R + 20;
    const maxCy = Math.max(...cells.map((c) => c.cy)) + R + 20;

    // host가 <svg>(폴 #hex)면 그 안에 직접, <div>(아카이브)면 자식 svg 생성.
    const isSvgHost = host.tagName && host.tagName.toLowerCase() === 'svg';
    let svg;
    if (isSvgHost) { svg = host; svg.innerHTML = ''; }
    else { svg = document.createElementNS(NS, 'svg'); svg.setAttribute('xmlns', NS); svg.setAttribute('class', 'governor-hex-svg'); }
    svg.setAttribute('viewBox', `${minCx} 0 ${maxCx - minCx} ${maxCy}`);

    for (const cell of cells) {
      const g = document.createElementNS(NS, 'g');
      const poly = document.createElementNS(NS, 'polygon');
      poly.setAttribute('points', hexPoints(cell.cx, cell.cy, R));
      let textCol = null;
      const selCls = (opts.selected === cell.sido) ? ' is-selected' : '';
      if (cell.win) {
        // fillOf: 정당색 대신 임의 채색(투표율 그라데이션 등). 주면 대비 텍스트색도 보정.
        const fill = opts.fillOf ? opts.fillOf(cell.sido, cell.win)
          : ((typeof partyFill === 'function') ? partyFill(cell.win.party) : '#888');
        poly.setAttribute('fill', fill);
        poly.setAttribute('class', 'gov-hex-cell has-data' + selCls);
        if (opts.fillOf && typeof pickTextColor === 'function') textCol = pickTextColor(fill, 1);
        if (opts.opacityOf) {                      // 폴 — 신뢰도 불투명도 + 라벨 대비 보정
          const op = opts.opacityOf(cell.win);
          poly.setAttribute('fill-opacity', op);
          if (typeof pickTextColor === 'function') textCol = pickTextColor(fill, op);
        }
        // 저신뢰 점선 — .gov-hex-cell의 밝은 간격 stroke로는 안 보이니 어두운 stroke로 덮어 가시화.
        if (opts.dashOf) { const dash = opts.dashOf(cell.win); if (dash) { poly.setAttribute('stroke-dasharray', dash); poly.setAttribute('stroke', 'var(--ink, #0a0e1a)'); } }
      } else {
        poly.setAttribute('class', 'gov-hex-cell no-data' + selCls);
      }
      // 여론조사 빗나감 — 실제 모드에서 막판 여론조사 1위 ≠ 실제 당선인 시도.
      //   missOf는 '여론조사가 예측한 정당색'을 반환(빗나감) 또는 falsy.
      const missCol = opts.missOf && opts.missOf(cell.sido);
      if (missCol) poly.classList.add('hex-poll-miss');
      g.appendChild(poly);
      // 점선 테두리(예측 정당색)를 채움색 위에서도 보이게 — 흰 케이싱 위에 색 점선, 살짝 안쪽으로.
      if (missCol) {
        for (const [w, col, dash] of [[4, '#fff', null], [2.4, missCol, '3,2.4']]) {
          const ol = document.createElementNS(NS, 'polygon');
          ol.setAttribute('points', hexPoints(cell.cx, cell.cy, R - 2.5));
          ol.setAttribute('fill', 'none'); ol.setAttribute('stroke', col); ol.setAttribute('stroke-width', String(w));
          if (dash) ol.setAttribute('stroke-dasharray', dash);
          ol.setAttribute('pointer-events', 'none'); g.appendChild(ol);
        }
      }
      const tt = document.createElementNS(NS, 'title');
      tt.textContent = opts.titleOf ? opts.titleOf(cell.sido, cell.win)
        : ((cell.win
          ? `${cell.sido} · ${cell.win.name}(${cell.win.party}) ${fmtPct(cell.win.pct, { digits: 1 })}`
          : `${cell.sido} · 데이터 없음`) + (missCol ? ' · 여론조사는 빗나감(테두리=조사 1위 정당)' : ''));
      g.appendChild(tt);
      // 시도 라벨
      const t1 = document.createElementNS(NS, 'text');
      t1.setAttribute('x', cell.cx); t1.setAttribute('y', cell.cy - 6);
      t1.setAttribute('text-anchor', 'middle');
      t1.setAttribute('font-size', '11');  // sidoCluster 지역명(.ar-genhex-label)과 렌더 크기 통일(~18px)
      t1.setAttribute('font-weight', '700');
      t1.setAttribute('class', cell.win ? 'gov-hex-label on-data' : 'gov-hex-label no-data');
      if (textCol) t1.setAttribute('fill', textCol);
      t1.textContent = cell.label;
      g.appendChild(t1);
      // 후보명 + 득표율
      if (cell.win) {
        const t2 = document.createElementNS(NS, 'text');
        t2.setAttribute('x', cell.cx); t2.setAttribute('y', cell.cy + 9);
        t2.setAttribute('text-anchor', 'middle');
        t2.setAttribute('font-size', '10');
        t2.setAttribute('font-weight', '700');
        t2.setAttribute('class', 'gov-hex-name');
        if (textCol) t2.setAttribute('fill', textCol);
        t2.textContent = cell.win.name;
        g.appendChild(t2);
        const t3 = document.createElementNS(NS, 'text');
        t3.setAttribute('x', cell.cx); t3.setAttribute('y', cell.cy + 22);
        t3.setAttribute('text-anchor', 'middle');
        t3.setAttribute('font-size', '9');
        t3.setAttribute('class', 'gov-hex-pct');
        t3.setAttribute('font-variant-numeric', 'tabular-nums');
        if (textCol) t3.setAttribute('fill', textCol);
        t3.textContent = `${fmtPct(cell.win.pct, { digits: 1 })}`;
        g.appendChild(t3);
      }
      if (opts.onSelect) { g.style.cursor = cell.win ? 'pointer' : 'default'; g.addEventListener('click', () => opts.onSelect(cell.sido)); }
      svg.appendChild(g);
    }
    if (!isSvgHost) {
      // 아카이브(div 호스트) — 새 svg에 팬·줌 부여 + 호스트 단위 줌 보존(재렌더 대비). 폴(svg 호스트)은
      // renderHex가 직접 attach(svg 재사용)하므로 건드리지 않음.
      const keep = window.SvgViewport ? window.SvgViewport.captureHost(host) : null;
      host.innerHTML = ''; host.appendChild(svg);
      if (window.SvgViewport) window.SvgViewport.applyHost(host, svg, { cells: cells.map((c) => ({ region: c.sido, cx: c.cx, cy: c.cy })) }, keep);
    }
    // 캡션의 '시·도 수'를 실제 데이터 있는 셀 수로 갱신(아카이브 .ar-source-line만 — 폴은 closest null이라 무시).
    const cap = host.closest && host.closest('.ar-section')?.querySelector('.info-pop, .ar-source-line');
    const nData = cells.filter((c) => c.win).length;
    if (cap && nData && !opts.winnerOf) cap.textContent = `${nData}개 시·도 — 1위 후보(정당색·득표율).`;
    // 줌·포커스 인프라(svg-viewport)용 — 지역→셀중심 + base viewBox. 기존 호출자는 반환값 무시.
    return { cells: cells.map((c) => ({ region: c.sido, cx: c.cx, cy: c.cy })), viewBox: [minCx, 0, maxCx - minCx, maxCy] };
  }

  // opts: {tc='3'(광역단체장)|'1'(대선), hostId='ar-governor-hex'} — 단독 호출용(sidoView 없이).
  function init(ctx, opts) {
    const tc = (opts && opts.tc) || '3';
    const hostId = (opts && opts.hostId) || 'ar-governor-hex';
    const host = document.getElementById(hostId);
    if (!host) return;
    const races = (ctx?.results?.races || []).filter(
      (r) => r.scope === 'sido' && r.sg_typecode === tc
    );
    if (!races.length) {
      host.parentElement?.setAttribute('hidden', '');
      return;
    }
    host.parentElement?.removeAttribute('hidden');
    draw(host, races);
  }

  window.Archive = window.Archive || {};
  window.Archive.governorHex = { init, draw };
})();
