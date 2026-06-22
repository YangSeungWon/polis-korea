// 여론조사 성·연령 추이 — /polls/{대선}/. 선택 성연령 셀의 후보지지 시계열(라인) + 출구조사 ◆ 끝점.
//   레이어 ①(사전 조사) ↔ ②(당일 출구조사) 연결. 데이터: poll_demographics_<n>pres.json.
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const AGES = ['18-29', '30', '40', '50', '60', '70+'];
  const AGE_LABEL = { '18-29': '18·20대', '30': '30대', '40': '40대', '50': '50대', '60': '60대', '70+': '70대+' };
  const SEXES = ['남성', '여성'];
  const pcol = (p) => (typeof partyColor === 'function' ? partyColor(p) : '#888');
  const lc = (h) => (typeof legibleColor === 'function' ? legibleColor(h) : h);

  let DATA = null, sel = '남성|18-29';

  const ts = (d) => Date.parse(d + 'T00:00:00+09:00');

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
    return `<svg viewBox="0 0 ${W} ${H}" class="pd-trend" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${AGE_LABEL[sel.split('|')[1]]} ${sel.split('|')[0]} 후보지지 추이">${grid}${lines}${xlab}</svg>`;
  }

  function draw(sec) {
    sec.querySelector('.pd-chart').innerHTML = trendSVG();
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
    const sec = document.createElement('section');
    sec.id = 'pd-section'; sec.className = 'pd-section';
    const cellBtns = SEXES.map((s) =>
      `<div class="pd-sexrow"><span class="pd-sexlab">${s}</span>`
      + AGES.map((a) => `<button class="pd-cell${(s + '|' + a) === sel ? ' is-active' : ''}" data-pdcell="${s}|${a}">${AGE_LABEL[a]}</button>`).join('')
      + '</div>').join('');
    sec.innerHTML = '<h3 class="pres-trend-title">여론조사 성·연령 추이 '
      + '<span class="info-i" tabindex="0" role="button" aria-label="설명">i<span class="info-pop">'
      + '성×연령 그리드를 공표한 조사의 후보지지 시계열(다자대결 잡음 줄이려 최종 3인만). '
      + `끝의 ◆ = 방송3사 출구조사. 출처: ${(d._meta.agencies || []).join('·')}.</span></span></h3>`
      + `<div class="pd-cells">${cellBtns}</div><div class="pd-chart"></div>`;
    const anchor = document.getElementById('pres-trend') || document.querySelector('.controls');
    (anchor && anchor.parentElement ? anchor.parentElement : document.body).insertBefore(sec, anchor ? anchor.nextSibling : null);
    sec.querySelectorAll('[data-pdcell]').forEach((b) => b.addEventListener('click', () => { sel = b.dataset.pdcell; draw(sec); }));
    draw(sec);
  }

  window.renderPollDemographics = render;
})();
