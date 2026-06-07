// poll-stats.js — 폴 시계열 통계 (DOM 의존 0).
// kernelSmooth · kernelBand · houseEffects · applyHouse.
// tracker.js와 회차별 폴 페이지 양쪽이 공유.

(function (root) {
  'use strict';

  const DAY = 864e5;

  // Gaussian 평활 — 불규칙 간격 점 → segment 배열 (큰 공백은 끊음).
  // points: [{t, v, ag?, n?}]. bwDays: 시간창. step/maxGap은 옵션.
  function kernelSmooth(points, bwDays, opts) {
    opts = opts || {};
    if (!points || points.length < 2) return points && points.length ? [points.slice()] : [];
    const pts = points.slice().sort((a, b) => a.t - b.t);
    const bw = bwDays * DAY;
    const step = (opts.stepDays || 7) * DAY;
    const maxGap = (opts.maxGapDays || 75) * DAY;
    const t0 = pts[0].t, t1 = pts[pts.length - 1].t;
    const segs = []; let cur = [];
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

  // 평활값 + ±밴드(가중표준편차) — segment마다 {t, v, sd}.
  function kernelBand(points, bwDays, opts) {
    opts = opts || {};
    if (!points || points.length < 2) return [];
    const pts = points.slice().sort((a, b) => a.t - b.t);
    const bw = bwDays * DAY;
    const step = (opts.stepDays || 7) * DAY;
    const maxGap = (opts.maxGapDays || 75) * DAY;
    const t0 = pts[0].t, t1 = pts[pts.length - 1].t;
    const segs = []; let cur = [];
    for (let t = t0; t <= t1 + 1; t += step) {
      let sw = 0, sv = 0, svv = 0, near = Infinity;
      for (const p of pts) {
        const d = t - p.t;
        if (d > near + 4 * bw) continue;
        const ad = Math.abs(d);
        near = Math.min(near, ad);
        const w = Math.exp(-(d * d) / (bw * bw));
        sw += w; sv += w * p.v; svv += w * p.v * p.v;
      }
      if (near <= maxGap && sw > 1e-9) {
        const mean = sv / sw;
        const variance = Math.max(0, svv / sw - mean * mean);
        cur.push({ t, v: mean, sd: Math.sqrt(variance) });
      } else if (cur.length) { segs.push(cur); cur = []; }
    }
    if (cur.length) segs.push(cur);
    return segs;
  }

  // 임의 시점 t의 평활 추세값.
  function kernelAt(points, t, bwDays) {
    const bw = (bwDays || 30) * DAY;
    let sw = 0, sv = 0;
    for (const p of points) {
      const d = t - p.t;
      const w = Math.exp(-(d * d) / (bw * bw));
      sw += w; sv += w * p.v;
    }
    return sw > 1e-9 ? sv / sw : null;
  }

  // house effect — 기관별 (조사값 − 추세값) 평균.
  // 강화: sample_size 가중 + shrinkage (n/(n+k))*raw_lean. hard cutoff 대신 부드럽게.
  // opts: {bwDays=30, shrinkK=10, minN=3, sampleWeight=true}
  function houseEffects(points, opts) {
    opts = opts || {};
    const bwDays = opts.bwDays || 30;
    const shrinkK = opts.shrinkK == null ? 10 : opts.shrinkK;
    const minN = opts.minN || 3;
    const sampleWeight = opts.sampleWeight !== false;
    const tr = points.map((p) => ({ t: p.t, v: p.v }));
    const res = {};   // ag → [{r, w}]
    for (const p of points) {
      const T = kernelAt(tr, p.t, bwDays);
      if (T == null) continue;
      const w = sampleWeight && p.n ? Math.sqrt(p.n) : 1;
      (res[p.ag] = res[p.ag] || []).push({ r: p.v - T, w });
    }
    const house = {};
    for (const [ag, arr] of Object.entries(res)) {
      if (arr.length < minN) { house[ag] = 0; continue; }
      let sw = 0, sr = 0;
      for (const x of arr) { sw += x.w; sr += x.w * x.r; }
      const raw = sw > 0 ? sr / sw : 0;
      // shrinkage: 적은 n은 0 쪽으로 끌어당김.
      house[ag] = (arr.length / (arr.length + shrinkK)) * raw;
    }
    return house;
  }

  const applyHouse = (points, house) =>
    points.map((p) => ({ t: p.t, v: p.v - (house[p.ag] || 0), ag: p.ag, n: p.n }));

  root.PollStats = { kernelSmooth, kernelBand, kernelAt, houseEffects, applyHouse };
})(typeof window !== 'undefined' ? window : globalThis);
