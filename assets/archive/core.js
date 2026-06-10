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

  const ctx = { meta, results, polls: null, byReasons: [], exitData: null, sgTypecode };
  if (mode) await mode.render(ctx);   // 여론조사·출구조사 없이 상단·결과 먼저(가드로 2차 섹션 스킵)

  // === 2단계: 2차 데이터 백그라운드 병렬 로드 → 해당 섹션만 채움 ===
  (async () => {
    const pollsPath = meta.pollsPath || 'data/polls/aggregated_candidates.json';
    const [polls, byReasons, exitData] = await Promise.all([
      fetch(pollsPath).then((r) => r.json())
        .then((all) => (all.polls || []).filter((p) => window.Archive.filterPoll(p, meta)))
        .catch(() => null),
      fetch('data/byelection_reasons.json').then((r) => r.json())
        .then((br) => (br.reasons || []).filter((r) => r.elctYmd === meta.date.replace(/-/g, '')))
        .catch(() => []),
      (meta.exitPollPath !== null
        ? fetch(meta.exitPollPath || `data/exit_polls/${meta.id}.json`).then((r) => r.ok ? r.json() : null).catch(() => null)
        : Promise.resolve(null)),
    ]);
    ctx.polls = polls;
    ctx.byReasons = byReasons;
    ctx.exitData = exitData;
    if (mode && mode.renderDeferred) await mode.renderDeferred(ctx);
  })();
})();
