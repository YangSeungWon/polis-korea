// chronology.html — 한국 근현대사 연표 (공화국·개헌·항쟁·정변 + 역대 선거 하이퍼링크)

const $ = (s) => document.querySelector(s);
const KIND_KO = { presidential: '대선', national_assembly: '총선', local: '지선' };
const KIND_UNIT = { presidential: '대', national_assembly: '대', local: '회' };
const TAG_CLASS = {
  국가: 'tg-state', 전쟁: 'tg-war', 개헌: 'tg-amend', 항쟁: 'tg-revolt',
  정변: 'tg-coup', 탄핵: 'tg-impeach', 경제: 'tg-econ',
};
const WIKI = 'https://ko.wikipedia.org/wiki/';

function yearOf(d) { return (d || '').slice(0, 4); }
function mdOf(d) {
  const m = (d || '').slice(5).replace('-', '.');
  return m && m !== '01.01' ? m : '';
}

(async function init() {
  const [ev, el] = await Promise.all([
    fetch('data/history_events.json').then((r) => r.json()),
    fetch('data/elections.json').then((r) => r.json()),
  ]);

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
  const reps = (ev.republics || []).slice().sort((a, b) => a.start.localeCompare(b.start));

  $('#loading').hidden = true;
  const root = $('#chrono');
  root.hidden = false;

  let repIdx = -1;
  for (const it of items) {
    while (repIdx + 1 < reps.length && it.date >= reps[repIdx + 1].start) {
      repIdx++;
      root.appendChild(repHeader(reps[repIdx]));
    }
    root.appendChild(it.type === 'election' ? electionRow(it) : eventRow(it));
  }

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

function electionRow(it) {
  const row = document.createElement('div');
  row.className = 'chr-row chr-election';
  row.dataset.type = 'election';
  const md = mdOf(it.date);
  const col = (typeof partyColor === 'function' && it.party) ? partyColor(it.party, it.date) : '#9aa3b3';
  const num = `${it.n}${KIND_UNIT[it.kind]} ${KIND_KO[it.kind]}`;
  const marks = (it.indirect ? '<span class="chr-mk ind">간선</span>' : '')
    + (it.annulled ? '<span class="chr-mk ann">무효</span>' : '');
  const winner = it.winner ? `<span class="chr-winner">${it.winner}</span>` : '';
  const href = `history.html?type=${it.kind}&n=${it.n}`;
  row.innerHTML = `<span class="chr-date"><b>${yearOf(it.date)}</b>${md ? `<small>${md}</small>` : ''}</span>`
    + `<span class="chr-node" style="--pc:${col}"></span>`
    + `<a class="chr-body chr-link" href="${href}">`
    + `<span class="chr-dot" style="background:${col}"></span>`
    + `<span class="chr-num">${it.btn ? it.btn + ' ' : ''}${num}</span>${marks}${winner}`
    + `<span class="chr-go">→</span></a>`;
  return row;
}
