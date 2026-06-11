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

  function partyBadge(party) {
    if (!party) return '';
    const col = (typeof partyColor === 'function') ? partyColor(party) : '#888';
    return `<span class="pp-party" style="color:${col};border-color:${col}">${escapeHtml(party)}</span>`;
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

  function renderTimelineCard(races, label) {
    // 실제 선거일순 — 같은 해 대선(3월)·재보궐(6월) 등 월까지 구분. date 없으면 year fallback.
    const dkey = (r) => r.date || (r.year ? String(r.year) : '');
    races = races.slice().sort((a, b) => dkey(a).localeCompare(dkey(b)));
    const wins = races.filter((r) => r.won).length;
    const losses = races.length - wins;
    const lastRace = races[races.length - 1];
    const sidos = new Set();
    const parties = [];
    const seen = new Set();
    for (const r of races) {
      if (r.party && !seen.has(r.party)) { seen.add(r.party); parties.push(r.party); }
      const m = (r.place || '').match(/^[가-힣]+(?:특별시|광역시|특별자치시|특별자치도|도)/);
      if (m) sidos.add(m[0]);
    }

    const rows = races.map((r) => {   // 최근이 아래로(오름차순) — 검색과 통일
      const tag = r.won ? '<span class="pp-tag pp-won">당선</span>' : '<span class="pp-tag pp-lost">낙선</span>';
      const pct = r.pct != null ? `${(+r.pct).toFixed(1)}%` : '—';
      const rank = r.rank && r.rank < 99 ? `${r.rank}위` : '';
      // 행 전체를 archive 링크로 — 모바일에서도 탭 가능
      return `<a class="pp-race" href="/archive/${r.eid}/">
        <div class="pp-yr">${r.year || '?'}</div>
        <div class="pp-round">${escapeHtml(r.round || r.eid)}</div>
        <div class="pp-place">${escapeHtml(r.place || '')}</div>
        <div class="pp-pty">${partyBadge(r.party)}</div>
        <div class="pp-rk">${rank}</div>
        <div class="pp-pct">${pct}</div>
        <div class="pp-tag-cell">${tag}</div>
        <div class="pp-link">→</div>
      </a>`;
    }).join('');

    return `<section class="pp-card">
      ${label ? `<div class="pp-namesake-label">${escapeHtml(label)}</div>` : ''}
      <div class="pp-summary">
        <div class="pp-stat"><span class="pp-stat-num">${wins}</span><span class="pp-stat-label">당선</span></div>
        <div class="pp-stat"><span class="pp-stat-num">${losses}</span><span class="pp-stat-label">낙선</span></div>
        <div class="pp-stat"><span class="pp-stat-num">${races.length}</span><span class="pp-stat-label">출마</span></div>
        <div class="pp-sidos">${[...sidos].join(' · ') || '—'}</div>
        <div class="pp-parties">${parties.slice(0, 5).map(partyBadge).join('')}</div>
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
      $('#person-sub').textContent =
        all.length > 1
          ? `동명이인 ${all.length}명 추정 · 합산 ${totalRaces}회 출마 · 당선 ${totalWins}`
          : `${totalRaces}회 출마 · 당선 ${totalWins} · 낙선 ${all[0].losses}`;
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
    } catch (e) {
      $('#person-body').innerHTML = '<div class="detail-empty">인덱스 로드 실패.</div>';
    }
  }

  load();
})();
