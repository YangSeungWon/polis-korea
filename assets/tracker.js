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
  // 테마 인지 색 보정 — 다크 배경(#0d1018)에선 어두운 당색·긍부정색을 밝게 올려 선·라벨 가독성 확보
  // (당색이 공식 다크 미대응이라 그대로면 거의 안 보임). 라이트에선 너무 밝은 색만 살짝 어둡게.
  let _dark = null;
  function isDark() {
    if (_dark === null) {
      const t = document.documentElement.getAttribute('data-theme');
      _dark = t === 'dark' ? true : t === 'light' ? false
        : matchMedia('(prefers-color-scheme: dark)').matches;
    }
    return _dark;
  }
  function _rgb(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
    if (!m) return null;
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function _rgb2hsl([r, g, b]) {
    r /= 255; g /= 255; b /= 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
    let h = 0, s = 0; const l = (mx + mn) / 2;
    if (mx !== mn) {
      const d = mx - mn;
      s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
      h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
      h /= 6;
    }
    return [h, s, l];
  }
  function _hsl2rgb(h, s, l) {
    if (s === 0) { const v = Math.round(l * 255); return [v, v, v]; }
    const hue = (p, q, t) => {
      if (t < 0) t += 1; if (t > 1) t -= 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
    return [hue(p, q, h + 1 / 3), hue(p, q, h), hue(p, q, h - 1 / 3)].map((v) => Math.round(v * 255));
  }
  // 명도만 올려(채도 유지·약간 부스트) 다크 배경서 선명하게 — 흰색 혼합(허여멀개) 대신 HSL.
  function legible(hex) {
    const c = _rgb(hex);
    if (!c) return hex;
    let [h, s, l] = _rgb2hsl(c);
    if (isDark()) {
      if (l < 0.55) { l = 0.62; s = Math.min(1, s * 1.08 + 0.05); }  // 어두운 색 → 밝고 선명하게
    } else if (l > 0.82) {
      l = 0.7;  // 라이트 배경서 너무 밝은 색만 살짝 내림
    }
    const out = _hsl2rgb(h, s, l);
    return `rgb(${out[0]},${out[1]},${out[2]})`;
  }
  // 테마 변경 시 차트 재렌더(legible는 _dark 캐시라 무효화 후 다시 그림). data-theme 속성·시스템 둘 다.
  let _rerender = null;
  function _onThemeChange() { _dark = null; if (_rerender) _rerender(); }
  new MutationObserver(_onThemeChange).observe(document.documentElement,
    { attributes: true, attributeFilter: ['data-theme'] });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', _onThemeChange);
  const AGG_FILES = ['19pres', '20pres', '21pres', '20th', '21st', '22nd', '7th', '8th', 'etc']
    .map((s) => `data/polls/aggregated_${s}.json`);
  const CANON = { '민주당': '더불어민주당', '국힘': '국민의힘', '국민의 힘': '국민의힘' };
  const NON_PARTY = new Set(['무소속', '없음', '기타', '무당층', '지지정당없음', '기타정당', '지지정당 없음']);

  // 한 조사의 candidates → [{party(canon), pct}]. 핵심 보정: '더불어민주당'이 명시된 조사에
  // 별도 '민주당'(1~8%)이 또 있으면 그건 열린민주당 등 군소의 split-header 오라벨이므로
  // 더불어민주당으로 합치지 않음(그대로 두면 CANON이 합쳐 더불어민주당 추세를 끌어내림).
  function cleanCands(poll) {
    const cs = (poll.candidates || []).filter((c) => c.pct != null && c.party);
    const hasDLP = cs.some((c) => c.party === '더불어민주당');
    const out = [];
    for (const c of cs) {
      if (c.party === '민주당' && hasDLP) continue;  // 오라벨 군소 — 제외
      out.push({ party: CANON[c.party] || c.party, pct: c.pct });
    }
    return out;
  }
  const ms = (d) => Date.parse(d);
  const ym = (d) => d.slice(0, 7);

  // ---- 공통 축 ----
  function gridAxes(W, H, P, tMin, tMax, yMax, yStep, xOf, yOf, opts = {}) {
    let g = '';
    for (let v = 0; v <= yMax; v += yStep) {
      const y = yOf(v);
      g += `<line x1="${P.l}" y1="${y.toFixed(1)}" x2="${W - P.r}" y2="${y.toFixed(1)}" stroke="var(--rule,#e6e9ef)" stroke-width="0.5"/>`;
      g += `<text x="${P.l - 6}" y="${(y + 3).toFixed(1)}" font-size="11" fill="var(--ink-mute,#8a93a3)" text-anchor="end">${v}</text>`;
    }
    if (opts.noYears) return g;   // 차기주자: 연도선은 클러스터별 라벨로 별도 처리
    const y0 = new Date(tMin).getFullYear(), y1 = new Date(tMax).getFullYear();
    for (let yr = y0; yr <= y1; yr++) {
      const t = Date.parse(`${yr}-01-01`);
      if (t < tMin || t > tMax) continue;
      const x = xOf(t);
      g += `<line x1="${x.toFixed(1)}" y1="${P.t}" x2="${x.toFixed(1)}" y2="${H - P.b}" stroke="var(--rule,#e6e9ef)" stroke-width="0.4" stroke-dasharray="2 3"/>`;
      g += `<text x="${x.toFixed(1)}" y="${H - P.b + 14}" font-size="11" fill="var(--ink-mute,#8a93a3)" text-anchor="middle">${yr}</text>`;
    }
    return g;
  }

  // 차트 래핑: 본문 svg를 가로 스크롤 컨테이너에 + 모바일용 Y축 고정 오버레이.
  // 데스크톱은 CSS에서 오버레이 숨김 → 본문 svg 자체 Y축 사용(현행과 동일).
  function wrapChart(W, H, P, yMax, yStep, yOf, inner, aria) {
    let ax = `<rect x="0" y="0" width="${P.l}" height="${H}" fill="var(--bg,#fff)"/>`;
    for (let v = 0; v <= yMax; v += yStep) {
      ax += `<text x="${P.l - 6}" y="${(yOf(v) + 3).toFixed(1)}" font-size="11" fill="var(--ink-mute,#8a93a3)" text-anchor="end">${v}</text>`;
    }
    return `<svg class="tk-axisfix" viewBox="0 0 ${P.l} ${H}" preserveAspectRatio="xMaxYMid meet" aria-hidden="true">${ax}</svg>`
      + `<div class="tk-scroll"><svg class="tk-body" viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${aria}">${inner}</svg></div>`;
  }

  const pathOf = (pts, xOf, yOf) =>
    pts.map((p, i) => `${i ? 'L' : 'M'}${xOf(p.t).toFixed(1)},${yOf(p.v).toFixed(1)}`).join(' ');

  // 평활·house effect — assets/poll-stats.js 공유 모듈 사용.
  const kernelSmooth = (pts, bwDays) => PollStats.kernelSmooth(pts, bwDays);
  const houseEffects = (pts) => PollStats.houseEffects(pts, { bwDays: 30, shrinkK: 10, minN: 3 });  // 아래 lean 표 전용

  // ===== 인터랙션: hover 툴팁 (차트별 점 좌표 저장 → 최근접 점 표시) =====
  const HOVER = {};  // chartId → [{x,y,tip,color}]
  function tipEl() {
    let t = document.getElementById('tk-tip');
    if (!t) { t = document.createElement('div'); t.id = 'tk-tip'; document.body.appendChild(t); }
    return t;
  }
  function attachHover(id) {
    const host = document.getElementById(id);
    const svg = host && host.querySelector('svg.tk-body');
    const pts = HOVER[id];
    if (!svg || !pts || !pts.length) return;
    const tip = tipEl();
    const move = (e) => {
      const ctm = svg.getScreenCTM();
      if (!ctm) return;
      const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
      let best = null, bd = 20 * 20;
      for (const q of pts) {
        const dx = q.x - pt.x, dy = q.y - pt.y, d = dx * dx + dy * dy;
        if (d < bd) { bd = d; best = q; }
      }
      if (best) {
        tip.style.display = 'block';
        tip.style.left = (e.clientX + 14) + 'px';
        tip.style.top = (e.clientY + 12) + 'px';
        tip.innerHTML = `<span class="tk-tip-dot" style="background:${best.color}"></span>${best.tip}`;
      } else { tip.style.display = 'none'; }
    };
    svg.addEventListener('mousemove', move);
    svg.addEventListener('mouseleave', () => { tipEl().style.display = 'none'; });
  }
  const fmtD = (t) => new Date(t).toISOString().slice(0, 10);

  // ===== ① 국정평가 =====
  function renderApproval(records) {
    if (!records.length) return '<div class="tk-empty">데이터 없음</div>';
    const houseOf = {};   // house effect는 아래 표로만 노출 — 추세선엔 미적용(원자료 그대로).
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
    HOVER['tk-approval'] = [];
    function lineFor(key, color) {
      color = legible(color);
      let body = '';
      const house = houseOf[key] || {};
      const klabel = key === 'positive' ? '긍정' : '부정';
      for (const p of PRES) {
        const pts = records.filter((r) => r.subject === p.name)
          .map((r) => ({ t: ms(r.period_end), v: r[key] - (house[r.agency] || 0), ag: r.agency }));
        if (!pts.length) continue;
        for (const r of pts) {
          body += `<circle cx="${xOf(r.t).toFixed(1)}" cy="${yOf(r.v).toFixed(1)}" r="1.2" fill="${color}" opacity="0.2"/>`;
          HOVER['tk-approval'].push({ x: xOf(r.t), y: yOf(r.v), color, tip: `${p.name} ${klabel} <b>${r.v.toFixed(1)}%</b><br>${(r.ag || '').replace(/\(주\)/g, '')} · ${fmtD(r.t)}` });
        }
        const segs = kernelSmooth(pts, 30);
        for (const seg of segs) {
          if (seg.length >= 2) body += `<path d="${pathOf(seg, xOf, yOf)}" fill="none" stroke="${color}" stroke-width="2" stroke-opacity="0.95"/>`;
        }
        const tail = segs[segs.length - 1];
        const last = tail && tail[tail.length - 1];
        if (last) {
          body += `<circle cx="${xOf(last.t).toFixed(1)}" cy="${yOf(last.v).toFixed(1)}" r="2.6" fill="${color}"/>`;
          body += `<text x="${(xOf(last.t) + 4).toFixed(1)}" y="${(yOf(last.v) + 3).toFixed(1)}" font-size="11.5" fill="${color}" font-weight="700">${Math.round(last.v)}</text>`;
        }
      }
      return body;
    }
    const lines = lineFor('positive', POS) + lineFor('negative', NEG);
    return wrapChart(W, H, P, yMax, 20, yOf, `${bands}${grid}${lines}`, '대통령 국정수행 평가 추이');
  }

  // ===== ② 정당지지 =====
  function renderPartySupport(polls) {
    // 개별 조사 점(전국) — party -> [{t,v,ag}]
    const byParty = {};
    for (const p of polls) {
      if (!p.period_end || !p.candidates) continue;
      const t = ms(p.period_end);
      if (!isFinite(t)) continue;
      for (const c of cleanCands(p)) {
        (byParty[c.party] ||= []).push({ t, v: c.pct, ag: p.agency || '?' });
      }
    }
    const series = {};
    let tMin = Infinity, tMax = -Infinity, yMax = 10;
    for (let [party, pts] of Object.entries(byParty)) {
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
    const W = 960, H = 380, P = { l: 30, r: 100, t: 16, b: 22 };  // r: 풀네임 라벨 여백
    const xOf = (t) => P.l + (t - tMin) / (tMax - tMin || 1) * (W - P.l - P.r);
    const yOf = (v) => P.t + (1 - v / yMax) * (H - P.t - P.b);
    const grid = gridAxes(W, H, P, tMin, tMax, yMax, 10, xOf, yOf);

    const mean = (ps) => ps.reduce((s, p) => s + p.v, 0) / ps.length;
    parties.sort((a, b) => mean(series[b].sm) - mean(series[a].sm));
    HOVER['tk-party'] = [];
    let dots = '', lines = '';
    const GONE = 200 * 864e5;   // 마지막 조사가 최신보다 200일+ 전이면 '사라진 정당'
    const labelsArr = [];       // {party, x, y, color, gone}
    for (const party of parties) {
      const { pts, sm } = series[party];
      const color = legible(partyColor(party, new Date(tMax).toISOString().slice(0, 10)));
      // 개별 조사 = 옅은 점 (house effect 산포)
      for (const p of pts) {
        dots += `<circle cx="${xOf(p.t).toFixed(1)}" cy="${yOf(p.v).toFixed(1)}" r="1" fill="${color}" opacity="0.16"/>`;
        HOVER['tk-party'].push({ x: xOf(p.t), y: yOf(p.v), color, tip: `${party} <b>${p.v.toFixed(1)}%</b><br>${(p.ag || '').replace(/\(주\)/g, '')} · ${fmtD(p.t)}` });
      }
      // 평활 추세선 (공백 끊김 segment별)
      for (const seg of kernelSmooth(pts, 30)) {
        if (seg.length >= 2) lines += `<path d="${pathOf(seg, xOf, yOf)}" fill="none" stroke="${color}" stroke-width="1.8" stroke-opacity="0.95"/>`;
      }
      const last = sm[sm.length - 1];
      if (last) labelsArr.push({ party, x: xOf(last.t), y: yOf(last.v), color, gone: (tMax - last.t) > GONE });
    }
    // 라벨(풀네임): 현역 정당은 우측 끝(세로 충돌 회피), 사라진 정당은 선이 끝난 지점에.
    let labels = '';
    const activeL = labelsArr.filter((L) => !L.gone).sort((a, b) => a.y - b.y);
    let ly = -99;
    for (const L of activeL) {
      let yy = L.y + 3; if (yy - ly < 13) yy = ly + 13; ly = yy;
      labels += `<text x="${(W - P.r + 5).toFixed(1)}" y="${yy.toFixed(1)}" font-size="11.5" fill="${L.color}" font-weight="700">${L.party}</text>`;
    }
    const goneL = labelsArr.filter((L) => L.gone).sort((a, b) => a.x - b.x || a.y - b.y);
    const placed = [];
    for (const L of goneL) {
      let yy = L.y;
      for (const q of placed) if (Math.abs(q.x - L.x) < 72 && Math.abs(q.yy - yy) < 13) yy = q.yy + 13;
      placed.push({ x: L.x, yy });
      labels += `<circle cx="${L.x.toFixed(1)}" cy="${L.y.toFixed(1)}" r="1.8" fill="${L.color}"/>`;
      if (yy - L.y > 2) labels += `<line x1="${L.x.toFixed(1)}" y1="${L.y.toFixed(1)}" x2="${(L.x + 4).toFixed(1)}" y2="${(yy).toFixed(1)}" stroke="${L.color}" stroke-width="0.5" stroke-opacity="0.4"/>`;
      labels += `<text x="${(L.x + 5).toFixed(1)}" y="${(yy + 3).toFixed(1)}" font-size="11.5" fill="${L.color}" font-weight="700">${L.party}</text>`;
    }
    const body = dots + lines + labels;  // 점 먼저(아래), 선·라벨 위에
    return wrapChart(W, H, P, yMax, 10, yOf, `${grid}${body}`, '정당 지지도 추이');
  }

  // ===== ③ 차기 대선주자 선호 (다자대결) =====
  function renderCandidatePref(polls) {
    // 다자대결만 — 후보 4명+, 합 70~106, 1위 <55 (양자·단독 적합 배제). 인물별 점+평활.
    const byCand = {};  // name -> {pts:[{t,v,ag}], party}
    for (const p of polls) {
      const cs = (p.candidates || []).filter((c) => c.pct != null && c.name);
      const s = cs.reduce((a, c) => a + c.pct, 0), mx = Math.max(0, ...cs.map((c) => c.pct));
      if (cs.length < 4 || s < 70 || s > 106 || mx >= 55) continue;
      const t = ms(p.period_end);
      if (!isFinite(t)) continue;
      for (const c of cs) {
        (byCand[c.name] ||= { pts: [], party: c.party }).pts.push({ t, v: c.pct, ag: p.agency || '?' });
        if (c.party) byCand[c.name].party = c.party;
      }
    }
    const series = {};
    let tMin = Infinity, tMax = -Infinity, yMax = 10;
    for (const [name, o] of Object.entries(byCand)) {
      o.pts.sort((a, b) => a.t - b.t);
      const sm = kernelSmooth(o.pts, 25).flat();
      const peak = Math.max(0, ...sm.map((p) => p.v));
      if (peak < 8) continue;  // 주요 주자만
      series[name] = { ...o, sm, peak };
      for (const pt of o.pts) { tMin = Math.min(tMin, pt.t); tMax = Math.max(tMax, pt.t); }
      yMax = Math.max(yMax, peak);
    }
    const names = Object.keys(series);
    if (!names.length) return '<div class="tk-empty">데이터 없음</div>';
    yMax = Math.min(60, Math.ceil(yMax / 10) * 10 + 5);
    const W = 960, H = 380, P = { l: 30, r: 96, t: 16, b: 26 };
    const yOf = (v) => P.t + (1 - v / yMax) * (H - P.t - P.b);

    // 빈 구간 압축 — 활성 시점을 대선 국면 클러스터로(200일+ 비면 끊김), 폭은 지속기간 비례.
    const allT = [];
    for (const n of names) for (const pt of series[n].pts) allT.push(pt.t);
    allT.sort((a, b) => a - b);
    const GAP = 200 * 864e5, BREAK = 52;
    const clusters = [];
    for (const t of allT) {
      const c = clusters[clusters.length - 1];
      if (!c || t - c.tEnd > GAP) clusters.push({ tStart: t, tEnd: t });
      else c.tEnd = t;
    }
    const availW = (W - P.l - P.r) - BREAK * (clusters.length - 1);
    const totDur = clusters.reduce((s, c) => s + Math.max(c.tEnd - c.tStart, 1), 0);
    let cx = P.l;
    for (const c of clusters) {
      c.w = availW * Math.max(c.tEnd - c.tStart, 1) / totDur;
      c.x0 = cx; c.x1 = cx + c.w; cx = c.x1 + BREAK;
    }
    const clusterIdx = (t) => {
      for (let i = 0; i < clusters.length; i++) if (t >= clusters[i].tStart && t <= clusters[i].tEnd) return i;
      let bi = 0, bd = Infinity;
      for (let i = 0; i < clusters.length; i++) { const d = Math.min(Math.abs(t - clusters[i].tStart), Math.abs(t - clusters[i].tEnd)); if (d < bd) { bd = d; bi = i; } }
      return bi;
    };
    const xOf = (t) => { const c = clusters[clusterIdx(t)]; return c.x0 + (t - c.tStart) / Math.max(c.tEnd - c.tStart, 1) * c.w; };

    // y 그리드만 + 클러스터별 연도 라벨 + 끊김(∥) 표시
    let grid = gridAxes(W, H, P, 0, 1, yMax, 10, xOf, yOf, { noYears: true });
    clusters.forEach((c, i) => {
      const ya = new Date(c.tStart).getFullYear(), yb = new Date(c.tEnd).getFullYear();
      const lab = ya === yb ? `${ya}` : `${ya}–${String(yb).slice(2)}`;
      grid += `<text x="${((c.x0 + c.x1) / 2).toFixed(1)}" y="${(H - P.b + 16).toFixed(1)}" font-size="11" fill="var(--ink-mute,#8a93a3)" text-anchor="middle">${lab}</text>`;
      if (i > 0) grid += `<text x="${(c.x0 - BREAK / 2).toFixed(1)}" y="${((P.t + H - P.b) / 2).toFixed(1)}" font-size="15" fill="var(--rule-strong,#c4c9d2)" text-anchor="middle" font-weight="700">∥</text>`;
    });

    names.sort((a, b) => series[b].peak - series[a].peak);
    HOVER['tk-cand'] = [];
    let dots = '', lines = '';
    const ends = clusters.map(() => []);  // 클러스터별 [{x,y,name,color}] (선 끝 라벨)
    for (const name of names) {
      const { pts, party } = series[name];
      const color = legible(party ? partyColor(party, fmtD(pts[pts.length - 1].t)) : '#888');
      for (const p of pts) {
        dots += `<circle cx="${xOf(p.t).toFixed(1)}" cy="${yOf(p.v).toFixed(1)}" r="1" fill="${color}" opacity="0.16"/>`;
        HOVER['tk-cand'].push({ x: xOf(p.t), y: yOf(p.v), color, tip: `${name} <b>${p.v.toFixed(1)}%</b><br>${(p.ag || '').replace(/\(주\)/g, '')} · ${fmtD(p.t)}` });
      }
      // 클러스터(대선 국면)별로 나눠 평활·라벨 — 라벨이 그 국면 선 끝에 위치.
      const byC = clusters.map(() => []);
      for (const p of pts) byC[clusterIdx(p.t)].push(p);
      byC.forEach((cpts, k) => {
        if (cpts.length < 2) return;
        const segs = kernelSmooth(cpts, 25);
        for (const seg of segs) if (seg.length >= 2) lines += `<path d="${pathOf(seg, xOf, yOf)}" fill="none" stroke="${color}" stroke-width="1.8" stroke-opacity="0.95"/>`;
        const flat = segs.flat(), last = flat[flat.length - 1];
        if (last && Math.max(...cpts.map((p) => p.v)) >= 6) ends[k].push({ x: xOf(last.t), y: yOf(last.v), name, color });
      });
    }
    // 라벨 — 클러스터 직후(마지막은 우측 여백)에, 세로 충돌 회피 + 선 끝까지 leader.
    let labels = '';
    ends.forEach((arr, k) => {
      arr.sort((a, b) => a.y - b.y);
      for (let i = 1; i < arr.length; i++) if (arr[i].y - arr[i - 1].y < 13) arr[i].y = arr[i - 1].y + 13;
      const lx = (k === clusters.length - 1) ? (W - P.r + 5) : (clusters[k].x1 + 5);
      for (const L of arr) {
        labels += `<circle cx="${L.x.toFixed(1)}" cy="${L.y.toFixed(1)}" r="1.8" fill="${L.color}"/>`;
        if (lx - L.x > 6) labels += `<line x1="${(L.x + 2).toFixed(1)}" y1="${L.y.toFixed(1)}" x2="${(lx - 1).toFixed(1)}" y2="${L.y.toFixed(1)}" stroke="${L.color}" stroke-width="0.5" stroke-opacity="0.4"/>`;
        labels += `<text x="${lx.toFixed(1)}" y="${(L.y + 3).toFixed(1)}" font-size="11.5" fill="${L.color}" font-weight="700">${L.name}</text>`;
      }
    });
    return wrapChart(W, H, P, yMax, 10, yOf, `${grid}${dots}${lines}${labels}`, '차기 대선주자 선호 추이');
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
    // 정당지지(전국) · 차기 대선주자(대통령 후보지지, 전국)
    const polls = [], candPolls = [];
    for (const a of aggs) for (const p of (a.polls || [])) {
      if (p.sido) continue;
      if (p.metric_type === '정당지지') polls.push(p);
      else if (p.metric_type === '후보지지' && p.office_level === '대통령') candPolls.push(p);
    }

    function renderAll() {
      document.getElementById('tk-approval').innerHTML = renderApproval(recs);
      document.getElementById('tk-party').innerHTML = renderPartySupport(polls);
      document.getElementById('tk-cand').innerHTML = renderCandidatePref(candPolls);
      const ar = recs.length ? `${recs.length}개 조사 · ${recs[0].period_end.slice(0, 7)}~${recs[recs.length - 1].period_end.slice(0, 7)}` : '';
      document.getElementById('tk-approval-meta').textContent = `다기관 통합 · ${ar}`;
      document.getElementById('tk-party-meta').textContent = `전국 ${polls.length}개 조사`;
      document.getElementById('tk-cand-meta').textContent = `다자대결 기준 · 대선 국면`;
      ['tk-approval', 'tk-party', 'tk-cand'].forEach(attachHover);
      // 모바일 가로 스크롤은 최신(우측 끝)이 보이도록 초기 스크롤.
      // requestAnimationFrame으로 레이아웃 완료 후 실행.
      requestAnimationFrame(() => {
        for (const id of ['tk-approval', 'tk-party', 'tk-cand']) {
          const sc = document.querySelector(`#${id} .tk-scroll`);
          if (sc) sc.scrollLeft = sc.scrollWidth;
        }
      });
    }
    _rerender = renderAll;
    renderAll();
    renderLeanTable(recs, polls);
    document.getElementById('tk-loading')?.remove();
  }

  // ---- 기관별 lean 표 (538식 투명성) — 민주·국힘·국정긍정 잔차 평균 ----
  function renderLeanTable(recs, polls) {
    const host = document.getElementById('tk-lean');
    if (!host) return;
    const ptsOf = (party) => {
      const out = [];
      for (const p of polls) {
        if (!p.period_end) continue;
        const t = ms(p.period_end);
        for (const c of cleanCands(p)) {
          if (c.party === party) out.push({ t, v: c.pct, ag: p.agency || '?' });
        }
      }
      return out;
    };
    const dem = houseEffects(ptsOf('더불어민주당'));
    const ppp = houseEffects(ptsOf('국민의힘'));
    const app = houseEffects(recs.map((r) => ({ t: ms(r.period_end), v: r.positive, ag: r.agency })));
    // 표본 수 (민주 기준)
    const cnt = {};
    for (const p of polls) cnt[p.agency || '?'] = (cnt[p.agency || '?'] || 0) + 1;
    const ags = [...new Set([...Object.keys(dem), ...Object.keys(ppp), ...Object.keys(app)])]
      .filter((a) => (dem[a] || ppp[a] || app[a]) && (cnt[a] || 0) >= 15)
      .sort((a, b) => (dem[b] || 0) - (dem[a] || 0));
    const cell = (v) => v == null || v === 0 ? '<td class="z">·</td>'
      : `<td class="${v > 0 ? 'pos' : 'neg'}">${v > 0 ? '+' : ''}${v.toFixed(1)}</td>`;
    const rows = ags.map((a) =>
      `<tr><td class="ag">${a.replace(/\(주\)|주식회사/g, '').trim()}</td>${cell(dem[a])}${cell(ppp[a])}${cell(app[a])}<td class="n">${cnt[a] || ''}</td></tr>`).join('');
    host.innerHTML = `<table class="tk-lean-tbl"><thead><tr><th>조사기관</th><th>민주</th><th>국힘</th><th>국정<br>긍정</th><th>n</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', load);
  else load();
})();
