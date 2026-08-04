// archive 엔트리 — window.__ARCHIVE__ = { id } + data/elections/{id}.json 메타로
// 결과(+시군구 chunk)만 먼저 받아 상단·결과를 즉시 렌더하고,
// 무거운 2차 데이터(여론조사 2.5MB·출구조사·재보궐사유)는 백그라운드 병렬 로드 후
// 해당 섹션만 채운다(renderDeferred). → 체감 지연 최소화.
//
// 로드 순서: shared.js → local.js → pres.js → general.js → core.js.

(async function () {
  const stub = window.__ARCHIVE__ || {};
  if (!stub.id) return;

  const reg = (typeof Elections !== 'undefined') ? await Elections.loadElectionMeta(stub.id) : null;
  if (!reg) {
    console.warn('[archive] 회차 메타 로드 실패:', stub.id);
    return;
  }
  const ar = reg.archive || {};
  const meta = {
    id: reg.id,
    name: reg.name,
    date: reg.date,
    electionKind: reg.kind,
    electionN: reg.n,
    sgTypecode: ar.sg_typecode,
    proportionalSgTypecode: ar.proportional_sg_typecode,
    resultsPath: ar.results_path,
    pollsPath: ar.polls_path,
    exitPollPath: ar.exit_poll_path,
    byelectionId: ar.byelection_id || null,
    comparePrevious: ar.compare_previous || null,
    pollsWindow: ar.polls_window ? { start: ar.polls_window[0], end: ar.polls_window[1] } : null,
  };

  const isPres = meta.electionKind === 'presidential';
  const isGeneral = meta.electionKind === 'general_election' || meta.electionKind === 'national_assembly';
  const isByelection = meta.electionKind === 'byelection';
  const sgTypecode = meta.sgTypecode || (isPres ? '1' : isGeneral ? '2' : '3');
  const mode = isPres ? window.Archive.pres
    : isGeneral ? window.Archive.general
      : isByelection ? window.Archive.byelection
        : window.Archive.local;

  // 정당색 시대 맥락 — 이 회차 날짜로 partyColor periods lookup 활성.
  if (typeof setPartyColorContext === 'function') setPartyColorContext(meta.date);

  // 선거별 렌즈 전환 바 — 같은 선거의 다른 보기(여론조사 vs 실제·역대 흐름)로 이동. 재보궐 제외.
  if (window.LensSwitcher && !isByelection) {
    const LT = { presidential: 'presidential', general_election: 'national_assembly', national_assembly: 'national_assembly', local: 'local' };
    window.LensSwitcher.mount({ current: 'archive', id: meta.id, type: LT[meta.electionKind], n: meta.electionN });
  }

  // === 1단계: 결과(+시군구 chunk) — 이것만 받고 즉시 코어 렌더 ===
  let results = null;
  try {
    results = await fetch(meta.resultsPath, { cache: 'no-cache' }).then((r) => r.ok ? r.json() : null);
    if (results?._meta?.chunked) {
      const chunkPath = meta.resultsPath.replace(/\.json$/, '.sigungu.json');
      const chunk = await fetch(chunkPath, { cache: 'no-cache' }).then((r) => r.ok ? r.json() : null).catch(() => null);
      if (chunk?.races) results.races = (results.races || []).concat(chunk.races);
    }
  } catch { results = null; }

  // 후보→인물 링크 색인 — 결과 렌더보다 먼저 받아 둔다(작은 파일).
  if (window.Archive.personLink) { try { await window.Archive.personLink.load(meta.id); } catch {} }
  const ctx = { meta, results, polls: null, byReasons: [], exitData: null, sgTypecode };
  if (mode) await mode.render(ctx);   // 여론조사·출구조사 없이 상단·결과 먼저(가드로 2차 섹션 스킵)
  // 공약 분야 분포 — 회차 종류와 무관하게 같은 처리라 mode 밖에서 한 번만. 데이터나
  // 섹션이 없는 회차(총선 등)에서는 스스로 조용히 끝난다.
  window.Archive.comparison?.render(ctx);
  window.Archive.pledgeRealms?.render(ctx);
  mountTrust(ctx);

  // === 2단계: 2차 데이터 백그라운드 병렬 로드 → 해당 섹션만 채움 ===
  (async () => {
    const pollsPath = meta.pollsPath || 'data/polls/aggregated_candidates.json';
    const [polls, byReasons, exitData, pollIndex] = await Promise.all([
      fetch(pollsPath).then((r) => r.json())
        .then((all) => (all.polls || []).filter((p) => window.Archive.filterPoll(p, meta)))
        .catch(() => null),
      fetch('data/byelection_reasons.json').then((r) => r.json())
        .then((br) => (br.reasons || []).filter((r) => r.elctYmd === meta.date.replace(/-/g, '')))
        .catch(() => []),
      (meta.exitPollPath !== null
        ? fetch(meta.exitPollPath || `data/exit_polls/${meta.id}.json`).then((r) => r.ok ? r.json() : null).catch(() => null)
        : Promise.resolve(null)),
      // /polls/{id}/ 페이지 존재 여부 — 그 회차만 폴 CTA 노출(없는 회차 링크 404 방지).
      fetch('data/polls/election_index.json').then((r) => r.ok ? r.json() : []).catch(() => []),
    ]);
    ctx.polls = polls;
    ctx.byReasons = byReasons;
    ctx.exitData = exitData;
    ctx.pollPageExists = (pollIndex || []).some((e) => e.slug === meta.id);
    if (mode && mode.renderDeferred) await mode.renderDeferred(ctx);
    mountTrust(ctx);   // 출구조사·여론조사는 2단계에서 오므로 한 번 더 (mount는 교체 방식)
  })();
})();

// 신뢰 상태 한 줄을 각 섹션 제목 아래에 붙인다 — docs/trust-states.md.
// 한 곳에서만 부른다: 섹션마다 _meta를 따로 해석하면 규칙이 갈라진다.
function mountTrust(ctx) {
  const T = window.Trust;
  if (!T) return;
  const meta = ctx.results?._meta || {};
  const races = ctx.results?.races || [];

  // 개표율 — 잠정일 때만 뜻이 있다(확정본의 count_pct는 무투표 race의 100뿐).
  const cps = races.map((r) => r.count_pct).filter((v) => typeof v === 'number');
  const countPct = cps.length ? cps.reduce((a, b) => a + b, 0) / cps.length : null;

  // 결과 기반 섹션 — 같은 데이터셋이라 같은 줄을 쓴다.
  const base = T.deriveDataset(meta, { countPct });
  ['ar-offices', 'ar-governor-hex-section', 'ar-metro-hex-section',
    'ar-council-hex-section', 'ar-winners-section'].forEach((id) => T.mount(id, base));

  // 기초의원 비례는 득표 미게시 시군구가 있다 — 그 섹션에서만 밝힌다.
  const pending = races.filter((r) => r.votes_pending).length;
  if (pending) {
    T.mount('ar-council-hex-section', T.deriveDataset(meta, { countPct, pendingCount: pending }));
  }

  // 출구조사 — 확정/잠정을 붙이지 않는다. 예측은 확정 결과가 아니다.
  // 출처가 둘 이상이면 섹션에 뭉뚱그리지 않고 시리즈별로 붙는 게 맞지만(스펙), 우선
  // 섹션 단위로 발표 시각만 밝히고 시리즈별 표기는 출구조사 렌더러가 맡는다.
  const ex = ctx.exitData?._meta;
  if (ex) {
    T.mount('ar-exitpoll', T.deriveDataset(ex, {
      sourceLabel: (ex.sources || []).map((s) => s.name).join(' · ') || null,
    }));
  }
}
