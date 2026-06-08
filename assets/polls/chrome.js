// polls.js chrome — detail 패널 · 보기 토글 · 범례.

// === 디테일 패널 ===

function renderDetail() {
  const pane = $('#detail-pane');
  if (!state.selectedSido) {
    pane.innerHTML =
      '<div class="detail-empty">시도·시군구를 선택하면 그 지역의 모든 여론조사가 여기에 표시됩니다.</div>';
    return;
  }
  const polls = pollsByRegion(state.selectedSido, state.selectedSigungu);
  // 시도만 선택했으면 시도 단위 record만 (시군구 records 섞이지 않게).
  // 시군구 선택했으면 pollsByRegion에서 이미 sigungu filter됨.
  const officePolls = polls.filter((p) => p.office_level === state.office
    && (state.selectedSigungu || !p.sigungu));

  const titleParts = [state.selectedSido];
  if (state.selectedSigungu) titleParts.push(state.selectedSigungu);

  let html = `<div class="detail-hdr">
    <h2>${titleParts.join(' · ')}</h2>
    <span class="count">${state.office} · ${officePolls.length}건</span>
  </div>`;
  if (!officePolls.length) {
    html += `<div class="detail-empty">${state.office} 관련 조사가 아직 없습니다.</div>`;
    pane.innerHTML = html;
    return;
  }

  // 실제 결과 — '실제 1위' 모드면 맨 위에 별도 카드(여론조사와 구분).
  const actual = (state.mode === 'result' && typeof window.actualResultFor === 'function')
    ? window.actualResultFor(state.selectedSido, state.selectedSigungu, state.office) : null;
  if (actual && actual.candidates && actual.candidates.length) {
    html += renderActualResultCard(actual);
  }

  // 시계열 차트 — 정당지지는 정당별 추이 선, 그 외는 후보 산점도(조사 ≥ 2건). 실제결과는 ◆로 오버레이.
  if (state.office === '정당지지') {
    const svg = buildPartyTrendSVG(officePolls, { showBand: true });
    if (svg) html += `<div class="scatter-wrap">${svg}</div>`;
  } else if (officePolls.length >= 2) {
    html += `<div class="scatter-wrap">${buildScatterSVG(officePolls, state.roster, actual)}</div>`;
  }
  // 기관별 lean mini-표 — 상위 1·2위 후보(또는 정당)별 잔차 평균.
  const leanHtml = buildLeanTableHTML(officePolls);
  if (leanHtml) html += leanHtml;
  // 첫 카드 위 라벨
  const latest = officePolls[0];
  if (latest) {
    html += `<div class="latest-label">조사 ${officePolls.length}건 · 최신 ${formatPeriod(latest.period_start, latest.period_end)}</div>`;
  }
  for (const p of officePolls) {
    html += renderPollCard(p, p.office_label);  // renderPollCard → utils.js (공용)
  }
  pane.innerHTML = html;
}

// 실제 결과 카드 — 개표 확정(NEC). 여론조사 카드와 구분되는 헤더(실제 결과 배지).
function renderActualResultCard(actual) {
  const cands = (actual.candidates || []).filter((c) => c.pct != null)
    .sort((a, b) => (b.pct || 0) - (a.pct || 0));
  if (!cands.length) return '';
  const maxPct = Math.max(...cands.map((c) => c.pct || 0)) || 100;
  const bars = cands.map((c) => {
    const color = partyColor(c.party);
    const w = maxPct > 0 ? (c.pct / maxPct) * 100 : 0;
    return `<div class="pc-bar-row">
      <span class="name">${c.name || c.party || ''}</span>
      <span class="pc-bar"><span class="pc-bar-fill" style="width:${w}%;background:${color}"></span></span>
      <span class="pct" style="color:${partyTextColor(c.party)}">${c.pct}%</span>
    </div>`;
  }).join('');
  return `<div class="poll-card actual-result-card">
    <div class="arc-hdr"><span class="arc-badge">실제 결과</span><span class="arc-sub">개표 확정 · NEC</span></div>
    ${bars}
  </div>`;
}

// 기관별 lean mini-표 — 현 region+office 폴 안에서 상위 1·2 (후보 또는 정당)의
// 기관별 잔차(개별 조사값 − 평활 추세) 평균. shrinkage 적용된 PollStats 사용.
function buildLeanTableHTML(officePolls) {
  if (typeof PollStats === 'undefined' || officePolls.length < 5) return '';
  const CANON = { '민주당': '더불어민주당', '국힘': '국민의힘', '국민의 힘': '국민의힘' };
  const isParty = state.office === '정당지지';
  // 키별 시계열 수집 — 후보면 name, 정당지지면 정당.
  const byKey = {};      // key → [{t,v,ag,n}]
  const meta = {};       // key → {label, color}
  for (const p of officePolls) {
    if (!p.period_end || !p.candidates) continue;
    const t = Date.parse(p.period_end);
    if (!isFinite(t)) continue;
    for (const c of p.candidates) {
      if (c.pct == null) continue;
      let key, label, party;
      if (isParty) {
        if (!c.party) continue;
        key = CANON[c.party] || c.party;
        label = (typeof PARTY_SHORT !== 'undefined' && PARTY_SHORT[key]) || key;
        party = key;
      } else {
        if (!c.name) continue;
        // 등록 후보만 (state.roster로)
        const hit = state.roster ? state.roster[`${p.sido}|${c.name}`] : null;
        if (state.roster && !(hit && hit.sg_typecode)) continue;
        key = c.name;
        label = c.name;
        party = c.party;
      }
      (byKey[key] = byKey[key] || []).push({ t, v: c.pct, ag: p.agency || '?', n: +p.sample_size || 0 });
      meta[key] = { label, color: party ? partyColor(party) : '#888' };
    }
  }
  // 상위 2 by mean.
  const ranked = Object.entries(byKey)
    .filter(([, pts]) => pts.length >= 3)
    .map(([k, pts]) => ({ k, pts, mean: pts.reduce((s, p) => s + p.v, 0) / pts.length }))
    .sort((a, b) => b.mean - a.mean)
    .slice(0, 2);
  if (ranked.length < 1) return '';
  // 기관별 lean 계산.
  const allHouse = ranked.map(({ k, pts }) => ({
    k, house: PollStats.houseEffects(pts, { bwDays: 21, shrinkK: 5, minN: 3 }),
  }));
  // n: 기관별 (이 region+office) 폴 수.
  const cnt = {};
  for (const p of officePolls) cnt[p.agency || '?'] = (cnt[p.agency || '?'] || 0) + 1;
  const ags = Object.keys(cnt)
    .filter((a) => cnt[a] >= 3)
    .sort((a, b) => (allHouse[0].house[b] || 0) - (allHouse[0].house[a] || 0));
  if (!ags.length) return '';
  const cell = (v) => v == null || Math.abs(v) < 0.05 ? '<td class="z">·</td>'
    : `<td class="${v > 0 ? 'pos' : 'neg'}">${v > 0 ? '+' : ''}${v.toFixed(1)}</td>`;
  const head = ranked.map(({ k }) =>
    `<th style="color:${meta[k].color}">${meta[k].label}</th>`).join('');
  const rows = ags.map((a) => {
    const cells = allHouse.map(({ house }) => cell(house[a])).join('');
    return `<tr><td class="ag">${a.replace(/\(주\)|주식회사/g, '').trim()}</td>${cells}<td class="n">${cnt[a]}</td></tr>`;
  }).join('');
  return `<div class="lean-mini">
    <div class="lean-mini-head">조사기관별 lean <span class="lean-mini-sub">잔차 평균 (+높게 / −낮게)</span></div>
    <table class="lean-mini-tbl"><thead><tr><th>기관</th>${head}<th>n</th></tr></thead><tbody>${rows}</tbody></table>
  </div>`;
}

// === 토글 ===

// view는 'map' 또는 'hex' 두 가지. office에 따라 자동 분기:
//   기초단체장 + map → 시군구 chloropleth
//   기초단체장 + hex → 시군구 hex (#hex2)
//   광역/교육감/정당지지/국정평가/투표의향 + map → 시도 chloropleth (기본)
//   다만 위 메트릭들도 시군구 데이터 있으면 scope='시군구'로 강제 가능 (state.scope)
function isSigunguMode() {
  if (state.office === '기초단체장') return true;
  if (state.scope === '시군구') return true;
  return false;
}

// 현재 office에 시군구 데이터가 있는지
function hasSigunguData() {
  return state.data.polls.some((p) => p.office_level === state.office && p.sigungu);
}

function setView(v) {
  state.view = v;
  const sigungu = isSigunguMode();
  $('#map').toggleAttribute('hidden', v !== 'map');
  $('#hex').toggleAttribute('hidden', !(v === 'hex' && !sigungu));
  $('#hex2').toggleAttribute('hidden', !(v === 'hex' && sigungu));
  document.querySelectorAll('[data-view]').forEach((b) => {
    b.classList.toggle('is-active', b.dataset.view === v);
  });
  if (v === 'map') renderMap();
  else if (sigungu) renderSigunguHex();
  else renderHex();
  renderLegend();
}

// 색 범례 — 현재 office의 지도/격자에 실제 등장하는 정당(또는 메트릭 카테고리).
function legendData() {
  const o = state.office;
  // 정당 기반 office (광역·기초·교육감·정당지지) — 지역별 1위 정당 수집
  const sg = isSigunguMode();
  const polls = state.data.polls.filter(
    (p) => p.office_level === o && !p.is_self_poll && (sg ? p.sigungu : !p.sigungu));
  const groups = {};
  for (const p of polls) {
    const k = sg ? `${p.sido}|${p.sigungu}` : p.sido;
    (groups[k] = groups[k] || []).push(p);
  }
  // 정당명 변형 정규화 (민주당→더불어민주당 등). 색은 partyColor가 이미 동일.
  const CANON = { '민주당': '더불어민주당', '국힘': '국민의힘', '국민의 힘': '국민의힘' };
  const parties = new Set();
  for (const k in groups) {
    const t = summarizeLatest(groups[k]);
    if (t) parties.add(CANON[t.party] || t.party || '무소속');
  }
  // 9회 출마 주요 정당은 1위 안 잡혀도 범례에 표시 (사전 안내)
  for (const p of LEGEND_DEFAULT_PARTIES) parties.add(p);
  const ORDER = LEGEND_DEFAULT_PARTIES.concat(['새로운미래']);
  const sorted = [...parties].sort((a, b) => {
    const ia = ORDER.indexOf(a), ib = ORDER.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
  return sorted.map((raw) => ({ label: raw, color: partyColor(raw) }));
}

function renderLegend() {
  const el = $('#poll-legend');
  if (!el) return;
  const items = legendData();
  el.innerHTML = items.map((it) =>
    `<span class="leg-item"><span class="leg-dot" style="background:${it.color}"></span>${it.label}</span>`
  ).join('') + '<span class="leg-item"><span class="leg-dot" style="background:#e6e9ef"></span>조사 없음</span>';
}
