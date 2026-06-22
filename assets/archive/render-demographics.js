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

  let DATA = null, TURN = null, view = 'group';   // 'group' | 'cand' | 'region'
  let rsex = '합계';   // 지역 투표율 뷰의 성별 (합계/남자/여자)
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

  function draw(host) {
    const body = host.querySelector('.dg-body');
    body.innerHTML = view === 'group' ? renderGroupView() : view === 'cand' ? renderCandView() : renderRegionView();
    host.querySelectorAll('[data-dgv]').forEach((b) => b.classList.toggle('is-active', b.dataset.dgv === view));
    body.querySelectorAll('[data-rsex]').forEach((b) => b.addEventListener('click', () => { rsex = b.dataset.rsex; draw(host); }));
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
      + (TURN ? '<button class="seg-btn" data-dgv="region" role="tab">지역 투표율</button>' : '') + '</div>'
      + '<div class="dg-body"></div>'
      + `<p class="ar-parl-note">크기=실측 투표자수 · 구성=출구조사 추정(±오차). 총 투표자 ${fmt(d.total_voters)}(표본).</p>`;
    anchor.parentElement.insertBefore(sec, anchor.nextSibling);
    sec.querySelectorAll('[data-dgv]').forEach((b) => b.addEventListener('click', () => { view = b.dataset.dgv; draw(sec); }));
    draw(sec);
  }

  window.Archive = window.Archive || {};
  window.Archive.demographics = { render };
})();
