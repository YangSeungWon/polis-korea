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

// utils.js의 PARTY_SHORT (현행 정당)에 옛 정당 추가 (시간축 1987~ 커버).
// timeline.html이 utils.js 다음에 로드되므로 redeclare 대신 Object.assign.
Object.assign(PARTY_SHORT, {
  '국민의미래': '국힘비례', '더불어민주연합': '민주비례',
  '새누리당': '새누리', '새정치민주연합': '새정치', '한나라당': '한나라',
  '민주노동당': '민노', '자유한국당': '한국', '바른미래당': '바른',
  '새천년민주당': '새천년', '열린우리당': '열우',
  '민주통합당': '민통', '민주당': '민주', '통합진보당': '통진',
  '국민회의': '국민', '자민련': '자민련', '민자당': '민자',
  '신한국당': '신한국', '한나라당계열': '한나라', '새정치국민회의': '국민회의',
  '기타': '기타',
});

// 회차 단위 100% stacked bar 데이터 — kind별로 다른 데이터 source.
function buildStackForRound(r) {
  let parts = [];
  if (r.kind === 'presidential' && r.presCandidates?.length) {
    // 대선: 후보 득표율
    parts = r.presCandidates.slice(0, 6).map((c) => ({
      party: c.party,
      value: c.pct || 0,
      label: `${c.pct?.toFixed(1) || 0}% (${c.name || '?'})`,
      short: PARTY_SHORT[c.party] || c.party.slice(0, 2),
    }));
  } else if (r.kind === 'national_assembly' && r.partySeats?.length) {
    // 총선: 정당별 의석
    parts = r.partySeats.map(([party, seats]) => ({
      party, value: seats,
      label: `${seats}석`,
      short: PARTY_SHORT[party] || party.slice(0, 2),
    }));
  } else if (r.kind === 'local' && r.sidoWinners) {
    // 지선: 광역단체장 정당별 시도 수
    const counter = {};
    for (const sido of Object.keys(r.sidoWinners)) {
      const w = r.sidoWinners[sido];
      if (w?.party) counter[w.party] = (counter[w.party] || 0) + 1;
    }
    parts = Object.entries(counter)
      .sort((a, b) => b[1] - a[1])
      .map(([party, n]) => ({
        party, value: n,
        label: `${n}곳`,
        short: PARTY_SHORT[party] || party.slice(0, 2),
      }));
  }
  const total = parts.reduce((s, p) => s + p.value, 0);
  return { parts, total };
}

function loadJson(p) {
  return fetch(p).then((r) => r.json());
}

(async function init() {
  const data = await loadJson('data/timeline.json');
  const rounds = data.rounds || [];
  $('#loading').hidden = true;
  const root = $('#tl-table');
  root.hidden = false;

  // (헤더 row 제거 — 시도 약칭 헤더는 stacked bar 구조에서 의미 없음.)

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

    // 종류별 100% stacked bar — 회차의 의미 있는 분포 표시.
    // 대선: 후보 득표율 / 총선: 정당별 의석 / 지선: 광역단체장 정당별 시도 수.
    const sidosBox = document.createElement('div');
    sidosBox.className = 'tl-sidos';
    const stack = buildStackForRound(r);
    if (stack.parts.length) {
      for (const p of stack.parts) {
        const seg = document.createElement('span');
        seg.className = 'tl-stack-seg';
        const col = (typeof partyColor === 'function') ? partyColor(p.party) : '#999';
        seg.style.flexGrow = String(p.value);
        seg.style.background = col;
        seg.title = `${p.party} ${p.label}`;
        // 큰 segment는 안에 정당 약칭
        if (p.value / stack.total >= 0.12) {
          seg.textContent = p.short || p.party;
        }
        sidosBox.appendChild(seg);
      }
    } else {
      sidosBox.classList.add('is-empty');
      sidosBox.textContent = r.upcoming ? '' : '';
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
