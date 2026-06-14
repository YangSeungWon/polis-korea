// 폴 ↔ 실제 결과 토글 — mayor/governor/polls 페이지에서 hex/map을
// '여론조사 1위' vs '실제 NEC 1위' 비교. 선거 종료 후 노출.

(function () {
  let loaded = false;

  // 실제 결과(NEC) → 1위 맵 빌드는 PollAdapter.localActualMaps. state.actualMaps에 저장.
  // (모드별 swap은 core.js regionSidoWinner/regionSigunguWinner가 주입 — 옛 몽키패치 제거.)
  async function loadActual() {
    if (loaded) return;
    loaded = true;
    try {
      const r = await fetch(POLL_ELECTION.results_path);
      if (!r.ok) return;
      const d = await r.json();
      state.actualMaps = PollAdapter.localActualMaps(d.races || []);
    } catch (e) {}
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
        if (!polls || !actual) continue;
        total++;
        if (polls.party === actual.party) match++;
      }
    } else {
      if (!Object.keys(maps.bySido).length) return null;
      for (const [sido] of Object.entries(SIDO_HEX_LAYOUT)) {
        const polls = PollAdapter.localSidoWinner(state.data.polls, sido, office, merge);
        const actual = maps.bySido[`${sido}|${office}`];
        if (!polls || !actual) continue;
        total++;
        if (polls.party === actual.party) match++;
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
    host.innerHTML = `여론조사 적중 <b>${acc.match}/${acc.total}</b> <span class="ra-pct">${pct}%</span>`;
  }

  function init() {
    if (typeof state === 'undefined') return;
    state.mode = state.mode || 'polls';
    document.querySelectorAll('[data-mode]').forEach((b) => {
      b.addEventListener('click', () => setMode(b.dataset.mode));
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
