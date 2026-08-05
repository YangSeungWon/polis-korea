// 성·연령 득표 기여 — archive 대선. 막대 길이=실제 투표자수(NEC 실측), 채움=후보 득표구성(출구조사).
//   우리 정신: 추상 % 아닌 실제 크기. 두 관점 토글:
//     ① 집단→후보(득표 기여): 성연령 12행, 길이=투표자수, 스택=후보.
//     ② 후보→지지층 구성(역피벗): 후보 3행, 길이=총득표, 스택=성연령.
//   데이터: data/polls/demographic_impact_<n>pres.json (build_demographic_impact).
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const AGES = ['18-29', '30', '40', '50', '60', '70+'];
  const AGE_LABEL = { '18-29': '18·20대', '30': '30대', '40': '40대', '50': '50대', '60': '60대', '70+': '70대+' };
  const SEXES = ['남성', '여성'];
  const pcol = (p) => (typeof partyColor === 'function' ? partyColor(p) : '#888');
  const ptc = (p) => (typeof partyTextColor === 'function' ? partyTextColor(p) : 'var(--ink)');
  const fmt = (n) => n.toLocaleString();

  let DATA = null, TURN = null, view = 'group';   // 'group' | 'cand' | 'region' | 'swing'
  let rsex = '합계';   // 지역 투표율 뷰의 성별 (합계/남자/여자)
  let PRIOR = null, priorN = null;   // 직전 비교 대선(성연령 grid 있는). swing 뷰용.
  let swingMetric = 'dem';           // 'dem'(이재명 득표율) | 'margin'(이재명 − 보수블록)
  // 연령은 순서가 있는 축이다 — 값으로 재정렬하면 연령 곡선이 사라진다. 기본은 연령 순.
  // (변화량 순은 '누가 가장 움직였나' 랭킹으로 여전히 쓸모 있어 토글로 남긴다.)
  let swingSort = 'age';             // 'age' | 'swing'
  const PRIOR_OF = { 21: 20 };       // 둘 다 출구조사 성연령 grid 보유 → 같은 후보(이재명) 비교 가능
  const SEX_SHORT = { '남성': '남', '여성': '여' };
  const MALE_C = '#2a6fb0', FEM_C = '#c2557a';   // 남/여 색(덤벨·격차)

  const hasGrid = () => SEXES.every((s) => AGES.some((a) => cellOf(s, a)));
  // 한 데이터셋·셀의 민주(이재명) 득표율, 또는 이재명−보수블록(국힘+개혁신당) 마진.
  function metricOf(data, sex, age, metric) {
    const c = (data.cells || []).find((x) => x.sex === sex && x.age === age);
    if (!c || !(c.shares || []).some((s) => s.party === '더불어민주당')) return null;
    const sum = (ps) => (c.shares || []).filter((s) => ps.includes(s.party)).reduce((a, s) => a + s.pct, 0);
    const dem = sum(['더불어민주당']);
    return metric === 'margin' ? dem - sum(['국민의힘', '개혁신당']) : dem;
  }
  const SIDO_ORDER = ['서울특별시', '인천광역시', '경기도', '강원특별자치도', '대전광역시', '세종특별자치시',
    '충청북도', '충청남도', '광주광역시', '전북특별자치도', '전라남도',
    '대구광역시', '부산광역시', '울산광역시', '경상북도', '경상남도', '제주특별자치도'];
  const SIDO_SHORT = { '서울특별시': '서울', '인천광역시': '인천', '경기도': '경기', '강원특별자치도': '강원',
    '대전광역시': '대전', '세종특별자치시': '세종', '충청북도': '충북', '충청남도': '충남', '광주광역시': '광주',
    '전북특별자치도': '전북', '전라남도': '전남', '대구광역시': '대구', '부산광역시': '부산', '울산광역시': '울산',
    '경상북도': '경북', '경상남도': '경남', '제주특별자치도': '제주' };

  function cellOf(sex, age) {
    return (DATA.cells || []).find((c) => c.sex === sex && c.age === age);
  }

  // 한 행 = 라벨 + 막대(길이 vw% ∝ value) + 스택 세그먼트.
  function barRow(label, sub, total, maxTotal, segs) {
    const w = maxTotal ? (total / maxTotal * 100) : 0;
    const segHtml = segs.filter((s) => s.value > 0).map((s) => {
      const sw = total ? (s.value / total * 100) : 0;
      return `<span class="dg-seg" style="width:${sw.toFixed(2)}%;background:${s.color}" title="${s.title}"></span>`;
    }).join('');
    return `<div class="dg-row">
      <div class="dg-rlab">${label}${sub ? `<span class="dg-rsub">${sub}</span>` : ''}</div>
      <div class="dg-track"><div class="dg-bar" style="width:${w.toFixed(1)}%">${segHtml}</div>
        <span class="dg-rtot">${fmt(total)}</span></div>
    </div>`;
  }

  function renderGroupView() {
    // 성연령 12행, 길이=투표자수, 스택=후보 득표. 남성/여성 그룹.
    const maxV = Math.max(...DATA.cells.map((c) => c.voters), 1);
    let html = '';
    for (const sex of SEXES) {
      html += `<div class="dg-grouphd">${sex}</div>`;
      for (const age of AGES) {
        const c = cellOf(sex, age);
        if (!c) continue;
        const segs = (c.shares || []).map((s) => ({
          value: s.votes, color: pcol(s.party),
          title: `${s.name} ${s.pct}% · ${fmt(s.votes)}표`,
        }));
        html += barRow(AGE_LABEL[age], `투표율 ${c.turnout}%`, c.voters, maxV, segs);
      }
    }
    return html;
  }

  function renderCandView() {
    // 후보 3행, 길이=총득표, 스택=성연령(진하기로 연령, 좌남우여는 생략—연령 띠 색 단계).
    const byCand = {};
    for (const c of DATA.cells) {
      for (const s of (c.shares || [])) {
        const k = s.name;
        (byCand[k] = byCand[k] || { name: s.name, party: s.party, total: 0, segs: [] });
        byCand[k].total += s.votes;
        byCand[k].segs.push({ sex: c.sex, age: c.age, votes: s.votes });
      }
    }
    const cands = Object.values(byCand).sort((a, b) => b.total - a.total);
    const maxT = Math.max(...cands.map((c) => c.total), 1);
    // 연령 명도 단계(같은 당색, 젊을수록 옅게) + 성별 좌우 구분은 라벨 타이틀로.
    return cands.map((c) => {
      const base = pcol(c.party);
      const order = [];
      for (const sex of SEXES) for (const age of AGES) {
        const sg = c.segs.find((x) => x.sex === sex && x.age === age);
        if (sg) order.push({ ...sg });
      }
      const segs = order.map((sg) => {
        const ai = AGES.indexOf(sg.age);
        const op = 0.45 + 0.55 * (ai / (AGES.length - 1));   // 70+ 진하게
        return {
          value: sg.votes,
          color: base, // 명도는 opacity 세그로
          _op: op, _sex: sg.sex, _age: sg.age,
          title: `${AGE_LABEL[sg.age]} ${sg.sex} · ${fmt(sg.votes)}표 (${(sg.votes / c.total * 100).toFixed(0)}%)`,
        };
      });
      // 스택 — opacity 적용 위해 직접 생성
      const segHtml = segs.map((s) => `<span class="dg-seg${s._sex === '여성' ? ' dg-f' : ''}" style="width:${(s.value / c.total * 100).toFixed(2)}%;background:${base};opacity:${s._op.toFixed(2)}" title="${s.title}"></span>`).join('');
      const w = (c.total / maxT * 100).toFixed(1);
      return `<div class="dg-row">
        <div class="dg-rlab" style="color:${ptc(c.party)}">${c.name}</div>
        <div class="dg-track"><div class="dg-bar" style="width:${w}%">${segHtml}</div>
          <span class="dg-rtot">${fmt(c.total)}</span></div>
      </div>`;
    }).join('');
  }

  // ── 지역 투표율 — 시도×연령 히트맵(성별 토글). 색 진하기 = 투표율(teal). 실측 NEC. ──
  function renderRegionView() {
    if (!TURN) return '<p class="detail-empty">지역 투표율 데이터가 없습니다.</p>';
    const all = [];
    for (const s of SIDO_ORDER) for (const a of AGES) {
      const t = (TURN[s] || {})[rsex] && TURN[s][rsex][a]; if (t && t.turnout != null) all.push(t.turnout);
    }
    const lo = Math.min(...all), hi = Math.max(...all);
    const cellBg = (v) => {
      const k = hi > lo ? (v - lo) / (hi - lo) : 0.5;            // 상대 스케일
      return `rgba(20,140,130,${(0.12 + 0.78 * k).toFixed(2)})`;  // teal
    };
    const sexBtns = ['합계', '남자', '여자'].map((s) => `<button class="dg-rsex${s === rsex ? ' is-active' : ''}" data-rsex="${s}">${s}</button>`).join('');
    let head = '<div class="dg-hcell"></div>' + AGES.map((a) => `<div class="dg-hcell">${AGE_LABEL[a]}</div>`).join('');
    let rows = '';
    for (const s of SIDO_ORDER) {
      const blk = (TURN[s] || {})[rsex] || {};
      rows += `<div class="dg-hcell dg-rlab2">${SIDO_SHORT[s] || s}</div>`;
      for (const a of AGES) {
        const t = blk[a];
        rows += t && t.turnout != null
          ? `<div class="dg-hm" style="background:${cellBg(t.turnout)}" title="${s} ${AGE_LABEL[a]} ${rsex} 투표율 ${t.turnout}% (투표 ${fmt(t.voters)}/${fmt(t.electors)})">${t.turnout.toFixed(0)}</div>`
          : '<div class="dg-hm dg-na"></div>';
      }
    }
    const nat = (TURN['전국'] || {})[rsex] || {};
    const natRow = AGES.map((a) => nat[a] ? `<b>${nat[a].turnout}</b>` : '–').join(' · ');
    return `<div class="dg-rtoggle">${sexBtns}</div>`
      + `<div class="dg-heat" style="grid-template-columns:46px repeat(${AGES.length},1fr)">${head}${rows}</div>`
      + `<p class="ar-parl-note">전국(${rsex}): ${natRow} · 색 진할수록 투표율 높음(상대). 실측 NEC 표본.</p>`;
  }

  // ── 직전 대선 대비 swing — 같은 민주 후보(이재명) 집단별 득표 변화. 발산형 막대. ──
  //   기본 정렬은 연령 순(남/여 짝). 변화량 순으로 정렬하면 12행이 섞여 연령 곡선과
  //   성별 격차가 둘 다 흩어진다 — 연령은 순서가 있는 축이라 값으로 재정렬하면 정보가 준다.
  function renderSwingView() {
    if (!PRIOR) return '<p class="detail-empty">비교할 직전 대선 데이터가 없습니다.</p>';
    const m = swingMetric;
    const tg = `<div class="dg-rtoggle">`
      + `<button class="dg-rsex${m === 'dem' ? ' is-active' : ''}" data-swm="dem">이재명 득표율</button>`
      + `<button class="dg-rsex${m === 'margin' ? ' is-active' : ''}" data-swm="margin">이재명 − 보수블록</button>`
      + `<span class="dg-rgap"></span>`
      + `<button class="dg-rsex${swingSort === 'age' ? ' is-active' : ''}" data-swsort="age">연령 순</button>`
      + `<button class="dg-rsex${swingSort === 'swing' ? ' is-active' : ''}" data-swsort="swing">변화 순</button></div>`;
    // 연령 순은 같은 연령의 남/여를 붙여 놓는다 — 연령 곡선과 성별 격차를 한 번에 읽게.
    const rows = [];
    if (swingSort === 'age') {
      for (const age of AGES) for (const sex of SEXES) {
        const now = metricOf(DATA, sex, age, m), pri = metricOf(PRIOR, sex, age, m);
        if (now == null || pri == null) continue;
        rows.push({ sex, age, now, pri, sw: now - pri });
      }
    } else {
      for (const sex of SEXES) for (const age of AGES) {
        const now = metricOf(DATA, sex, age, m), pri = metricOf(PRIOR, sex, age, m);
        if (now == null || pri == null) continue;
        rows.push({ sex, age, now, pri, sw: now - pri });
      }
      rows.sort((a, b) => b.sw - a.sw);
    }
    if (!rows.length) return '<p class="detail-empty">비교 데이터가 없습니다.</p>';
    const maxAbs = Math.max(...rows.map((r) => Math.abs(r.sw)), 1);
    const demC = pcol('더불어민주당');
    const lossC = '#c0392b';
    const demTC = ptc('더불어민주당');
    const lossTC = (typeof _textLegible === 'function') ? _textLegible(lossC) : lossC;
    let html = '';
    let prevAge = null;
    for (const r of rows) {
      // 연령 순일 때만 연령이 바뀌는 자리에 여백 — 남/여 한 쌍이 한 덩어리로 보이게.
      const newGroup = swingSort === 'age' && prevAge != null && r.age !== prevAge;
      prevAge = r.age;
      const pos = r.sw >= 0, col = pos ? demC : lossC;
      // 막대 바깥 값은 글씨 — 면색 그대로 쓰면 배경 대비가 안 나온다.
      const tcol = pos ? demTC : lossTC;
      const w = Math.abs(r.sw) / maxAbs * 46;
      const ws = w.toFixed(1);
      const bar = pos
        ? `<div class="dg-sbar" style="left:50%;width:${ws}%;background:${col}"></div>`
        : `<div class="dg-sbar" style="left:calc(50% - ${ws}%);width:${ws}%;background:${col}"></div>`;
      const inside = w >= 13;   // 긴 막대는 값을 막대 안(흰색), 짧은 막대는 바깥(당색)
      const valStyle = inside
        ? (pos ? `right:calc(50% - ${ws}% + 4px);text-align:right;color:#fff`
               : `left:calc(50% - ${ws}% + 4px);color:#fff`)
        : (pos ? `left:calc(50% + ${ws}% + 4px);color:${tcol}`
               : `right:calc(50% + ${ws}% + 4px);text-align:right;color:${tcol}`);
      html += `<div class="dg-srow${newGroup ? ' is-newage' : ''}"><span class="dg-slab">${SEX_SHORT[r.sex]} ${AGE_LABEL[r.age]}</span>`
        + `<div class="dg-strack"><div class="dg-zero"></div>${bar}`
        + `<span class="dg-sval" style="${valStyle}">${pos ? '+' : ''}${r.sw.toFixed(1)}</span></div>`
        + `<span class="dg-send" title="이재명 득표율 ${priorN}대→현재">${r.pri.toFixed(0)}→${r.now.toFixed(0)}</span></div>`;
    }
    const what = swingMetric === 'margin' ? '이재명 − 보수블록(국힘+개혁신당) 마진' : '민주당 후보(이재명) 득표율';
    return tg
      + `<p class="ar-parl-note">${what}의 직전 대선(${priorN}대) 대비 변화 — 같은 후보라 순수 이동. `
      + `<b style="color:${demTC}">파랑=이재명 쪽</b>, <b style="color:${lossTC}">빨강=보수 쪽</b>. 출구조사 기준.</p>`
      + `<div class="dg-swing">${html}</div>`;
  }

  // ── 성별 격차(이대남·이대녀) — 연령별 이재명 득표율 남녀 덤벨. grid 있는 회차. ──
  function renderGapView() {
    const data = [];
    let mx = 0;
    for (const age of AGES) {
      const m = metricOf(DATA, '남성', age, 'dem'), f = metricOf(DATA, '여성', age, 'dem');
      if (m == null || f == null) continue;
      data.push({ age, m, f, gap: m - f });
      mx = Math.max(mx, m, f);
    }
    if (!data.length) return '<p class="detail-empty">성·연령 grid가 없습니다.</p>';
    const scale = Math.max(10, Math.ceil(mx / 10) * 10);
    let html = '';
    for (const r of data) {
      const xm = (r.m / scale * 100), xf = (r.f / scale * 100);
      const lo = Math.min(xm, xf), hi = Math.max(xm, xf);
      html += `<div class="dg-grow"><span class="dg-slab">${AGE_LABEL[r.age]}</span>`
        + `<div class="dg-gtrack"><div class="dg-gline" style="left:${lo.toFixed(1)}%;width:${(hi - lo).toFixed(1)}%"></div>`
        + `<span class="dg-gdot" style="left:${xf.toFixed(1)}%;background:${FEM_C}" title="여성 ${r.f.toFixed(1)}%"></span>`
        + `<span class="dg-gdot" style="left:${xm.toFixed(1)}%;background:${MALE_C}" title="남성 ${r.m.toFixed(1)}%"></span></div>`
        + `<span class="dg-send">${r.gap >= 0 ? '+' : ''}${r.gap.toFixed(0)}</span></div>`;
    }
    return `<p class="ar-parl-note"><b style="color:${MALE_C}">●남성</b> <b style="color:${FEM_C}">●여성</b>의 이재명(민주) 득표율 — 점 사이=남녀 격차. `
      + `18·20대에서 가장 크게 갈린다(이대남·이대녀). 우측 숫자=남−여(%p). 출구조사 기준.</p>`
      + `<div class="dg-gap">${html}</div>`;
  }

  function draw(host) {
    const body = host.querySelector('.dg-body');
    body.innerHTML = view === 'group' ? renderGroupView() : view === 'cand' ? renderCandView()
      : view === 'gap' ? renderGapView() : view === 'swing' ? renderSwingView() : renderRegionView();
    host.querySelectorAll('[data-dgv]').forEach((b) => b.classList.toggle('is-active', b.dataset.dgv === view));
    body.querySelectorAll('[data-rsex]').forEach((b) => b.addEventListener('click', () => { rsex = b.dataset.rsex; draw(host); }));
    body.querySelectorAll('[data-swm]').forEach((b) => b.addEventListener('click', () => { swingMetric = b.dataset.swm; draw(host); }));
    body.querySelectorAll('[data-swsort]').forEach((b) => b.addEventListener('click', () => { swingSort = b.dataset.swsort; draw(host); }));
  }

  async function render(ctx) {
    const n = ctx && ctx.meta && ctx.meta.electionN;
    if (n == null) return;
    if (document.getElementById('ar-demographics')) return;   // 1회
    let d;
    try {
      d = await fetch(`data/polls/demographic_impact_${n}pres.json`).then((r) => (r.ok ? r.json() : null));
    } catch (e) { d = null; }
    if (!d || !(d.cells || []).length) return;
    DATA = d;
    try { TURN = await fetch(`data/polls/turnout_demographics_${n}pres.json`).then((r) => (r.ok ? r.json() : null)); }
    catch (e) { TURN = null; }
    // 직전 대선(성연령 grid 보유) 로드 → swing 뷰. 같은 민주 후보(이재명) 집단 이동 비교.
    PRIOR = null; priorN = PRIOR_OF[n] || null;
    if (priorN) {
      try { PRIOR = await fetch(`data/polls/demographic_impact_${priorN}pres.json`).then((r) => (r.ok ? r.json() : null)); }
      catch (e) { PRIOR = null; }
      if (!PRIOR || !(PRIOR.cells || []).length) { PRIOR = null; priorN = null; }
    }
    const anchor = document.getElementById('ar-exitpoll') || document.getElementById('ar-counting')
      || document.querySelector('.ar-section');
    if (!anchor || !anchor.parentElement) return;
    const sec = document.createElement('section');
    sec.className = 'ar-section'; sec.id = 'ar-demographics';
    sec.innerHTML = '<h2 class="ar-section-title">성·연령 득표 기여'
      + '<span class="info-i" tabindex="0" role="button" aria-label="설명">i<span class="info-pop">'
      + '막대 길이 = 실제 투표자수(NEC 투표율 분석, 표본). 채움 = 후보 득표 구성(방송3사 출구조사 추정). '
      + '%가 아닌 실제 표 크기로 영향을 본다 — 이대남은 비율 높아도 인구·투표율이 낮아 표는 작다.</span></span></h2>'
      + '<div class="dg-toggle seg" role="tablist">'
      + '<button class="seg-btn is-active" data-dgv="group" role="tab">집단 → 후보</button>'
      + '<button class="seg-btn" data-dgv="cand" role="tab">후보 → 지지층</button>'
      + (hasGrid() ? '<button class="seg-btn" data-dgv="gap" role="tab">성별 격차</button>' : '')
      + (TURN ? '<button class="seg-btn" data-dgv="region" role="tab">지역 투표율</button>' : '')
      + (PRIOR ? `<button class="seg-btn" data-dgv="swing" role="tab">직전 대비 swing</button>` : '') + '</div>'
      + '<div class="dg-body"></div>'
      + `<p class="ar-parl-note">크기=실측 투표자수 · 구성=출구조사 추정(±오차). 총 투표자 ${fmt(d.total_voters)}(표본).</p>`;
    anchor.parentElement.insertBefore(sec, anchor.nextSibling);
    sec.querySelectorAll('[data-dgv]').forEach((b) => b.addEventListener('click', () => { view = b.dataset.dgv; draw(sec); }));
    draw(sec);
  }

  window.Archive = window.Archive || {};
  window.Archive.demographics = { render };
})();
