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

  // 시계열 차트 — 정당지지는 정당별 추이 선, 그 외는 후보 산점도 (조사 ≥ 2건)
  if (state.office === '정당지지') {
    const svg = buildPartyTrendSVG(officePolls);
    if (svg) html += `<div class="scatter-wrap">${svg}</div>`;
  } else if (officePolls.length >= 2) {
    html += `<div class="scatter-wrap">${buildScatterSVG(officePolls, state.roster)}</div>`;
  }
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
