// 찾은 것과 찾은 조건을 가져간다 (Shneiderman의 Extract).
//
// 두 가지를 준다(링크는 따로 없다 — 방식·선택·필터가 이미 주소창 URL에 있다):
//   · 그림 — 캡처가 만들어 둔 og/maps/{회차}/{뷰 키}.png. 지금 보이는 **방식**의 기본
//     그림이다(고른 지역·확대·필터는 담기지 않는다). 없으면 **없다고 말한다**(버튼을
//     숨기지 않는다 — 결손 모델: 못 받았다 ≠ 없다).
//   · CSV — 결과 원자료를 행으로 편 것. 비어 있는 칸은 빈칸이다(0이 아니다).
//
// 라벨·파일명은 손으로 짓지 않는다 — 뷰 키와 회차 id에서 나온다.
(function () {
  // 선거 코드(sg_typecode) → 이름. NEC 코드 체계 그대로.
  const SG_LABEL = {
    1: '대통령', 2: '국회의원(지역구)', 3: '시·도지사', 4: '구·시·군의 장', 5: '시·도의원(지역구)',
    6: '구·시·군의원(지역구)', 7: '국회의원(비례)', 8: '시·도의원(비례)', 9: '구·시·군의원(비례)',
    10: '교육의원', 11: '교육감',
  };

  // ── CSV ──────────────────────────────────────────────────────────
  function cell(v) {
    if (v == null) return '';
    const s = String(v);
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  // notes: 맨 앞 '# ' 줄들(출처·조건). pandas는 comment='#'로 읽는다.
  function toCSV(columns, rows, notes) {
    const out = [];
    for (const n of notes || []) out.push('# ' + String(n).replace(/[\r\n]+/g, ' '));
    out.push(columns.map((c) => cell(c.label)).join(','));
    for (const r of rows) out.push(columns.map((c) => cell(r[c.key])).join(','));
    return out.join('\r\n') + '\r\n';
  }

  function download(filename, text) {
    // BOM — 엑셀이 UTF-8 한글을 깨지 않고 연다.
    const blob = new Blob(['﻿' + text], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand('copy'); } catch (e2) { ok = false; }
      ta.remove();
      return ok;
    }
  }

  // 결과 파일(races[].candidates[]) → 후보 한 명당 한 행.
  const RESULT_COLUMNS = [
    { key: 'sg_typecode', label: '선거코드' },
    { key: 'office', label: '선거' },
    { key: 'scope', label: '집계단위' },
    { key: 'sido', label: '시도' },
    { key: 'sigungu', label: '시군구' },
    { key: 'district', label: '선거구' },
    { key: 'electors', label: '선거인수' },
    { key: 'voters', label: '투표수' },
    { key: 'valid_votes', label: '유효투표수' },
    { key: 'rank', label: '순위' },
    { key: 'name', label: '후보' },
    { key: 'party', label: '정당' },
    { key: 'votes', label: '득표수' },
    { key: 'pct', label: '득표율' },
    { key: 'seats', label: '의석' },
    { key: 'won', label: '당선' },
    { key: 'uncontested', label: '무투표' },
  ];

  function resultRows(results) {
    const rows = [];
    for (const r of (results && results.races) || []) {
      const uncontested = !!(r.is_uncontested || r.uncontested);
      for (const c of r.candidates || []) {
        rows.push({
          sg_typecode: r.sg_typecode,
          office: SG_LABEL[r.sg_typecode] || '',
          scope: r.scope,
          sido: r.sido || '',
          sigungu: r.sigungu || '',
          district: r.district || '',
          electors: r.electors,
          voters: r.voters,
          valid_votes: r.valid_votes,
          rank: c.rank,
          name: c.name,
          party: c.party,
          votes: c.votes,          // null이면 빈칸 — 모른다 ≠ 0표
          pct: c.pct,
          seats: c.seats,
          won: c.won == null ? null : (c.won ? 'Y' : 'N'),
          uncontested: (uncontested || c.uncontested || c.is_uncontested) ? 'Y' : '',
        });
      }
    }
    return rows;
  }

  // ── 그림(og/maps) 목록 — 디스크 관측(map_manifest). 한 번만 받는다.
  let manifestP = null;
  function manifestViews(electionId) {
    if (!manifestP) {
      manifestP = fetch('/data/map_manifest.json').then((r) => (r.ok ? r.json() : null)).catch(() => null);
    }
    return manifestP.then((m) => {
      const e = m && m.elections && m.elections[electionId];
      return e ? new Set(e.views || []) : null;
    });
  }

  function currentKey(host) {
    const VK = window.ViewKeys;
    const token = host.dataset.mapHost;
    if (!token) return null;
    if (!VK) return token;
    const mode = host.dataset.mode ? VK.modeOf(host.dataset.mode) : null;
    return VK.keyFor(token, mode);
  }

  // ── 도구줄 ─────────────────────────────────────────────────────────
  function flash(btn, text) {
    const orig = btn.dataset.label || btn.textContent;
    btn.dataset.label = orig;
    btn.textContent = text;
    clearTimeout(btn._ft);
    btn._ft = setTimeout(() => { btn.textContent = orig; }, 1800);
  }

  function button(label, title) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'fig-tool';
    b.textContent = label;
    if (title) b.title = title;
    return b;
  }

  // section 제목 옆에 [그림] — 섹션 안 첫 지도 host를 대상으로.
  function mountSection(section, electionId) {
    if (!electionId || !section || section.dataset.figTools) return;
    const host = section.querySelector('[data-map-host]');
    const title = section.querySelector('.ar-section-title');
    if (!host || !title) return;
    section.dataset.figTools = '1';
    const bar = document.createElement('span');
    bar.className = 'fig-tools';
    const img = button('그림', '이 방식으로 미리 그려 둔 전국 그림(PNG) — 고른 지역·확대·필터는 담기지 않는다');
    img.addEventListener('click', async () => {
      const key = currentKey(host);
      const views = await manifestViews(electionId);
      if (key && views && views.has(key)) {
        window.open(`/og/maps/${encodeURIComponent(electionId)}/${key}.png`, '_blank', 'noopener');
      } else {
        // 숨기지 않는다 — 이 모드의 그림이 왜 없는지 말한다.
        flash(img, views ? '이 방식의 그림은 아직 없음' : '그림 목록을 못 받음');
      }
    });
    bar.appendChild(img);
    title.appendChild(bar);
  }

  // archive — 지도가 있는 섹션마다 [그림] + 맨 아래 결과 원자료 내려받기 블록.
  // 지도 섹션은 **나중에 생긴다**(시군구 결과는 렌더러가 비동기로 섹션째 끼워 넣는다).
  // 정해진 시점에 한 번 훑으면 그 섹션을 놓친다 — 그래서 지도 host가 생길 때마다 붙인다.
  // 섹션마다 한 번만 붙으므로 여러 번 불려도 된다.
  let observer = null;
  function mountArchive(ctx) {
    const id = ctx && ctx.meta && ctx.meta.id;
    const scan = () => document.querySelectorAll('[data-map-host]').forEach((h) => mountSection(h.closest('.ar-section'), id));
    scan();
    mountDataBlock(ctx);
    if (!observer && 'MutationObserver' in window) {
      let queued = false;
      observer = new MutationObserver(() => {
        if (queued) return;
        queued = true;
        requestAnimationFrame(() => { queued = false; scan(); });
      });
      observer.observe(document.querySelector('main') || document.body,
        { childList: true, subtree: true, attributes: true, attributeFilter: ['data-map-host'] });
    }
  }

  function mountDataBlock(ctx) {
    if (!ctx || !ctx.meta || document.getElementById('ar-data-export')) return;
    // 맨 아래 — 본 결과보다 내려받기가 먼저 나오지 않게. 아래쪽 회차 이동 막대 바로 앞.
    const first = document.getElementById('ar-map-figures') || document.querySelector('.ar-section');
    if (!first) return;
    const meta = ctx.meta;
    const sec = document.createElement('section');
    sec.className = 'ar-section';
    sec.id = 'ar-data-export';
    const hasRows = !!(ctx.results && (ctx.results.races || []).length);
    const raw = String(meta.resultsPath || '').replace(/^\/+/, '');
    // 큰 회차는 시군구 행을 .sigungu.json으로 따로 둔다 — 본 파일 하나만 걸면 반쪽이다.
    const chunked = !!(ctx.results && ctx.results._meta && ctx.results._meta.chunked);
    const rawFiles = raw ? [raw].concat(chunked ? [raw.replace(/\.json$/, '.sigungu.json')] : []) : [];
    sec.innerHTML = `<h2 class="ar-section-title">데이터 내려받기</h2>
      <p class="ar-source-line">이 선거의 후보별 득표 — 집계단위(전국·시도·시군구·선거구)마다 후보 한 명이 한 행. 비어 있는 칸은 모른다는 뜻이고 0이 아니다.</p>
      <div class="fig-export-row">
        <button type="button" class="fig-tool" id="ar-results-csv"${hasRows ? '' : ' disabled title="결과 파일을 못 받았다"'}>결과 CSV</button>
        ${rawFiles.map((f, i) => `<a class="fig-tool" href="/${f}" download>${rawFiles.length > 1 ? (i ? '원본 JSON (시군구)' : '원본 JSON (전국·시도)') : '원본 JSON'}</a>`).join('')}
        <a class="fig-tool-link" href="/about/data/">데이터 형식·출처</a>
      </div>`;
    const bottom = document.querySelector('.ar-nav-bottom');
    if (bottom && bottom.parentNode === first.parentNode) bottom.before(sec);
    else first.parentNode.appendChild(sec);
    const btn = sec.querySelector('#ar-results-csv');
    if (btn && hasRows) {
      btn.addEventListener('click', () => {
        const rows = resultRows(ctx.results);
        const src = ctx.results._meta && ctx.results._meta.source;
        download(`${meta.id}-results.csv`, toCSV(RESULT_COLUMNS, rows, [
          `${meta.name} (${meta.date}) 후보별 득표 · ${rows.length}행`,
          `출처: 중앙선거관리위원회${src ? ' (' + src + ')' : ''} · polis.ysw.kr 정리`,
          `원본: ${rawFiles.map((f) => `${location.origin}/${f}`).join(' + ')}`,
          '지도·표에 건 필터와 상관없이 이 선거의 모든 행이다',
        ]));
      });
    }
  }

  window.FigureTools = { toCSV, download, copyText, resultRows, RESULT_COLUMNS, mountArchive, mountSection, currentKey };
})();
