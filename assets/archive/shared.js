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

  // 시도별 dorling — 권역 seed에서 크기(√합계) 원 packing + 정당 파이. 대선·총선·지선 공용.
  //   host: 그릴 element / bySido: {시도:{정당:수}} / opts: {rmax, seedGap}
  Archive.drawSidoDorling = function (host, bySido, opts) {
    if (!host || typeof SIDO_HEX_LAYOUT !== 'object') return false;
    opts = opts || {};
    const NS = 'http://www.w3.org/2000/svg';
    const Rmax = opts.rmax || 40, seedGap = opts.seedGap || 80;
    const pcol = Archive.pcol, ssh = Archive.ssh;
    let maxTot = 1; const ent0 = [];
    for (const [sido, pos] of Object.entries(SIDO_HEX_LAYOUT)) {
      const seats = bySido[sido]; if (!seats) continue;
      const tot = Object.values(seats).reduce((s, n) => s + n, 0);
      if (!tot) continue;
      maxTot = Math.max(maxTot, tot); ent0.push({ sido, seats, tot, pos });
    }
    if (!ent0.length) return false;
    const nodes = ent0.map((e) => ({
      sido: e.sido, seats: e.seats, tot: e.tot,
      r: Math.max(7, Rmax * Math.sqrt(e.tot / maxTot)),
      cx0: e.pos.col * seedGap + (e.pos.row % 2 ? seedGap / 2 : 0),
      cy0: e.pos.row * seedGap * 0.87,
    }));
    Archive.packClusters(nodes, { pad: 3 });
    const minX = Math.min(...nodes.map((n) => n.cx - n.r)) - 6;
    const minY = Math.min(...nodes.map((n) => n.cy - n.r)) - 6;
    const W = Math.max(...nodes.map((n) => n.cx + n.r)) - minX + 6;
    const H = Math.max(...nodes.map((n) => n.cy + n.r)) - minY + 6;
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('xmlns', NS);
    svg.setAttribute('viewBox', `${minX.toFixed(1)} ${minY.toFixed(1)} ${W.toFixed(1)} ${H.toFixed(1)}`);
    svg.setAttribute('class', 'ar-dorling-svg');
    const pie = (cx, cy, r, a0, a1) => {
      const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0);
      const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
      const lg = (a1 - a0) > Math.PI ? 1 : 0;
      return `M${cx.toFixed(1)},${cy.toFixed(1)} L${x0.toFixed(1)},${y0.toFixed(1)} A${r.toFixed(1)},${r.toFixed(1)} 0 ${lg} 1 ${x1.toFixed(1)},${y1.toFixed(1)} Z`;
    };
    for (const n of nodes) {
      const e = Object.entries(n.seats).sort((a, b) => b[1] - a[1]);
      const g = document.createElementNS(NS, 'g');
      const tt = document.createElementNS(NS, 'title');
      tt.textContent = `${n.sido} ${n.tot}석 · ${e.map(([p, c]) => `${p} ${c}`).join(', ')}`;
      g.appendChild(tt);
      if (e.length > 1) {
        let a0 = -Math.PI / 2;
        for (const [p, c] of e) {
          const a1 = a0 + (c / n.tot) * 2 * Math.PI;
          const path = document.createElementNS(NS, 'path');
          path.setAttribute('d', pie(n.cx, n.cy, n.r, a0, a1));
          path.setAttribute('fill', pcol(p));
          g.appendChild(path); a0 = a1;
        }
      } else {
        const c = document.createElementNS(NS, 'circle');
        c.setAttribute('cx', n.cx.toFixed(1)); c.setAttribute('cy', n.cy.toFixed(1)); c.setAttribute('r', n.r.toFixed(1));
        c.setAttribute('fill', e[0] ? pcol(e[0][0]) : '#e6e9ef');
        g.appendChild(c);
      }
      const ring = document.createElementNS(NS, 'circle');
      ring.setAttribute('cx', n.cx.toFixed(1)); ring.setAttribute('cy', n.cy.toFixed(1)); ring.setAttribute('r', n.r.toFixed(1));
      ring.setAttribute('class', 'ar-dorling-ring');
      g.appendChild(ring);
      if (n.r >= 11) {
        const t = document.createElementNS(NS, 'text');
        t.setAttribute('x', n.cx.toFixed(1)); t.setAttribute('y', (n.cy + 3).toFixed(1));
        t.setAttribute('text-anchor', 'middle'); t.setAttribute('class', 'ar-dorling-label');
        t.textContent = ssh(n.sido);
        g.appendChild(t);
      }
      svg.appendChild(g);
    }
    host.innerHTML = ''; host.appendChild(svg);
    return true;
  };
})();
