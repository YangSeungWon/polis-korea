// 폴 데이터 어댑터 — 출처(폴 aggregated · 결과 results)를 렌더러-무관 형태로 정규화.
// 출처/종류 의존을 여기로 격리 → 렌더러는 정규화된 형태만 안다.
//
//  [공간] cellsFromResults/cellsFromPolls → RegionCell (시도 비례 viz, render-sido-prop)
//     RegionCell = { sido, candidates:[{name,party,share,pct}], weight }
//       share=비례 기준(폴=pct, 결과=votes), weight=셀 크기(결과 valid_votes; 폴은 weights 주입)
//  [시간] presTrend → { polls, actual } (대선 본선 후보 추이, buildPartyTrendSVG)
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

  // [시간] 대선 본선 후보 추이 — 폴 + 실제결과(권위) → buildPartyTrendSVG 입력.
  //   실제 결과 후보를 본선 집합으로: 상위2인(당선·차점) 모두 등장 + 본선후보 합≥70 인
  //   전국 후보 폴만(경선·가상대결·truncated 자동 제외, 날짜 하드코딩 X), 후보도 본선집합 한정.
  //   반환 { polls, actual:[{key,pct}] }.
  function presTrend(polls, nationRace) {
    const fin = ((nationRace && nationRace.candidates) || [])
      .filter((c) => c.pct != null).slice().sort((a, b) => b.pct - a.pct);
    if (fin.length < 2) return { polls: [], actual: [] };
    const finalSet = new Set(fin.map((c) => c.name));
    const top2 = [fin[0].name, fin[1].name];
    const kept = (polls || []).filter((p) => {
      if (p.office_level !== '대통령' || p.sido) return false;          // 전국 후보 폴만
      const named = (p.candidates || []).filter((c) => c.pct != null);
      const names = new Set(named.map((c) => c.name));
      if (!top2.every((n) => names.has(n))) return false;              // 본선 양강 모두 등장
      const s = named.filter((c) => finalSet.has(c.name)).reduce((a, c) => a + c.pct, 0);
      return s >= 70;                                                  // 본선후보 합 정상
    }).map((p) => ({ ...p, candidates: (p.candidates || []).filter((c) => finalSet.has(c.name)) }));
    return { polls: kept, actual: fin.map((c) => ({ key: c.name, pct: c.pct })) };
  }

  // 21·22대 비례 위성정당 → 본당. 정당지지(본당) 추이와 비례 실제결과(위성) ◆ 정렬용.
  // 20대 이전은 위성 없음(매핑 시 self). 새 위성 생기면 여기 추가.
  const SATELLITE = {
    '국민의미래': '국민의힘', '더불어민주연합': '더불어민주당',
    '미래한국당': '미래통합당', '더불어시민당': '더불어민주당',
  };

  // [시간] 총선 정당 지지율 추이 — 정당지지(전국·본당, 풀사이클) → buildPartyTrendSVG party 모드.
  //   actual ◆ = 비례 실제 결과(위성→본당 매핑). 반환 { polls, actual:[{key=정당, pct}] }.
  function genTrend(polls, propNationRace) {
    const kept = (polls || []).filter((p) =>
      p.office_level === '정당지지' && !p.sido && (p.candidates || []).length);
    const acc = {};
    for (const c of ((propNationRace && propNationRace.candidates) || [])) {
      if (c.pct == null || !c.party) continue;
      const key = SATELLITE[c.party] || c.party;
      acc[key] = (acc[key] || 0) + c.pct;
    }
    const actual = Object.entries(acc).map(([key, pct]) => ({ key, pct: Math.round(pct * 100) / 100 }));
    return { polls: kept, actual };
  }

  window.PollAdapter = { cellsFromResults, cellsFromPolls, weightsFromResults, presTrend, genTrend };
})();
