// tracker.js — 선거에 안 묶이는 상시 지표 연속 시계열.
//   ① 대통령 국정수행 평가(한국갤럽, approval_gallup.json) — 긍정/부정 + 임기 band.
//   ② 정당지지 연속(aggregated_*.json metric_type='정당지지' & 전국) — 주요정당 라인.
// parties.js(partyColor)·utils.js(PARTY_SHORT) 의존.
(function () {
  'use strict';

  const PRES = [
    { name: '박근혜', a: '2013-02-25', b: '2017-03-10' },
    { name: '문재인', a: '2017-05-10', b: '2022-05-09' },
    { name: '윤석열', a: '2022-05-10', b: '2025-04-04' },
    { name: '이재명', a: '2025-06-04', b: '2030-12-31' },
  ];
  const POS = '#1f7a4d', NEG = '#c0392b';
  const AGG_FILES = ['19pres', '20pres', '21pres', '20th', '21st', '22nd', '7th', '8th']
    .map((s) => `data/polls/aggregated_${s}.json`);
  const CANON = { '민주당': '더불어민주당', '국힘': '국민의힘', '국민의 힘': '국민의힘' };
  const NON_PARTY = new Set(['무소속', '없음', '기타', '무당층', '지지정당없음', '기타정당', '지지정당 없음']);
  const ms = (d) => Date.parse(d);
  const ym = (d) => d.slice(0, 7);

  // ---- 공통 축 ----
  function gridAxes(W, H, P, tMin, tMax, yMax, yStep, xOf, yOf) {
    let g = '';
    for (let v = 0; v <= yMax; v += yStep) {
      const y = yOf(v);
      g += `<line x1="${P.l}" y1="${y.toFixed(1)}" x2="${W - P.r}" y2="${y.toFixed(1)}" stroke="var(--rule,#e6e9ef)" stroke-width="0.5"/>`;
      g += `<text x="${P.l - 6}" y="${(y + 3).toFixed(1)}" font-size="10" fill="var(--ink-mute,#8a93a3)" text-anchor="end">${v}</text>`;
    }
    const y0 = new Date(tMin).getFullYear(), y1 = new Date(tMax).getFullYear();
    for (let yr = y0; yr <= y1; yr++) {
      const t = Date.parse(`${yr}-01-01`);
      if (t < tMin || t > tMax) continue;
      const x = xOf(t);
      g += `<line x1="${x.toFixed(1)}" y1="${P.t}" x2="${x.toFixed(1)}" y2="${H - P.b}" stroke="var(--rule,#e6e9ef)" stroke-width="0.4" stroke-dasharray="2 3"/>`;
      g += `<text x="${x.toFixed(1)}" y="${H - P.b + 14}" font-size="10" fill="var(--ink-mute,#8a93a3)" text-anchor="middle">${yr}</text>`;
    }
    return g;
  }

  const pathOf = (pts, xOf, yOf) =>
    pts.map((p, i) => `${i ? 'L' : 'M'}${xOf(p.t).toFixed(1)},${yOf(p.v).toFixed(1)}`).join(' ');

  // ===== ① 국정평가 =====
  function renderApproval(records) {
    if (!records.length) return '<div class="tk-empty">데이터 없음</div>';
    const W = 960, H = 360, P = { l: 30, r: 64, t: 28, b: 22 };
    const tMin = Math.min(...records.map((r) => ms(r.period_end)));
    const tMax = Math.max(...records.map((r) => ms(r.period_end)));
    const yMax = 100;
    const xOf = (t) => P.l + (t - tMin) / (tMax - tMin || 1) * (W - P.l - P.r);
    const yOf = (v) => P.t + (1 - v / yMax) * (H - P.t - P.b);

    // 대통령 임기 band (범위 내 clip) + 라벨
    let bands = '';
    PRES.forEach((p, i) => {
      const a = Math.max(ms(p.a), tMin), b = Math.min(ms(p.b), tMax);
      if (b <= a) return;
      const x0 = xOf(a), x1 = xOf(b);
      bands += `<rect x="${x0.toFixed(1)}" y="${P.t}" width="${(x1 - x0).toFixed(1)}" height="${H - P.t - P.b}" fill="${i % 2 ? 'var(--ink)' : 'transparent'}" opacity="${i % 2 ? 0.03 : 0}"/>`;
      bands += `<text x="${((x0 + x1) / 2).toFixed(1)}" y="${P.t - 12}" font-size="11" font-weight="700" fill="var(--ink-soft,#5b6573)" text-anchor="middle">${p.name}</text>`;
      bands += `<line x1="${x0.toFixed(1)}" y1="${P.t}" x2="${x0.toFixed(1)}" y2="${H - P.b}" stroke="var(--rule-strong,#c4c9d2)" stroke-width="0.6"/>`;
    });

    // 긍정·부정 — 대통령별 월평균(갤럽+리얼미터 통합, house effect 완화) 라인 + 원자료 점.
    const grid = gridAxes(W, H, P, tMin, tMax, yMax, 20, xOf, yOf);
    function lineFor(key, color) {
      let body = '';
      for (const p of PRES) {
        const recs = records.filter((r) => r.subject === p.name);
        // 원자료 점(옅게)
        for (const r of recs) {
          body += `<circle cx="${xOf(ms(r.period_end)).toFixed(1)}" cy="${yOf(r[key]).toFixed(1)}" r="1.4" fill="${color}" opacity="0.28"/>`;
        }
        // 월평균 라인
        const byM = {};
        for (const r of recs) ((byM[ym(r.period_end)] ||= []).push(r[key]));
        const seg = Object.entries(byM).map(([k, a]) => ({
          t: Date.parse(`${k}-15`), v: a.reduce((x, y) => x + y, 0) / a.length,
        })).sort((a, b) => a.t - b.t);
        if (seg.length >= 2) body += `<path d="${pathOf(seg, xOf, yOf)}" fill="none" stroke="${color}" stroke-width="2" stroke-opacity="0.95"/>`;
        if (seg.length) {
          const last = seg[seg.length - 1];
          body += `<circle cx="${xOf(last.t).toFixed(1)}" cy="${yOf(last.v).toFixed(1)}" r="2.6" fill="${color}"/>`;
          body += `<text x="${(xOf(last.t) + 4).toFixed(1)}" y="${(yOf(last.v) + 3).toFixed(1)}" font-size="9" fill="${color}" font-weight="700">${Math.round(last.v)}</text>`;
        }
      }
      return body;
    }
    const lines = lineFor('positive', POS) + lineFor('negative', NEG);
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" role="img" aria-label="대통령 국정수행 평가 추이">${bands}${grid}${lines}</svg>`;
  }

  // ===== ② 정당지지 =====
  function renderPartySupport(polls) {
    // 월별 평균(전국)
    const byParty = {};  // party -> {ym -> [pct]}
    for (const p of polls) {
      if (!p.period_end || !p.candidates) continue;
      for (const c of p.candidates) {
        if (c.pct == null || !c.party) continue;
        const party = CANON[c.party] || c.party;
        ((byParty[party] ||= {})[ym(p.period_end)] ||= []).push(c.pct);
      }
    }
    // party -> sorted points (월평균)
    const series = {};
    let tMin = Infinity, tMax = -Infinity, yMax = 10;
    for (const [party, m] of Object.entries(byParty)) {
      const pts = Object.entries(m).map(([k, arr]) => ({
        t: Date.parse(`${k}-15`), v: arr.reduce((a, b) => a + b, 0) / arr.length,
      })).sort((a, b) => a.t - b.t);
      // 주요 정당만 — 무당층·기타 제외, 월평균 최고 ≥ 5% (전국 유의미 지지).
      if (NON_PARTY.has(party)) continue;
      const peak = Math.max(...pts.map((p) => p.v));
      if (peak < 5) continue;
      series[party] = pts;
      for (const pt of pts) { tMin = Math.min(tMin, pt.t); tMax = Math.max(tMax, pt.t); yMax = Math.max(yMax, pt.v); }
    }
    const parties = Object.keys(series);
    if (!parties.length) return '<div class="tk-empty">데이터 없음</div>';
    yMax = Math.min(60, Math.ceil(yMax / 10) * 10);
    const W = 960, H = 380, P = { l: 30, r: 88, t: 16, b: 22 };
    const xOf = (t) => P.l + (t - tMin) / (tMax - tMin || 1) * (W - P.l - P.r);
    const yOf = (v) => P.t + (1 - v / yMax) * (H - P.t - P.b);
    const grid = gridAxes(W, H, P, tMin, tMax, yMax, 10, xOf, yOf);

    // 라벨 y겹침 방지
    const mean = (ps) => ps.reduce((s, p) => s + p.v, 0) / ps.length;
    parties.sort((a, b) => mean(series[b]) - mean(series[a]));
    let lastLabelY = -99, body = '';
    for (const party of parties) {
      const pts = series[party];
      const color = partyColor(party, new Date(tMax).toISOString().slice(0, 10));
      // 3개월 넘는 공백은 끊기
      let seg = [];
      const flush = () => {
        if (seg.length >= 2) body += `<path d="${pathOf(seg, xOf, yOf)}" fill="none" stroke="${color}" stroke-width="1.6" stroke-opacity="0.85"/>`;
        else if (seg.length === 1) body += `<circle cx="${xOf(seg[0].t).toFixed(1)}" cy="${yOf(seg[0].v).toFixed(1)}" r="1.8" fill="${color}"/>`;
        seg = [];
      };
      for (let i = 0; i < pts.length; i++) {
        if (i && pts[i].t - pts[i - 1].t > 1000 * 60 * 60 * 24 * 100) flush();
        seg.push(pts[i]);
      }
      flush();
      const last = pts[pts.length - 1];
      let ly = yOf(last.v) + 3;
      if (ly - lastLabelY < 11) ly = lastLabelY + 11;
      lastLabelY = ly;
      body += `<text x="${(W - P.r + 4).toFixed(1)}" y="${ly.toFixed(1)}" font-size="9.5" fill="${color}" font-weight="700">${(typeof PARTY_SHORT !== 'undefined' && PARTY_SHORT[party]) || party}</text>`;
    }
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" role="img" aria-label="정당 지지도 추이">${grid}${body}</svg>`;
  }

  // ---- load ----
  async function load() {
    const [gallup, realmeter, nbs, ...aggs] = await Promise.all([
      fetch('data/polls/approval_gallup.json').then((r) => r.json()).catch(() => ({ records: [] })),
      fetch('data/polls/approval_realmeter.json').then((r) => r.json()).catch(() => ({ records: [] })),
      fetch('data/polls/approval_nbs.json').then((r) => r.json()).catch(() => ({ records: [] })),
      ...AGG_FILES.map((f) => fetch(f).then((r) => r.json()).catch(() => ({ polls: [] }))),
    ]);
    // 국정평가 — 갤럽+리얼미터+NBS 통합
    const recs = [...(gallup.records || []), ...(realmeter.records || []), ...(nbs.records || [])]
      .filter((r) => r.subject && r.positive != null)
      .sort((a, b) => ms(a.period_end) - ms(b.period_end));
    document.getElementById('tk-approval').innerHTML = renderApproval(recs);
    const ar = recs.length ? `${recs.length}개 조사 · ${recs[0].period_end.slice(0, 7)} ~ ${recs[recs.length - 1].period_end.slice(0, 7)}` : '';
    document.getElementById('tk-approval-meta').textContent = `한국갤럽·리얼미터·NBS · ${ar}`;

    // 정당지지 (전국만)
    const polls = [];
    for (const a of aggs) for (const p of (a.polls || [])) {
      if (p.metric_type === '정당지지' && !p.sido) polls.push(p);
    }
    document.getElementById('tk-party').innerHTML = renderPartySupport(polls);
    document.getElementById('tk-party-meta').textContent = `전국 ${polls.length}개 조사 · 월평균`;

    document.getElementById('tk-loading')?.remove();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', load);
  else load();
})();
