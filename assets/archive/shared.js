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

  // ── 시도 클러스터 (의석 기반 헥스/dorling 공용) ────────────────────────────────
  // layout()이 위치·viewBox를 한 번 계산 → drawHex/drawDorling이 공유 → 토글해도 권역 위치 고정.
  // bySido = {시도:{정당:석수}}. 헥스=연속 스파이럴(1 hex=1석), dorling=원+파이. 둘 다 r=clusterR(석수).
  Archive.sidoCluster = (function () {
    const NS = 'http://www.w3.org/2000/svg';
    const SMALL_R = 6, SEED_GAP = 85, PAD = 4;
    const clusterR = (N) => { const L = Math.ceil(Math.sqrt(Math.max(N - 1, 0) / 3)); return Math.max(9, (L + 0.6) * Math.sqrt(3) * SMALL_R); };
    const NB = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]];
    const ring = (L) => { const out = []; let q = -L, r = L; for (let s = 0; s < 6; s++) { const [dq, dr] = NB[s]; for (let i = 0; i < L; i++) { out.push([q, r]); q += dq; r += dr; } } return out; };
    // 연속 스파이럴 — 중심 + 꽉 찬 링 + 마지막 부분 링은 연속(slice). 듬성듬성 분산 안 함.
    const spiral = (N) => { if (N <= 0) return []; const out = [[0, 0]]; let L = 0; while (out.length < N) { L++; const rg = ring(L); const rem = N - out.length; out.push(...(rem >= rg.length ? rg : rg.slice(0, rem))); } return out; };
    const hexPts = (cx, cy, R) => { const p = []; for (let i = 0; i < 6; i++) { const a = Math.PI / 6 + i * Math.PI / 3; p.push(`${cx + R * Math.cos(a)},${cy + R * Math.sin(a)}`); } return p.join(' '); };

    // 전남광주 통합(2026 지선) → 광주+전남+통합 한 셀 + honamMergedLayout. 그 외 분리 유지.
    function mergeHonam(bySido) {
      if (!((bySido['전남광주특별시'] || bySido['전남광주통합특별시']) && typeof honamMergedLayout === 'function')) {
        return { data: bySido, layout: SIDO_HEX_LAYOUT };
      }
      const merged = {};
      for (const src of ['광주광역시', '전라남도', '전남광주특별시', '전남광주통합특별시']) {
        const s = bySido[src]; if (!s) continue;
        for (const [p, c] of Object.entries(s)) merged[p] = (merged[p] || 0) + c;
      }
      const data = Object.assign({}, bySido);
      delete data['광주광역시']; delete data['전라남도']; delete data['전남광주통합특별시'];
      data['전남광주특별시'] = merged;
      return { data, layout: honamMergedLayout(SIDO_HEX_LAYOUT) };
    }

    // 공유 레이아웃 — 위치(packClusters)·viewBox를 한 번 계산. 헥스·dorling이 동일 호출 → 위치 고정.
    function layout(bySido) {
      if (typeof SIDO_HEX_LAYOUT !== 'object') return null;
      const { data, layout: lay } = mergeHonam(bySido);
      const nodes = [];
      for (const [sido, pos] of Object.entries(lay)) {
        const seats = data[sido]; if (!seats) continue;
        const tot = Object.values(seats).reduce((s, n) => s + n, 0);
        if (!tot) continue;
        nodes.push({
          sido, seats, tot, label: pos.label, r: clusterR(tot),
          cx0: pos.col * SEED_GAP + (pos.row % 2 ? SEED_GAP / 2 : 0), cy0: pos.row * SEED_GAP * 0.87,
        });
      }
      if (!nodes.length) return null;
      Archive.packClusters(nodes, { pad: PAD });
      const minX = Math.min(...nodes.map((n) => n.cx - n.r)) - 6;
      const minY = Math.min(...nodes.map((n) => n.cy - n.r)) - 16;
      const W = Math.max(...nodes.map((n) => n.cx + n.r)) - minX + 6;
      const H = Math.max(...nodes.map((n) => n.cy + n.r)) - minY + 6;
      return { nodes, viewBox: `${minX.toFixed(1)} ${minY.toFixed(1)} ${W.toFixed(1)} ${H.toFixed(1)}` };
    }

    function legendOf(nodes) {
      const partyTotal = new Map(); let totalSeats = 0;
      for (const n of nodes) for (const [p, c] of Object.entries(n.seats)) { partyTotal.set(p, (partyTotal.get(p) || 0) + c); totalSeats += c; }
      return { totalSeats, partyTotal };
    }

    function newSvg(viewBox) {
      const svg = document.createElementNS(NS, 'svg');
      svg.setAttribute('xmlns', NS); svg.setAttribute('viewBox', viewBox); svg.setAttribute('class', 'ar-sidocluster-svg');
      return svg;
    }

    // 헥스 — 1 hex = 1석, 정당 의석 desc로 중심부터 연속 채움(큰 당이 안쪽). opts.onSelect(sido) 클릭.
    function drawHex(host, bySido, opts) {
      opts = opts || {};
      const L = layout(bySido); if (!host || !L) { host && (host.innerHTML = ''); return { totalSeats: 0, partyTotal: new Map() }; }
      const svg = newSvg(L.viewBox);
      for (const n of L.nodes) {
        const entries = Object.entries(n.seats).sort((a, b) => b[1] - a[1]);
        const g = document.createElementNS(NS, 'g');
        if (opts.onSelect) { g.style.cursor = 'pointer'; g.addEventListener('click', () => opts.onSelect(n.sido)); }
        const outline = document.createElementNS(NS, 'circle');
        outline.setAttribute('cx', n.cx.toFixed(1)); outline.setAttribute('cy', n.cy.toFixed(1)); outline.setAttribute('r', n.r.toFixed(1));
        outline.setAttribute('class', 'ar-genhex-outline'); g.appendChild(outline);
        const tt = document.createElementNS(NS, 'title');
        tt.textContent = `${n.sido} ${n.tot}석 · ${entries.map(([p, c]) => `${p} ${c}`).join(', ')}`; g.appendChild(tt);
        const fills = [];
        for (const [p, c] of entries) for (let k = 0; k < c; k++) fills.push(Archive.pcol(p));
        const sp = spiral(n.tot);
        for (let i = 0; i < sp.length; i++) {
          const [q, ar] = sp[i];
          const sx = n.cx + SMALL_R * Math.sqrt(3) * (q + ar / 2), sy = n.cy + SMALL_R * 1.5 * ar;
          const poly = document.createElementNS(NS, 'polygon');
          poly.setAttribute('points', hexPts(sx, sy, SMALL_R * 0.92));
          poly.setAttribute('fill', fills[i] || '#e6e9ef');
          poly.setAttribute('stroke', 'rgba(255,255,255,0.5)'); poly.setAttribute('stroke-width', '0.3');
          g.appendChild(poly);
        }
        svg.appendChild(g);
      }
      // 라벨은 모든 클러스터 뒤에 별도 패스 — 이웃 클러스터에 가리지 않게(항상 위, halo 가독).
      for (const n of L.nodes) {
        const t = document.createElementNS(NS, 'text');
        t.setAttribute('x', n.cx.toFixed(1)); t.setAttribute('y', (n.cy - n.r + 3).toFixed(1));  // outline 동그라미와 살짝 겹치게
        t.setAttribute('text-anchor', 'middle'); t.setAttribute('class', 'ar-genhex-label');
        t.textContent = `${n.label || Archive.ssh(n.sido)} ${n.tot}`;
        svg.appendChild(t);
      }
      host.innerHTML = ''; host.appendChild(svg);
      return legendOf(L.nodes);
    }

    const pie = (cx, cy, r, a0, a1) => {
      const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0), x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
      const lg = (a1 - a0) > Math.PI ? 1 : 0;
      return `M${cx.toFixed(1)},${cy.toFixed(1)} L${x0.toFixed(1)},${y0.toFixed(1)} A${r.toFixed(1)},${r.toFixed(1)} 0 ${lg} 1 ${x1.toFixed(1)},${y1.toFixed(1)} Z`;
    };
    // dorling — 같은 layout(위치·viewBox 동일) → 토글해도 권역 고정. 원 r=clusterR + 정당 파이.
    function drawDorling(host, bySido, opts) {
      opts = opts || {};
      const L = layout(bySido); if (!host || !L) { host && (host.innerHTML = ''); return { totalSeats: 0, partyTotal: new Map() }; }
      const svg = newSvg(L.viewBox);
      for (const n of L.nodes) {
        const e = Object.entries(n.seats).sort((a, b) => b[1] - a[1]);
        const g = document.createElementNS(NS, 'g');
        if (opts.onSelect) { g.style.cursor = 'pointer'; g.addEventListener('click', () => opts.onSelect(n.sido)); }
        const tt = document.createElementNS(NS, 'title');
        tt.textContent = `${n.sido} ${n.tot}석 · ${e.map(([p, c]) => `${p} ${c}`).join(', ')}`; g.appendChild(tt);
        if (e.length > 1) {
          let a0 = -Math.PI / 2;
          for (const [p, c] of e) { const a1 = a0 + (c / n.tot) * 2 * Math.PI; const path = document.createElementNS(NS, 'path'); path.setAttribute('d', pie(n.cx, n.cy, n.r, a0, a1)); path.setAttribute('fill', Archive.pcol(p)); g.appendChild(path); a0 = a1; }
        } else {
          const c = document.createElementNS(NS, 'circle');
          c.setAttribute('cx', n.cx.toFixed(1)); c.setAttribute('cy', n.cy.toFixed(1)); c.setAttribute('r', n.r.toFixed(1));
          c.setAttribute('fill', e[0] ? Archive.pcol(e[0][0]) : '#e6e9ef'); g.appendChild(c);
        }
        const rng = document.createElementNS(NS, 'circle');
        rng.setAttribute('cx', n.cx.toFixed(1)); rng.setAttribute('cy', n.cy.toFixed(1)); rng.setAttribute('r', n.r.toFixed(1));
        rng.setAttribute('class', 'ar-dorling-ring'); g.appendChild(rng);
        svg.appendChild(g);
      }
      // 라벨 별도 패스 — 이웃 원에 가리지 않게(항상 위). 작은 원(r<11)은 위쪽에 표시.
      for (const n of L.nodes) {
        const t = document.createElementNS(NS, 'text');
        const small = n.r < 11;
        t.setAttribute('x', n.cx.toFixed(1)); t.setAttribute('y', (small ? n.cy - n.r - 3 : n.cy + 3).toFixed(1));
        t.setAttribute('text-anchor', 'middle');
        t.setAttribute('class', small ? 'ar-genhex-label' : 'ar-dorling-label');  // 작은 원은 바깥(검정 halo) 라벨
        t.textContent = n.label || Archive.ssh(n.sido);
        svg.appendChild(t);
      }
      host.innerHTML = ''; host.appendChild(svg);
      return legendOf(L.nodes);
    }

    return { layout, drawHex, drawDorling, spiral, clusterR };
  })();

  // (구) drawSidoDorling — sidoCluster.drawDorling로 위임(하위호환).
  Archive.drawSidoDorling = function (host, bySido) { return Archive.sidoCluster.drawDorling(host, bySido); };
})();
