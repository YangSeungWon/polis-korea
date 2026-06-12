// chronology.html — 한국 근현대사 연표 (공화국·개헌·항쟁·정변 + 역대 선거 하이퍼링크)

const $ = (s) => document.querySelector(s);
const KIND_KO = { presidential: '대선', national_assembly: '총선', local: '지선' };
const KIND_UNIT = { presidential: '대', national_assembly: '대', local: '회' };
const TAG_CLASS = {
  국가: 'tg-state', 전쟁: 'tg-war', 개헌: 'tg-amend', 항쟁: 'tg-revolt',
  정변: 'tg-coup', 탄핵: 'tg-impeach', 경제: 'tg-econ',
};
const WIKI = 'https://ko.wikipedia.org/wiki/';

// 회차 키 — 같은 n에 변형(4대 3·15 무효·윤보선 간선)이 있어 flag로 구분.
const keyOf = (x) => `${x.kind}|${x.n}|${x.annulled ? 'a' : x.indirect ? 'i' : ''}`;

function yearOf(d) { return (d || '').slice(0, 4); }
function mdOf(d) {
  const m = (d || '').slice(5).replace('-', '.');
  return m && m !== '01.01' ? m : '';
}

(async function init() {
  const [ev, el, tl] = await Promise.all([
    fetch('data/history_events.json').then((r) => r.json()),
    fetch('data/elections.json').then((r) => r.json()),
    fetch('data/timeline.json').then((r) => r.json()).catch(() => ({ rounds: [] })),
  ]);
  // 총선=최다의석당, 지선=최다 광역단체장 당 + 결과 바. (대선은 후보 득표율 바)
  // 4대 대선처럼 같은 n에 둘(3·15 무효·윤보선 간선)이면 flag로 구분.
  const tlByKey = {};
  for (const r of (tl.rounds || [])) tlByKey[keyOf(r)] = r;

  // 선거 flatten (대선·총선·지선) — 날짜 있는 것만, 미래/예측 제외
  const elections = [];
  for (const kind of ['presidential', 'national_assembly', 'local']) {
    for (const x of (el[kind]?.elections || [])) {
      if (!x.date || x.predicted) continue;
      elections.push({
        type: 'election', kind, n: x.n, variant: x.variant || null, date: x.date,
        winner: x.winner, party: x.winner_party, indirect: x.indirect, annulled: x.annulled,
        btn: x.btn,
      });
    }
  }
  const events = (ev.events || []).map((e) => ({ type: 'event', date: e.date, title: e.title, tag: e.tag, wiki: e.wiki }));
  // 같은 날짜는 사건 먼저(맥락) → 선거
  const items = [...events, ...elections].sort((a, b) =>
    a.date.localeCompare(b.date) || (a.type === 'event' ? -1 : 1));
  // 시대 구분: 공화국(상위) + 정부(제6공화국 하위, 행정부) — 시작일순 병합
  const dividers = [
    ...(ev.republics || []).map((r) => ({ k: 'rep', date: r.start, data: r })),
    ...(ev.governments || []).map((g) => ({ k: 'gov', date: g.start, data: g })),
  ].sort((a, b) => a.date.localeCompare(b.date) || (a.k === 'rep' ? -1 : 1));

  $('#loading').hidden = true;
  const root = $('#chrono');
  root.hidden = false;

  let di = 0;
  const emitDividers = (upto) => {
    while (di < dividers.length && dividers[di].date <= upto) {
      const dv = dividers[di++];
      root.appendChild(dv.k === 'rep' ? repHeader(dv.data) : govHeader(dv.data));
    }
  };
  for (const it of items) {
    emitDividers(it.date);
    root.appendChild(it.type === 'election' ? electionRow(it, tlByKey) : eventRow(it));
  }
  emitDividers('9999');  // 마지막 항목 뒤 시대(예: 국민주권정부 출범 후) 처리

  // 필터 (전체/선거/사건) — 행·헤더 토글
  document.querySelectorAll('[data-filter]').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-filter]').forEach((b) => b.classList.toggle('is-active', b === btn));
      const f = btn.dataset.filter;
      root.querySelectorAll('.chr-row').forEach((row) => {
        row.classList.toggle('is-hidden', f !== 'all' && row.dataset.type !== f);
      });
    });
  });
})();

function repHeader(rep) {
  const d = document.createElement('div');
  d.className = 'chr-era';
  d.dataset.type = 'era';
  d.innerHTML = `<span class="chr-era-yr">${yearOf(rep.start)}</span>`
    + `<span class="chr-era-name">${rep.name}</span>`
    + (rep.note ? `<span class="chr-era-note">${rep.note}</span>` : '');
  return d;
}

function govHeader(g) {
  // 정부(행정부) 하위 구분 — 제6공화국이 길어(1987~현행) 정부별로 쪼갬. 정당색 마디.
  const d = document.createElement('div');
  d.className = 'chr-gov';
  d.dataset.type = 'era';
  const col = (typeof partyColor === 'function' && g.party) ? partyColor(g.party, g.start) : 'var(--rule-strong)';
  d.style.setProperty('--gc', col);
  const name = g.wiki
    ? `<a class="chr-gov-name chr-wiki" href="${WIKI}${encodeURIComponent(g.wiki)}" target="_blank" rel="noopener">${g.name}<span class="chr-ext">↗</span></a>`
    : `<span class="chr-gov-name">${g.name}</span>`;
  d.innerHTML = `<span class="chr-gov-yr">${yearOf(g.start)}</span>${name}`
    + (g.president ? `<span class="chr-gov-pres">${g.president}</span>` : '');
  return d;
}

function eventRow(it) {
  const row = document.createElement('div');
  row.className = 'chr-row chr-event';
  row.dataset.type = 'event';
  const md = mdOf(it.date);
  const tag = it.tag ? `<span class="chr-tag ${TAG_CLASS[it.tag] || ''}">${it.tag}</span>` : '';
  // 위키 문서 있으면 사건명 = 외부 링크('알아서 찾아보세요'). 없으면 라벨만.
  const body = it.wiki
    ? `<a class="chr-body chr-wiki" href="${WIKI}${encodeURIComponent(it.wiki)}" target="_blank" rel="noopener">`
      + `${tag}<span class="chr-title">${it.title}</span><span class="chr-ext">↗</span></a>`
    : `<span class="chr-body">${tag}<span class="chr-title">${it.title}</span></span>`;
  row.innerHTML = `<span class="chr-date"><b>${yearOf(it.date)}</b>${md ? `<small>${md}</small>` : ''}</span>`
    + `<span class="chr-node"></span>${body}`;
  return row;
}

// 총선=최다 의석당, 지선=최다 광역단체장 당 → {party, detail}. 대선은 null(winner 사용).
function leadInfo(it, tlByKey) {
  const r = tlByKey[keyOf(it)];
  if (!r) return null;
  if (it.kind === 'national_assembly' && r.partySeats?.length) {
    const [party, seats] = r.partySeats[0];
    return { party, detail: `${party} ${seats}석` };
  }
  if (it.kind === 'local' && r.sidoWinners) {
    const counts = {};
    for (const v of Object.values(r.sidoWinners)) {
      if (v?.party) counts[v.party] = (counts[v.party] || 0) + 1;
    }
    const top = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
    if (top) return { party: top[0], detail: `${top[0]} ${top[1]}곳` };
  }
  return null;
}

// 작은 100% 결과 바 — 대선=후보 득표율, 총선=정당 의석, 지선=광역단체장 정당별 시도 수.
function resultBar(it, tlByKey) {
  const r = tlByKey[keyOf(it)];
  if (!r) return '';
  let segs = [];
  if (it.kind === 'presidential' && r.presCandidates?.length) {
    segs = r.presCandidates.slice(0, 6).map((c) => ({ party: c.party, val: c.pct || 0 }));
  } else if (it.kind === 'national_assembly' && r.partySeats?.length) {
    segs = r.partySeats.slice(0, 8).map(([p, s]) => ({ party: p, val: s }));
  } else if (it.kind === 'local' && r.sidoWinners) {
    const c = {};
    for (const v of Object.values(r.sidoWinners)) if (v?.party) c[v.party] = (c[v.party] || 0) + 1;
    segs = Object.entries(c).sort((a, b) => b[1] - a[1]).map(([p, n]) => ({ party: p, val: n }));
  }
  const total = segs.reduce((s, x) => s + x.val, 0);
  if (!total) return '';
  const inner = segs.filter((s) => s.val > 0).map((s) => {
    const col = (typeof partyColor === 'function') ? partyColor(s.party, it.date) : '#999';
    return `<span style="flex:${s.val};background:${col}" title="${s.party}"></span>`;
  }).join('');
  return `<span class="chr-bar" aria-hidden="true">${inner}</span>`;
}

function electionRow(it, tlByKey) {
  const row = document.createElement('div');
  row.className = 'chr-row chr-election';
  row.dataset.type = 'election';
  const md = mdOf(it.date);
  // 대선=당선자·소속당색 / 총선·지선=우세 정당색·정당명(분위기)
  let party = it.party, detail = it.winner ? `<span class="chr-winner">${it.winner}</span>` : '';
  if (it.kind !== 'presidential') {
    const li = leadInfo(it, tlByKey);
    if (li) { party = li.party; detail = `<span class="chr-winner chr-lead">${li.detail}</span>`; }
  }
  const col = (typeof partyColor === 'function' && party) ? partyColor(party, it.date) : '#9aa3b3';
  const num = `${it.n}${KIND_UNIT[it.kind]} ${KIND_KO[it.kind]}`;
  const marks = (it.indirect ? '<span class="chr-mk ind">간선</span>' : '')
    + (it.annulled ? '<span class="chr-mk ann">무효</span>' : '');
  const href = `history.html?type=${it.kind}&n=${it.n}`;
  row.innerHTML = `<span class="chr-date"><b>${yearOf(it.date)}</b>${md ? `<small>${md}</small>` : ''}</span>`
    + `<span class="chr-node" style="--pc:${col}"></span>`
    + `<a class="chr-body chr-link" href="${href}">`
    + `<span class="chr-dot" style="background:${col}"></span>`
    + `<span class="chr-num">${it.btn ? it.btn + ' ' : ''}${num}</span>${marks}${detail}`
    + resultBar(it, tlByKey)
    + `<span class="chr-go">→</span></a>`;
  return row;
}
