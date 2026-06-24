// 여론조사 성·연령 추이 — /polls/{대선}/. 선택 성연령 셀의 후보지지 시계열(라인) + 출구조사 ◆ 끝점.
//   레이어 ①(사전 조사) ↔ ②(당일 출구조사) 연결. 데이터: poll_demographics_<n>pres.json.
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const AGES = ['18-29', '30', '40', '50', '60', '70+'];
  const AGE_LABEL = { '18-29': '18·20대', '30': '30대', '40': '40대', '50': '50대', '60': '60대', '70+': '70대+' };
  const SEXES = ['남성', '여성'];
  const pcol = (p) => (typeof partyColor === 'function' ? partyColor(p) : '#888');
  const lc = (h) => (typeof legibleColor === 'function' ? legibleColor(h) : h);

  let DATA = null, dim = '성연령', sel = '남성|18-29';
  const DIMS = [['성연령', '성×연령'], ['성별', '성별'], ['연령', '연령'], ['성별격차', '성별 격차']];
  const AGE_GAP_C = { '18-29': '#43c6ac', '30': '#1d9bc9', '40': '#2c6fb8', '50': '#3b4fa0', '60': '#6a3d9a', '70+': '#9b2f86' };

  // 차원별 셀 키 목록 + 기본 선택.
  function dimCells(d) {
    if (d === '성별') return SEXES.map((s) => ['성별|' + s, s]);
    if (d === '연령') return AGES.map((a) => ['연령|' + a, AGE_LABEL[a]]);
    return null;   // 성연령은 grid(아래 별도)
  }
  const hasCell = (k) => (DATA && (DATA.cells[k] || []).length > 0);
  // 차원에 데이터가 있나 — 옛 회차(2017 등)는 성×연령 그리드 미공표라 비어있을 수 있음.
  function dimAvail(d) {
    if (d === '성별') return SEXES.some((s) => hasCell('성별|' + s));
    if (d === '연령') return AGES.some((a) => hasCell('연령|' + a));
    // 성별격차는 성×연령 grid 필요(남·여 둘 다 있는 연령대 ≥1)
    if (d === '성별격차') return AGES.some((a) => hasCell('남성|' + a) && hasCell('여성|' + a));
    return SEXES.some((s) => AGES.some((a) => hasCell(s + '|' + a)));
  }
  // 민주(더불어민주당) 후보명 — 남녀 격차 기준(이재명 등).
  function focalDemName() {
    for (const key of Object.keys(DATA.cells)) {
      for (const p of DATA.cells[key]) for (const c of p.c) if (c.party === '더불어민주당') return c.name;
    }
    for (const key of Object.keys(DATA.exit || {})) for (const c of DATA.exit[key]) if (c.party === '더불어민주당') return c.name;
    return null;
  }
  // 데이터 있는 첫 셀(없으면 관례 기본값).
  function defaultSel(d) {
    if (d === '성별') return '성별|' + (SEXES.find((s) => hasCell('성별|' + s)) || '남성');
    if (d === '연령') return '연령|' + (AGES.find((a) => hasCell('연령|' + a)) || '18-29');
    for (const s of SEXES) for (const a of AGES) if (hasCell(s + '|' + a)) return s + '|' + a;
    return '남성|18-29';
  }

  const ts = (d) => Date.parse(d + 'T00:00:00+09:00');
  function selLabel() {
    const [a, b] = sel.split('|');
    if (a === '성별') return b;                       // 성별|남성 → 남성
    if (a === '연령') return AGE_LABEL[b] || b;        // 연령|30 → 30대
    return `${a} ${AGE_LABEL[b] || b}`;               // 남성|18-29 → 남성 18·20대
  }

  function focalCands() {
    // 출구조사에 있는 최종 후보(이재명·김문수·이준석)에 집중 — 초기 다자대결 잡음 제외.
    const ex = DATA.exit[sel] || [];
    if (ex.length) return ex.map((c) => ({ name: c.name, party: c.party }));
    // exit 없으면 마지막 폴 후보
    const series = DATA.cells[sel] || [];
    const last = series[series.length - 1];
    return last ? last.c.map((c) => ({ name: c.name, party: c.party })) : [];
  }

  function trendSVG() {
    const series = DATA.cells[sel] || [];
    const exit = DATA.exit[sel] || [];
    const cands = focalCands();
    if (!series.length) return '<p class="detail-empty">이 집단의 추이 데이터가 없습니다.</p>';
    const W = 580, H = 250, PL = 30, PR = 54, PT = 14, PB = 26;
    const elDate = (typeof POLL_ELECTION === 'object' && POLL_ELECTION.date) || series[series.length - 1].date;
    const t0 = ts(series[0].date), t1 = ts(elDate);
    const pctOf = (row, name) => { const f = (row || []).find((c) => c.name === name); return f ? f.pct : null; };
    const allv = [];
    for (const p of series) for (const c of cands) { const v = pctOf(p.c, c.name); if (v != null) allv.push(v); }
    for (const c of cands) { const v = pctOf(exit, c.name); if (v != null) allv.push(v); }
    const yMax = Math.max(50, Math.ceil(Math.max(...allv, 10) / 10) * 10);
    const X = (d) => PL + (ts(d) - t0) / (t1 - t0 || 1) * (W - PL - PR);
    const Y = (v) => PT + (1 - v / yMax) * (H - PT - PB);
    // 격자
    let grid = '';
    for (let g = 0; g <= yMax; g += 10) grid += `<line x1="${PL}" y1="${Y(g).toFixed(1)}" x2="${W - PR}" y2="${Y(g).toFixed(1)}" stroke="var(--rule)" stroke-width="1"/><text x="${PL - 5}" y="${(Y(g) + 3).toFixed(1)}" font-size="9" fill="var(--ink-mute)" text-anchor="end">${g}</text>`;
    // 라인 + 출구조사 ◆
    let lines = '';
    for (const c of cands) {
      const col = lc(pcol(c.party));
      const pts = series.map((p) => { const v = pctOf(p.c, c.name); return v == null ? null : `${X(p.date).toFixed(1)},${Y(v).toFixed(1)}`; }).filter(Boolean);
      if (pts.length >= 2) lines += `<polyline points="${pts.join(' ')}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round" opacity="0.9"/>`;
      for (const p of series) { const v = pctOf(p.c, c.name); if (v != null) lines += `<circle cx="${X(p.date).toFixed(1)}" cy="${Y(v).toFixed(1)}" r="2" fill="${col}"/>`; }
      const ev = pctOf(exit, c.name);
      if (ev != null) {
        const x = X(elDate), y = Y(ev);
        lines += `<path d="M${x} ${y - 5}L${x + 5} ${y}L${x} ${y + 5}L${x - 5} ${y}Z" fill="${col}" stroke="var(--bg)" stroke-width="1"><title>${c.name} 출구조사 ${ev}%</title></path>`;
        lines += `<text x="${x + 8}" y="${(y + 3).toFixed(1)}" font-size="10" font-weight="700" fill="${col}">${c.name} ${ev}</text>`;
      }
    }
    // x축 라벨(첫·끝·선거일)
    const xlab = `<text x="${PL}" y="${H - 8}" font-size="9" fill="var(--ink-mute)">${series[0].date.slice(2)}</text>`
      + `<text x="${W - PR}" y="${H - 8}" font-size="9" fill="var(--ink-mute)" text-anchor="end">선거일 ◆출구</text>`;
    return `<svg viewBox="0 0 ${W} ${H}" class="pd-trend" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${selLabel()} 후보지지 추이">${grid}${lines}${xlab}</svg>`;
  }

  // 성별 격차 추이 — 연령대별 (남−여) 이재명 득표율, 0기준. 캠페인 중 이대남 격차 형성.
  function gapSVG() {
    const dem = focalDemName();
    if (!dem) return '<p class="detail-empty">민주 후보 데이터가 없습니다.</p>';
    const series = {}; const exitGap = {};
    let t0 = Infinity, yM = 6;
    for (const a of AGES) {
      const M = {}, F = {};
      for (const p of (DATA.cells['남성|' + a] || [])) { const c = p.c.find((x) => x.name === dem); if (c) M[p.date] = c.pct; }
      for (const p of (DATA.cells['여성|' + a] || [])) { const c = p.c.find((x) => x.name === dem); if (c) F[p.date] = c.pct; }
      const pts = [];
      for (const dt in M) if (dt in F) pts.push({ t: ts(dt), v: M[dt] - F[dt] });
      if (pts.length) { pts.sort((x, y) => x.t - y.t); series[a] = pts; for (const p of pts) { t0 = Math.min(t0, p.t); yM = Math.max(yM, Math.abs(p.v)); } }
      const em = (DATA.exit['남성|' + a] || []).find((x) => x.name === dem);
      const ef = (DATA.exit['여성|' + a] || []).find((x) => x.name === dem);
      if (em && ef) { exitGap[a] = em.pct - ef.pct; yM = Math.max(yM, Math.abs(exitGap[a])); }
    }
    const ages = Object.keys(series);
    if (!ages.length) return '<p class="detail-empty">성×연령 격차 데이터가 없습니다.</p>';
    yM = Math.ceil(yM / 5) * 5;
    const W = 580, H = 250, PL = 30, PR = 60, PT = 16, PB = 26;
    const elDate = (typeof POLL_ELECTION === 'object' && POLL_ELECTION.date) || null;
    const t1 = elDate ? ts(elDate) : Math.max(...ages.flatMap((a) => series[a].map((p) => p.t)));
    const X = (t) => PL + (t - t0) / (t1 - t0 || 1) * (W - PL - PR);
    const Y = (v) => PT + (1 - (v + yM) / (2 * yM)) * (H - PT - PB);
    let grid = '';
    for (let g = -yM; g <= yM; g += yM / 2) {
      const zero = g === 0;
      grid += `<line x1="${PL}" y1="${Y(g).toFixed(1)}" x2="${W - PR}" y2="${Y(g).toFixed(1)}" stroke="var(--rule)" stroke-width="${zero ? 1 : 0.5}"${zero ? '' : ' stroke-dasharray="2 3"'}/>`
        + `<text x="${PL - 5}" y="${(Y(g) + 3).toFixed(1)}" font-size="9" fill="var(--ink-mute)" text-anchor="end">${g > 0 ? '+' : ''}${g}</text>`;
    }
    grid += `<text x="${PL}" y="11" font-size="9" fill="var(--ink-mute)">▲남↑</text>`
      + `<text x="${PL}" y="${H - 14}" font-size="9" fill="var(--ink-mute)">▼여↑</text>`;
    let lines = '';
    const lab = [];
    for (const a of ages) {
      const col = lc(AGE_GAP_C[a]);
      const pts = series[a].map((p) => `${X(p.t).toFixed(1)},${Y(p.v).toFixed(1)}`);
      if (pts.length >= 2) lines += `<polyline points="${pts.join(' ')}" fill="none" stroke="${col}" stroke-width="1.8" opacity="0.9"/>`;
      for (const p of series[a]) lines += `<circle cx="${X(p.t).toFixed(1)}" cy="${Y(p.v).toFixed(1)}" r="1.5" fill="${col}"/>`;
      let endV = series[a][series[a].length - 1].v, endX = X(series[a][series[a].length - 1].t);
      if (a in exitGap && elDate) {
        const x = X(t1), y = Y(exitGap[a]);
        lines += `<path d="M${x} ${y - 4}L${x + 4} ${y}L${x} ${y + 4}L${x - 4} ${y}Z" fill="${col}" stroke="var(--bg)" stroke-width="1"><title>${AGE_LABEL[a]} 출구조사 격차 ${exitGap[a].toFixed(1)}</title></path>`;
        endV = exitGap[a]; endX = x;
      }
      lab.push({ a, x: endX, y: Y(endV), col });
    }
    lab.sort((p, q) => p.y - q.y); let ly = -99;
    let labels = '';
    for (const L of lab) { let yy = L.y + 3; if (yy - ly < 12) yy = ly + 12; ly = yy; labels += `<text x="${(W - PR + 4).toFixed(1)}" y="${yy.toFixed(1)}" font-size="9.5" font-weight="700" fill="${L.col}">${AGE_LABEL[L.a]}</text>`; }
    return `<svg viewBox="0 0 ${W} ${H}" class="pd-trend" preserveAspectRatio="xMidYMid meet" role="img" aria-label="성별 격차 추이">${grid}${lines}${labels}</svg>`;
  }

  function draw(sec) {
    sec.querySelector('.pd-chart').innerHTML = dim === '성별격차' ? gapSVG() : trendSVG();
    sec.querySelectorAll('[data-pdcell]').forEach((b) => b.classList.toggle('is-active', b.dataset.pdcell === sel));
  }

  async function render() {
    const n = (typeof POLL_ELECTION === 'object' && POLL_ELECTION.n);
    if (!n || document.getElementById('pd-section')) return;
    let d;
    try { d = await fetch(`data/polls/poll_demographics_${n}pres.json`).then((r) => (r.ok ? r.json() : null)); }
    catch (e) { d = null; }
    if (!d || !d.cells || !Object.values(d.cells).some((v) => v.length)) return;
    DATA = d;
    const dims = DIMS.filter(([k]) => dimAvail(k));   // 데이터 있는 차원만(옛 회차 성연령 누락 대응)
    if (!dims.length) return;
    dim = dims[0][0]; sel = defaultSel(dim);           // 성연령 비면 성별/연령으로 폴백
    const sec = document.createElement('section');
    sec.id = 'pd-section'; sec.className = 'pd-section';
    const dimBtns = dims.map(([k, lbl]) => `<button class="seg-btn${k === dim ? ' is-active' : ''}" data-pddim="${k}">${lbl}</button>`).join('');
    const hasExit = d.exit && Object.keys(d.exit).length > 0;
    const hasGrid = dims.some(([k]) => k === '성연령');
    sec.innerHTML = '<h3 class="pres-trend-title">여론조사 성·연령 추이 '
      + '<span class="info-i" tabindex="0" role="button" aria-label="설명">i<span class="info-pop">'
      + `후보지지를 ${hasGrid ? '성별·연령·성×연령' : '성별·연령'}으로 본 시계열(다자대결 잡음 줄이려 최종 후보만). `
      + (hasExit ? '끝의 ◆ = 방송3사 출구조사. ' : '')
      + `성별·연령은 다기관(${(d._meta.agencies || []).length}곳)`
      + (hasGrid ? ', 성×연령 그리드는 공표 기관이 적음' : '') + '.</span></span></h3>'
      + `<div class="pd-dim seg" role="tablist">${dimBtns}</div>`
      + '<div class="pd-cells"></div><div class="pd-chart"></div>';
    const anchor = document.getElementById('pres-trend') || document.querySelector('.controls');
    (anchor && anchor.parentElement ? anchor.parentElement : document.body).insertBefore(sec, anchor ? anchor.nextSibling : null);
    sec.querySelectorAll('[data-pddim]').forEach((b) => b.addEventListener('click', () => {
      dim = b.dataset.pddim; sel = defaultSel(dim);
      sec.querySelectorAll('[data-pddim]').forEach((x) => x.classList.toggle('is-active', x.dataset.pddim === dim));
      renderCells(sec); draw(sec);
    }));
    renderCells(sec);
    draw(sec);
  }

  function renderCells(sec) {
    const host = sec.querySelector('.pd-cells');
    if (dim === '성별격차') {
      const dem = focalDemName() || '민주 후보';
      host.innerHTML = `<p class="pd-gap-note">연령대별 <b>${dem}</b> 득표율의 남−여 격차(%p). 선이 0 위면 남성, 아래면 여성이 더 지지. ◆=출구조사. 캠페인 동안 이대남·이대녀 격차가 어떻게 벌어지는지.</p>`;
      return;
    }
    if (dim === '성연령') {
      host.innerHTML = SEXES.map((s) =>
        `<div class="pd-sexrow"><span class="pd-sexlab">${s}</span>`
        + AGES.map((a) => `<button class="pd-cell${(s + '|' + a) === sel ? ' is-active' : ''}" data-pdcell="${s}|${a}">${AGE_LABEL[a]}</button>`).join('')
        + '</div>').join('');
    } else {
      host.innerHTML = '<div class="pd-sexrow">'
        + dimCells(dim).map(([k, lbl]) => `<button class="pd-cell${k === sel ? ' is-active' : ''}" data-pdcell="${k}">${lbl}</button>`).join('')
        + '</div>';
    }
    host.querySelectorAll('[data-pdcell]').forEach((b) => b.addEventListener('click', () => { sel = b.dataset.pdcell; draw(sec); }));
  }

  window.renderPollDemographics = render;
})();
