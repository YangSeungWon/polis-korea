// history.js entry — 회차 chrome · renderAll · detail pane · init.
// 마지막에 로드: state·routing·data·render-* 모두 정의된 후 init() 호출.

function renderHistoryLegend() {
  // detail-pane 안에 있었다가 회차/종류 전환 시 함께 지워질 수 있어 — 없으면 재생성.
  let el = $('#history-legend');
  if (!el) {
    const viz = document.querySelector('.viz');
    if (!viz) return;
    el = document.createElement('div');
    el.id = 'history-legend';
    el.className = 'hist-legend';
    el.hidden = true;
    viz.appendChild(el);
  }
  const type = state.type;
  // 총선은 기본 범례 없음. 단 옛총선 geo에 보로노이 추정 경계(점선)가 있으면 그 설명만 표시.
  if (type === 'national_assembly') {
    const feats = state.geoCache?.[state.n]?.features || [];
    const hasApprox = state.effDisplay === 'geo' && feats.some((f) => f.properties?.approx);
    if (hasApprox) {
      // .viz는 display:flex(가로)라 그 안에 두면 지도·detail 사이 칸으로 끼어 어색.
      // .viz 바로 아래(전체폭 행)로 빼서 '지도 아래 범례'로.
      const viz = document.querySelector('.viz');
      if (viz) viz.insertAdjacentElement('afterend', el);
      el.hidden = false;
      el.innerHTML = '<span class="leg-item"><span class="leg-dash"></span>점선 = 추정 경계 (갑·을 등 다인선거구 분할)</span>';
    } else {
      el.hidden = true; el.innerHTML = '';
    }
    return;
  }
  // 대선은 detail-pane(우측 그래프) 아래로 이동, 그 외는 viz 안 기본 위치
  const detailPane = $('#detail-pane');
  const vizParent = detailPane?.parentElement;
  if (type === 'presidential' && detailPane && el.parentElement !== detailPane) {
    detailPane.appendChild(el);
  } else if (type !== 'presidential' && vizParent && el.parentElement !== vizParent) {
    vizParent.insertBefore(el, detailPane);
  }
  const parties = new Set();
  if (type === 'presidential') {
    // 시군구별 1위 정당
    for (const r of (state.results?.sigungu || [])) {
      const w = (r.candidates || [])[0];
      if (w?.party) parties.add(w.party);
    }
  } else if (type === 'local') {
    // 광역단체장은 sido, 기초단체장은 sigungu
    const list = (state.results?.sido || []).concat(state.results?.sigungu || []);
    for (const r of list) {
      const w = (r.candidates || [])[0];
      if (w?.party) parties.add(w.party);
    }
  }
  if (!parties.size) {
    el.hidden = true; el.innerHTML = ''; return;
  }
  // 등장 순 정렬 (가나다순)
  const sorted = [...parties].sort((a, b) => a.localeCompare(b, 'ko'));
  el.hidden = false;
  el.innerHTML = sorted.map((p) =>
    `<span class="leg-item"><span class="leg-dot" style="background:${partyColor(p)}"></span>${p}</span>`
  ).join('') + '<span class="leg-item"><span class="leg-dot" style="background:#9aa3b3"></span>데이터 없음</span>';
}

// 간선 대선 — 지도 대신 선거 방식·선거인 득표 정보 카드.
function renderIndirectCard(el, nat) {
  const cands = (nat?.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
  const total = cands.reduce((s, c) => s + (c.votes || 0), 0);
  const rows = cands.slice(0, 12).map((c) => {
    const pct = total ? (c.votes / total * 100) : 0;
    const col = (typeof partyColor === 'function') ? partyColor(c.party, el.date) : '#999';
    return `<div class="ind-row">
      <span class="ind-name">${c.name}${c.party && c.party !== '무소속' ? ` <small>${c.party}</small>` : ''}</span>
      <span class="ind-bar"><span style="width:${pct.toFixed(1)}%;background:${col}"></span></span>
      <span class="ind-pct">${(c.votes || 0).toLocaleString()}<small> (${pct.toFixed(1)}%)</small></span>
    </div>`;
  }).join('');
  const kind = el.indirect_kind || '간접선거';
  const elec = total ? `선거인 ${total.toLocaleString()}명` : '';
  return `<div class="indirect-card">
    <div class="ind-badge">간접선거 · ${kind}</div>
    <h3>${el.n}대 대통령선거 <span class="ind-date">${el.date || ''}</span></h3>
    <p class="ind-note">국민 직접투표가 아니라 <b>${kind}</b>가 대통령을 선출했습니다.
      지역별(시·도/시·군·구) 개표가 없습니다. ${elec}</p>
    <div class="ind-winner">당선 <b>${el.winner || ''}</b>${el.winner_party ? ` <small>${el.winner_party}</small>` : ''}</div>
    <div class="ind-rows">${rows}</div>
  </div>`;
}

// 옛 총선 — 지도 대신 지역구 당선 정당별 의석 카드.
function renderSeatsCard(el, district) {
  const seats = new Map();
  for (const d of district || []) {
    const wins = (d.winners && d.winners.length) ? d.winners : (d.winner_party ? [{ party: d.winner_party }] : []);
    for (const w of wins) if (w.party) seats.set(w.party, (seats.get(w.party) || 0) + 1);
  }
  const parties = [...seats.entries()].sort((a, b) => b[1] - a[1]);
  const total = parties.reduce((s, p) => s + p[1], 0);
  const rows = parties.slice(0, 14).map(([p, n]) => {
    const pct = total ? (n / total * 100) : 0;
    const col = (typeof partyColor === 'function') ? partyColor(p, el.date) : '#999';
    return `<div class="ind-row">
      <span class="ind-name">${p}</span>
      <span class="ind-bar"><span style="width:${pct.toFixed(1)}%;background:${col}"></span></span>
      <span class="ind-pct">${n}석<small> (${pct.toFixed(1)}%)</small></span>
    </div>`;
  }).join('');
  return `<div class="indirect-card">
    <div class="ind-badge" style="background:#2d6e7e">옛 총선 · 지역구 지도 없음</div>
    <h3>${el.n}대 국회의원선거 <span class="ind-date">${el.date || ''}</span></h3>
    <p class="ind-note">옛 회차라 선거구 경계 지도가 없습니다. 지역구 당선 <b>정당별 의석</b> (총 ${total}석):</p>
    <div class="ind-rows">${rows}</div>
    ${el.note ? `<p class="ind-extra">📌 ${el.note}</p>` : ''}
  </div>`;
}

// 현재 단위에 맞는 hex 렌더 + detail
async function renderAll() {
  const unit = activeUnit(state.type, state.office, state.results);
  // 간선 카드 — 전용 컨테이너(#indirect-card)에 그린다. 매 렌더 시작에 숨김·비움해 회차 전환 시
  // 잔류 방지. (#geomap에 직접 주입하면 Leaflet 지도 컨테이너가 망가지고 다른 회차로 가도 안 지워짐.)
  let icard = document.getElementById('indirect-card');
  if (!icard && $('#geomap')) {
    icard = document.createElement('div');
    icard.id = 'indirect-card';
    $('#geomap').after(icard);
  }
  if (icard) { icard.hidden = true; icard.innerHTML = ''; }
  // 간선(국회·통대·선거인단) 대선 — 지역별 개표가 없어 지도 대신 "어떤 선거였는지" 정보 카드.
  const elMeta0 = currentEl();
  if (state.type === 'presidential' && elMeta0?.indirect && state.results) {
    $('#hex')?.toggleAttribute('hidden', true);
    $('#hex2')?.toggleAttribute('hidden', true);
    $('#geomap')?.toggleAttribute('hidden', true);
    $('#display-seg')?.toggleAttribute('hidden', true);
    $('#sizing-seg')?.toggleAttribute('hidden', true);
    if (icard) { icard.hidden = false; icard.innerHTML = renderIndirectCard(elMeta0, activeOfficeData()?.national); }
    renderDetail();
    renderHistoryLegend();
    return;
  }
  // 옛 총선(1~8대) — 정확 경계는 없지만 시군/시도 centroid로 만든 근사 hex(district_hex_1~8) 사용.
  // 지도 view 지원 회차 — 21·22(OhmyNews) + 9~20(SGIS 읍면동 복원).
  // 9~12 중선거구(1구 2인)는 당선 2당 줄무늬, 13~22 소선거구는 1위 단색.
  // 1~8대 = 옛총선 근사 geo(시군 union). 3·4·5대는 위키 별표(선거구역)로 시군 획정 확보.
  const GEO_GENERAL = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22];
  const HEX_DISTRICT = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22];  // 지역구 hex 레이아웃 보유
  const geoSupported = state.type === 'national_assembly' && GEO_GENERAL.includes(state.n);
  const hexSupported = geoSupported && HEX_DISTRICT.includes(state.n);
  // 지선 geo — 광역장/교육감 시도(전 회차), 기초장 시군구(회차별). 대선 geo — 시군구 margin 명도(16~20대).
  const localGeo = (typeof localGeoSupported === 'function') && localGeoSupported(unit, state.n);
  const presGeo = (typeof presGeoSupported === 'function') && presGeoSupported(state.n);
  // 요소 누락(캐시된 옛 HTML 등)에도 깨지지 않게 null guard
  const toggle = (sel, hide) => { const el = $(sel); if (el) el.toggleAttribute('hidden', hide); };
  // Hex+지도 토글: 총선 9~22·지선 전회차·대선 16~20. 9~16 총선은 지도 전용 → 숨김·강제.
  toggle('#display-seg', !(hexSupported || localGeo || presGeo));
  const effDisplay = (geoSupported && !hexSupported) ? 'geo' : state.display;
  state.effDisplay = effDisplay;  // 범례(점선 추정경계)가 참조
  const showGeo = (geoSupported || localGeo || presGeo) && effDisplay === 'geo';
  toggle('#hex', showGeo || unit !== 'sido');
  toggle('#hex2', showGeo || unit === 'sido');
  toggle('#geomap', !showGeo);
  // 사이즈 토글은 시군구 hex + 표심 분포 의미 있는 type만 (대선·옛 총선). 지선·geo 모드는 숨김.
  toggle('#sizing-seg', showGeo || unit !== 'sigungu' || state.type === 'local');
  if (showGeo) {
    if (state.type === 'local') await renderLocalGeoMap(unit);
    else if (state.type === 'presidential') await renderPresGeoMap();
    else await renderGeoMap();
  }
  else if (unit === 'sido') renderSidoHex();
  else if (unit === 'district') await renderDistrictHex();
  else renderSigunguHex();
  renderDetail();
  renderHistoryLegend();
}

async function loadDistrictHex(n) {
  if (state.districtHex[n]) return state.districtHex[n];
  try {
    state.districtHex[n] = await loadJson(`data/geo/district_hex_${n}.json`);
  } catch {
    state.districtHex[n] = null;
  }
  return state.districtHex[n];
}

// 현재 선택 회차의 election 메타 — n + variant(예 4대 3·15 부정선거)로 구분.
function currentEl() {
  const list = state.elections[state.type]?.elections || [];
  return list.find((x) => x.n === state.n && (x.variant || null) === (state.variant || null)) || null;
}

function renderRoundsSeg() {
  const seg = $('#rounds-seg');
  seg.innerHTML = '';
  const list = state.elections[state.type]?.elections || [];
  const available = state.elections._available?.[state.type] || [];
  const seen = new Set();
  for (const e of list) {
    // variant(별도 키, 예 4대 3·15)는 같은 n이어도 별 버튼으로. 일반 회차는 n당 하나.
    if (!e.variant) {
      if (seen.has(e.n)) continue;
      seen.add(e.n);
    }
    const btn = document.createElement('button');
    btn.className = 'seg-btn';
    if (e.variant) btn.classList.add('seg-variant');
    if (!e.variant && !available.includes(e.n)) btn.classList.add('no-data');
    btn.dataset.n = e.n;
    if (e.variant) btn.dataset.variant = e.variant;
    btn.textContent = e.btn || `${e.n}`;
    btn.title = `${e.date}${e.note ? ' · ' + e.note : ''}${(e.variant || available.includes(e.n)) ? '' : ' · 데이터 미수집'}`;
    btn.addEventListener('click', () => setRound(e.n, e.variant || null));
    seg.appendChild(btn);
  }
}

// 교육감은 5회(2010)부터 전국 직선 동시선거 — 1~4회엔 office 선택지에서 숨기고,
// 그때 교육감을 보고 있었으면 기초단체장으로 전환.
function updateOfficeAvailability(n) {
  const supBtn = document.querySelector('[data-office="교육감"]');
  const hasSup = state.type === 'local' && n >= 5;
  if (supBtn) supBtn.toggleAttribute('hidden', !hasSup);
  if (!hasSup && state.office === '교육감') {
    state.office = '기초단체장';
    document.querySelectorAll('[data-office]').forEach((b) =>
      b.classList.toggle('is-active', b.dataset.office === state.office));
  }
}

async function setRound(n, variant = null) {
  state.n = n;
  state.variant = variant || null;
  state.selected = null;
  updateOfficeAvailability(n);
  updateURL();
  document.querySelectorAll('#rounds-seg [data-n]').forEach((b) => {
    b.classList.toggle('is-active', +b.dataset.n === n && (b.dataset.variant || '') === (variant || ''));
  });
  const el = currentEl();
  if (el) {
    $('#election-date').textContent = `${el.date}${el.note ? ' · ' + el.note : ''}`;
    // 정당색 시대 맥락 — 회차 변경할 때마다 그 회차 날짜로 partyColor periods 활성.
    if (typeof setPartyColorContext === 'function') setPartyColorContext(el.date);
  }
  // 캐시 — 본 회차 재방문은 즉시(역대선거 왔다갔다 매끄럽게). adapt 결과를 type|n 키로 저장.
  if (!state.roundCache) state.roundCache = new Map();
  const cacheKey = `${state.type}|${n}|${variant || ''}`;
  if (state.roundCache.has(cacheKey)) {
    state.results = state.roundCache.get(cacheKey);
    renderAll();
    return;
  }

  state.results = null;
  // 첫 로드만 로딩 표시 — 180ms 넘게 걸릴 때만(빠른 로드 깜빡임 방지). 캐시 히트는 위에서 즉시 return.
  const loadingEl = $('#loading');
  const loadingTimer = setTimeout(() => { if (loadingEl) loadingEl.hidden = false; }, 180);
  // 1차: election 메타에 file 지정(예 4대 윤보선·3·15) 우선, 없으면 새 schema path.
  const newPath = el?.file ? `data/results/${el.file}` : newSchemaPath(state.type, n);
  if (newPath) {
    try {
      const raw = await loadJson(newPath);
      // _meta.chunked 면 sigungu/district_sigungu race가 별도 파일 — 같이 fetch.
      if (raw._meta?.chunked) {
        const subPath = newPath.replace(/\.json$/, '.sigungu.json');
        try {
          const sub = await loadJson(subPath);
          raw.races = (raw.races || []).concat(sub.races || []);
        } catch {} // sigungu 파일 없으면 main race만으로 진행
      }
      state.results = adaptNewSchema(raw, state.type);
    } catch (e) {
      // 2차 fallback: 옛 path
      try {
        state.results = await loadJson(`data/results/${state.type}_${n}.json`);
      } catch {
        state.results = null;
      }
    }
  } else {
    try {
      state.results = await loadJson(`data/results/${state.type}_${n}.json`);
    } catch {
      state.results = null;
    }
  }
  clearTimeout(loadingTimer);
  if (loadingEl) loadingEl.hidden = true;
  // 이 회차 결과가 바뀌었어도(같은 세션) 다시 안 받게 캐시. 회차당 1회만 페치.
  if (state.results) state.roundCache.set(cacheKey, state.results);
  renderAll();
}

// === Parliament half-donut chart ===
// renderParliamentChart → assets/parliament.js (공용)

// === Detail Pane ===
// 회차별 archive 페이지 매핑 — data/elections 레지스트리에서 startup 시 채움.
// kind|n 키 → /archive/{id}/ URL. assets/elections.js 필요.
const ARCHIVE_PAGES = {};
(function populateArchivePages() {
  if (typeof Elections === 'undefined') return;
  Elections.loadArchiveablePages().then((metas) => {
    // history.js state.type은 'national_assembly' — 레지스트리 'general_election'을 정규화.
    const KIND_ALIAS = { 'general_election': 'national_assembly' };
    for (const m of metas) {
      if (!m || !m.archive || !m.archive.page) continue;
      const key = (KIND_ALIAS[m.kind] || m.kind) + '|' + m.n;
      ARCHIVE_PAGES[key] = m.archive.page;
    }
    // 비어있던 detail 재렌더 — 일치 회차 detail이 열려있으면 banner 다시.
    if (typeof renderDetail === 'function' && document.getElementById('detail-pane')) {
      try { renderDetail(); } catch {}
    }
  }).catch((e) => {
    console.warn('[history] archive populate 실패:', e);
  });
})();

// 비지역구 의석 제도 — 회차별 명칭·배분 규칙 설명. (유정회/전국구/비례대표)
function propSystemInfo(n) {
  if (n <= 10) return { label: '유정회', note: '유신정우회 — 선거 아님. 대통령이 추천하고 통일주체국민회의가 선출. 지역구 정수의 1/2.' };
  if (n <= 12) return { label: '전국구', note: '지역구의 1/2. 제1당이 2/3를 자동 배분받고, 나머지는 지역구 5석 이상 정당에 의석 비율로. (정당 득표 아님)' };
  if (n <= 16) return { label: '전국구', note: '지역구 의석·득표 비율로 배분.' };
  return { label: '비례대표', note: '정당 득표율에 따른 비례 배분 (1인 2표 정당명부, 2004~).' };
}

function renderDetail() {
  const pane = $('#detail-pane');
  const el = currentEl();
  const archiveHref = ARCHIVE_PAGES[`${state.type}|${state.n}`];
  const archiveBanner = archiveHref
    ? `<a class="archive-banner" href="${archiveHref}">이 회차 아카이브 →</a>`
    : '';

  if (!state.results) {
    pane.innerHTML = `<div class="detail-empty">
      <strong>${state.n}${state.type === 'local' ? '회' : '대'} ${TYPE_LABEL[state.type].ko}</strong>
      ${el ? `(${el.date})` : ''}
      <br><br>데이터를 아직 수집하지 않았습니다.
      ${archiveBanner}
    </div>`;
    return;
  }

  const data = activeOfficeData();
  const nat = data?.national;
  let html = archiveBanner;
  if (state.type === 'national_assembly' && nat) {
    // 정당별 총 의석 (지역구 + 비례). 중선거구(9~12대)는 winners[]에 1구 2인 → 둘 다 카운트.
    const seatsByParty = new Map();
    for (const d of state.results?.district || []) {
      const wins = (d.winners && d.winners.length) ? d.winners
        : (d.winner_party ? [{ party: d.winner_party }] : []);
      for (const w of wins) {
        if (!w.party) continue;
        seatsByParty.set(w.party, (seatsByParty.get(w.party) || 0) + 1);
      }
    }
    for (const p of nat.proportional_seats || []) {
      seatsByParty.set(p.party, (seatsByParty.get(p.party) || 0) + (p.seats || 0));
    }
    const parties = [...seatsByParty.entries()]
      .map(([party, seats]) => ({ party, seats, color: partyColor(party) }))
      .sort((a, b) => b.seats - a.seats);
    const total = parties.reduce((s, p) => s + p.seats, 0);
    // 비지역구 의석(유정회/전국구/비례) — geo 모드엔 hex 비례 컬럼이 없으니 상세 패널에 표기.
    const propSeats = [...(nat.proportional_seats || [])].sort((a, b) => (b.seats || 0) - (a.seats || 0));
    const propTotal = propSeats.reduce((s, p) => s + (p.seats || 0), 0);
    const distSeats = total - propTotal;
    const prop = propSystemInfo(state.n);
    // 큰 정당 헤드라인(ns-name/ns-party)은 도넛 차트와 중복 → 제거. 제목+투표율만.
    html += `<div class="national-summary">
      <div class="ns-title">${state.n}${state.type === 'local' ? '회' : '대'} ${TYPE_LABEL[state.type].ko} · 전국 의석 (총 ${total}석)</div>
      ${propTotal ? `<div class="seat-split" title="${prop.note}">
        <span class="ss-seg ss-dist" style="flex:${distSeats}">지역구 ${distSeats}</span>
        <span class="ss-seg ss-prop" style="flex:${propTotal}">${prop.label} ${propTotal}</span>
      </div>` : ''}
      <div class="ns-stat">
        <span>투표율 ${turnoutLabel(nat?.turnout, el)}</span>
        ${el?.date ? `<span>${el.date}</span>` : ''}
      </div>
      ${el?.note ? `<div class="ns-note">📌 ${el.note}</div>` : ''}
    </div>
    <div class="parliament-wrap">
      ${renderParliamentChart(parties, total)}
      <div class="party-seats">
        ${parties.map((p) => `<span class="ps-item" title="${p.party} ${p.seats}석">
          <span class="ps-dot" style="background:${p.color}"></span>${p.party} <b>${p.seats}</b>
        </span>`).join('')}
      </div>
      ${propTotal ? `<div class="party-seats prop-seats">
        <span class="prop-label">${prop.label} ${propTotal}석 —</span>
        ${propSeats.map((p) => `<span class="ps-item" title="${p.party} ${prop.label} ${p.seats}석">
          <span class="ps-dot" style="background:${partyColor(p.party)}"></span>${p.party} <b>${p.seats}</b>
        </span>`).join('')}
      </div>
      <div class="prop-note"><b>${prop.label}</b> ${prop.note}</div>` : ''}
    </div>`;
  } else if (state.type === 'local') {
    // 지선 — 광역단체장·기초단체장·교육감 winner_party 카운트 (정당별 당선 곳 수)
    const winsByParty = new Map();
    for (const r of data?.sigungu || []) {
      const winner = r.candidates?.[0];
      if (!winner?.party) continue;
      winsByParty.set(winner.party, (winsByParty.get(winner.party) || 0) + 1);
    }
    const parties = [...winsByParty.entries()]
      .map(([party, wins]) => ({ party, wins, color: partyColor(party) }))
      .sort((a, b) => b.wins - a.wins);
    const total = parties.reduce((s, p) => s + p.wins, 0);
    const top = parties[0];
    html += `<div class="national-summary" style="border-left-color:${top ? top.color : 'var(--ink)'}">
      <div class="ns-title">${state.n}${state.type === 'local' ? '회' : '대'} ${TYPE_LABEL[state.type].ko} · ${state.office}</div>
      <div class="ns-name" style="color:${top ? top.color : 'var(--ink)'}">${top ? top.party : '—'}</div>
      <div class="ns-party">${top ? `${top.wins}곳 / 총 ${total}곳` : (el?.date || '')}</div>
      <div class="ns-stat">
        <span>투표율 ${turnoutLabel(nat?.turnout, el)}</span>
        ${el?.date ? `<span>${el.date}</span>` : ''}
      </div>
    </div>
    ${parties.length ? `<div class="party-seats">
      ${parties.map((p) => `<span class="ps-item" title="${p.party} ${p.wins}곳">
        <span class="ps-dot" style="background:${p.color}"></span>${p.party} <b>${p.wins}</b>
      </span>`).join('')}
    </div>` : ''}`;
  } else if (nat?.candidates?.length) {
    const sorted = [...nat.candidates].sort((a, b) => (b.pct || 0) - (a.pct || 0));
    const top = sorted[0];
    const color = partyColor(top.party);
    const maxPct = top.pct || 0;
    // 1·2위 격차 그리고 전체 분포 (최대 10명 막대그래프)
    const barRows = sorted.slice(0, 10).map((c) => {
      const cColor = partyColor(c.party);
      const w = maxPct > 0 ? ((c.pct || 0) / maxPct) * 100 : 0;
      return `<div class="rc-bar-row">
        <span class="name">${candLabel(c)}</span>
        <span class="rc-bar"><span class="rc-bar-fill" style="width:${w}%;background:${cColor}"></span></span>
        <span class="pct" style="color:${cColor}">${c.pct != null ? c.pct.toFixed(1) + '%' : '—'}</span>
      </div>`;
    }).join('');
    html += `<div class="national-summary" style="border-left-color:${color}">
      <div class="ns-title">${state.n}${state.type === 'local' ? '회' : '대'} ${TYPE_LABEL[state.type].ko} · 전국</div>
      <div class="ns-name" style="color:${color}">${candLabel(top) || el?.winner || '—'}</div>
      <div class="ns-party">${top.party} · ${top.pct?.toFixed(1)}%</div>
      <div class="ns-stat">
        <span>투표율 ${turnoutLabel(nat?.turnout, el)}</span>
        ${el?.date ? `<span>${el.date}</span>` : ''}
      </div>
    </div>
    <div class="result-card" style="border-left-color:${color}">${barRows}</div>`;
  } else if (el) {
    html += `<div class="national-summary">
      <div class="ns-title">${state.n}${state.type === 'local' ? '회' : '대'} ${TYPE_LABEL[state.type].ko}</div>
      <div class="ns-name">${el.winner || '—'}</div>
      <div class="ns-party">${el.winner_party || ''} · 투표율 ${el.turnout ?? '—'}%</div>
      <div class="ns-stat"><span>${el.date}</span></div>
    </div>`;
  }

  // 선택된 지역 결과 (시도/시군구/지역구)
  if (state.selected) {
    const isSido = !state.selected.name;
    const isDistrict = state.selected.kind === 'district';
    const result = isSido
      ? resultForSido(state.selected.sido)
      : isDistrict
        ? resultForDistrict(state.selected.sido, state.selected.name)
        : resultForSigungu(state.selected.sido, state.selected.name);
    const titleText = isSido ? state.selected.sido : `${state.selected.sido} · ${state.selected.name}`;
    const tag = isSido ? '시도 합산' : isDistrict ? '지역구' : '시군구';
    html += `<div class="detail-hdr">
      <h2>${titleText}</h2>
      <span class="count">${tag}</span>
    </div>`;
    if (result?.candidates?.length) {
      const sorted = [...result.candidates].sort((a, b) => b.pct - a.pct);
      const maxPct = sorted[0].pct;
      const top = sorted[0];
      const leftColor = partyColor(top.party);
      const unopposed = result.uncontested || result.is_uncontested;  // 데이터 플래그명은 is_uncontested
      // 단독 출마(투표 시행) — 후보 1명·무투표 아님. pct=찬성률(votes/투표수), 나머지=무효(반대).
      const single = !unopposed && sorted.length === 1;
      const barRows = sorted.slice(0, 10).map((c) => {
        const color = partyColor(c.party);
        const w = unopposed ? 100 : (single ? (c.pct || 0) : (maxPct > 0 ? (c.pct / maxPct) * 100 : 0));
        const pctTxt = (unopposed || c.uncontested) ? '무투표'
          : (c.pct != null ? c.pct.toFixed(1) + '%' : '무투표');
        return `<div class="rc-bar-row">
          <span class="name">${candLabel(c)}</span>
          <span class="rc-bar"><span class="rc-bar-fill" style="width:${w}%;background:${color}"></span></span>
          <span class="pct" style="color:${color}">${pctTxt}</span>
        </div>`;
      }).join('');
      const meta = unopposed ? '단독 출마(무투표)'
        : single ? `단독 출마 · 무효 ${(100 - (top.pct || 0)).toFixed(1)}% · 투표율 ${turnoutLabel(result.turnout, el)}`
          : '투표율 ' + turnoutLabel(result.turnout, el);
      html += `<div class="result-card" style="border-left-color:${leftColor}">
        <div class="rc-hdr">
          <span class="rc-name">${candLabel(top)} ${unopposed ? '무투표 당선' : (single ? '단독 출마' : '1위')}</span>
          <span class="rc-meta">${meta}</span>
        </div>
        ${barRows}
      </div>`;
    } else {
      html += `<div class="detail-empty">이 지역 데이터 없음</div>`;
    }
  } else {
    // 선택 X — '박빙 top 5' 시군구/지역구 highlight (격차 작은 순)
    const closeRaces = computeCloseRaces();
    if (closeRaces.length) {
      html += `<div class="hist-close">
        <div class="hist-close-title">박빙 ${closeRaces.length}곳 <span class="hist-close-sub">격차 작은 순 · 클릭 시 그 지역으로</span></div>
        ${closeRaces.map((r) => {
          const top = r.candidates[0], second = r.candidates[1];
          const col1 = partyColor(top.party), col2 = partyColor(second.party);
          return `<a class="hist-close-row" data-sido="${r.sido}" data-name="${r.name}" data-kind="${r.scope}">
            <span class="hist-close-loc">${r.sido} ${r.name}</span>
            <span class="hist-close-cands">
              <span class="hist-close-cand" style="color:${col1}">${top.name}(${top.party}) ${top.pct.toFixed(1)}</span>
              <span class="hist-close-cand" style="color:${col2}">${second.name}(${second.party}) ${second.pct.toFixed(1)}</span>
            </span>
            <span class="hist-close-margin">+${r.margin.toFixed(2)}%p</span>
          </a>`;
        }).join('')}
      </div>
      <div class="detail-empty hist-empty-hint">시도·시군구를 클릭하면 그 지역 결과가 표시됩니다.</div>`;
    } else {
      html += `<div class="detail-empty">시도·시군구를 클릭하면 그 지역 결과가 표시됩니다.</div>`;
    }
  }
  pane.innerHTML = html;
  // 박빙 row 클릭 → 선택
  pane.querySelectorAll('.hist-close-row').forEach((row) => {
    row.addEventListener('click', () => {
      const sido = row.dataset.sido, name = row.dataset.name, kind = row.dataset.kind;
      state.selected = { sido, name, kind };
      renderDetail();
    });
  });
}

// 박빙 top N race 추출 — 2위 있고 격차 작은 순
function computeCloseRaces(N = 5) {
  const data = activeOfficeData();
  const pool = [];
  // core.js _raceToOldRow가 race를 {sido, name, candidates, ...}로 정규화 — name이
  // sigungu(또는 district). list별로 scope만 따로 부여.
  for (const [list, scope] of [[data?.sigungu || [], 'sigungu'], [data?.district || [], 'district']]) {
    for (const r of list) {
      if (!r.candidates || r.candidates.length < 2) continue;
      const sorted = [...r.candidates].filter((c) => c.pct != null).sort((a, b) => b.pct - a.pct);
      if (sorted.length < 2) continue;
      const margin = sorted[0].pct - sorted[1].pct;
      if (margin >= 30) continue;  // 너무 큰 격차 X
      pool.push({ sido: r.sido, name: r.name, scope, candidates: sorted, margin });
    }
  }
  pool.sort((a, b) => a.margin - b.margin);
  return pool.slice(0, N);
}


// 확대 시 "전체" 리셋 버튼 — 공용 1개, 보이는 지도가 확대돼 있으면 표시.
const _zoomables = [];
let _resetBtn = null;
function updateResetBtn() {
  const viz = document.querySelector('.viz');
  if (!viz) return;
  if (!_resetBtn) {
    _resetBtn = document.createElement('button');
    _resetBtn.type = 'button';
    _resetBtn.className = 'pz-reset';
    _resetBtn.innerHTML = '⤢ 전체';
    _resetBtn.hidden = true;
    _resetBtn.addEventListener('click', () => _zoomables.forEach((z) => z.reset()));
    viz.appendChild(_resetBtn);
  }
  _resetBtn.hidden = !_zoomables.some((z) => !z.svg.hasAttribute('hidden') && z.isZoomed());
}

// 모바일 핀치 확대·드래그 — 빽빽한 전국 hex를 viewBox 조작으로 확대(렌더 시 자동 리셋).
//  2손가락: 핀치 줌 + 드래그 pan. 확대 상태에서만 1손가락 pan(아니면 페이지 스크롤 허용).
//  더블탭: 리셋. 셀 탭은 그대로 선택, 제스처 직후 합성 click은 억제.
function enablePinchZoom(svg) {
  if (!svg || svg._pz) return;
  svg._pz = true;
  const MAX = 8;
  let base, vb, lastSet;
  const read = () => (svg.getAttribute('viewBox') || '0 0 100 100').split(/\s+/).map(Number);
  function updateTA() {
    const zoomed = vb && base && vb[2] < base[2] - 0.5;
    svg.style.touchAction = zoomed ? 'none' : 'pan-y';
    svg.style.cursor = zoomed ? 'grab' : '';
    updateResetBtn();
  }
  function clamp(b) {
    let [x, y, w, h] = b;
    if (w >= base[2]) return base.slice();
    const minW = base[2] / MAX;
    if (w < minW) { const s = minW / w; w *= s; h *= s; }
    const padX = base[2] * 0.12, padY = base[3] * 0.12;
    x = Math.min(Math.max(x, base[0] - padX), base[0] + base[2] - w + padX);
    y = Math.min(Math.max(y, base[1] - padY), base[1] + base[3] - h + padY);
    return [x, y, w, h];
  }
  function set(b) { vb = clamp(b); lastSet = vb.map((v) => +v.toFixed(2)).join(' '); svg.setAttribute('viewBox', lastSet); updateTA(); }
  function sync() { base = read(); vb = base.slice(); lastSet = svg.getAttribute('viewBox'); updateTA(); }
  sync();
  _zoomables.push({ svg, reset: () => set(base.slice()), isZoomed: () => base && vb[2] < base[2] - 0.5 });
  new MutationObserver(() => { const cur = svg.getAttribute('viewBox'); if (cur && cur !== lastSet) sync(); })
    .observe(svg, { attributes: true, attributeFilter: ['viewBox'] });

  const rect = () => svg.getBoundingClientRect();
  const toSvg = (cx, cy, b, r) => [b[0] + (cx - r.left) / r.width * b[2], b[1] + (cy - r.top) / r.height * b[3]];
  const dist2 = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
  let moved = false, mode = null, startD = 0, startVb = null, anchor = null, pan0 = null, lastTap = 0;

  svg.addEventListener('touchstart', (e) => {
    moved = false;
    const r = rect();
    if (e.touches.length === 2) {
      mode = 'pinch'; startD = dist2(e.touches); startVb = vb.slice();
      anchor = toSvg((e.touches[0].clientX + e.touches[1].clientX) / 2, (e.touches[0].clientY + e.touches[1].clientY) / 2, vb, r);
      e.preventDefault();
    } else if (e.touches.length === 1) {
      const now = Date.now();
      if (now - lastTap < 300 && vb[2] < base[2] - 0.5) { set(base.slice()); e.preventDefault(); }
      lastTap = now;
      mode = (vb[2] < base[2] - 0.5) ? 'pan' : 'tap';
      pan0 = { x: e.touches[0].clientX, y: e.touches[0].clientY, vb: vb.slice() };
    }
  }, { passive: false });

  svg.addEventListener('touchmove', (e) => {
    const r = rect();
    if (mode === 'pinch' && e.touches.length === 2) {
      e.preventDefault(); moved = true;
      const s = dist2(e.touches) / (startD || 1);
      const w = startVb[2] / s, h = startVb[3] / s;
      const mx = (e.touches[0].clientX + e.touches[1].clientX) / 2, my = (e.touches[0].clientY + e.touches[1].clientY) / 2;
      const fx = (mx - r.left) / r.width, fy = (my - r.top) / r.height;
      set([anchor[0] - fx * w, anchor[1] - fy * h, w, h]);
    } else if (mode === 'pan' && e.touches.length === 1) {
      const dx = e.touches[0].clientX - pan0.x, dy = e.touches[0].clientY - pan0.y;
      if (!moved && Math.hypot(dx, dy) < 6) return;
      e.preventDefault(); moved = true;
      set([pan0.vb[0] - dx / r.width * vb[2], pan0.vb[1] - dy / r.height * vb[3], vb[2], vb[3]]);
    }
  }, { passive: false });

  svg.addEventListener('touchend', () => { mode = null; });
  svg.addEventListener('click', (e) => { if (moved) { e.stopPropagation(); e.preventDefault(); moved = false; } }, true);
  svg.addEventListener('wheel', (e) => {
    if (!base || !(e.ctrlKey || e.metaKey)) return;   // 데스크톱: Ctrl+휠만 줌(일반 휠=페이지 스크롤)
    e.preventDefault();
    const r = rect();
    const s = e.deltaY < 0 ? 1 / 1.2 : 1.2;
    const w = vb[2] * s, h = vb[3] * s;
    const fx = (e.clientX - r.left) / r.width, fy = (e.clientY - r.top) / r.height;
    set([vb[0] + fx * vb[2] - fx * w, vb[1] + fy * vb[3] - fy * h, w, h]);
  }, { passive: false });

  // 데스크톱 마우스 드래그 pan — 확대 상태에서만.
  let mDrag = null;
  svg.addEventListener('mousedown', (e) => {
    if (!base || vb[2] >= base[2] - 0.5) return;
    mDrag = { x: e.clientX, y: e.clientY, vb: vb.slice() };
    moved = false;
    svg.style.cursor = 'grabbing';
    e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if (!mDrag) return;
    const r = rect();
    const dx = e.clientX - mDrag.x, dy = e.clientY - mDrag.y;
    if (!moved && Math.hypot(dx, dy) < 4) return;
    moved = true;
    const w = mDrag.vb[2], h = mDrag.vb[3];
    set([mDrag.vb[0] - dx / r.width * w, mDrag.vb[1] - dy / r.height * h, w, h]);
  });
  window.addEventListener('mouseup', () => { if (mDrag) { mDrag = null; updateTA(); } });
}

// === Bootstrap ===
async function init() {
  enablePinchZoom($('#hex'));
  enablePinchZoom($('#hex2'));
  // 모바일 핀치 힌트 — 한 번만, 첫 터치/5초 후 사라짐.
  if (matchMedia('(hover: none)').matches) {
    const viz = document.querySelector('.viz');
    if (viz && !viz.querySelector('.pz-hint')) {
      const hint = document.createElement('div');
      hint.className = 'pz-hint';
      hint.textContent = '✥ 두 손가락으로 확대 · 더블탭 리셋';
      viz.appendChild(hint);
      const kill = () => hint.remove();
      viz.addEventListener('touchstart', kill, { once: true, passive: true });
      setTimeout(kill, 5000);
    }
  }
  const [elections, hex, hexLegacy, manifest] = await Promise.all([
    loadJson('data/elections.json'),
    loadJson('data/geo/sigungu_hex.json'),
    loadJson('data/geo/sigungu_hex_legacy.json').catch(() => null),
    loadJson('data/results/manifest.json').catch(() => ({ presidential: [], national_assembly: [], local: [] })),
  ]);
  state.elections = elections;
  state.elections._available = manifest;
  state.hexData = hex;
  state.hexLegacy = hexLegacy;

  document.querySelectorAll('[data-type]').forEach((b) => {
    b.addEventListener('click', () => setType(b.dataset.type));
  });
  document.querySelectorAll('[data-office]').forEach((b) => {
    b.addEventListener('click', () => setOffice(b.dataset.office));
  });
  document.querySelectorAll('[data-sizing]').forEach((b) => {
    b.addEventListener('click', () => setSizing(b.dataset.sizing));
  });
  document.querySelectorAll('[data-display]').forEach((b) => {
    b.addEventListener('click', () => setDisplay(b.dataset.display));
  });

  // 초기 상태 — path 우선 (prerender path 호환), 쿼리스트링·INITIAL_STATE fallback
  // path: /history/presidential/16/ or /history/local/8/governor/
  const init0 = parseInitialState();
  const type0 = init0.type || 'presidential';
  setType(type0, /*skipDefaultRound=*/ init0.n != null);
  if (init0.office && init0.office !== state.office) setOffice(init0.office);
  // URL ?sizing= 가 있으면 type 기본을 override (setType이 이미 type 기본 적용)
  if (init0.sizing && init0.sizing !== state.sizing) setSizing(init0.sizing);
  if (init0.n != null) setRound(init0.n);

  // popstate (브라우저 뒤·앞) — path 우선
  window.addEventListener('popstate', () => {
    const s = parseInitialState();
    if (s.type && s.type !== state.type) setType(s.type, s.n != null);
    if (s.office && s.office !== state.office) setOffice(s.office);
    if (s.n != null && s.n !== state.n) setRound(s.n);
  });

  $('#loading').hidden = true;
}

init();
