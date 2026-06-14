// 셀 어댑터 — 폴(aggregated)·결과(results)를 공통 RegionCell로 정규화.
//   RegionCell = { sido, candidates:[{name,party,share,pct}], weight }
//     share  = 비례 배분 기준 (폴=pct, 결과=votes)
//     weight = 셀 크기 (결과=valid_votes; 폴은 결과의 valid_votes를 weights로 주입 → 모드 토글해도 크기 일정)
//   render-sido-prop(drawGrid/drawDorling)이 이 형태를 그대로 소비 (share/weight 일반화됨).
// 출처(폴/실제)·종류 의존을 여기로 격리 → 렌더러는 RegionCell만 안다.
(function () {
  'use strict';
  const norm = () => (typeof canonSido === 'function') ? canonSido : (n) => n || '';

  // 결과 races(scope=sido) → cells. share=votes, weight=valid_votes.
  function cellsFromResults(races) {
    return (races || [])
      .filter((r) => r.scope === 'sido' && (r.candidates || []).length)
      .map((r) => ({
        sido: r.sido,
        weight: r.valid_votes || (r.candidates || []).reduce((s, c) => s + (c.votes || 0), 0),
        candidates: (r.candidates || []).map((c) => ({
          name: c.name, party: c.party, share: c.votes || 0, pct: c.pct,
        })),
      }));
  }

  // 결과 races → { canonSido: valid_votes } — 폴 cell weight 주입용.
  function weightsFromResults(races) {
    const cs = norm();
    const w = {};
    for (const r of races || []) {
      if (r.scope !== 'sido') continue;
      w[cs(r.sido)] = r.valid_votes || 0;
    }
    return w;
  }

  // 폴 → cells. 시도별 최신 1건(해당 office)의 후보 pct. share=pct, weight=weights[시도].
  function cellsFromPolls(polls, opts) {
    opts = opts || {};
    const office = opts.office || '대통령';
    const weights = opts.weights || {};
    const cs = norm();
    const latest = {};   // canonSido → 최신 폴
    for (const p of polls || []) {
      if (p.office_level !== office) continue;
      if (!p.sido || p.sigungu) continue;            // 시도 단위만
      if (!(p.candidates || []).length) continue;
      const key = cs(p.sido);
      if (!latest[key] || (p.period_end || '') > (latest[key].period_end || '')) latest[key] = p;
    }
    return Object.entries(latest).map(([key, p]) => ({
      sido: p.sido,
      weight: weights[key] || 1,
      candidates: (p.candidates || []).map((c) => ({
        name: c.name, party: c.party, share: c.pct || 0, pct: c.pct,
      })),
    }));
  }

  window.PollCellAdapter = { cellsFromResults, cellsFromPolls, weightsFromResults };
})();
