// history.js entry — 회차 chrome · renderAll · detail pane · init.
// 마지막에 로드: state·routing·data·render-* 모두 정의된 후 init() 호출.

function renderHistoryLegend() {
  const el = $('#history-legend');
  if (!el) return;
  const type = state.type;
  // 총선은 범례 안 보임 (지역구 색 자체로 충분)
  if (type === 'national_assembly') {
    el.hidden = true; el.innerHTML = '';
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

// 현재 단위에 맞는 hex 렌더 + detail
async function renderAll() {
  const unit = activeUnit(state.type, state.office, state.results);
  // 지도 view 지원 회차 — 21·22(OhmyNews) + 9~20(SGIS 읍면동 복원).
  // 9~12 중선거구(1구 2인)는 당선 2당 줄무늬, 13~22 소선거구는 1위 단색.
  const GEO_GENERAL = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22];
  const HEX_DISTRICT = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22];  // 지역구 hex 레이아웃 보유
  const geoSupported = state.type === 'national_assembly' && GEO_GENERAL.includes(state.n);
  const hexSupported = geoSupported && HEX_DISTRICT.includes(state.n);
  // 지선 geo — 광역장/교육감 시도(전 회차), 기초장 시군구(최근 회차). render-local-geo.js.
  const localGeo = (typeof localGeoSupported === 'function') && localGeoSupported(unit, state.n);
  // 요소 누락(캐시된 옛 HTML 등)에도 깨지지 않게 null guard
  const toggle = (sel, hide) => { const el = $(sel); if (el) el.toggleAttribute('hidden', hide); };
  // Hex+지도 토글: 총선은 둘 다 있는 회차(17~22), 지선은 localGeo 회차. 9~16 총선은 지도 전용 → 숨김·강제.
  toggle('#display-seg', !(hexSupported || localGeo));
  const effDisplay = (geoSupported && !hexSupported) ? 'geo' : state.display;
  const showGeo = (geoSupported || localGeo) && effDisplay === 'geo';
  toggle('#hex', showGeo || unit !== 'sido');
  toggle('#hex2', showGeo || unit === 'sido');
  toggle('#geomap', !showGeo);
  // 사이즈 토글은 시군구 hex + 표심 분포 의미 있는 type만 (대선·옛 총선). 지선·geo 모드는 숨김.
  toggle('#sizing-seg', showGeo || unit !== 'sigungu' || state.type === 'local');
  if (showGeo) await (state.type === 'local' ? renderLocalGeoMap(unit) : renderGeoMap());
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

function renderRoundsSeg() {
  const seg = $('#rounds-seg');
  seg.innerHTML = '';
  const list = state.elections[state.type]?.elections || [];
  const available = state.elections._available?.[state.type] || [];
  for (const e of list) {
    const btn = document.createElement('button');
    btn.className = 'seg-btn';
    if (!available.includes(e.n)) btn.classList.add('no-data');
    btn.dataset.n = e.n;
    btn.textContent = `${e.n}`;
    btn.title = `${e.date}${e.note ? ' · ' + e.note : ''}${available.includes(e.n) ? '' : ' · 데이터 미수집'}`;
    btn.addEventListener('click', () => setRound(e.n));
    seg.appendChild(btn);
  }
}

async function setRound(n) {
  state.n = n;
  state.selected = null;
  updateURL();
  document.querySelectorAll('#rounds-seg [data-n]').forEach((b) => {
    b.classList.toggle('is-active', +b.dataset.n === n);
  });
  const el = (state.elections[state.type]?.elections || []).find((x) => x.n === n);
  if (el) {
    $('#election-date').textContent = `${el.date}${el.note ? ' · ' + el.note : ''}`;
    // 정당색 시대 맥락 — 회차 변경할 때마다 그 회차 날짜로 partyColor periods 활성.
    if (typeof setPartyColorContext === 'function') setPartyColorContext(el.date);
  }
  state.results = null;
  // 1차: 새 schema (통일 path) — data/results/{Nth}-{kind}-{year}.json
  const newPath = newSchemaPath(state.type, n);
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

function renderDetail() {
  const pane = $('#detail-pane');
  const list = state.elections[state.type]?.elections || [];
  const el = list.find((x) => x.n === state.n);
  const archiveHref = ARCHIVE_PAGES[`${state.type}|${state.n}`];
  const archiveBanner = archiveHref
    ? `<a class="archive-banner" href="${archiveHref}">이 회차 아카이브 →</a>`
    : '';

  if (!state.results) {
    pane.innerHTML = `<div class="detail-empty">
      <strong>${TYPE_LABEL[state.type].ko} ${state.n}회</strong>
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
    // 정당별 총 의석 (지역구 winner_party 카운트 + 비례 의석)
    const seatsByParty = new Map();
    for (const d of state.results?.district || []) {
      if (!d.winner_party) continue;
      seatsByParty.set(d.winner_party, (seatsByParty.get(d.winner_party) || 0) + 1);
    }
    for (const p of nat.proportional_seats || []) {
      seatsByParty.set(p.party, (seatsByParty.get(p.party) || 0) + (p.seats || 0));
    }
    const parties = [...seatsByParty.entries()]
      .map(([party, seats]) => ({ party, seats, color: partyColor(party) }))
      .sort((a, b) => b.seats - a.seats);
    const total = parties.reduce((s, p) => s + p.seats, 0);
    const top = parties[0];
    html += `<div class="national-summary" style="border-left-color:${top ? top.color : 'var(--ink)'}">
      <div class="ns-title">${TYPE_LABEL[state.type].ko} ${state.n}회 · 전국 의석</div>
      <div class="ns-name" style="color:${top ? top.color : 'var(--ink)'}">${top ? top.party : '—'}</div>
      <div class="ns-party">${top ? `${top.seats}석 / 총 ${total}석` : ''}</div>
      <div class="ns-stat">
        <span>투표율 ${turnoutLabel(nat?.turnout, el)}</span>
        ${el?.date ? `<span>${el.date}</span>` : ''}
      </div>
    </div>
    <div class="parliament-wrap">
      ${renderParliamentChart(parties, total)}
      <div class="party-seats">
        ${parties.map((p) => `<span class="ps-item" title="${p.party} ${p.seats}석">
          <span class="ps-dot" style="background:${p.color}"></span>${p.party} <b>${p.seats}</b>
        </span>`).join('')}
      </div>
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
      <div class="ns-title">${TYPE_LABEL[state.type].ko} ${state.n}회 · ${state.office}</div>
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
      <div class="ns-title">${TYPE_LABEL[state.type].ko} ${state.n}회 · 전국</div>
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
      <div class="ns-title">${TYPE_LABEL[state.type].ko} ${state.n}회</div>
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
      const barRows = sorted.slice(0, 10).map((c) => {
        const color = partyColor(c.party);
        const w = result.uncontested ? 100 : (maxPct > 0 ? (c.pct / maxPct) * 100 : 0);
        return `<div class="rc-bar-row">
          <span class="name">${candLabel(c)}</span>
          <span class="rc-bar"><span class="rc-bar-fill" style="width:${w}%;background:${color}"></span></span>
          <span class="pct" style="color:${color}">${c.pct != null ? c.pct.toFixed(1) + '%' : '무투표'}</span>
        </div>`;
      }).join('');
      html += `<div class="result-card" style="border-left-color:${leftColor}">
        <div class="rc-hdr">
          <span class="rc-name">${candLabel(top)} ${result.uncontested ? '무투표 당선' : '1위'}</span>
          <span class="rc-meta">${result.uncontested ? '단독 출마' : '투표율 ' + turnoutLabel(result.turnout, el)}</span>
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
            <span class="hist-close-cand" style="color:${col1}">${top.name}(${top.party}) ${top.pct.toFixed(1)}</span>
            <span class="hist-close-vs">vs</span>
            <span class="hist-close-cand" style="color:${col2}">${second.name}(${second.party}) ${second.pct.toFixed(1)}</span>
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


// === Bootstrap ===
async function init() {
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
