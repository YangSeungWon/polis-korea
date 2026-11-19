// 두 지역 나란히 — /region/compare.html?a={slug}&b={slug}
//
// 지역 페이지 표를 같은 선거끼리 맞춰 놓는다. 새 값을 계산하지 않는다 — 행은
// build_region_pages가 낸 data/regions/{slug}.json 그대로이고, 위의 한 줄 요약만
// 대선 득표율(pres)에서 센다. 모르는 칸은 '—'(0이 아니다), 한쪽에만 있는 선거는 다른 쪽을 비운다.
(function () {
  const $ = (s) => document.querySelector(s);
  const VS = window.ViewState;
  let index = null;
  const bySlug = new Map();
  const byLabel = new Map();

  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const fill = (p, d) => (typeof partyFill === 'function' ? partyFill(p, d) : '#999');
  const ink = (p, d) => (typeof partyTextColor === 'function' ? partyTextColor(p, d) : 'inherit');
  const pct = (v) => (v == null ? '<span class="rg-nd" title="자료 없음">—</span>' : `${Number(v).toFixed(1)}%`);

  function resolve(text) {
    const t = String(text || '').trim();
    if (!t) return null;
    if (bySlug.has(t)) return t;
    if (byLabel.has(t)) return byLabel.get(t);
    // 시군구명만 친 경우 — 하나로 정해질 때만(중구는 여럿이다).
    const hits = index.regions.filter((r) => r.name === t || r.short.replace(/\s+/g, '') === t.replace(/\s+/g, ''));
    return hits.length === 1 ? hits[0].slug : null;
  }

  async function region(slug) {
    const r = await fetch(`data/regions/${encodeURIComponent(slug)}.json`);
    if (!r.ok) throw new Error(slug);
    return r.json();
  }

  function cell(r) {
    if (!r) return '<td class="cmp-cell cmp-none">이 지역 기록 없음</td>';
    const v = r.uncontested ? '<span class="rg-nv">무투표</span>' : pct(r.pct);
    // 교육감은 정당이 없다(party null) — '무소속'으로 바꿔 적지 않는다.
    const party = r.party
      ? `<span class="cmp-dot" style="background:${fill(r.party, r.date)}"></span>`
        + `<span class="cmp-party" style="color:${ink(r.party, r.date)}">${esc(r.party)}</span> `
      : '<span class="cmp-party cmp-noparty" title="교육감 선거는 정당 공천이 없습니다">정당 없음</span> ';
    return `<td class="cmp-cell">${party}`
      + `<span class="cmp-name">${esc(r.name || '')}</span> <span class="cmp-pct">${v}</span>`
      + `<span class="cmp-turn">투표율 ${pct(r.turnout)}</span></td>`;
  }

  function bar(v, cands, date) {
    if (!v) return '<div class="cmp-bar cmp-bar-none">자료 없음</div>';
    return `<div class="cmp-bar" role="img" aria-label="${esc(cands[0][0])} ${v[0]}%, ${esc(cands[1][0])} ${v[1]}%">`
      + `<span style="width:${v[0]}%;background:${fill(cands[0][1], date)}"></span>`
      + `<span style="width:${v[1]}%;background:${fill(cands[1][1], date)}"></span></div>`
      + `<span class="cmp-bar-num">${v[0].toFixed(1)} · ${v[1].toFixed(1)}</span>`;
  }

  // 한 줄 요약 — 대선 득표율의 거리 하나만. 지역별 '1위가 같았나'는 세지 않는다:
  // 대선은 지역 승부가 아니고(단색 금지), 교육감 '무소속=무소속'은 같은 편이 아니다.
  function summary(A, B) {
    const common = Object.keys(A.pres || {}).filter((e) => B.pres && B.pres[e]);
    if (!common.length) return '';
    let sq = 0;
    for (const e of common) sq += (A.pres[e][0] - B.pres[e][0]) ** 2 + (A.pres[e][1] - B.pres[e][1]) ** 2;
    const d = Math.sqrt(sq / (2 * common.length)).toFixed(1);
    // 산술평균이 아니라 제곱평균제곱근이다 — '평균 n%p'라고 쓰지 않고 계산법을 밝힌다
    // (tests/ui/test_relate.mjs). '1·2위 득표율 차이'로 읽히지 않게 '두 지역 사이'를 적는다.
    return `<p class="rg-swing">두 지역 모두 결과가 있는 대선 ${common.length}번에서, 전국 1·2위 후보의 득표율이 `
      + `두 지역 사이에 <b>${d}%p</b>쯤 달랐습니다 <span class="cmp-how">(회차·후보별 차이의 제곱평균제곱근)</span>.</p>`;
  }

  function render(A, B) {
    const label = (x) => `<a href="/region/${encodeURIComponent(x.slug)}/">${esc(bySlug.get(x.slug)?.short || x.name)}</a>`;
    let html = `<h2 class="cmp-title">${label(A)} <span class="cmp-vs">·</span> ${label(B)}</h2>` + summary(A, B);

    const pe = Object.keys(index.pres || {}).filter((e) => (A.pres && A.pres[e]) || (B.pres && B.pres[e]))
      .sort((x, y) => (index.pres[y].date || '').localeCompare(index.pres[x].date || ''));
    if (pe.length) {
      html += '<section class="rg-sec"><h2>대선 전국 1·2위 후보의 지역 득표율</h2><div class="cmp-wrap"><table class="pp-static cmp-pres"><thead><tr>'
        + `<th>대선</th><th>${esc(bySlug.get(A.slug)?.short || A.name)}</th><th>${esc(bySlug.get(B.slug)?.short || B.name)}</th></tr></thead><tbody>`;
      for (const e of pe) {
        const p = index.pres[e];
        const c = p.cands;
        html += `<tr><td><a href="/archive/${esc(e)}/">${esc((p.date || '').slice(0, 4))}</a>`
          + `<span class="cmp-cands"><span style="color:${ink(c[0][1], p.date)}">${esc(c[0][0])}</span> · <span style="color:${ink(c[1][1], p.date)}">${esc(c[1][0])}</span></span></td>`
          + `<td>${bar(A.pres && A.pres[e], c, p.date)}</td><td>${bar(B.pres && B.pres[e], c, p.date)}</td></tr>`;
      }
      html += '</tbody></table></div></section>';
    }

    const keys = new Map();
    for (const r of A.rows) keys.set(`${r.eid}|${r.office}`, { a: r, b: null, date: r.date, election: r.election, eid: r.eid, office: r.office });
    for (const r of B.rows) {
      const k = `${r.eid}|${r.office}`;
      if (keys.has(k)) keys.get(k).b = r;
      else keys.set(k, { a: null, b: r, date: r.date, election: r.election, eid: r.eid, office: r.office });
    }
    const rows = [...keys.values()].sort((x, y) => (y.date || '').localeCompare(x.date || '') || x.office.localeCompare(y.office));
    html += '<section class="rg-sec"><h2>선거별 지역 1위</h2><div class="cmp-wrap"><table class="pp-static cmp-table"><thead><tr>'
      + `<th>선거</th><th>${esc(bySlug.get(A.slug)?.short || A.name)}</th><th>${esc(bySlug.get(B.slug)?.short || B.name)}</th></tr></thead><tbody>`
      + rows.map((x) => {
        return `<tr><td><span class="cmp-year">${esc((x.date || '').slice(0, 4))}</span> `
          + `<a href="/archive/${esc(x.eid)}/">${esc(x.election)}</a><span class="cmp-office">${esc(x.office)}</span></td>`
          + cell(x.a) + cell(x.b) + '</tr>';
      }).join('')
      + '</tbody></table></div></section>';
    $('#cmp-out').innerHTML = html;
  }

  let seq = 0;
  async function update() {
    const a = resolve($('#cmp-a').value), b = resolve($('#cmp-b').value);
    if (VS) VS.set({ a: a || null, b: b || null });
    const out = $('#cmp-out');
    if (!a || !b) {
      const bad = [['A', $('#cmp-a').value, a], ['B', $('#cmp-b').value, b]].filter(([, t, s]) => t.trim() && !s);
      out.innerHTML = `<p class="rg-sim-none">${bad.length
        ? bad.map(([k, t]) => `지역 ${k}의 “${esc(t)}”에 맞는 곳을 하나로 정하지 못했습니다. 목록에서 골라 주세요.`).join(' ')
        : '두 지역을 고르면 여기에 나란히 나옵니다.'}</p>`;
      return;
    }
    const my = ++seq;
    try {
      const [A, B] = await Promise.all([region(a), region(b)]);
      if (my === seq) render(A, B);
    } catch (e) {
      if (my === seq) out.innerHTML = '<p class="rg-sim-none">지역 자료를 받지 못했습니다.</p>';
    }
  }

  async function init() {
    try {
      index = await (await fetch('data/regions/index.json')).json();
    } catch (e) {
      $('#cmp-out').innerHTML = '<p class="rg-sim-none">지역 목록을 받지 못했습니다.</p>';
      return;
    }
    const dl = $('#cmp-regions');
    for (const r of index.regions) {
      bySlug.set(r.slug, r);
      byLabel.set(r.short, r.slug);
      const o = document.createElement('option');
      o.value = r.short;
      dl.appendChild(o);
    }
    for (const k of ['a', 'b']) {
      const s = VS ? VS.get(k) : new URLSearchParams(location.search).get(k);
      if (s && bySlug.has(s)) $(`#cmp-${k}`).value = bySlug.get(s).short;
      $(`#cmp-${k}`).addEventListener('change', update);
    }
    if (VS) VS.quiet(update); else update();
  }
  init();
})();
