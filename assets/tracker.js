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
  const AGG_FILES = ['19pres', '20pres', '21pres', '20th', '21st', '22nd', '7th', '8th', 'etc']
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

  // Gaussian 커널 평활 — 불규칙 간격 개별 조사 → 추세선. 시간창(bw) 안 다기관 평균으로
  // house effect 완화(가중평균이라 구성편향도 단순 월평균보다 덜함). 큰 공백은 segment로 끊음.
  function kernelSmooth(points, bwDays) {
    if (points.length < 2) return points.length ? [points.slice()] : [];
    const pts = points.slice().sort((a, b) => a.t - b.t);
    const bw = bwDays * 864e5, step = 7 * 864e5, maxGap = 75 * 864e5;
    const t0 = pts[0].t, t1 = pts[pts.length - 1].t;
    const segs = [];
    let cur = [];
    for (let t = t0; t <= t1 + 1; t += step) {
      let sw = 0, sv = 0, near = Infinity;
      for (const p of pts) {
        const d = t - p.t;
        if (d > near + 4 * bw) continue;
        const ad = Math.abs(d);
        near = Math.min(near, ad);
        const w = Math.exp(-(d * d) / (bw * bw));
        sw += w; sv += w * p.v;
      }
      if (near <= maxGap && sw > 1e-9) cur.push({ t, v: sv / sw });
      else if (cur.length) { segs.push(cur); cur = []; }
    }
    if (cur.length) segs.push(cur);
    return segs;
  }

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

    // 긍정·부정 — 개별 조사 점(옅게) + 대통령별 평활 추세선(다기관 통합, house effect 완화).
    const grid = gridAxes(W, H, P, tMin, tMax, yMax, 20, xOf, yOf);
    function lineFor(key, color) {
      let body = '';
      for (const p of PRES) {
        const pts = records.filter((r) => r.subject === p.name)
          .map((r) => ({ t: ms(r.period_end), v: r[key] }));
        if (!pts.length) continue;
        for (const r of pts) {
          body += `<circle cx="${xOf(r.t).toFixed(1)}" cy="${yOf(r.v).toFixed(1)}" r="1.2" fill="${color}" opacity="0.2"/>`;
        }
        const segs = kernelSmooth(pts, 30);
        for (const seg of segs) {
          if (seg.length >= 2) body += `<path d="${pathOf(seg, xOf, yOf)}" fill="none" stroke="${color}" stroke-width="2" stroke-opacity="0.95"/>`;
        }
        const tail = segs[segs.length - 1];
        const last = tail && tail[tail.length - 1];
        if (last) {
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
    // 개별 조사 점(전국) — party -> [{t,v}]
    const byParty = {};
    for (const p of polls) {
      if (!p.period_end || !p.candidates) continue;
      const t = ms(p.period_end);
      if (!isFinite(t)) continue;
      for (const c of p.candidates) {
        if (c.pct == null || !c.party) continue;
        const party = CANON[c.party] || c.party;
        (byParty[party] ||= []).push({ t, v: c.pct });
      }
    }
    const series = {};
    let tMin = Infinity, tMax = -Infinity, yMax = 10;
    for (const [party, pts] of Object.entries(byParty)) {
      if (NON_PARTY.has(party)) continue;
      pts.sort((a, b) => a.t - b.t);
      // 주요 정당만 — 평활 추세 최고 ≥ 5% (단발 이상치 말고 추세 기준).
      const sm = kernelSmooth(pts, 30).flat();
      const peak = Math.max(...sm.map((p) => p.v), 0);
      if (peak < 5) continue;
      series[party] = { pts, sm };
      for (const pt of pts) { tMin = Math.min(tMin, pt.t); tMax = Math.max(tMax, pt.t); }
      yMax = Math.max(yMax, peak);
    }
    const parties = Object.keys(series);
    if (!parties.length) return '<div class="tk-empty">데이터 없음</div>';
    yMax = Math.min(60, Math.ceil(yMax / 10) * 10 + 5);
    const W = 960, H = 380, P = { l: 30, r: 88, t: 16, b: 22 };
    const xOf = (t) => P.l + (t - tMin) / (tMax - tMin || 1) * (W - P.l - P.r);
    const yOf = (v) => P.t + (1 - v / yMax) * (H - P.t - P.b);
    const grid = gridAxes(W, H, P, tMin, tMax, yMax, 10, xOf, yOf);

    const mean = (ps) => ps.reduce((s, p) => s + p.v, 0) / ps.length;
    parties.sort((a, b) => mean(series[b].sm) - mean(series[a].sm));
    let lastLabelY = -99, dots = '', lines = '';
    for (const party of parties) {
      const { pts, sm } = series[party];
      const color = partyColor(party, new Date(tMax).toISOString().slice(0, 10));
      // 개별 조사 = 옅은 점 (house effect 산포)
      for (const p of pts) {
        dots += `<circle cx="${xOf(p.t).toFixed(1)}" cy="${yOf(p.v).toFixed(1)}" r="1" fill="${color}" opacity="0.16"/>`;
      }
      // 평활 추세선 (공백 끊김 segment별)
      for (const seg of kernelSmooth(pts, 30)) {
        if (seg.length >= 2) lines += `<path d="${pathOf(seg, xOf, yOf)}" fill="none" stroke="${color}" stroke-width="1.8" stroke-opacity="0.95"/>`;
      }
      const last = sm[sm.length - 1];
      if (!last) continue;
      let ly = yOf(last.v) + 3;
      if (ly - lastLabelY < 11) ly = lastLabelY + 11;
      lastLabelY = ly;
      lines += `<text x="${(W - P.r + 4).toFixed(1)}" y="${ly.toFixed(1)}" font-size="9.5" fill="${color}" font-weight="700">${(typeof PARTY_SHORT !== 'undefined' && PARTY_SHORT[party]) || party}</text>`;
    }
    const body = dots + lines;  // 점 먼저(아래), 선 위에
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" role="img" aria-label="정당 지지도 추이">${grid}${body}</svg>`;
  }

  // ---- load ----
  async function load() {
    const APPR_FILES = ['gallup', 'realmeter', 'nbs', 'hrc', 'general']
      .map((s) => `data/polls/approval_${s}.json`);
    const all = await Promise.all([
      ...APPR_FILES.map((f) => fetch(f).then((r) => r.json()).catch(() => ({ records: [] }))),
      ...AGG_FILES.map((f) => fetch(f).then((r) => r.json()).catch(() => ({ polls: [] }))),
    ]);
    const apprData = all.slice(0, APPR_FILES.length);
    const aggs = all.slice(APPR_FILES.length);
    // 국정평가 — 4기관 + 범용(기타 기관) 통합. ntt 중복 제거.
    const seen = new Set();
    const recs = apprData.flatMap((d) => d.records || [])
      .filter((r) => r.subject && r.positive != null && !seen.has(r.ntt_id) && seen.add(r.ntt_id))
      .sort((a, b) => ms(a.period_end) - ms(b.period_end));
    document.getElementById('tk-approval').innerHTML = renderApproval(recs);
    const ar = recs.length ? `${recs.length}개 조사 · ${recs[0].period_end.slice(0, 7)} ~ ${recs[recs.length - 1].period_end.slice(0, 7)}` : '';
    document.getElementById('tk-approval-meta').textContent = `다기관 통합 · ${ar}`;

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
