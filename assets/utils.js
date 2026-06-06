// 공통 유틸리티 — polls.js에서 사용. 시도 코드 매핑, 날짜·라벨 포매팅, 시계열 산점도.
// (Python 측 scripts/_geo.py 매핑과 동기 유지)

// === 시도 코드 매핑 (Python _geo.py와 동기) ===
const SIDO_CODE_TO_NAME = {
  '11':'서울특별시','21':'부산광역시','22':'대구광역시','23':'인천광역시',
  '24':'광주광역시','25':'대전광역시','26':'울산광역시','29':'세종특별자치시',
  '31':'경기도','32':'강원특별자치도','33':'충청북도','34':'충청남도',
  '35':'전북특별자치도','36':'전라남도','37':'경상북도','38':'경상남도','39':'제주특별자치도',
};
const SIGUNGU_SIDO_OVERRIDE = {
  '37310': '대구광역시', // 군위군 — 2023-07-01 경북→대구
};
const SIGUNGU_SIDO_LOOKUP = new Proxy({}, {
  get(_t, key) {
    if (typeof key !== 'string') return undefined;
    return SIGUNGU_SIDO_OVERRIDE[key] || SIDO_CODE_TO_NAME[key.slice(0, 2)];
  },
});

function sigunguSidoFromCode(code) {
  if (!code) return '';
  return SIGUNGU_SIDO_OVERRIDE[code] || SIDO_CODE_TO_NAME[code.slice(0, 2)] || '';
}

// GeoJSON 옛 시도명 → 현행 캐노니컬
function canonSido(s) {
  if (s === '강원도') return '강원특별자치도';
  if (s === '전라북도') return '전북특별자치도';
  if (s === '제주도') return '제주특별자치도';  // 2006-07-01 이전 명칭 (16대 대선 등)
  return s;
}

// === 시군구 짧은 라벨 (hex 셀용) ===
const SIDO_LABEL_SHORT = {
  '서울특별시': '서울', '부산광역시': '부산', '대구광역시': '대구',
  '인천광역시': '인천', '광주광역시': '광주', '대전광역시': '대전',
  '울산광역시': '울산', '세종특별자치시': '세종',
  '경기도': '경기', '강원특별자치도': '강원', '강원도': '강원',
  '충청북도': '충북', '충청남도': '충남',
  '전북특별자치도': '전북', '전라북도': '전북', '전라남도': '전남',
  '경상북도': '경북', '경상남도': '경남',
  '제주특별자치도': '제주',
};

function shortSigunguLabel(name, sido) {
  if (!name) return { prefix: '', short: '' };
  const sidoShort = SIDO_LABEL_SHORT[sido] || '';
  // 일반구 "OOO시XX구" → prefix=시도 약어, short="모도시 일반구"
  // (시도가 빠지면 다른 시도와 헷갈림. "전주 덕진"이 어느 권역인지 권역 표시 필요)
  const m = name.match(/^([가-힣]+)시([가-힣]+구)$/);
  if (m) return { prefix: sidoShort, short: m[1] + ' ' + m[2].replace(/구$/, '') };
  // 일반 시군구 → prefix=시도 약어, short=시군구 suffix 제거
  // 광역시의 한 글자 구(동구·서구·중구 등)는 short=name 원본 (구분 위해)
  const stripped = name.replace(/[시군구]$/, '');
  if (stripped.length === 1) {
    return { prefix: sidoShort, short: name };
  }
  return { prefix: sidoShort, short: stripped };
}

// === 날짜 포매팅 ===
function fmtDate(d) {
  if (!d) return '';
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${+m[2]}/${+m[3]}` : d;
}

function formatPeriod(start, end) {
  if (!start && !end) return '—';
  if (start && end && start !== end) return `${fmtDate(start)} ~ ${fmtDate(end)}`;
  return fmtDate(start || end);
}

// 시간 decay + 표본수 가중 평균으로 정당 기준 1위 산출 (메인 폴 지도·대시보드 공용).
// decay: 7일 = e-fold (최근 추세 반영). polls: 한 지역·직위의 조사 배열.
function summarizeLatest(polls, decayDays = 7, requireRecent = { n: 2, windowDays: 30 }) {
  if (!polls.length) return null;
  const now = Date.now();
  // 최근 N일 안 폴 부족하면 "low_recent" 플래그만 — 데이터는 옛 폴로 계산해 일단 보여줌
  let lowRecent = false;
  if (requireRecent && requireRecent.n > 0) {
    const cutoff = now - requireRecent.windowDays * 86_400_000;
    const recent = polls.filter((p) => {
      const ts = Date.parse(p.period_end || p.period_start || '0');
      return isFinite(ts) && ts >= cutoff;
    });
    if (recent.length < requireRecent.n) lowRecent = true;
  }
  const partyAgg = {};
  const polls_sorted = [...polls].sort((a, b) => (b.period_end || '').localeCompare(a.period_end || ''));
  const latestName = {};
  for (const p of polls_sorted) {
    if (!p.candidates) continue;
    const endStr = p.period_end || p.period_start;
    const endTs = endStr ? Date.parse(endStr) : now;
    const daysOld = Math.max(0, (now - endTs) / 86_400_000);
    const w = Math.exp(-daysOld / decayDays) * (p.sample_size || 500);
    for (const c of p.candidates) {
      if (c.pct == null || c.pct < 0 || c.pct > 100) continue;
      const key = c.party || c.name;
      if (!partyAgg[key]) partyAgg[key] = { party: c.party, sum: 0, w: 0 };
      partyAgg[key].sum += c.pct * w;
      partyAgg[key].w += w;
      if (!(key in latestName)) latestName[key] = c.name;
    }
  }
  const sorted = Object.entries(partyAgg)
    .map(([k, v]) => ({ party: v.party, name: latestName[k] || '', pct: v.sum / v.w }))
    .filter((x) => x.pct != null && isFinite(x.pct))
    .sort((a, b) => b.pct - a.pct);
  if (!sorted.length) return null;
  const top = sorted[0];
  const sec = sorted[1] || { name: '', pct: 0 };
  // sample_error 평균 — "95% 신뢰수준에 ±4.4%P" 형태에서 "±" 뒤 숫자만.
  // (그냥 첫 숫자면 "95"가 잡혀버림)
  const errs = polls.map((p) => {
    const m = (p.sample_error || '').match(/±\s*(\d+\.?\d*)/);
    return m ? parseFloat(m[1]) : null;
  }).filter((x) => x != null);
  const avgErr = errs.length ? errs.reduce((a, b) => a + b, 0) / errs.length : null;
  const gap = top.pct - (sec.pct || 0);
  // 통계적으로 의미 있는 격차: gap - err (1×, 광역 시도 단위는 폴 다수 평균이라 사실상 더 작음)
  const effGap = avgErr != null ? Math.max(0, gap - avgErr) : gap;
  return {
    party: top.party, name: top.name, pct: Math.round(top.pct * 10) / 10,
    second_name: sec.name, second_pct: Math.round(sec.pct * 10) / 10,
    gap, effective_gap: effGap, sample_error: avgErr,
    low_recent: lowRecent,
    period: polls_sorted[0].period_end, n_polls: polls.length, source: polls_sorted[0],
  };
}

// 여론조사 카드 HTML (메인 폴 페이지·재보궐 공용). parties.js partyColor 의존.
// p: 조사 record (candidates·agency·기간·meta·source_url), officeLabel: pc-office 표시 텍스트.
function renderPollCard(p, officeLabel) {
  // 비율 높은 순으로 표시 — 시각적으로 1위가 위
  const sortedCands = [...p.candidates].sort((a, b) => (b.pct || 0) - (a.pct || 0));
  const maxPct = Math.max(...sortedCands.map((c) => c.pct || 0));
  const topParty = sortedCands.length ? sortedCands[0].party : '';
  const pctField = (v) => (v != null && v !== '' ? v + '%' : '—');
  const bars = sortedCands.map((c) => {
    const color = partyColor(c.party);
    const textCol = partyTextColor(c.party);
    const w = maxPct > 0 ? (c.pct / maxPct) * 100 : 0;
    return `<div class="pc-bar-row">
      <span class="name">${c.name || c.party || ''}</span>
      <span class="pc-bar"><span class="pc-bar-fill" style="width:${w}%;background:${color}"></span></span>
      <span class="pct" style="color:${textCol}">${c.pct}%</span>
    </div>`;
  }).join('');
  // 메트릭(적합도·당선가능성)·당내 경선·양자대결을 office 라벨 옆에 표시 — 같은 후보 표가 여러 번 보일 때 구분
  const metricBadge = p.metric_type && p.metric_type !== '후보지지' && p.metric_type !== p.office_label
    ? ` · ${p.metric_type}` : '';
  const titleTag = (() => {
    const t = p.table_title || '';
    const m = t.match(/(더불어민주당|국민의힘|조국혁신당|개혁신당|진보당)\s*후보/);
    if (m) return ` · ${m[1]} 경선`;
    if (/vs\.?|맞붙|가상대결/.test(t)) return ' · 양자대결';
    return '';
  })();
  return `<div class="poll-card" style="border-left-color:${partyColor(topParty)}">
    <div class="pc-hdr">
      <span class="pc-period">${formatPeriod(p.period_start, p.period_end)}</span>
      <span class="pc-office">${officeLabel || p.office_label || ''}${metricBadge}${titleTag}</span>
    </div>
    <div class="pc-agency">${p.agency}</div>
    <div class="pc-bars">${bars}</div>
    <div class="pc-meta">
      <span>의뢰 · ${p.requester || '—'}</span>
      <span>방법 · ${p.method || '—'}</span>
      <span>표본 · ${p.sample_size ? p.sample_size + '명' : '—'}</span>
      <span>응답률 · ${pctField(p.response_rate)}</span>
      <span>접촉률 · ${pctField(p.contact_rate)}</span>
      <span>오차 · ${p.sample_error || '—'}</span>
    </div>
    <div class="pc-legal">그 밖의 사항은 <a href="${p.source_url}" target="_blank" rel="noopener">중앙선거여론조사심의위원회 홈페이지</a> 참조</div>
  </div>`;
}

// === 정당 누적 비율 막대 + 범례 (메인 status·지선 archive 공용) ===
// counts: [[party, n], ...] (정렬 가정 안 함 — 내부 정렬), total: 합계.
// CSS는 common.css의 .sbar* / .sleg*. 바깥 배치(가로/세로)는 호출부가 정함.
function partyStackBar(counts, total) {
  const sorted = counts.slice().sort((a, b) => b[1] - a[1]);
  const segs = sorted.map(([p, c]) => {
    const pct = total > 0 ? (c / total * 100) : 0;
    return `<span class="sbar-seg" style="flex:${c};background:${partyColor(p)}" title="${p} ${c} (${pct.toFixed(1)}%)">${pct >= 9 ? `<span class="sbar-seg-n">${c}</span>` : ''}</span>`;
  }).join('');
  return `<div class="sbar">${segs}</div>`;
}
// 1·N위 inline, 나머지(1석 소수정당 포함)는 "+ …" tail로 전부 표시.
function partyStackLegend(counts, top = 2) {
  const sorted = counts.slice().sort((a, b) => b[1] - a[1]);
  const head = sorted.slice(0, top), tail = sorted.slice(top);
  const headHTML = head.map(([p, c]) =>
    `<span class="sleg" style="color:${partyColor(p)}"><b>${c}</b> ${p}</span>`).join(' ');
  const tailHTML = tail.length
    ? '<span class="sleg-tail">+ ' + tail.map(([p, c]) =>
        `<span style="color:${partyColor(p)}"><b>${c}</b> ${p}</span>`).join(' · ') + '</span>'
    : '';
  return headHTML + (tailHTML ? ' ' + tailHTML : '');
}

// === 시계열 산점도 SVG ===
// 각 점 = 한 조사·한 후보. x=조사기간 끝, y=지지율, color=정당색.
// 같은 ts 여러 점 약간 jitter, hover 메타. (parties.js의 partyColor 의존)
// roster: { "sido|name": {sgg,jd,...} or null } — NEC 등록 후보 명부.
// 등록 후보면 진한 dot + line, 사전 거론은 옅은 dot만.
function buildScatterSVG(polls, roster = null) {
  const W = 380, H = 180, pad_l = 28, pad_r = 12, pad_t = 14, pad_b = 22;
  const points = [];
  for (const p of polls) {
    if (!p.period_end || !p.candidates) continue;
    const ts = Date.parse(p.period_end);
    if (!isFinite(ts)) continue;
    for (const c of p.candidates) {
      if (c.pct == null) continue;
      const sd = p.sido || '';
      const nm = c.name || '';
      // 빈 객체 {} 는 truthy지만 미등록 — sg_typecode 있어야 진짜 등록
      const hit = roster && nm ? roster[`${sd}|${nm}`] : null;
      const registered = !!(hit && hit.sg_typecode);
      points.push({ ts, pct: c.pct, party: c.party, name: nm, agency: p.agency, registered });
    }
  }
  if (points.length < 2) return '';
  const minTs = Math.min(...points.map((p) => p.ts));
  const maxTs = Math.max(...points.map((p) => p.ts));
  const singleTs = minTs === maxTs;  // 한 조사만 — 모든 점이 같은 ts
  const tsRange = (maxTs - minTs) || 86_400_000 * 7;
  const maxPct = Math.max(60, Math.ceil(Math.max(...points.map((p) => p.pct)) / 10) * 10);
  // singleTs면 모든 점을 중앙(W/2)으로
  const x = (ts) => singleTs
    ? (pad_l + W - pad_r) / 2
    : pad_l + ((ts - minTs) / tsRange) * (W - pad_l - pad_r);
  const y = (pct) => pad_t + (1 - pct / maxPct) * (H - pad_t - pad_b);
  const jittered = points.map((p) => ({
    ...p,
    jx: x(p.ts) + (Math.random() - 0.5) * 4,
  }));
  let grid = '';
  for (const v of [0, 25, 50, maxPct]) {
    if (v > maxPct) continue;
    const yy = y(v);
    grid += `<line x1="${pad_l}" y1="${yy}" x2="${W - pad_r}" y2="${yy}" stroke="var(--rule, #e6e9ef)" stroke-width="0.6"/>`;
    grid += `<text x="${pad_l - 4}" y="${yy + 3}" font-size="9" fill="var(--ink-mute, #8a93a3)" text-anchor="end">${v}</text>`;
  }
  const midTs = (minTs + maxTs) / 2;
  let xax = '';
  const axisTimes = singleTs ? [minTs] : [minTs, midTs, maxTs];
  for (const ts of axisTimes) {
    const xx = x(ts);
    const d = new Date(ts);
    const label = `${d.getMonth() + 1}/${d.getDate()}`;
    xax += `<text x="${xx}" y="${H - 6}" font-size="9" fill="var(--ink-mute, #8a93a3)" text-anchor="middle">${label}</text>`;
  }
  // 등록 후보 + "최근까지 살아남은" 후보만 line. 최신 폴 기준 14일 안에 등장한 후보만.
  let lines = '';
  if (roster) {
    const latestTs = Math.max(...points.map((p) => p.ts));
    const cutoff = latestTs - 14 * 86_400_000;
    const byName = {};
    for (const p of points) {
      if (!p.registered) continue;
      (byName[p.name] ||= []).push(p);
    }
    for (const [nm, ps] of Object.entries(byName)) {
      if (ps.length < 2) continue;
      ps.sort((a, b) => a.ts - b.ts);
      // 후보의 가장 최신 점이 cutoff 이전이면 line 안 그림 (= 마지막까지 못 온 후보)
      if (ps[ps.length - 1].ts < cutoff) continue;
      const color = partyColor(ps[0].party);
      const path = ps.map((p) => `${x(p.ts).toFixed(1)},${y(p.pct).toFixed(1)}`).join(' ');
      lines += `<polyline points="${path}" fill="none" stroke="${color}" stroke-width="1.2" stroke-opacity="0.55" stroke-linejoin="round"/>`;
    }
  }
  const dots = jittered.map((p) => {
    // 등록 후보: 정당색 진하게. 사전 거론: 회색 통일 + 옅고 작게 (시각적 노이즈 감소).
    const isSub = roster && !p.registered;
    const color = isSub ? '#9ea3ad' : partyColor(p.party);
    const fillOp = isSub ? 0.35 : (roster ? 0.85 : 0.75);
    const r = isSub ? 1.6 : (roster ? 3.2 : 2.5);
    const strokeAttr = isSub ? '' : ` stroke="${color}" stroke-width="0.5"`;
    return `<circle cx="${p.jx.toFixed(1)}" cy="${y(p.pct).toFixed(1)}" r="${r}" fill="${color}" fill-opacity="${fillOp}"${strokeAttr}><title>${p.name || '?'} (${p.party || '?'}) ${p.pct}%${isSub ? ' · 미등록/사전' : ''} · ${p.agency} · ${fmtDate(new Date(p.ts).toISOString().slice(0, 10))}</title></circle>`;
  }).join('');
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet">${grid}${xax}${lines}${dots}</svg>`;
}

// 정당 지지율 추이 — 정당별 시계열 선 (정당지지 office 전용).
// 같은 날짜 여러 조사는 평균내 하루 한 점으로 묶어 선이 덜 튀게 한다.
const PARTY_SHORT = {
  '더불어민주당': '민주', '국민의힘': '국힘', '조국혁신당': '조국혁신',
  '개혁신당': '개혁', '진보당': '진보', '기본소득당': '기본소득',
  '사회민주당': '사민', '새로운미래': '새미래', '정의당': '정의', '무소속': '무소속',
};
function buildPartyTrendSVG(polls) {
  const CANON = { '민주당': '더불어민주당', '국힘': '국민의힘', '국민의 힘': '국민의힘' };
  const series = {};  // party → { dateStr → [pct] }
  for (const p of polls) {
    if (!p.period_end || !p.candidates) continue;
    if (!isFinite(Date.parse(p.period_end))) continue;
    for (const c of p.candidates) {
      if (c.pct == null || !c.party) continue;
      const party = CANON[c.party] || c.party;
      ((series[party] ||= {})[p.period_end] ||= []).push(c.pct);
    }
  }
  const lines = {};  // party → [{ts, pct}] (하루 평균, 시간순)
  let minTs = Infinity, maxTs = -Infinity, maxPct = 0;
  for (const [party, byDate] of Object.entries(series)) {
    const pts = Object.entries(byDate).map(([ds, arr]) => ({
      ts: Date.parse(ds), pct: arr.reduce((a, b) => a + b, 0) / arr.length,
    })).sort((a, b) => a.ts - b.ts);
    lines[party] = pts;
    for (const pt of pts) { minTs = Math.min(minTs, pt.ts); maxTs = Math.max(maxTs, pt.ts); maxPct = Math.max(maxPct, pt.pct); }
  }
  const parties = Object.keys(lines);
  if (!parties.length) return '';
  const mean = (ps) => ps.reduce((s, p) => s + p.pct, 0) / ps.length;
  parties.sort((a, b) => mean(lines[b]) - mean(lines[a]));  // 지지율 높은 순
  const W = 380, H = 210, pl = 28, pr = 56, pt = 12, pb = 24;
  maxPct = Math.max(50, Math.ceil(maxPct / 10) * 10);
  const tsRange = (maxTs - minTs) || 86_400_000 * 7;
  const x = (ts) => pl + ((ts - minTs) / tsRange) * (W - pl - pr);
  const y = (pct) => pt + (1 - pct / maxPct) * (H - pt - pb);
  let grid = '';
  for (const v of [0, 25, 50, maxPct]) {
    if (v > maxPct) continue;
    const yy = y(v);
    grid += `<line x1="${pl}" y1="${yy}" x2="${W - pr}" y2="${yy}" stroke="var(--rule, #e6e9ef)" stroke-width="0.6"/>`;
    grid += `<text x="${pl - 4}" y="${yy + 3}" font-size="9" fill="var(--ink-mute, #8a93a3)" text-anchor="end">${v}</text>`;
  }
  let xax = '';
  for (const ts of [minTs, (minTs + maxTs) / 2, maxTs]) {
    const d = new Date(ts);
    xax += `<text x="${x(ts)}" y="${H - 6}" font-size="9" fill="var(--ink-mute, #8a93a3)" text-anchor="middle">${d.getMonth() + 1}/${d.getDate()}</text>`;
  }
  // 라벨 y겹침 방지 — 위에서부터 최소 간격 11px
  let lastLabelY = -99;
  let body = '';
  for (const party of parties) {
    const pts = lines[party];
    const color = partyColor(party);
    if (pts.length >= 2) {
      const dpath = pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.ts).toFixed(1)},${y(p.pct).toFixed(1)}`).join(' ');
      body += `<path d="${dpath}" fill="none" stroke="${color}" stroke-width="1.8" stroke-opacity="0.9"/>`;
    }
    for (const p of pts) {
      body += `<circle cx="${x(p.ts).toFixed(1)}" cy="${y(p.pct).toFixed(1)}" r="2.4" fill="${color}"><title>${PARTY_SHORT[party] || party} ${p.pct.toFixed(1)}% · ${fmtDate(new Date(p.ts).toISOString().slice(0, 10))}</title></circle>`;
    }
    const last = pts[pts.length - 1];
    let ly = y(last.pct) + 3;
    if (ly - lastLabelY < 11) ly = lastLabelY + 11;  // 겹치면 아래로 밀기
    lastLabelY = ly;
    body += `<text x="${W - pr + 3}" y="${ly.toFixed(1)}" font-size="9" fill="${color}" font-weight="600">${PARTY_SHORT[party] || party}</text>`;
  }
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet">${grid}${xax}${body}</svg>`;
}
