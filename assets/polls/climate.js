// 선거 무렵 분위기 — per-election 폴 페이지에 그 선거 ±윈도우(기본 12개월) 동안의
//   ① 대통령 국정 지지율(긍정/부정)  ② 정당 지지율  추이를 보여준다.
// 선거 결과(후보/비례)를 만든 "배경"이라 같은 페이지에서 함께 봐야 함(tracker.html은 상시 연속).
//   데이터: approval_*.json(국정, 기관 통합·ntt dedup) + aggregated_etc.json(metric_type=정당지지, 전국).
//   렌더: buildPartyTrendSVG(utils.js) 재사용 — 후보/정당 추이와 동일 시각 언어. 국정은 colorMap으로 긍정/부정 색.
(function () {
  const MONTHS_MS = 30.4 * 86400000;
  let _cache = null;

  async function loadData() {
    if (_cache) return _cache;
    const APPR = ['gallup', 'realmeter', 'nbs', 'hrc', 'general'].map((s) => `data/polls/approval_${s}.json`);
    const [apprAll, etc] = await Promise.all([
      Promise.all(APPR.map((f) => fetch(f).then((r) => r.json()).catch(() => ({ records: [] })))),
      fetch('data/polls/aggregated_etc.json').then((r) => r.json()).catch(() => ({ polls: [] })),
    ]);
    const seen = new Set();
    const approval = apprAll.flatMap((d) => d.records || [])
      .filter((r) => r.positive != null && r.period_end && !seen.has(r.ntt_id) && seen.add(r.ntt_id));
    const party = (etc.polls || []).filter((p) => p.metric_type === '정당지지' && !p.sido && p.period_end);
    _cache = { approval, party };
    return _cache;
  }

  // 윈도우 안 approval에서 가장 많이 잡힌 대통령 1명만(임기 교체 구간 혼선 방지).
  function dominantSubject(recs) {
    const c = {};
    for (const r of recs) c[r.subject] = (c[r.subject] || 0) + 1;
    return Object.entries(c).sort((a, b) => b[1] - a[1])[0]?.[0];
  }

  async function render(host, electionDate, opts) {
    opts = opts || {};
    const months = opts.months || 12;
    if (!host || !electionDate || typeof buildPartyTrendSVG !== 'function') { host && host.remove(); return; }
    const endTs = Date.parse(electionDate);
    if (!isFinite(endTs)) { host.remove(); return; }
    const startTs = endTs - months * MONTHS_MS;
    const inWin = (s) => { const t = Date.parse(s); return t >= startTs && t <= endTs; };

    const { approval, party } = await loadData();

    // 국정 — 윈도우 + 단일 대통령 → 긍정/부정 2선 pseudo-poll
    const apprWin = approval.filter((r) => inWin(r.period_end));
    const subj = dominantSubject(apprWin);
    const apprPolls = apprWin.filter((r) => r.subject === subj).map((r) => ({
      period_end: r.period_end, agency: r.agency,
      candidates: [{ name: '긍정', party: '긍정', pct: r.positive }, { name: '부정', party: '부정', pct: r.negative }],
    }));
    // per-election 폴(그 선거 정당지지)을 트래커 데이터와 병합 — 트래커가 듬성한 시즌을 채움(22대
    // 조국혁신당처럼 신생당이 트래커엔 빠진 경우). ntt_id 스킴이 파일마다 달라 내용키(기관|기간)로 dedup,
    // per-election을 먼저 둬 같은 폴이면 그쪽(후보 풍부)을 채택.
    const elParty = (opts.polls || []).filter((p) => (p.metric_type === '정당지지' || p.office_level === '정당지지') && !p.sido && p.period_end);
    const seen = new Set(); const mergedParty = [];
    for (const p of [...elParty, ...party]) {
      const k = `${p.agency || ''}|${p.period_start || ''}|${p.period_end || ''}`;
      if (seen.has(k)) continue; seen.add(k); mergedParty.push(p);
    }
    const partyPolls = mergedParty.filter((p) => inWin(p.period_end));

    // 두 차트 x축을 선거일까지 연장 → 오른쪽 끝(선거일) 정렬·연도 라벨 통일.
    //   국정선이 일찍 끝나면 그 자체가 맥락(탄핵 등 임기 중단).
    const apprSvg = apprPolls.length >= 3
      ? buildPartyTrendSVG(apprPolls, { keyBy: 'candidate', colorMap: { '긍정': '#2e7d6f', '부정': '#c8553d' }, bandMinPts: 6, electionTs: endTs })
      : '';
    // 총선은 정당 지지가 곧 선거 지표 → opts.partyActual(비례 실제, 위성정당→본당)을 ◆로 오버레이.
    const partySvg = partyPolls.length >= 3
      ? buildPartyTrendSVG(partyPolls, { keyBy: 'party', topN: 6, bandMinPts: 6, electionTs: endTs, actual: opts.partyActual })
      : '';

    if (!apprSvg && !partySvg) { host.remove(); return; }   // 데이터 없으면 섹션 자체 제거(옛 회차)

    const range = `${new Date(startTs).toISOString().slice(0, 7)}~${electionDate.slice(0, 7)}`;
    host.innerHTML = `
      <h2 class="poll-climate-title">선거 무렵 분위기 <span class="info-i" tabindex="0" role="button" aria-label="설명">i<span class="info-pop">선거 ${months}개월 전 ~ 선거일 (${range}) 구간. 결과를 만든 국정·정당 지지 배경.</span></span></h2>
      <div class="poll-climate-grid">
        ${apprSvg ? `<div class="poll-climate-block"><div class="poll-climate-lbl">${subj || ''} 국정 지지율 <span class="pc-pos">긍정</span>·<span class="pc-neg">부정</span></div>${apprSvg}</div>` : ''}
        ${partySvg ? `<div class="poll-climate-block"><div class="poll-climate-lbl">정당 지지율${opts.partyActual ? ' <span class="pc-actual">◆ 비례 실제</span>' : ''}</div>${partySvg}</div>` : ''}
      </div>`;
  }

  // 앵커 뒤에 섹션 삽입 후 렌더. opts.after=기준 요소 id(추이 차트). 없으면 .controls 앞 / main 끝.
  async function mount(opts) {
    opts = opts || {};
    // 특정 선거 페이지(/polls/{id}/)에만 — 허브({})·office({office})는 election 없어 제외.
    const el = window.__INITIAL_STATE__ && window.__INITIAL_STATE__.election;
    const date = el && el.date;
    if (!date) return;
    if (document.getElementById('poll-climate')) return; // 1회
    const sec = document.createElement('section');
    sec.id = 'poll-climate';
    sec.className = 'poll-climate-sec';
    const anchor = opts.after && document.getElementById(opts.after);
    if (anchor) anchor.insertAdjacentElement('afterend', sec);
    else {
      const ctrl = document.querySelector('.controls');
      if (ctrl && ctrl.parentElement) ctrl.parentElement.insertBefore(sec, ctrl);
      else document.querySelector('main.page')?.appendChild(sec);
    }
    await render(sec, date, opts);
  }

  window.PollClimate = { mount, render };
})();
