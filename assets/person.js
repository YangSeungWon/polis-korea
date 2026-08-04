// 인물 타임라인 — URL ?name=... 으로 인물 지정, person-index.json 로드 후 렌더.

(function () {
  const $ = (s) => document.querySelector(s);
  const params = new URLSearchParams(location.search);
  // 정적 페이지면 inline JSON 사용, 동적 fallback이면 ?name= 으로 fetch
  const inlineEl = document.getElementById('person-data');
  const inlineData = inlineEl ? JSON.parse(inlineEl.textContent) : null;
  const targetName = (inlineData && inlineData.persons[0]?.name) || params.get('name') || '';

  function escapeHtml(s) {
    return String(s || '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  // 정당 공천·표방이 법으로 금지된 직 — 교육감(tc 11). 이 직의 빈 정당은 '자료 없음'이
  // 아니라 '제도적으로 정당이 없음'이다. 개표 라이브 포털은 여기에 '무소속'을 채웠지만
  // OpenAPI 확정본은 빈값을 준다(그쪽이 사실에 맞다). 빈칸으로 두면 누락처럼 보이므로
  // 명시적으로 표기한다.
  const PARTYLESS_TC = new Set(['11']);

  function partylessChip() {
    return '<span class="pp-party pp-party-none" title="교육감은 정당의 추천·표방이 금지된 직입니다">정당 없음</span>';
  }

  function partyBadge(party, asLink, tc) {
    if (!party) return PARTYLESS_TC.has(tc) ? partylessChip() : '';
    const col = (typeof partyTextColor === 'function') ? partyTextColor(party) : '#888';  // 정의당 노랑 등 가독 보정
    const sty = `color:${col};border-color:${col}`;
    // asLink: 정당 페이지로. 레이스 행 배지는 행 전체가 <a>라 중첩 불가 → span 유지.
    return asLink
      ? `<a class="pp-party" href="/party/${encodeURIComponent(party)}/" style="${sty}">${escapeHtml(party)}</a>`
      : `<span class="pp-party" style="${sty}">${escapeHtml(party)}</span>`;
  }

  // 백엔드(enrich_person_index)가 이미 assembly_id 기준으로 split했으므로
  // 프론트는 단순 렌더만. 이름 검색 시 동명이인 entry 여러 건 그대로 나열.
  function _splitNamesakesDeprecated(person) {
    const PARTY_FAMILY = {
      '통일민주당': 'M', '민주당': 'M', '새정치국민회의': 'M', '새천년민주당': 'M',
      '열린우리당': 'M', '민주통합당': 'M', '새정치민주연합': 'M', '더불어민주당': 'M', '더불어민주연합': 'M',
      '민주자유당': 'C', '신한국당': 'C', '한나라당': 'C', '새누리당': 'C',
      '자유한국당': 'C', '미래통합당': 'C', '국민의힘': 'C', '국민의미래': 'C',
    };
    const races = person.races.slice();
    // union-find by (race index, race index): connect if any shared sido OR same party-family near time
    const n = races.length;
    const parent = Array.from({length: n}, (_, i) => i);
    const find = (i) => parent[i] === i ? i : (parent[i] = find(parent[i]));
    const union = (a, b) => { const ra = find(a), rb = find(b); if (ra !== rb) parent[ra] = rb; };

    // sido per race
    const rcSido = races.map((r) => {
      // place 안에서 시도명 추출
      const sidos = new Set();
      const m = (r.place || '').match(/^[가-힣]+(?:특별시|광역시|특별자치시|특별자치도|도)/);
      if (m) sidos.add(m[0]);
      return sidos;
    });
    const rcFamily = races.map((r) => PARTY_FAMILY[r.party] || null);

    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        // 같은 시도 있으면 연결
        let share = false;
        for (const s of rcSido[i]) if (rcSido[j].has(s)) { share = true; break; }
        // 같은 정당 패밀리이고 연도 차 ≤ 8년이면 연결 (정치적 연속성)
        const sameFam = rcFamily[i] && rcFamily[i] === rcFamily[j];
        const yearGap = Math.abs((races[i].year || 0) - (races[j].year || 0));
        if (share || (sameFam && yearGap <= 8)) union(i, j);
      }
    }
    const groups = {};
    for (let i = 0; i < n; i++) {
      const r = find(i);
      (groups[r] = groups[r] || []).push(races[i]);
    }
    return Object.values(groups);
  }

  // ── 선거공약 ──────────────────────────────────────────────────────────────
  // 공약 원본은 회차별 2MB짜리라 인물별로 쪼갠 파일을 필요할 때만 받는다.
  // 데이터는 당선인 것만 존재한다(NEC API 제약) — 낙선 이력엔 붙지 않는다.
  let pledgeIndex = null;

  async function loadPledgeIndex() {
    if (pledgeIndex) return pledgeIndex;
    try {
      const r = await fetch('assets/pledges-index.json');
      pledgeIndex = await r.json();
    } catch (e) {
      pledgeIndex = {};
    }
    return pledgeIndex;
  }

  function renderPledgeEntry(e) {
    const where = [e.sido, e.sigungu].filter(Boolean).join(' ');
    const items = (e.pledges || []).map((p) => `
      <details class="pp-pledge">
        <summary><span class="pp-pledge-n">${p.order}</span>${escapeHtml(p.title)}</summary>
        <div class="pp-pledge-body">${escapeHtml(p.content)}</div>
      </details>`).join('');
    return `
      <div class="pp-pledge-group">
        <div class="pp-pledge-head">
          <b>${escapeHtml(e.round || '')}</b>
          <span class="pp-pledge-where">${escapeHtml(where)} · ${escapeHtml(e.office)}</span>
        </div>
        ${items}
      </div>`;
  }

  async function renderPledges(personId, mount) {
    try {
      const r = await fetch(`data/pledges/by-person/${encodeURIComponent(personId)}.json`);
      const doc = await r.json();
      mount.innerHTML = (doc.entries || []).map(renderPledgeEntry).join('');
    } catch (e) {
      mount.innerHTML = '<div class="detail-empty">공약 로드 실패.</div>';
    }
  }

  function renderTimelineCard(races, label) {
    // 실제 선거일순 — 같은 해 대선(3월)·재보궐(6월) 등 월까지 구분. date 없으면 year fallback.
    const dkey = (r) => r.date || (r.year ? String(r.year) : '');
    races = races.slice().sort((a, b) => dkey(a).localeCompare(dkey(b)));
    const wins = races.filter((r) => r.won).length;
    const losses = races.length - wins;
    const parties = [];
    const seen = new Set();
    for (const r of races) {
      if (r.party && !seen.has(r.party)) { seen.add(r.party); parties.push(r.party); }
    }
    // 교육감만 출마한 인물은 정당이 하나도 없다 — 요약의 '정당' 칸이 통째로 비어
    // 자료 누락처럼 보인다. 정당 없는 직만 뛴 경우임을 밝힌다.
    const allPartyless = parties.length === 0 && races.every((r) => PARTYLESS_TC.has(r.tc));

    const rows = races.map((r) => {   // 최근이 아래로(오름차순) — 검색과 통일
      const tag = r.won ? '<span class="pp-tag pp-won">당선</span>' : '<span class="pp-tag pp-lost">낙선</span>';
      const pct = r.pct != null ? `${(+r.pct).toFixed(1)}%` : '—';
      const rank = r.rank && r.rank < 99 ? `${r.rank}위` : '';
      // 행 전체를 archive 링크로 — 모바일에서도 탭 가능
      return `<a class="pp-race" href="/archive/${r.eid}/">
        <div class="pp-yr">${r.year || '?'}</div>
        <div class="pp-round">${escapeHtml(r.round || r.eid)}</div>
        <div class="pp-place">${escapeHtml(r.place || '')}</div>
        <div class="pp-pty">${partyBadge(r.party, false, r.tc)}</div>
        <div class="pp-rk">${rank}</div>
        <div class="pp-pct">${pct}</div>
        <div class="pp-tag-cell">${tag}</div>
        <div class="pp-link">→</div>
      </a>`;
    }).join('');

    return `<section class="pp-card">
      ${label ? `<div class="pp-namesake-label">${escapeHtml(label)}</div>` : ''}
      <div class="pp-summary">
        <div class="pp-record">
          <div class="pp-stat"><b class="pp-stat-num">${races.length}</b><span class="pp-stat-label">출마</span></div>
          <div class="pp-stat pp-win"><b class="pp-stat-num">${wins}</b><span class="pp-stat-label">당선</span></div>
          <div class="pp-stat pp-loss"><b class="pp-stat-num">${losses}</b><span class="pp-stat-label">낙선</span></div>
        </div>
        <div class="pp-meta">
          <div class="pp-field"><span class="pp-field-k">정당</span><span class="pp-field-v pp-parties">${allPartyless ? partylessChip() : parties.slice(0, 5).map((p) => partyBadge(p, true)).join('')}</span></div>
        </div>
      </div>
      <div class="pp-races">${rows}</div>
    </section>`;
  }

  async function load() {
    if (!targetName) {
      $('#person-body').innerHTML =
        '<div class="detail-empty">URL에 <code>?name=이재명</code> 같이 인물 이름을 넣어주세요. 또는 <a href="/search.html">검색</a>에서 결과 클릭.</div>';
      return;
    }
    try {
      let j;
      if (inlineData) {
        j = inlineData;
      } else {
        const r = await fetch('assets/person-index.json');
        j = await r.json();
      }
      const person = (j.persons || []).find((p) => p.name === targetName);
      if (!person) {
        $('#person-body').innerHTML =
          `<div class="detail-empty">${escapeHtml(targetName)} 일치 없음. <a href="/search.html?q=${encodeURIComponent(targetName)}">검색</a>으로 확인.</div>`;
        return;
      }
      // 같은 이름 entry 여러 건 (동명이인) — 모두 표시
      const all = (j.persons || []).filter((p) => p.name === targetName);
      const totalRaces = all.reduce((s, p) => s + p.races.length, 0);
      const totalWins = all.reduce((s, p) => s + p.wins, 0);
      $('#person-title').textContent = targetName;
      // 단일 인물 lede는 요약 카드(출마·당선·낙선)와 중복 → 제거. 동명이인일 때만 구분 안내.
      const sub = $('#person-sub');
      if (sub) {
        if (all.length > 1) sub.textContent = `동명이인 ${all.length}명 추정 · 합산 ${totalRaces}회 출마 · 당선 ${totalWins}`;
        else sub.remove();
      }
      let html = '';
      all.sort((a, b) => b.races.length - a.races.length);
      all.forEach((p, i) => {
        let label = null;
        if (all.length > 1) {
          const meta = [];
          if (p.dob) meta.push(p.dob);
          if (p.hanja) meta.push(p.hanja);
          if (p.assembly_id) meta.push('국회');
          else meta.push('비국회');
          label = `인물 ${String.fromCharCode(65 + i)} — ${p.races.length}회 (${p.wins}당선)${meta.length ? ' · ' + meta.join(' · ') : ''}`;
        }
        html += renderTimelineCard(p.races, label);
      });
      $('#person-body').innerHTML = html;

      // 공약 섹션 — 인덱스에 있는 인물만. 본문은 펼칠 때 받는다.
      const idx = await loadPledgeIndex();
      all.forEach((p) => {
        const n = idx[p.id];
        if (!n) return;
        const sec = document.createElement('section');
        sec.className = 'pp-card pp-pledges';
        const who = all.length > 1 ? ` — ${escapeHtml(p.name)}${p.dob ? ' (' + p.dob + ')' : ''}` : '';
        sec.innerHTML = `
          <details class="pp-pledge-toggle">
            <summary><b>선거공약</b> <span class="pp-pledge-count">${n}건</span>${who}</summary>
            <div class="pp-pledge-mount"><div class="detail-empty">불러오는 중…</div></div>
          </details>`;
        $('#person-body').appendChild(sec);
        const det = sec.querySelector('details');
        det.addEventListener('toggle', function once() {
          if (!det.open) return;
          det.removeEventListener('toggle', once);
          renderPledges(p.id, sec.querySelector('.pp-pledge-mount'));
        });
      });
    } catch (e) {
      $('#person-body').innerHTML = '<div class="detail-empty">인덱스 로드 실패.</div>';
    }
  }

  load();
})();
