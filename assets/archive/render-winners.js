// 시·도의원·시·군·구의원 당선인 list — 검색/filter UI.
// 9회: NEC live winner (tc=5는 정확, tc=6는 infer_council_winners.py가 추정 magnitude로 top-K won 마킹).
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
      grid.innerHTML = filtered.slice(0, 500).map((w) => {
        const col = (typeof partyColor === 'function') ? partyColor(w.party) : '#999';
        const lvlBadge = w.level === '광역의원' ? '광' : '기';
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

  window.Archive = window.Archive || {};
  window.Archive.winners = { init };
})();
