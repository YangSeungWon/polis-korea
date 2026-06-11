// 시·도의원·시·군·구의원 당선인 list — 검색/filter UI.
// 기초의원(tc=6 지역구·tc=9 비례)은 NEC 확정 당선인 명부로 회수 — 9회 EPEI01 라이브,
// 5~8회 OpenAPI (fetch_council_winners_live/_winners/_prop). 추정 아님. docs/local-seats-provenance.md
// 8회 이전: 위키 inject는 정당별 의석만 — 개별 명단 없음 → list 표시 안 됨.

(function () {
  function init(ctx) {
    const host = document.getElementById('ar-winners-section');
    if (!host) return;
    const races = ctx?.results?.races || [];
    // tc=5/6 race winners
    const winners = [];
    for (const r of races) {
      if (!['5', '6'].includes(r.sg_typecode)) continue;
      if (r.scope !== 'district') continue;
      const level = r.sg_typecode === '5' ? '광역의원' : '기초의원';
      for (const c of r.candidates || []) {
        if (!c.won) continue;
        winners.push({
          level,
          sido: r.sido || '',
          district: r.district || r.sigungu || '',
          name: c.name,
          party: c.party || '무소속',
          pct: c.pct,
        });
      }
    }
    if (winners.length === 0) {
      host.setAttribute('hidden', '');
      return;
    }
    host.removeAttribute('hidden');
    const body = document.getElementById('ar-winners-body');
    if (!body) return;

    const SIDO_ORDER = [
      '서울특별시', '부산광역시', '대구광역시', '인천광역시', '광주광역시',
      '대전광역시', '울산광역시', '세종특별자치시',
      '경기도', '강원특별자치도', '충청북도', '충청남도',
      '전북특별자치도', '전라남도', '경상북도', '경상남도', '제주특별자치도',
    ];
    const parties = Array.from(new Set(winners.map((w) => w.party))).sort();
    // 지역(시도)순 → 직급(광역<기초) → 선거구. 필터 시 그 지역의 광역·기초가 함께 정렬돼 나옴.
    const sidoIdx = (s) => { const i = SIDO_ORDER.indexOf(s); return i < 0 ? 99 : i; };
    winners.sort((a, b) => sidoIdx(a.sido) - sidoIdx(b.sido)
      || a.level.localeCompare(b.level)
      || (a.district || '').localeCompare(b.district || '', 'ko'));

    // filter controls
    const ctrl = document.createElement('div');
    ctrl.className = 'ar-winners-controls';
    ctrl.innerHTML = `
      <input type="search" id="ar-winners-q" placeholder="이름·선거구 검색" autocomplete="off">
      <select id="ar-winners-sido">
        <option value="">전 시도</option>
        ${SIDO_ORDER.filter((s) => winners.some((w) => w.sido === s)).map((s) => `<option value="${s}">${s}</option>`).join('')}
      </select>
      <select id="ar-winners-party">
        <option value="">전 정당</option>
        ${parties.map((p) => `<option value="${p}">${p}</option>`).join('')}
      </select>
      <select id="ar-winners-level">
        <option value="">광역+기초</option>
        <option value="광역의원">광역의원</option>
        <option value="기초의원">기초의원</option>
      </select>
      <span class="ar-winners-count" id="ar-winners-count"></span>
    `;
    body.innerHTML = '';
    body.appendChild(ctrl);
    const grid = document.createElement('div');
    grid.className = 'ar-winners-grid';
    body.appendChild(grid);

    function render() {
      const q = document.getElementById('ar-winners-q').value.trim().toLowerCase();
      const sido = document.getElementById('ar-winners-sido').value;
      const party = document.getElementById('ar-winners-party').value;
      const level = document.getElementById('ar-winners-level').value;
      const filtered = winners.filter((w) => {
        if (sido && w.sido !== sido) return false;
        if (party && w.party !== party) return false;
        if (level && w.level !== level) return false;
        if (q && !`${w.name} ${w.district}`.toLowerCase().includes(q)) return false;
        return true;
      });
      document.getElementById('ar-winners-count').textContent = `${filtered.length}명`;
      // 필터 없으면 2,661명 통째 dump 대신 안내(지도 클릭·검색 유도) — 광역의원만 500개 깔리는 문제 방지.
      if (!(q || sido || party || level)) {
        grid.innerHTML = `<div class="ar-winners-hint">총 <b>${winners.length.toLocaleString()}명</b>. 위 <b>지도(시·도의회·시군구의회 hex)</b>를 클릭하거나, 검색·시도·정당·직급으로 좁혀 보세요.</div>`;
        return;
      }
      grid.innerHTML = filtered.slice(0, 500).map((w) => {
        const col = (typeof partyColor === 'function') ? partyColor(w.party) : '#999';
        const lvlBadge = w.level === '광역의원' ? '광역' : '기초';
        return `<div class="ar-winner-row" style="border-left:3px solid ${col}">
          <span class="ar-winner-lvl">${lvlBadge}</span>
          <span class="ar-winner-loc">${w.sido.replace(/(특별|광역|특별자치)?(시|도)/, '$2')} ${w.district}</span>
          <span class="ar-winner-name">${w.name}</span>
          <span class="ar-winner-party" style="color:${col}">${w.party}</span>
          ${w.pct != null ? `<span class="ar-winner-pct">${w.pct.toFixed(1)}%</span>` : ''}
        </div>`;
      }).join('') + (filtered.length > 500 ? `<div class="ar-winners-more">… ${filtered.length - 500}명 추가 (검색·filter로 좁히세요)</div>` : '');
    }
    for (const id of ['ar-winners-q', 'ar-winners-sido', 'ar-winners-party', 'ar-winners-level']) {
      const el = document.getElementById(id);
      el.addEventListener('input', render);
      el.addEventListener('change', render);
    }
    render();
  }

  // hex 클릭 등 외부에서 호출 — 지역(sido)·검색어(q·시군구명)·직급(level)로 필터 + 스크롤.
  function focus({ sido, q, level } = {}) {
    const host = document.getElementById('ar-winners-section');
    if (!host || host.hasAttribute('hidden')) return;
    const sidoEl = document.getElementById('ar-winners-sido');
    const qEl = document.getElementById('ar-winners-q');
    const lvlEl = document.getElementById('ar-winners-level');
    const partyEl = document.getElementById('ar-winners-party');
    if (!sidoEl) return;
    // sido 옵션에 있으면 설정(없으면 전체 — q·level로만 필터).
    sidoEl.value = (sido && [...sidoEl.options].some((o) => o.value === sido)) ? sido : '';
    if (qEl) qEl.value = q || '';
    if (lvlEl) lvlEl.value = level || '';
    if (partyEl) partyEl.value = '';
    (qEl || sidoEl).dispatchEvent(new Event('input', { bubbles: true }));  // render() 트리거
    host.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  window.Archive = window.Archive || {};
  window.Archive.winners = { init, focus };
})();
