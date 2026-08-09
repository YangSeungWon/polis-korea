// 폴 ↔ 실제 결과 토글 — mayor/governor/polls 페이지에서 hex/map을
// '여론조사 1위' vs '실제 NEC 1위' 비교. 선거 종료 후 노출.

(function () {
  let actualP = null;   // memoized — 진행 중 fetch를 둘 이상이 await해도 같은 promise 공유(레이스 방지)

  // 실제 결과(NEC) → 1위 맵 빌드는 PollAdapter.localActualMaps. state.actualMaps에 저장.
  // (모드별 swap은 core.js regionSidoWinner/regionSigunguWinner가 주입 — 옛 몽키패치 제거.)
  function loadActual() {
    if (actualP) return actualP;
    actualP = (async () => {
      try {
        // 본 결과 + (있으면) 기초단체장 등 시군구 결과(.sigungu.json) 병합 — 7·8회는 tc4가 별도 파일에 있음.
        const paths = [POLL_ELECTION.results_path];
        if (POLL_ELECTION.results_sigungu_path) paths.push(POLL_ELECTION.results_sigungu_path);
        const parts = await Promise.all(paths.map((p) =>
          getJson(p, { races: [] })));
        const races = parts.flatMap((d) => d.races || []);
        if (races.length) state.actualMaps = PollAdapter.localActualMaps(races);
      } catch (e) {}
    })();
    return actualP;
  }

  // 선택 지역의 실제 결과(전체 후보) — detail 패널·산점도가 mode=result일 때 사용.
  window.actualResultFor = function (sido, sigungu, office) {
    const m = (typeof SIDO_MERGE !== 'undefined') ? SIDO_MERGE : null;
    return sigungu
      ? PollAdapter.localActualSigungu(state.actualMaps, sido, sigungu, office)
      : PollAdapter.localActualSido(state.actualMaps, sido, office, m);
  };

  // 적중률 계산 (시도 단위 — 광역단체장·기초단체장·교육감)
  function accuracyForOffice(office) {
    const maps = state.actualMaps;
    if (!maps) return null;
    const merge = (typeof SIDO_MERGE !== 'undefined') ? SIDO_MERGE : null;
    let match = 0, total = 0;
    if (office === '기초단체장') {
      // sigungu 단위 — 폴 있는 시군구만 비교
      for (const key of Object.keys(maps.bySigungu)) {
        if (!key.endsWith('|기초단체장')) continue;
        const [sd, sgg] = key.split('|');
        const polls = PollAdapter.localSigunguWinner(state.data.polls, sd, sgg, '기초단체장');
        const actual = maps.bySigungu[key];
        if (!polls || !actual || !polls.party || !actual.party) continue;   // 정당 불명 폴은 비교 제외(맵 표시와 일치)
        total++;
        if (samePartyName(polls.party, actual.party)) match++;   // 약칭/정식명 차('민주당'='더불어민주당')는 적중
      }
    } else {
      if (!Object.keys(maps.bySido).length) return null;
      for (const [sido] of Object.entries(SIDO_HEX_LAYOUT)) {
        const polls = PollAdapter.localSidoWinner(state.data.polls, sido, office, merge);
        const actual = maps.bySido[`${sido}|${office}`];
        if (!polls || !actual || !polls.party || !actual.party) continue;   // 정당 불명 폴은 비교 제외(맵 표시와 일치)
        total++;
        if (samePartyName(polls.party, actual.party)) match++;   // 약칭/정식명 차('민주당'='더불어민주당')는 적중
      }
    }
    return total ? { match, total } : null;
  }

  async function setMode(m) {
    state.mode = m;
    document.querySelectorAll('[data-mode]').forEach((b) => {
      b.classList.toggle('is-active', b.dataset.mode === m);
    });
    if (m === 'result') await loadActual();
    setView(state.view);
    if (typeof renderDetail === 'function') renderDetail();
    updateAccuracyBadge();
  }

  function updateAccuracyBadge() {
    const host = document.getElementById('result-accuracy');
    if (!host) return;
    const acc = accuracyForOffice(state.office);
    if (!acc) { host.textContent = ''; return; }
    const pct = ((acc.match / acc.total) * 100).toFixed(0);
    const legend = (state.mode === 'result' && acc.match < acc.total) ? ' <span class="ra-legend">점선 테두리=여론조사 1위 정당</span>' : '';
    host.innerHTML = `여론조사 적중 <b>${acc.match}/${acc.total}</b> <span class="ra-pct">${pct}%</span>${legend}`;
  }

  // 과거 선거 기본 모드(result)일 때 main.js가 첫 렌더 전 실제결과를 미리 로드(빈 화면 깜빡임 방지).
  window.pollEnsureActual = loadActual;

  function init() {
    if (typeof state === 'undefined') return;
    state.mode = state.mode || 'polls';   // core.js가 IS_PAST면 'result'로 이미 설정
    document.querySelectorAll('[data-mode]').forEach((b) => {
      b.addEventListener('click', () => setMode(b.dataset.mode));
      b.classList.toggle('is-active', b.dataset.mode === state.mode);   // 초기 토글 동기화
    });
    // 선거 종료 후 토글 노출
    const past = new Date() >= ELECTION;
    const seg = document.getElementById('mode-seg');
    if (seg) seg.hidden = !past;
    // office 변경 시 적중률 갱신
    const origSetOffice = window.setOffice;
    if (typeof origSetOffice === 'function') {
      window.setOffice = function (o) { origSetOffice(o); updateAccuracyBadge(); };
    }
    if (past) loadActual().then(updateAccuracyBadge);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
