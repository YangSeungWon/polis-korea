// 시군구 표-비례 카토그램 (공용 단일 렌더러) — 격자: 시군구당 N개 작은 hex(1 hex=2만표) /
//   dorling: 원(표 비례·force-directed, 파이=후보 구성). 역대 흐름·종합·폴이 모두 이걸 씀.
//   시점성(회차별 셀·_borrowed/_fill)은 호출부가 데이터로 주입 — 렌더러는 받은 셀만 그림.
//   의존(전역): partyColor·drawSidoEdgeLabels·gapOpacity·shortSigunguLabel·periodSidoName·fmtUnitName·
//     pickTextColor·CartogramUtil(hexSpiral/allocateByVotes/convexHull/pieSlice/packCircles/drawBorders).
//   Archive.drawSigunguCartogram(svg, cells, resultFn, opts) → { shown, cells, viewBox }
//     cells = [{sido,name,c,r, code?, _borrowed?}]
//     resultFn(sido,name) → { candidates:[{party,name,votes,pct,uncontested?}], voted, _fill? } | null
//     opts = { mode:'격자'|'dorling', r=22, unit=20000, selected:{sido,name}|null,
//              onSelect(sido,name,result,cell), date('' 종합/폴 → 현행 시도명) }
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  // 당색 fill — 다크 배경서 어두운 당색이 묻히지 않게 legibleColor 보정(라이트선 거의 무변).
  const pcol = (p) => {
    const c = (typeof partyColor === 'function') ? partyColor(p) : '#888';
    return (typeof legibleColor === 'function') ? legibleColor(c) : c;
  };
  function hexPoints(cx, cy, r) {
    const p = [];
    for (let i = 0; i < 6; i++) { const a = Math.PI / 6 + i * Math.PI / 3; p.push(`${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`); }
    return p.join(' ');
  }
  const hexCenter = (col, row, colW, rowH, offX, offY) => [offX + col * colW + (row % 2 ? colW / 2 : 0), offY + row * rowH];

  const CU = window.CartogramUtil || {};
  const psido = (s, date) => (typeof periodSidoName === 'function' ? periodSidoName(s, date || '') : s);
  const uname = (n) => (typeof fmtUnitName === 'function' ? fmtUnitName(n) : n);
  const slabel = (n, s) => (typeof shortSigunguLabel === 'function' ? shortSigunguLabel(n, s) : { short: n });

  function drawSigunguCartogram(svg, cells, resultFn, opts) {
    opts = opts || {};
    const mode = opts.mode || '격자';
    const sel = opts.selected || null;
    const date = opts.date || '';
    const r = opts.r || 22, colW = r * Math.sqrt(3), rowH = r * 1.5;
    const minC = Math.min(...cells.map((c) => c.c)), minR = Math.min(...cells.map((c) => c.r));
    const maxC = Math.max(...cells.map((c) => c.c)), maxR = Math.max(...cells.map((c) => c.r));
    const offX = -minC * colW + colW / 2, offY = -minR * rowH + rowH;
    const w = (maxC - minC + 1) * colW + colW, h = (maxR - minR + 1) * rowH + rowH;
    const EM = (typeof SIDO_EDGE_MARGIN !== 'undefined') ? SIDO_EDGE_MARGIN : 78;
    svg.innerHTML = '';
    const vb = [-EM, 0, Math.ceil(w) + 2 * EM, Math.ceil(h)];   // base viewBox(줌·포커스용)
    svg.setAttribute('viewBox', `${vb[0]} ${vb[1]} ${vb[2]} ${vb[3]}`);
    svg.setAttribute('width', Math.ceil(w) + 2 * EM); svg.setAttribute('height', Math.ceil(h));
    const geom = { colW, rowH, offX, offY, r };
    const ctr = (d) => hexCenter(d.c, d.r, colW, rowH, offX, offY);
    // 줌·포커스 앵커 — region(시도|시군구)→셀 중심(그리드). 단색/격자/원형 교차 보존에 공통 키.
    const focusCells = cells.map((d) => { const [cx, cy] = ctr(d); return { region: d.sido + '|' + d.name, cx, cy }; });
    const isSel = (d) => !!(sel && sel.sido === d.sido && sel.name === d.name);
    const bindClick = (g, d) => { if (opts.onSelect) { g.style.cursor = 'pointer'; g.addEventListener('click', () => opts.onSelect(d.sido, d.name, resultFn(d.sido, d.name), d)); } };
    // 득표율이 없으면 '0%'가 아니라 '—'. 0%는 '아무도 안 찍었다'는 없는 사실이다.
    const pctStr = (top) => (top.uncontested ? '무투표 당선'
      : (top.pct != null ? top.pct.toFixed(1) + '%' : '득표율 자료 없음'));
    const titleText = (d, top, extra) => (top
      ? `${psido(d.sido, date)} ${uname(d.name)} · ${top.name || top.party}(${top.party}) ${pctStr(top)}${extra || ''}`
      : `${psido(d.sido, date)} ${uname(d.name)}`);

    // 총투표수 — voted 없으면 voters(live-count는 voters만). maxVoted는 차용(_fill) 제외(스케일 왜곡 방지).
    const vget = (r) => ((r && r.voted != null) ? r.voted : ((r && r.voters) || 0));
    const rmap = new Map(); let maxVoted = 0;
    // _pending = 선거는 있었고 결과(의석)도 확정인데 **정당별 득표가 아직 공표되지 않음**.
    // 빈 칸으로 두면 '선거가 없었다'·'자료가 없다'와 구별되지 않는다 — 셋은 다르다.
    const pending = [];
    for (const d of cells) {
      const res = resultFn(d.sido, d.name);
      if (res && res._pending && !vget(res)) { pending.push([d, res]); continue; }
      if (res && vget(res)) { rmap.set(d, res); if (!res._fill) maxVoted = Math.max(maxVoted, vget(res)); }
    }

    if (typeof drawSidoEdgeLabels === 'function') {
      drawSidoEdgeLabels(svg, cells.map((d) => { const [cx, cy] = ctr(d); return { sido: d.sido, cx, cy }; }));
    }

    // 미공표 셀 — 옅은 빗금 hex + 이유를 title로. 색(정치)을 주지 않는다.
    function drawPending() {
      if (!pending.length) return;
      // 빗금 pattern은 이 svg 안에 있어야 url(#...)이 걸린다(문서 공유 defs 아님).
      const defs = document.createElementNS(NS, 'defs');
      const pat = document.createElementNS(NS, 'pattern');
      pat.setAttribute('id', 'sig-pending-hatch'); pat.setAttribute('width', '6');
      pat.setAttribute('height', '6'); pat.setAttribute('patternUnits', 'userSpaceOnUse');
      pat.setAttribute('patternTransform', 'rotate(135)');
      const bg = document.createElementNS(NS, 'rect');
      bg.setAttribute('width', '6'); bg.setAttribute('height', '6');
      bg.setAttribute('fill', 'var(--bg2, #f2f4f8)');
      const ln = document.createElementNS(NS, 'line');
      ln.setAttribute('x1', '0'); ln.setAttribute('y1', '0');
      ln.setAttribute('x2', '0'); ln.setAttribute('y2', '6');
      ln.setAttribute('stroke', 'var(--rule-strong, #b9c0c8)'); ln.setAttribute('stroke-width', '1.6');
      pat.appendChild(bg); pat.appendChild(ln); defs.appendChild(pat); svg.appendChild(defs);
      for (const [d, res] of pending) {
        const [cx, cy] = ctr(d);
        const g = document.createElementNS(NS, 'g'); bindClick(g, d); g.setAttribute('data-sido', d.sido);
        g.setAttribute('class', 'sig-pending');
        const poly = document.createElementNS(NS, 'polygon');
        poly.setAttribute('points', hexPoints(cx, cy, r - 1));
        poly.setAttribute('class', 'sig-pending-fill');
        g.appendChild(poly);
        const tt = document.createElementNS(NS, 'title');
        tt.textContent = `${psido(d.sido, date)} ${uname(d.name)} · `
          + (res._pending_note || '정당별 득표 미공표');
        g.appendChild(tt);
        const lbl = slabel(d.name, d.sido);
        if (lbl.short) {
          const txt = document.createElementNS(NS, 'text');
          txt.setAttribute('x', cx.toFixed(1)); txt.setAttribute('y', (cy - 8).toFixed(1));
          txt.setAttribute('text-anchor', 'middle');
          txt.setAttribute('font-size', lbl.short.length > 3 ? '6' : '8');
          txt.setAttribute('font-weight', '700'); txt.setAttribute('class', 'hist-sigungu-label');
          txt.setAttribute('pointer-events', 'none');
          txt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
          txt.textContent = lbl.short; g.appendChild(txt);
        }
        svg.appendChild(g);
      }
    }

    // ── Dorling — 원(표 비례), 파이=후보, 시도별 convex hull 권역 ──────────────
    if (mode === 'dorling' && maxVoted > 0) {
      const gapOp = (typeof gapOpacity === 'function') ? gapOpacity : () => 1;
      const nodes = cells.filter((d) => rmap.get(d) && !d._borrowed).map((d) => {
        const res = rmap.get(d);
        const cs = (res.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
        const top = cs[0], gap = (cs[0] && cs[1]) ? (cs[0].pct - cs[1].pct) : null;
        const v = res._fill ? 0 : vget(res);   // 차용 셀은 v-비례 금지 → 작은 대표 원
        const [cx0, cy0] = ctr(d);
        return { d, res, top, cands: cs, cx0, cy0, cx: cx0, cy: cy0,
          radius: v > 0 ? Math.max(3, (r - 0.7) * Math.sqrt(v / maxVoted)) : 3,
          fill: top ? pcol(top.party) : 'var(--bg3, #e6e9ef)', op: top ? gapOp(gap) : 1 };
      });
      CU.packCircles(nodes, 40);
      // 권역(시도) 테두리 — 시도별 convex hull(원 외곽 padding 포함). dorling은 hex 경계 안 씀.
      const groups = new Map();
      for (const n of nodes) { const k = n.d.sido; (groups.get(k) || groups.set(k, []).get(k)).push(n); }
      for (const [sido, list] of groups) {
        const pts = [];
        for (const n of list) for (let k = 0; k < 12; k++) { const a = k * Math.PI / 6; pts.push({ x: n.cx + Math.cos(a) * (n.radius + 3), y: n.cy + Math.sin(a) * (n.radius + 3) }); }
        const hull = CU.convexHull(pts);
        if (hull.length < 3) continue;
        const poly = document.createElementNS(NS, 'polygon');
        poly.setAttribute('points', hull.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '));
        
        poly.setAttribute('stroke-linejoin', 'round'); poly.setAttribute('pointer-events', 'none');
        poly.setAttribute('class', 'sido-hull'); poly.setAttribute('data-sido', sido);   // 권역 호버 강조용
        svg.appendChild(poly);
      }
      const pieSlice = CU.pieSlice;
      for (const n of nodes) {
        const g = document.createElementNS(NS, 'g'); bindClick(g, n.d); g.setAttribute('data-sido', n.d.sido);
        const cs = n.cands, totalV = cs.reduce((s, c) => s + (c.votes || 0), 0);
        const selW = isSel(n.d) ? '1.6' : '0.5';
        if (totalV > 0 && cs.filter((c) => (c.votes || 0) > 0).length > 1) {
          let a0 = -Math.PI / 2;
          for (const cand of cs) { const frac = (cand.votes || 0) / totalV; if (frac <= 0) continue; const a1 = a0 + frac * 2 * Math.PI; const p = document.createElementNS(NS, 'path'); p.setAttribute('d', pieSlice(n.cx, n.cy, n.radius, a0, a1)); p.setAttribute('fill', pcol(cand.party)); g.appendChild(p); a0 = a1; }
          const ring = document.createElementNS(NS, 'circle'); ring.setAttribute('cx', n.cx.toFixed(1)); ring.setAttribute('cy', n.cy.toFixed(1)); ring.setAttribute('r', n.radius.toFixed(1)); ring.setAttribute('fill', 'none'); ring.setAttribute('stroke', 'var(--ink,#0a0e1a)'); ring.setAttribute('stroke-width', selW); g.appendChild(ring);
        } else {
          const c = document.createElementNS(NS, 'circle'); c.setAttribute('cx', n.cx.toFixed(1)); c.setAttribute('cy', n.cy.toFixed(1)); c.setAttribute('r', n.radius.toFixed(1)); c.setAttribute('fill', n.fill); c.setAttribute('stroke', 'var(--ink,#0a0e1a)'); c.setAttribute('stroke-width', selW); g.appendChild(c);
        }
        const tt = document.createElementNS(NS, 'title'); tt.textContent = titleText(n.d, n.top); g.appendChild(tt);
        // 라벨 — 큰 원만(겹침 방지)
        if (n.radius >= 10 && n.top) {
          const lbl = slabel(n.d.name, n.d.sido);
          if (lbl.short) {
            const txt = document.createElementNS(NS, 'text');
            txt.setAttribute('x', n.cx.toFixed(1)); txt.setAttribute('y', (n.cy + 3).toFixed(1));
            txt.setAttribute('text-anchor', 'middle'); txt.setAttribute('font-size', '7'); txt.setAttribute('font-weight', '600');
            txt.setAttribute('fill', (n.fill && typeof pickTextColor === 'function') ? pickTextColor(n.fill) : 'var(--ink)');
            txt.setAttribute('pointer-events', 'none'); txt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
            txt.textContent = lbl.short; g.appendChild(txt);
          }
        }
        svg.appendChild(g);
      }
      drawPending();
      CU.wireSidoHover(svg);
      return { shown: nodes.length, cells: focusCells, viewBox: vb, pending: pending.length };
    }

    // ── 격자 — 시군구당 N개 작은 hex(1 hex=2만표). 차용/모도시 셀은 단일 채움 ──────
    const unit = opts.unit || 20000, smallR = 3.2;
    let shown = 0, selectedG = null;
    for (const d of cells) {
      const res = rmap.get(d); if (!res || !vget(res)) continue;
      const isFill = !!res._fill || d._borrowed;   // 당시 미분리 구·모도시 broadcast → 단일 hex
      const N = isFill ? 1 : Math.max(1, Math.ceil(vget(res) / unit));
      const [cx0, cy0] = ctr(d);
      const cands = (res.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      const top = cands[0];
      const g = document.createElementNS(NS, 'g'); bindClick(g, d); g.setAttribute('data-sido', d.sido); if (!isFill) shown += 1;
      const tt = document.createElementNS(NS, 'title');
      tt.textContent = titleText(d, top, isFill ? ' · 당시 미분리(부모 구)' : ' · ' + N + '석(2만표=1)'); g.appendChild(tt);
      // footprint(테마 반투명 흰 배경) — 같은 구 인접 셀끼리 이어져 병합 구가 한 면처럼.
      const fp = document.createElementNS(NS, 'polygon');
      fp.setAttribute('points', hexPoints(cx0, cy0, r)); fp.setAttribute('class', 'sig-outline'); fp.setAttribute('stroke', 'none');
      g.appendChild(fp);
      if (isFill) {
        const poly = document.createElementNS(NS, 'polygon');
        poly.setAttribute('points', hexPoints(cx0, cy0, r - 1));
        poly.setAttribute('fill', top ? pcol(top.party) : 'var(--bg3, #e6e9ef)'); poly.setAttribute('opacity', '0.85');
        g.appendChild(poly);
      } else {
        const alloc = CU.allocateByVotes(cands, N);
        const fills = [];
        for (let i = 0; i < cands.length; i++) for (let k = 0; k < alloc[i]; k++) fills.push(pcol(cands[i].party));
        while (fills.length < N) fills.push('var(--bg3, #e6e9ef)');
        const spiral = CU.hexSpiral(N);
        let ext = 0; for (const [q, ar] of spiral) ext = Math.max(ext, Math.hypot(Math.sqrt(3) * (q + ar / 2), 1.5 * ar));
        const sr = Math.min(smallR, (r - 2) / (ext + 1));
        for (let i = 0; i < spiral.length; i++) {
          const [q, ar] = spiral[i];
          const sx = cx0 + sr * Math.sqrt(3) * (q + ar / 2), sy = cy0 + sr * 1.5 * ar;
          const poly = document.createElementNS(NS, 'polygon');
          poly.setAttribute('points', hexPoints(sx, sy, sr - 0.4));
          poly.setAttribute('fill', fills[i] || 'var(--bg3, #e6e9ef)');
          g.appendChild(poly);
        }
        // 셀 라벨 — canonical 셀(클러스터)에만(차용 셀은 같은 이름 중복이라 생략)
        const lbl = slabel(d.name, d.sido);
        if (lbl.short) {
          const txt = document.createElementNS(NS, 'text');
          txt.setAttribute('x', cx0.toFixed(1)); txt.setAttribute('y', (cy0 - 8).toFixed(1)); txt.setAttribute('text-anchor', 'middle');
          txt.setAttribute('font-size', lbl.short.length > 3 ? '6' : '8'); txt.setAttribute('font-weight', '700');
          txt.setAttribute('class', 'hist-sigungu-label'); txt.setAttribute('pointer-events', 'none');
          txt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
          txt.textContent = lbl.short; g.appendChild(txt);
        }
      }
      svg.appendChild(g);
      if (isSel(d)) selectedG = g;
    }
    // 구 외곽선(병합 구 한 면) → 시도 경계(굵게) 순으로 셀 위에. cartogram-util 공용(hexgrid 의존 없음).
    CU.drawBorders(svg, cells, geom, { key: (c) => c.sido + '|' + c.name, includeOutline: false, lineClass: 'gu-outline' });
    CU.drawBorders(svg, cells, geom, { key: (c) => c.sido, includeOutline: true, lineClass: 'sido-border' });
    // 선택 강조 — 선택 셀 위로 + 선택 구 외곽선 맨 위
    if (selectedG) svg.appendChild(selectedG);
    if (sel) {
      const selCells = cells.filter((x) => x.sido === sel.sido && x.name === sel.name);
      if (selCells.length) CU.drawBorders(svg, selCells, geom, { key: (c) => c.sido + '|' + c.name, includeOutline: true, lineClass: 'gu-outline is-selected' });
    }
    drawPending();
    CU.wireSidoHover(svg);
    return { shown, cells: focusCells, viewBox: vb, pending: pending.length };
  }

  window.Archive = window.Archive || {};
  window.Archive.drawSigunguCartogram = drawSigunguCartogram;
})();
