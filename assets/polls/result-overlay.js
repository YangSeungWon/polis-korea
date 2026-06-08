// 폴 ↔ 실제 결과 토글 — mayor/governor/polls 페이지에서 hex/map을
// '여론조사 1위' vs '실제 NEC 1위' 비교. 선거 종료 후 노출.

(function () {
  const TC_TO_OFFICE = { '3': '광역단체장', '4': '기초단체장', '11': '교육감' };
  let actualBySidoOffice = {};   // "{sido}|{office}" → {party, name, pct}
  let actualBySigunguOffice = {}; // "{sido}|{sigungu}|{office}" → {party, name, pct}
  let loaded = false;

  async function loadActual() {
    if (loaded) return;
    loaded = true;
    try {
      const r = await fetch('data/results/9th-local-2026.json');
      if (!r.ok) return;
      const d = await r.json();
      for (const race of d.races || []) {
        const office = TC_TO_OFFICE[race.sg_typecode];
        if (!office) continue;
        const cands = (race.candidates || []).slice()
          .sort((a, b) => (b.votes || 0) - (a.votes || 0));
        const top = cands[0];
        if (!top) continue;
        const cell = {
          party: top.party,
          name: top.name,
          pct: top.pct,
          n_polls: 1,
          gap: 99,
          effective_gap: 99,
          actual: true,
          candidates: cands.slice(0, 8).map((c) => ({ name: c.name, party: c.party, pct: c.pct, votes: c.votes })),
        };
        if (race.scope === 'sido') {
          actualBySidoOffice[`${race.sido}|${office}`] = cell;
        } else if (race.scope === 'sigungu') {
          actualBySigunguOffice[`${race.sido}|${race.sigungu}|${office}`] = cell;
        }
      }
    } catch (e) {}
  }

  // 기존 lookup 함수를 mode=result일 때 swap
  const _origSido = window.sidoLastWinningParty;
  const _origSigungu = window.sigunguLastWinningParty;
  window.sidoLastWinningParty = function (sido, office) {
    if (state.mode === 'result') {
      // 분리 시도로 못 찾으면 통합키(전남광주특별시) fallback — 2026 지선 통합.
      const merged = (typeof SIDO_MERGE !== 'undefined' && SIDO_MERGE[sido]) ? SIDO_MERGE[sido] : null;
      return actualBySidoOffice[`${sido}|${office}`]
        || (merged && actualBySidoOffice[`${merged}|${office}`])
        || null;
    }
    return _origSido(sido, office);
  };
  window.sigunguLastWinningParty = function (sido, sigungu, office = '기초단체장') {
    if (state.mode === 'result') {
      let v = actualBySigunguOffice[`${sido}|${sigungu}|${office}`];
      if (v) return v;
      // 일반구 → 모도시 fallback (수원시장안구 → 수원시)
      if (typeof parentSigungu === 'function') {
        const p = parentSigungu(sigungu);
        if (p) v = actualBySigunguOffice[`${sido}|${p}|${office}`];
      }
      return v || null;
    }
    return _origSigungu(sido, sigungu, office);
  };
  // 선택 지역의 실제 결과(전체 후보) — detail 패널·산점도가 mode=result일 때 사용.
  window.actualResultFor = function (sido, sigungu, office) {
    if (sigungu) {
      let v = actualBySigunguOffice[`${sido}|${sigungu}|${office}`];
      if (!v && typeof parentSigungu === 'function') {
        const p = parentSigungu(sigungu);
        if (p) v = actualBySigunguOffice[`${sido}|${p}|${office}`];
      }
      return v || null;
    }
    let v = actualBySidoOffice[`${sido}|${office}`];
    if (!v) {
      const m = (typeof SIDO_MERGE !== 'undefined' && SIDO_MERGE[sido]) ? SIDO_MERGE[sido] : null;
      if (m) v = actualBySidoOffice[`${m}|${office}`];
    }
    return v || null;
  };

  // 적중률 계산 (시도 단위 — 광역단체장·기초단체장·교육감)
  function accuracyForOffice(office) {
    let match = 0, total = 0;
    if (office === '기초단체장') {
      // sigungu 단위 — 폴 있는 시군구만 비교
      for (const key of Object.keys(actualBySigunguOffice)) {
        if (!key.endsWith('|기초단체장')) continue;
        const [sd, sgg] = key.split('|');
        const polls = _origSigungu(sd, sgg, '기초단체장');
        const actual = actualBySigunguOffice[key];
        if (!polls || !actual) continue;
        total++;
        if (polls.party === actual.party) match++;
      }
    } else {
      if (!Object.keys(actualBySidoOffice).length) return null;
      for (const [sido] of Object.entries(SIDO_HEX_LAYOUT)) {
        if (sido === '전라북도') continue;
        const polls = _origSido(sido, office);
        const actual = actualBySidoOffice[`${sido}|${office}`];
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
