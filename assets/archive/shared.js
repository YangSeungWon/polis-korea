// archive 공통 — 모든 모드가 쓰는 SIDO_ORDER · helpers · 필터 · 폴 목록.
// window.Archive 네임스페이스에 attach. 다른 모드 모듈이 여기서 destructure 가능.

(function () {
  const Archive = (window.Archive = window.Archive || {});

  Archive.SIDO_ORDER = [
    '서울특별시', '인천광역시', '경기도', '강원특별자치도',
    '세종특별자치시', '대전광역시', '충청북도', '충청남도',
    '광주광역시', '전북특별자치도', '전라남도',
    '대구광역시', '부산광역시', '울산광역시', '경상북도', '경상남도',
    '제주특별자치도',
  ];

  Archive.ssh = (s) => (typeof SIDO_LABEL_SHORT !== 'undefined') ? (SIDO_LABEL_SHORT[s] || s) : s;
  Archive.pcol = (p) => (typeof partyColor === 'function') ? partyColor(p) : '#999';

  // 위성정당 → 본정당: assets/parties.js 의 SATELLITE_TO_MAIN/mainParty 전역 사용.
  // 단일 출처: data/parties/satellites.json → sync_satellites_js.py가 parties.js로 sync.
  Archive.SATELLITE_TO_MAIN = (typeof SATELLITE_TO_MAIN !== 'undefined') ? SATELLITE_TO_MAIN : {};
  Archive.mainParty = (typeof mainParty === 'function') ? mainParty : ((p) => Archive.SATELLITE_TO_MAIN[p] || p);

  // 폴 필터: pollsWindow (meta) 안 period_start 인 폴만 통과. window 없으면 1년 전 ~ 회차일.
  Archive.filterPoll = function (poll, meta) {
    const ps = poll.period_start || '';
    if (!ps) return false;
    const w = meta.pollsWindow || {};
    const start = w.start || (() => {
      const d = new Date(meta.date); d.setFullYear(d.getFullYear() - 1);
      return d.toISOString().slice(0, 10);
    })();
    const end = w.end || meta.date;
    return ps >= start && ps <= end;
  };

  // 조사 목록 — 회차·모드 무관 공통 렌더. 모든 모드에서 마지막에 호출.
  Archive.renderPollsList = function (polls) {
    if (!polls?.length) return;
    const host = document.getElementById('ar-polls-list-host');
    polls.slice()
      .sort((a, b) => (b.period_end || '').localeCompare(a.period_end || ''))
      .slice(0, 60)
      .forEach((p) => {
        const item = document.createElement('div');
        item.className = 'ar-poll-item';
        item.innerHTML = `
          <div class="agency">${p.agency || '—'}</div>
          <div class="period">${p.period_start || '?'} ~ ${p.period_end || '?'} · ${p.sido || ''} · n=${p.sample_size || '?'}</div>
        `;
        host.appendChild(item);
      });
    if (polls.length > 60) {
      const more = document.createElement('div');
      more.className = 'ar-poll-item';
      more.style.textAlign = 'center';
      more.style.color = 'var(--ink-mute)';
      more.textContent = `… 외 ${polls.length - 60}건`;
      host.appendChild(more);
    }
    document.getElementById('ar-polls-list').hidden = false;
  };

  // 후보·정당 시계열 SVG — 대선(후보별)·총선(정당별) 둘 다 쓰는 공용 차트.
  // series: [{ label, color, points: [{d, pct}] }]
  Archive.renderTrendSVG = function (host, series, opts = {}) {
    if (!series.length) return false;
    const W = opts.width || 720, H = opts.height || 280;
    const P = { l: 36, r: 12, t: 12, b: 28 };
    const innerW = W - P.l - P.r, innerH = H - P.t - P.b;
    const allD = series.flatMap((s) => s.points.map((p) => p.d)).filter(Boolean).sort();
    if (!allD.length) return false;
    const d0 = new Date(allD[0]).getTime();
    const d1 = new Date(allD[allD.length - 1]).getTime();
    const allV = series.flatMap((s) => s.points.map((p) => p.pct));
    const yMax = Math.max(opts.yMin || 50, Math.ceil(Math.max(...allV) / 10) * 10);
    const yStep = opts.yStep || 10;
    const xf = (d) => P.l + ((new Date(d).getTime() - d0) / (d1 - d0 || 1)) * innerW;
    const yf = (v) => P.t + innerH - (v / yMax) * innerH;
    let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;max-height:340px">`;
    for (let v = 0; v <= yMax; v += yStep) {
      const y = yf(v);
      svg += `<line x1="${P.l}" x2="${W - P.r}" y1="${y}" y2="${y}" stroke="var(--line)" stroke-width="0.5"/>`;
      svg += `<text x="${P.l - 6}" y="${y + 3}" text-anchor="end" font-size="10" fill="var(--ink-mute)">${v}%</text>`;
    }
    const dt0 = new Date(d0), dt1 = new Date(d1);
    const months = (dt1.getFullYear() - dt0.getFullYear()) * 12 + (dt1.getMonth() - dt0.getMonth());
    const step = Math.max(1, Math.ceil(months / 6));
    for (let i = 0; i <= months; i += step) {
      const dx = new Date(dt0.getFullYear(), dt0.getMonth() + i, 1);
      if (dx.getTime() > d1) break;
      const x = xf(dx.toISOString().slice(0, 10));
      svg += `<text x="${x}" y="${H - 8}" text-anchor="middle" font-size="10" fill="var(--ink-mute)">${dx.getFullYear() % 100}.${(dx.getMonth() + 1).toString().padStart(2, '0')}</text>`;
    }
    for (const s of series) {
      const sorted = s.points.slice().sort((a, b) => (a.d || '').localeCompare(b.d || ''));
      const path = sorted.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xf(p.d).toFixed(1)} ${yf(p.pct).toFixed(1)}`).join(' ');
      svg += `<path d="${path}" stroke="${s.color}" stroke-width="1.4" fill="none" opacity="0.85"/>`;
      const last = sorted[sorted.length - 1];
      svg += `<circle cx="${xf(last.d)}" cy="${yf(last.pct)}" r="2.5" fill="${s.color}"/>`;
      svg += `<text x="${xf(last.d) + 5}" y="${yf(last.pct) + 3}" font-size="10" fill="${s.color}" font-weight="700">${s.label}</text>`;
    }
    svg += '</svg>';
    host.innerHTML = svg;
    return true;
  };

  // 출구조사 vs 실제 — 시도별 덤벨(예측 ●━ line ━● 실제). 대선·지선 공용.
  //   host: 그리드 element / sources: exitData.sources / actual: {sido:{name,party,pct}}
  //   opts: { order:[sido...], matchBy:'name'|'party' }
  // 미스(1위 빗나감)는 빨강(행·연결선·✗ 배지)으로 강조, 적중은 초록 ✓.
  Archive.renderExitDumbbell = function (host, sources, actual, opts) {
    const order = (opts && opts.order) || Archive.SIDO_ORDER;
    const matchBy = (opts && opts.matchBy) || 'party';
    const now = new Date();
    let any = false;
    for (const ep of sources) {
      const qa = ep.quote_after ? new Date(ep.quote_after) : null;
      if (qa && now < qa) continue;
      const res = ep.results || {};
      if (!Object.keys(res).length) continue;
      let hits = 0, total = 0, errSum = 0, errN = 0;
      const rows = [];
      for (const sido of order) {
        const e = res[sido] && res[sido][0];
        const a = actual[sido];
        if (!e || !a) continue;
        const hit = matchBy === 'name' ? (e.name === a.name) : (e.party === a.party);
        total += 1; if (hit) hits += 1;
        if (e.pct != null && a.pct != null) { errSum += Math.abs(e.pct - a.pct); errN += 1; }
        rows.push({ sido, e, a, hit });
      }
      if (!rows.length) continue;
      any = true;
      const rate = total ? Math.round(hits / total * 100) : 0;
      const avgErr = errN ? (errSum / errN).toFixed(2) : '—';
      const card = document.createElement('div');
      card.className = 'ar-exit-block';
      card.innerHTML = `<h3 class="ar-exit-source">${ep.name || ep.key}
        <span class="ar-exit-hitrate">${hits}/${total} 적중 ${rate}%</span>
        <span class="ar-exit-err">평균 오차 ${avgErr}%p</span></h3>`;
      const chart = document.createElement('div');
      chart.className = 'ar-exit-dumbbell';
      let rowsHtml = '';
      for (const r of rows) {
        const e = r.e, a = r.a, hit = r.hit, sido = r.sido;
        const ePct = e.pct || 0, aPct = a.pct || 0;
        const eCol = Archive.pcol(e.party), aCol = Archive.pcol(a.party);
        const lo = Math.min(ePct, aPct), hi = Math.max(ePct, aPct);
        const diff = (e.pct != null && a.pct != null) ? Math.abs(ePct - aPct).toFixed(1) : '';
        const cls = (hit ? 'is-hit' : 'is-miss') + (sido === '전국' ? ' is-nation' : '');
        const mark = hit ? '<span class="ar-exit-mark">✓</span>'
          : '<span class="ar-exit-mark ar-exit-miss-mark">✗</span>';
        rowsHtml += `
          <div class="ar-exit-dbb ${cls}">
            <span class="ar-exit-sido">${sido === '전국' ? '전국' : Archive.ssh(sido)}</span>
            <div class="ar-exit-track">
              <div class="ar-exit-line ${hit ? '' : 'is-miss'}" style="left:${lo}%;width:${hi - lo}%"></div>
              <div class="ar-exit-dot ar-exit-dot-pred" style="left:${ePct}%;background:${eCol}" title="예측 ${e.name || e.party} ${ePct.toFixed(1)}%"></div>
              <div class="ar-exit-dot ar-exit-dot-actual" style="left:${aPct}%;background:${aCol}" title="실제 ${a.name || a.party} ${aPct.toFixed(1)}%"></div>
            </div>
            <span class="ar-exit-pred-pct" style="color:${eCol}">${ePct.toFixed(1)}</span>
            <span class="ar-exit-arrow">→</span>
            <span class="ar-exit-actual-pct" style="color:${aCol}">${aPct.toFixed(1)}</span>
            <span class="ar-exit-diff">${diff}%p</span>
            ${mark}
          </div>`;
      }
      chart.innerHTML = rowsHtml;
      card.appendChild(chart);
      host.appendChild(card);
    }
    return any;
  };

  // 시도 클러스터 force-packing — 권역 격자 seed에서 크기대로 가변 간격으로 뭉침.
  // 작은 권역(세종·제주)은 가까이, 큰 권역(경기)만 필요한 만큼 벌어짐 → 균일 간격 낭비 제거.
  // nodes: [{cx0, cy0, r, ...}] 의 cx/cy를 갱신(겹침 반발 + seed 앵커). 대선 dorling과 동일 알고리즘.
  Archive.packClusters = function (nodes, opts) {
    opts = opts || {};
    const iters = opts.iters || 120;
    const pad = opts.pad != null ? opts.pad : 4;
    const anchor = opts.anchor != null ? opts.anchor : 0.05;
    for (const n of nodes) { n.cx = n.cx0; n.cy = n.cy0; }
    for (let it = 0; it < iters; it++) {
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          const dx = b.cx - a.cx, dy = b.cy - a.cy;
          const dist = Math.hypot(dx, dy) || 0.01;
          const ov = a.r + b.r + pad - dist;
          if (ov > 0) { const p = ov * 0.5 / dist; a.cx -= p * dx; a.cy -= p * dy; b.cx += p * dx; b.cy += p * dy; }
        }
      }
      for (const n of nodes) { n.cx += (n.cx0 - n.cx) * anchor; n.cy += (n.cy0 - n.cy) * anchor; }
    }
    return nodes;
  };

  // ── 시도 클러스터 (의석·득표비례 공용, mode 옵션) ─────────────────────────────
  // layout()이 위치·viewBox 1회 계산 → drawHex/drawDorling 공유(토글 위치 고정).
  //   mode='seats'(기본): bySido={시도:{정당:석}}. 1 hex=1석 (allocate가 정확).
  //   mode='proportional': races=[{sido,candidates:[{name,party,votes|share,pct}],valid_votes|weight}].
  //     1 hex≈10만표, allocate가 득표 비율로 배분 (대선 — 승자독식 단색 거부). seedGap·smallR만 mode별.
  Archive.sidoCluster = (function () {
    const NS = 'http://www.w3.org/2000/svg';
    const PAD = 4;
    const PARAM = { seats: { smallR: 6, seedGap: 85 }, proportional: { smallR: 3.5, seedGap: 65 } };
    const clusterR = (N, smallR) => { const L = Math.ceil(Math.sqrt(Math.max(N - 1, 0) / 3)); return Math.max(9, (L + 0.6) * Math.sqrt(3) * smallR); };
    const NB = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]];
    const ring = (L) => { const out = []; let q = -L, r = L; for (let s = 0; s < 6; s++) { const [dq, dr] = NB[s]; for (let i = 0; i < L; i++) { out.push([q, r]); q += dq; r += dr; } } return out; };
    const spiral = (N) => { if (N <= 0) return []; const out = [[0, 0]]; let L = 0; while (out.length < N) { L++; const rg = ring(L); const rem = N - out.length; out.push(...(rem >= rg.length ? rg : rg.slice(0, rem))); } return out; };
    const hexPts = (cx, cy, R) => { const p = []; for (let i = 0; i < 6; i++) { const a = Math.PI / 6 + i * Math.PI / 3; p.push(`${cx + R * Math.cos(a)},${cy + R * Math.sin(a)}`); } return p.join(' '); };
    // 평평top 소헥스 — 뾰족top 소헥스 덩어리는 평평top이 돼 뾰족top 셀과 어긋남. 평평top으로 깔면 덩어리가 뾰족top → 셀 정렬.
    const hexPtsFlat = (cx, cy, R) => { const p = []; for (let i = 0; i < 6; i++) { const a = i * Math.PI / 3; p.push(`${cx + R * Math.cos(a)},${cy + R * Math.sin(a)}`); } return p.join(' '); };
    const _v = (c) => (c && c.share != null ? c.share : ((c && c.votes) || 0));

    // 전남광주 통합(2026 지선, seats만) — 광주+전남+통합 한 셀 + honamMergedLayout.
    function mergeHonam(bySido) {
      if (!((bySido['전남광주특별시'] || bySido['전남광주통합특별시']) && typeof honamMergedLayout === 'function')) return { data: bySido, layout: SIDO_HEX_LAYOUT };
      const merged = {};
      for (const src of ['광주광역시', '전라남도', '전남광주특별시', '전남광주통합특별시']) { const s = bySido[src]; if (!s) continue; for (const [p, c] of Object.entries(s)) merged[p] = (merged[p] || 0) + c; }
      const data = Object.assign({}, bySido); delete data['광주광역시']; delete data['전라남도']; delete data['전남광주통합특별시']; data['전남광주특별시'] = merged;
      return { data, layout: honamMergedLayout(SIDO_HEX_LAYOUT) };
    }

    // 입력 → {bySido:{sido:{slices:[{key,color,value,tip}], sizeTotal}}, hexLayout}
    function normalize(input, mode) {
      const out = {}; const ns = (typeof canonSido === 'function') ? canonSido : (s) => s;
      if (mode === 'proportional') {
        for (const r of (input || [])) {
          const cands = (r.candidates || []).slice().sort((a, b) => _v(b) - _v(a)).filter((c) => _v(c) > 0);
          if (!cands.length) continue;
          const sizeTotal = r.weight != null ? r.weight : (r.valid_votes != null ? r.valid_votes : cands.reduce((s, c) => s + _v(c), 0));
          if (!sizeTotal) continue;
          out[ns(r.sido)] = { slices: cands.map((c) => ({ key: c.name, color: Archive.pcol(c.party), value: _v(c), tip: `${c.name}(${c.party}) ${(c.pct || 0).toFixed(1)}%` })), sizeTotal };
        }
        return { bySido: out, hexLayout: SIDO_HEX_LAYOUT };
      }
      const m = mergeHonam(input || {});
      for (const [sido, seats] of Object.entries(m.data)) {
        const entries = Object.entries(seats).sort((a, b) => b[1] - a[1]);
        const tot = entries.reduce((s, [, c]) => s + c, 0); if (!tot) continue;
        out[sido] = { slices: entries.map(([p, c]) => ({ key: p, color: Archive.pcol(p), value: c, tip: `${p} ${c}` })), sizeTotal: tot };
      }
      return { bySido: out, hexLayout: m.layout };
    }

    // 큰 정수 잔여(largest remainder)로 N칸을 value 비율 배분. seats(N=합계)면 정확, prop이면 비례.
    function allocate(slices, N) {
      const total = slices.reduce((s, x) => s + x.value, 0);
      if (!total) return slices.map(() => 0);
      const raw = slices.map((x) => x.value * N / total);
      const fl = raw.map(Math.floor);
      const rem = N - fl.reduce((a, b) => a + b, 0);
      const order = raw.map((v, i) => ({ i, f: v - Math.floor(v) })).sort((a, b) => b.f - a.f);
      for (let k = 0; k < rem && order.length; k++) fl[order[k % order.length].i] += 1;
      return fl;
    }

    function layout(input, mode) {
      if (typeof SIDO_HEX_LAYOUT !== 'object') return null;
      const P = PARAM[mode] || PARAM.seats;
      const { bySido, hexLayout } = normalize(input, mode);
      let unit = null;
      if (mode === 'proportional') {
        const maxTot = Math.max(1, ...Object.values(bySido).map((c) => c.sizeTotal));
        unit = Math.max(20000, Math.round(maxTot / 90 / 10000) * 10000);  // 1 hex ≈ 10만표
      }
      const nodes = [];
      for (const [sido, pos] of Object.entries(hexLayout)) {
        const cell = bySido[sido]; if (!cell) continue;
        const N = mode === 'proportional' ? Math.max(1, Math.round(cell.sizeTotal / unit)) : cell.sizeTotal;
        nodes.push({ sido, label: pos.label, slices: cell.slices, sizeTotal: cell.sizeTotal, N, r: clusterR(N, P.smallR),
          cx0: pos.col * P.seedGap + (pos.row % 2 ? P.seedGap / 2 : 0), cy0: pos.row * P.seedGap * 0.87 });
      }
      if (!nodes.length) return null;
      // seats(시도의회·총선 지역구 의석)는 셀이 정당색으로 꽉 차므로 고정 그리드가 governorHex처럼 깔끔.
      //   회차마다 같은 자리(충북 추적 용이) — packClusters 표류 대신. 옛 회차에 없는 시도는 자연히 빈 칸.
      //   prop(대선/총선 비례)은 size=득표가 메시지라 균등화 시 셀 내부가 비어 어색 → 종전 force-pack 유지.
      const fixed = (mode === 'seats');
      let Rcell = null;
      if (fixed) {
        // 삼각격자(seedGap 간격, 0.87≈√3/2)의 보로노이 = 정육각형. center-to-vertex = seedGap/√3로
        //   그리면 셀이 빈틈없이 맞물려(governorHex식) 휑한 빈칸이 사라진다. 안의 의석은 inradius(seedGap/2)에 채움.
        const hexR = P.seedGap / Math.sqrt(3);          // 맞물리는 육각 셀 반지름
        const fitR = P.seedGap * 0.5;                   // 의석 미니헥스가 채울 반경(육각 내접원)
        Rcell = hexR;
        const maxN = Math.max(1, ...nodes.map((n) => n.N));
        for (const n of nodes) {
          n.cx = n.cx0; n.cy = n.cy0;                   // 그리드 좌표 그대로 (표류 없음)
          const Lr = Math.ceil(Math.sqrt(Math.max(n.N - 1, 0) / 3));
          n.smallR = fitR / ((Lr + 0.6) * Math.sqrt(3));            // 균등 셀을 N석으로 채우는 셀별 소헥스
          n.rSize = Math.max(fitR * 0.42, fitR * Math.sqrt(n.N / maxN));  // 원형(dorling): 의석∝반지름, 셀 안에
          n.r = hexR;                                   // 외곽 육각·bbox
        }
      } else {
        Archive.packClusters(nodes, { pad: PAD });
      }
      const minX = Math.min(...nodes.map((n) => n.cx - n.r)) - 6;
      const minY = Math.min(...nodes.map((n) => n.cy - n.r)) - 16;
      const W = Math.max(...nodes.map((n) => n.cx + n.r)) - minX + 6;
      const H = Math.max(...nodes.map((n) => n.cy + n.r)) - minY + 6;
      return { nodes, unit, mode, smallR: P.smallR, fixed, Rcell, minX, minY, viewBox: `${minX.toFixed(1)} ${minY.toFixed(1)} ${W.toFixed(1)} ${H.toFixed(1)}` };
    }

    function legendOf(nodes) {  // seats 모드 외부 범례용(정당별 합). prop은 반환 무시됨.
      const partyTotal = new Map(); let totalSeats = 0;
      for (const n of nodes) for (const s of n.slices) { partyTotal.set(s.key, (partyTotal.get(s.key) || 0) + s.value); totalSeats += s.value; }
      return { totalSeats, partyTotal };
    }
    function newSvg(viewBox) { const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('xmlns', NS); svg.setAttribute('viewBox', viewBox); svg.setAttribute('class', 'ar-sidocluster-svg'); return svg; }
    function tipOf(n, mode) { return `${n.sido}${mode === 'seats' ? ` ${n.sizeTotal}석` : ''} · ${n.slices.slice(0, 3).map((s) => s.tip).join(' · ')}`; }
    function nameOf(n) { return n.label || Archive.ssh(n.sido); }
    function addLegend(svg, L, text, shape) {
      const x0 = L.minX + 4, y = L.minY + 12; let tx = x0;
      if (shape === 'hex') {   // 격자 셀과 같은 육각형 마커(■ 대신 실제 모양)
        const hr = 6, hp = document.createElementNS(NS, 'polygon');
        hp.setAttribute('points', hexPts(x0 + hr, y - 3.5, hr));
        hp.setAttribute('class', 'sido-prop-legend-hex');
        svg.appendChild(hp); tx = x0 + 2 * hr + 5;
      }
      const leg = document.createElementNS(NS, 'text'); leg.setAttribute('x', tx.toFixed(1)); leg.setAttribute('y', y.toFixed(1)); leg.setAttribute('class', 'sido-prop-legend'); leg.textContent = text; svg.appendChild(leg);
    }
    const pie = (cx, cy, r, a0, a1) => { const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0), x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1); const lg = (a1 - a0) > Math.PI ? 1 : 0; return `M${cx.toFixed(1)},${cy.toFixed(1)} L${x0.toFixed(1)},${y0.toFixed(1)} A${r.toFixed(1)},${r.toFixed(1)} 0 ${lg} 1 ${x1.toFixed(1)},${y1.toFixed(1)} Z`; };

    function drawHex(host, input, opts) {
      opts = opts || {}; const mode = opts.mode || 'seats';
      const L = layout(input, mode); if (!host || !L) { if (host) host.innerHTML = ''; return { totalSeats: 0, partyTotal: new Map() }; }
      const svg = newSvg(L.viewBox);
      for (const n of L.nodes) {
        const g = document.createElementNS(NS, 'g');
        if (opts.onSelect) { g.style.cursor = 'pointer'; g.addEventListener('click', () => opts.onSelect(n.sido)); }
        let outline;
        if (L.fixed) {   // 고정 그리드: 맞물리는 육각 셀(빈칸 없이 벌집처럼)
          outline = document.createElementNS(NS, 'polygon');
          outline.setAttribute('points', hexPts(n.cx, n.cy, n.r));
        } else {
          outline = document.createElementNS(NS, 'circle');
          outline.setAttribute('cx', n.cx.toFixed(1)); outline.setAttribute('cy', n.cy.toFixed(1)); outline.setAttribute('r', n.r.toFixed(1));
        }
        outline.setAttribute('class', 'ar-genhex-outline');
        const missCol = opts.missOf && opts.missOf(n.sido);   // 여론조사 빗나감 → 조사 1위 정당색 점선 테두리
        if (missCol) { outline.setAttribute('stroke', missCol); outline.setAttribute('stroke-width', '2.4'); outline.setAttribute('stroke-dasharray', '3,2.4'); outline.setAttribute('fill', 'none'); }
        g.appendChild(outline);
        const tt = document.createElementNS(NS, 'title'); tt.textContent = tipOf(n, mode) + (missCol ? ' · 여론조사 빗나감(테두리=조사 1위 정당)' : ''); g.appendChild(tt);
        const alloc = allocate(n.slices, n.N);
        const fills = [];
        for (let i = 0; i < n.slices.length; i++) for (let k = 0; k < alloc[i]; k++) fills.push(n.slices[i].color);
        while (fills.length < n.N) fills.push('#e6e9ef');
        const sp = spiral(n.N);
        const sr = n.smallR || L.smallR;   // 고정 그리드(seats)는 셀별 소헥스 크기로 균등 셀을 채움
        // flat-top 배치 — 덩어리가 뾰족top 셀에 정렬되도록(dx=1.5q, dy=√3(ar+q/2)).
        // 방향 채움(밴드) — 셀을 x(컬럼)→y로 정렬해 정당이 연속 세로띠가 되게(동심 스파이럴 '과녁' 대신
        //   호각=좌우분할·압도=한 색+얇은 띠로 한 배치에서 읽힘). fills는 등수 순(1등 먼저)이라 1등이 왼쪽.
        const spos = sp.map(([q, ar]) => ({ x: sr * 1.5 * q, y: sr * Math.sqrt(3) * (ar + q / 2) }));
        const sord = spos.map((_, i) => i).sort((a, b) => spos[a].x - spos[b].x || spos[a].y - spos[b].y);
        const cfill = new Array(n.N);
        for (let k = 0; k < sord.length; k++) cfill[sord[k]] = fills[k];
        for (let i = 0; i < sp.length; i++) {
          const sx = n.cx + spos[i].x, sy = n.cy + spos[i].y;
          const poly = document.createElementNS(NS, 'polygon');
          poly.setAttribute('points', hexPtsFlat(sx, sy, sr * 0.9));
          poly.setAttribute('fill', cfill[i] || '#e6e9ef');
          poly.setAttribute('stroke', 'rgba(255,255,255,0.5)'); poly.setAttribute('stroke-width', '0.3');
          g.appendChild(poly);
        }
        svg.appendChild(g);
      }
      for (const n of L.nodes) {  // 라벨 별도 패스 — 이웃에 안 가림(위, halo, outline과 살짝 겹침)
        const t = document.createElementNS(NS, 'text');
        t.setAttribute('x', n.cx.toFixed(1)); t.setAttribute('y', (n.cy - n.r + 3).toFixed(1));
        t.setAttribute('text-anchor', 'middle'); t.setAttribute('class', 'ar-genhex-label');
        t.textContent = mode === 'seats' ? `${nameOf(n)} ${n.sizeTotal}` : nameOf(n);
        svg.appendChild(t);
      }
      if (mode === 'proportional') addLegend(svg, L, opts.legend || `1개 = ${(L.unit / 10000).toLocaleString()}만표`, 'hex');
      const keep = window.SvgViewport ? window.SvgViewport.captureHost(host) : null;
      host.innerHTML = ''; host.appendChild(svg);
      if (window.SvgViewport) window.SvgViewport.applyHost(host, svg, { cells: L.nodes.map((n) => ({ region: n.sido, cx: n.cx, cy: n.cy })) }, keep);
      return legendOf(L.nodes);
    }

    function drawDorling(host, input, opts) {
      opts = opts || {}; const mode = opts.mode || 'seats';
      const L = layout(input, mode); if (!host || !L) { if (host) host.innerHTML = ''; return { totalSeats: 0, partyTotal: new Map() }; }
      const svg = newSvg(L.viewBox);
      for (const n of L.nodes) {
        const g = document.createElementNS(NS, 'g');
        if (opts.onSelect) { g.style.cursor = 'pointer'; g.addEventListener('click', () => opts.onSelect(n.sido)); }
        const missCol = opts.missOf && opts.missOf(n.sido);   // 여론조사 빗나감 → 조사 1위 정당색 점선 링
        const tt = document.createElementNS(NS, 'title'); tt.textContent = tipOf(n, mode) + (missCol ? ' · 여론조사 빗나감(테두리=조사 1위 정당)' : ''); g.appendChild(tt);
        const dr = L.fixed ? n.rSize : n.r;   // 고정 그리드(seats)는 의석∝반지름(셀 안), 아니면 cartogram 반지름
        const total = n.slices.reduce((s, x) => s + x.value, 0);
        if (total > 0 && n.slices.length > 1) {
          let a0 = -Math.PI / 2;
          for (const s of n.slices) { const a1 = a0 + (s.value / total) * 2 * Math.PI; const p = document.createElementNS(NS, 'path'); p.setAttribute('d', pie(n.cx, n.cy, dr, a0, a1)); p.setAttribute('fill', s.color); g.appendChild(p); a0 = a1; }
        } else {
          const c = document.createElementNS(NS, 'circle');
          c.setAttribute('cx', n.cx.toFixed(1)); c.setAttribute('cy', n.cy.toFixed(1)); c.setAttribute('r', dr.toFixed(1));
          c.setAttribute('fill', n.slices[0] ? n.slices[0].color : '#e6e9ef'); g.appendChild(c);
        }
        const rng = document.createElementNS(NS, 'circle');
        rng.setAttribute('cx', n.cx.toFixed(1)); rng.setAttribute('cy', n.cy.toFixed(1));
        rng.setAttribute('r', (dr + (missCol ? 1.5 : 0)).toFixed(1));
        rng.setAttribute('class', 'ar-dorling-ring');
        if (missCol) { rng.setAttribute('stroke', missCol); rng.setAttribute('stroke-width', '2.4'); rng.setAttribute('stroke-dasharray', '3,2.4'); rng.setAttribute('fill', 'none'); }
        g.appendChild(rng);
        svg.appendChild(g);
      }
      for (const n of L.nodes) {  // 라벨 별도 패스 — 큰 원 중앙(흰), 작은 원 바깥 위(검정 halo)
        const dr = L.fixed ? n.rSize : n.r;
        const small = dr < 11;
        const t = document.createElementNS(NS, 'text');
        t.setAttribute('x', n.cx.toFixed(1)); t.setAttribute('y', (small ? n.cy - dr - 3 : n.cy + 3).toFixed(1));
        t.setAttribute('text-anchor', 'middle'); t.setAttribute('class', small ? 'ar-genhex-label' : 'ar-dorling-label');
        t.textContent = nameOf(n); svg.appendChild(t);
      }
      if (mode === 'proportional') addLegend(svg, L, opts.legend || '● 크기=득표 · 파이=후보 득표 구성');
      const keep = window.SvgViewport ? window.SvgViewport.captureHost(host) : null;
      host.innerHTML = ''; host.appendChild(svg);
      if (window.SvgViewport) window.SvgViewport.applyHost(host, svg, { cells: L.nodes.map((n) => ({ region: n.sido, cx: n.cx, cy: n.cy })) }, keep);
      return legendOf(L.nodes);
    }

    return { layout, drawHex, drawDorling, spiral, clusterR };
  })();
})();
