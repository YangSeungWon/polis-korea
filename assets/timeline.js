// timeline.html — 역대 선거 시도별 1위 정당 그리드

const $ = (s) => document.querySelector(s);

// 시도 column 순서 (수도권 → 충청 → 호남 → 영남 → 제주, 권역 내 행정구역 순)
const SIDO_ORDER = [
  '서울특별시', '인천광역시', '경기도', '강원특별자치도',
  '세종특별자치시', '대전광역시', '충청북도', '충청남도',
  '광주광역시', '전북특별자치도', '전라남도',
  '대구광역시', '부산광역시', '울산광역시', '경상북도', '경상남도',
  '제주특별자치도',
];

const KIND_LABEL = {
  presidential: { ko: '대선', cls: 'pres' },
  national_assembly: { ko: '총선', cls: 'gen' },
  local: { ko: '지선', cls: 'local' },
};

const TYPE_SLUG = {
  presidential: 'presidential',
  national_assembly: 'national_assembly',
  local: 'local',
};

function loadJson(p) {
  return fetch(p).then((r) => r.json());
}

(async function init() {
  const data = await loadJson('data/timeline.json');
  const rounds = data.rounds || [];
  $('#loading').hidden = true;
  const root = $('#tl-table');
  root.hidden = false;

  // 헤더 row — 시도 약칭
  const header = document.createElement('div');
  header.className = 'tl-header';
  const emptyL = document.createElement('div');
  emptyL.className = 'tl-header-empty';
  const sidos = document.createElement('div');
  sidos.className = 'tl-header-sidos';
  for (const s of SIDO_ORDER) {
    const span = document.createElement('span');
    span.textContent = (typeof SIDO_LABEL_SHORT !== 'undefined') ? (SIDO_LABEL_SHORT[s] || s) : s;
    sidos.appendChild(span);
  }
  const emptyR = document.createElement('div');
  header.appendChild(emptyL); header.appendChild(sidos); header.appendChild(emptyR);
  root.appendChild(header);

  // 회차 row들 (시간 역순 — 최근 위)
  const sorted = [...rounds].sort((a, b) => b.date.localeCompare(a.date));
  for (const r of sorted) {
    const row = document.createElement('div');
    row.className = 'tl-row';
    row.dataset.kind = r.kind;

    // 좌측 라벨
    const meta = document.createElement('div');
    meta.className = 'tl-meta';
    const lbl = document.createElement('div');
    lbl.className = 'tl-label';
    const tag = document.createElement('span');
    tag.className = `tl-kind ${KIND_LABEL[r.kind].cls}`;
    tag.textContent = KIND_LABEL[r.kind].ko;
    lbl.appendChild(tag);
    const num = document.createElement('span');
    num.textContent = `${r.n}회`;
    lbl.appendChild(num);
    const date = document.createElement('div');
    date.className = 'tl-date';
    date.textContent = r.date;
    meta.appendChild(lbl);
    meta.appendChild(date);

    // 시도 cells
    const sidosBox = document.createElement('div');
    sidosBox.className = 'tl-sidos';
    for (const s of SIDO_ORDER) {
      const cell = document.createElement('div');
      const winner = (r.sidoWinners || {})[s];
      if (winner && winner.party) {
        cell.className = 'tl-sido-cell';
        const color = (typeof partyColor === 'function') ? partyColor(winner.party) : '#999';
        cell.style.background = color;
        cell.title = `${s} · ${winner.party} ${winner.pct?.toFixed(1) || ''}%`;
      } else {
        cell.className = 'tl-sido-cell no-data';
        cell.title = `${s} · 데이터 없음`;
      }
      sidosBox.appendChild(cell);
    }

    // 우측 meta
    const right = document.createElement('div');
    right.className = 'tl-right';
    if (r.upcoming) {
      const tag = document.createElement('div');
      tag.className = 'tl-upcoming-tag';
      tag.textContent = r.predicted ? '예측' : '예정';
      right.appendChild(tag);
    } else {
      if (r.winner) {
        const w = document.createElement('div');
        w.className = 'tl-winner';
        w.textContent = r.winner;
        right.appendChild(w);
      }
      if (r.turnout != null) {
        const t = document.createElement('div');
        t.textContent = `투표율 ${r.turnout.toFixed(1)}%`;
        right.appendChild(t);
      }
    }

    if (r.upcoming) row.classList.add('is-upcoming');

    // 클릭 → 그 회차 history 페이지 (upcoming은 클릭 비활성)
    if (!r.upcoming) {
      row.style.cursor = 'pointer';
      row.addEventListener('click', () => {
        const slug = TYPE_SLUG[r.kind];
        location.href = `history.html?type=${slug}&n=${r.n}`;
      });
    }

    row.appendChild(meta);
    row.appendChild(sidosBox);
    row.appendChild(right);
    root.appendChild(row);
  }

  // 필터
  document.querySelectorAll('[data-filter]').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-filter]').forEach((b) =>
        b.classList.toggle('is-active', b === btn));
      const f = btn.dataset.filter;
      document.querySelectorAll('.tl-row').forEach((row) => {
        if (!row.dataset.kind) return;  // 헤더 row 무시
        row.classList.toggle('is-dimmed', f !== 'all' && row.dataset.kind !== f);
      });
    });
  });
})();
