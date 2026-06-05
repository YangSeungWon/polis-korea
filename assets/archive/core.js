// archive 엔트리 — window.__ARCHIVE__ = { id } + data/elections/{id}.json 메타로
// results · polls · byelection · 출구조사 fetch 후 모드(local/pres/general) dispatch.
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

  // 1. 결과 — _meta.chunked 플래그 있으면 .sigungu.json chunk 합치기
  let results = null;
  try {
    results = await fetch(meta.resultsPath, { cache: 'no-cache' }).then((r) => r.ok ? r.json() : null);
    if (results?._meta?.chunked) {
      const chunkPath = meta.resultsPath.replace(/\.json$/, '.sigungu.json');
      const chunk = await fetch(chunkPath, { cache: 'no-cache' }).then((r) => r.ok ? r.json() : null).catch(() => null);
      if (chunk?.races) results.races = (results.races || []).concat(chunk.races);
    }
  } catch { results = null; }

  // 2. 폴 (회차별 path)
  let polls = null;
  try {
    // 활성 회차(9회) archive는 후보 race만 → lite chunk. 옛 회차는 회차별 path.
    const path = meta.pollsPath || 'data/polls/aggregated_candidates.json';
    const all = await fetch(path).then((r) => r.json());
    polls = (all.polls || []).filter((p) => window.Archive.filterPoll(p, meta));
  } catch { polls = null; }

  // 3. 재보궐 사유
  let byReasons = [];
  try {
    const br = await fetch('data/byelection_reasons.json').then((r) => r.json());
    byReasons = (br.reasons || []).filter((r) => r.elctYmd === meta.date.replace(/-/g, ''));
  } catch {}

  // 4. 출구조사 — meta에서 명시적으로 null이면 fetch 스킵 (해당 회차 출구조사 없음)
  let exitData = null;
  if (meta.exitPollPath !== null) {
    try {
      const path = meta.exitPollPath || `data/exit_polls/${meta.id}.json`;
      exitData = await fetch(path).then((r) => r.ok ? r.json() : null);
    } catch {}
  }

  const isPres = meta.electionKind === 'presidential';
  const isGeneral = meta.electionKind === 'general_election' || meta.electionKind === 'national_assembly';
  const isByelection = meta.electionKind === 'byelection';
  const sgTypecode = meta.sgTypecode || (isPres ? '1' : isGeneral ? '2' : '3');

  const ctx = { meta, results, polls, byReasons, exitData, sgTypecode };

  if (isPres) window.Archive.pres.render(ctx);
  else if (isGeneral) window.Archive.general.render(ctx);
  else if (isByelection) await window.Archive.byelection.render(ctx);
  else await window.Archive.local.render(ctx);
  // 조사 60건 list section 제거됨 — 사용자 거의 안 보던 영역.
})();
