// UI 불변식 — 실제 브라우저에서 렌더한 DOM으로 검사한다.
//
// 이 파일이 잡는 것은 '예쁜가'가 아니라 **검증 가능한 파손**이다:
//   · 가로 스크롤(모바일에서 잘림)      · JS 예외·콘솔 에러
//   · 토글 반복 후 범례·패널 중복       · 숨긴 요소가 자리를 차지
//   · 데이터는 있는데 화면이 비는 경우   · 결손을 0/무투표로 주장하는 표기
//
// 눈으로는 "좀 이상한데?" 정도로만 보여서 리뷰로 안 잡히는 것들이다.
// 스크린샷(shoot.mjs)은 사람이 보는 용도이고, 통과/실패는 여기서 낸다.
//
// 실행: node tests/ui/test_ui_invariants.mjs [--only=archive-pres]
import { chromium } from 'playwright';
import { serve } from './server.mjs';
import { PAGES, VIEWPORTS } from './pages.mjs';

const ROOT = new URL('../..', import.meta.url).pathname;
const only = (process.argv.find((a) => a.startsWith('--only=')) || '').split('=')[1];
const pages = only ? PAGES.filter((p) => p.id === only) : PAGES;

let pass = 0; const fails = [];
// **실패 줄만 봐도 어느 페이지인지 알아야 한다.** 페이지 헤더는 위쪽에 한 번 찍히는데,
// gate는 로그 끝 몇 줄만 남겨서 그 헤더가 잘려 나간다 — 실제로 어느 화면에서 난
// 콘솔 에러인지 못 찾았다. 요약에는 페이지 id를 붙인다.
let curPage = '';
const ck = (name, cond, detail) => {
  if (cond) { pass++; } else { fails.push(`[${curPage}] ${name}${detail ? ' — ' + detail : ''}`); }
  console.log(`  ${cond ? '✓' : '✗'} ${name}${cond || !detail ? '' : ' — ' + detail}`);
};

// 콘솔 소음 중 우리 잘못이 아닌 것 — 외부 CDN·favicon 등.
const IGNORE = [/favicon/i, /net::ERR_/i, /jsdelivr/i, /unpkg/i, /Failed to load resource/i];

const srv = await serve(ROOT, 8099);
const browser = await chromium.launch();

for (const spec of pages) {
  curPage = spec.id;
  console.log(`\n[${spec.id}] ${spec.url}  (${spec.why})`);
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: 1,
    });
    const page = await ctx.newPage();
    const errors = [];
    page.on('console', (m) => {
      if (m.type() !== 'error') return;
      const t = m.text();
      if (!IGNORE.some((r) => r.test(t))) errors.push(t.slice(0, 140));
    });
    page.on('pageerror', (e) => errors.push('예외: ' + String(e).slice(0, 140)));

    await page.goto(srv.url + spec.url, { waitUntil: 'networkidle', timeout: 30000 });

    // 렌더가 끝날 때까지 기다린다. 고정 대기(400ms)로 했더니 아직 안 그려진 화면을
    // 검사해 **전부 공허하게 통과**했다 — 지도가 0개면 '지도에 키가 있는가'는 자동
    // 통과다. 없는 걸 검사하고 통과했다고 말하는 게 검사가 없는 것보다 나쁘다.
    await page.waitForFunction(() => {
      const m = document.querySelector('main') || document.body;
      const svgDrawn = [...document.querySelectorAll('svg')]
        .some((s) => s.querySelectorAll('path,polygon,circle,rect,g').length > 5);
      return svgDrawn || (m.innerText || '').trim().length > 300;
    }, null, { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(700);   // 그린 뒤 후속 주입(범례·툴팁)까지

    // 공허한 통과 방지 — 아래 검사들이 '아무것도 없어서' 통과하는 걸 막는다.
    const rendered = await page.evaluate(() => {
      const m = document.querySelector('main') || document.body;
      return {
        text: (m.innerText || '').trim().length,
        nodes: m.querySelectorAll('*').length,
        svgCells: [...document.querySelectorAll('svg')]
          .reduce((n, s) => n + s.querySelectorAll('path,polygon,circle,rect').length, 0),
      };
    });
    // 작은 정당·짧은 지역 페이지는 원래 내용이 적다(노동당 125자) — 빈 화면과 다르다.
    ck(`${vp.id} 화면이 실제로 그려짐`, rendered.text > 100 && rendered.nodes > 20,
      `글자 ${rendered.text} · 노드 ${rendered.nodes} · svg 도형 ${rendered.svgCells}`);

    // ── 1. 가로 넘침 ────────────────────────────────────────────────────────
    // 본문이 가로로 넘치면 모바일에서 내용이 잘린다. 넓은 콘텐츠(표·지도)는
    // 자기 컨테이너 안에서 스크롤해야지 페이지를 밀면 안 된다.
    const of = await page.evaluate(() => {
      const de = document.documentElement;
      const over = [];
      if (de.scrollWidth > de.clientWidth + 1) {
        for (const el of document.querySelectorAll('body *')) {
          const r = el.getBoundingClientRect();
          if (r.width === 0) continue;
          if (r.right > de.clientWidth + 1 || r.left < -1) {
            const s = getComputedStyle(el);
            // 스스로 스크롤하는 컨테이너는 정상
            if (s.overflowX === 'auto' || s.overflowX === 'scroll') continue;
            const p = el.parentElement && getComputedStyle(el.parentElement);
            if (p && (p.overflowX === 'auto' || p.overflowX === 'scroll' || p.overflowX === 'hidden')) continue;
            over.push(`${el.tagName.toLowerCase()}.${(el.className || '').toString().split(' ')[0]}`
              + ` (${Math.round(r.left)}→${Math.round(r.right)})`);
          }
        }
      }
      return { scrollW: de.scrollWidth, clientW: de.clientWidth, over: [...new Set(over)].slice(0, 4) };
    });
    ck(`${vp.id} 가로 넘침 없음`, of.scrollW <= of.clientW + 1,
      `${of.scrollW} > ${of.clientW} · ${of.over.join(', ')}`);

    // ── 2. JS 예외 ──────────────────────────────────────────────────────────
    ck(`${vp.id} 콘솔 에러 없음`, errors.length === 0, errors.slice(0, 2).join(' | '));

    // ── 3. 결손을 사실로 주장하는 표기 ──────────────────────────────────────
    // 화면 텍스트에 '0.0%'가 있는 것 자체는 정상(실제 0%도 있다)이지만,
    // 투표율 0.0%는 우리 데이터에 존재하지 않는다 — 나오면 결손 강제변환이다.
    const zero = await page.evaluate(() =>
      (document.body.innerText.match(/투표율\s*0\.0+%/g) || []).length);
    ck(`${vp.id} 투표율 0.0% 없음`, zero === 0, `${zero}건`);

    // ── 3.5 범례가 실제로 있는 인코딩만 설명하는가 ─────────────────────────
    // '있는지'만 보면 부족하다. 폴 화면은 '실제 결과' 모드에서 gap=99 sentinel이
    // 들어가 모든 칸이 같은 명도인데도 '색 진하기 = 격차' 키가 붙어 있었다 —
    // 범례가 설명하지 않는 걸 설명한다고 말한 것이다. 그래서 **명도가 실제로
    // 변하는지**를 기준으로 삼는다. (반대로 변하는데 키가 없으면 연한 칸이
    // '자료 부실'로 읽힌다.)
    const enc = await page.evaluate(() => {
      const vis = (el) => {
        if (!el || el.hasAttribute('hidden')) return false;
        const r = el.getBoundingClientRect();
        return r.width > 8 && r.height > 8;   // 범례 한 줄은 20px 미만이다
      };
      let varying = 0;
      for (const svg of document.querySelectorAll('svg')) {
        if (!vis(svg)) continue;
        const els = [...svg.querySelectorAll('[fill-opacity]')];
        const vals = new Set(els
          .map((e) => Math.round(parseFloat(e.getAttribute('fill-opacity')) * 50))
          .filter((v) => !isNaN(v)));
        // 셀이 많고 명도가 3단계 이상 → 지도가 명도로 값을 나른다.
        // 셀 수 조건이 없으면 스파크라인·아이콘 같은 작은 svg가 오탐된다.
        // 다만 20은 너무 높다 — **시도 지도는 16~17칸뿐**이고 그것도 격차 명도를 쓴다.
        // 20으로 두면 광역단체장 뷰가 '명도를 안 쓴다'로 잡혀 정상 램프를 오탐한다.
        // 대신 아이콘 오탐은 '큰 그림인가'로 막는다.
        const r = svg.getBoundingClientRect();
        if (els.length >= 12 && vals.size >= 3 && r.width >= 200 && r.height >= 200) varying++;
      }
      // 범례 존재 여부가 아니라 **격차 램프**를 본다. 범례는 다른 인코딩(크기 등)
      // 때문에 있을 수 있다 — 램프가 곧 '색 진하기 = 격차'라는 주장이다.
      const ramps = [...document.querySelectorAll('.vz-gap-ramp')].filter(vis).length;
      return { varying, legs: ramps };
    });
    ck(`${vp.id} 명도가 변하면 격차 램프가 있다`, enc.varying === 0 || enc.legs > 0,
      `명도 지도 ${enc.varying} · 램프 ${enc.legs}`);
    ck(`${vp.id} 명도가 안 변하면 램프도 없다`, enc.varying > 0 || enc.legs === 0,
      `명도 지도 ${enc.varying} · 램프 ${enc.legs}`);

    // ── 3.6 범례가 시각화 옆 컬럼을 차지하지 않는가 ───────────────────────
    // history의 .viz는 지도(flex 1) + 상세(고정폭) **가로 flex**다. 범례를 형제로
    // 넣으면 세 번째 컬럼이 되어 지도 옆 222px를 먹고 높이도 지도만큼(672px) 늘어난다.
    // 내용은 19px 한 줄인데 상자만 커진 것이라 '공간을 이상하게 차지'하는 것으로 보인다.
    const legBox = await page.evaluate(() => [...document.querySelectorAll('.vz-gap-legend')]
      .map((e) => { const r = e.getBoundingClientRect();
        return { h: Math.round(r.height), w: Math.round(r.width),
                 lines: e.querySelectorAll('.vz-gap-item').length }; })
      .filter((b) => b.h > 0));
    // 한 줄 범례가 항목 수에 비해 지나치게 높으면 stretch된 것이다.
    ck(`${vp.id} 범례가 세로로 늘어나지 않았다`,
      legBox.every((b) => b.h <= 40 * Math.max(1, b.lines)),
      JSON.stringify(legBox));

    // ── 3.7 비어 있는 칸에 이유가 있는가 ──────────────────────────────────
    // 자료가 아직 공표되지 않은 시군구를 그냥 비워 두면 '선거가 없었다'와 구별되지
    // 않는다. 9회 기초의원 비례 58곳이 그렇게 빈 칸이었다.
    // **데이터에서 몇 곳이 미공표인지 세어** DOM과 대조한다. 화면만 보면 '빈 칸이
    // 하나도 없으니 통과'라는 공허한 검사가 된다(실제로 그렇게 통과했다).
    const pend = await page.evaluate(async () => {
      const sec = document.querySelector('#ar-sgg-prop');
      if (!sec) return null;
      const id = location.pathname.match(/\/archive\/([^/]+)\//)?.[1];
      if (!id) return null;
      const raw = await fetch(`/data/results/${id}.json`).then((r) => r.json()).catch(() => null);
      if (!raw?.races) return null;
      const expect = raw.races.filter((r) => r.sg_typecode === '9'
        && r.scope === 'proportional_sigungu'
        && !(r.candidates || []).some((c) => c.party && (c.votes || 0) > 0)).length;
      const svg = [...sec.querySelectorAll('svg')].find((x) => x.querySelectorAll('polygon').length > 20);
      const drawn = svg ? [...svg.children].filter((e) => e.tagName === 'g'
        && !e.classList.contains('sig-pending')).length : 0;
      return { expect, drawn, cells: sec.querySelectorAll('g.sig-pending').length,
               note: (sec.querySelector('.ar-sgg-prop-note')?.innerText || '').length };
    });
    if (pend && pend.expect) {
      // 자료가 없는 시군구를 빈 칸으로 두면 '선거가 없었다'와 구별되지 않는다
      ck(`${vp.id} 미공표 시군구를 빈 칸으로 두지 않는다 (${pend.cells}/${pend.expect})`,
        pend.cells >= pend.expect, JSON.stringify(pend));
      ck(`${vp.id} 미공표 칸에 설명이 있다`, pend.note > 20, JSON.stringify(pend));
    }
    // 전부 빗금인 지도는 정보가 0인데 지도인 척한다 — 그럴 땐 지도를 그리지 않는다.
    if (pend && pend.cells) {
      ck(`${vp.id} 표심 지도에 실제 값이 하나는 있다`, pend.drawn > 0, JSON.stringify(pend));
    }

    // ── 3.8 지선 요약이 **직위가 뽑히는 단위**로 세는가 ────────────────────
    // 광역단체장인데 시군구 breakdown을 세어 '158곳 / 총 256곳'이 나왔다.
    // 시도에서 1명을 뽑는 직위의 총합이 시군구 규모면 단위를 잘못 센 것이다.
    const office = await page.evaluate(() => {
      const t = document.querySelector('.ns-title')?.innerText || '';
      const m = (document.querySelector('.ns-party')?.innerText || '').match(/총\s*(\d+)\s*곳/);
      return m ? { title: t, total: +m[1] } : null;
    });
    if (office && /광역단체장|교육감/.test(office.title)) {
      // 시도는 17개(2026 전남·광주 통합으로 16)를 넘지 않는다
      ck(`${vp.id} 광역 직위는 시도 수만큼 센다`, office.total <= 17,
        JSON.stringify(office));
    }
    if (office && /기초단체장/.test(office.title)) {
      ck(`${vp.id} 기초 직위는 시군구 수만큼 센다`,
        office.total > 100 && office.total <= 260, JSON.stringify(office));
    }

    // ── 4.5 클릭 가능한 링크가 실제로 살아 있는가 ─────────────────────────
    // 정적 href 감사(108,439개)는 통과했는데 /history/local/9/가 404였다.
    // lens-switcher가 **런타임에 조립**하는 URL이라 파일을 훑어서는 안 보인다.
    // '정적 링크 무결성'과 '실제 navigation 무결성'은 별개의 검사다.
    if (vp.id === 'desktop') {
      const runtime = await page.evaluate(() => {
        const out = new Set();
        // 파일에 없던 링크만 — 정적 감사가 이미 본 것을 또 볼 이유가 없다.
        for (const a of document.querySelectorAll('a[href^="/"]')) {
          const h = a.getAttribute('href').split('#')[0].split('?')[0];
          if (h && h !== '/') out.add(h);
        }
        return [...out];
      });
      const dead = [];
      for (const h of runtime.slice(0, 60)) {
        const r = await page.request.get(srv.url + h, { failOnStatusCode: false });
        if (r.status() >= 400) dead.push(`${h} → ${r.status()}`);
      }
      ck(`렌더된 링크 ${Math.min(runtime.length, 60)}개가 전부 살아 있음`,
        !dead.length, dead.slice(0, 4).join(' · '));
    }

    if (vp.id === 'desktop') {
      // ── 4. 숨긴 요소가 자리를 차지하지 않는다 ─────────────────────────────
      const ghost = await page.evaluate(() => {
        const out = [];
        for (const el of document.querySelectorAll('[hidden]')) {
          const r = el.getBoundingClientRect();
          if (r.height > 2 || r.width > 2) {
            out.push(`${el.tagName.toLowerCase()}#${el.id || ''}.${(el.className || '').toString().split(' ')[0]}`
              + ` ${Math.round(r.width)}×${Math.round(r.height)}`);
          }
        }
        return out.slice(0, 4);
      });
      ck('숨긴 요소가 자리를 차지하지 않음', ghost.length === 0, ghost.join(', '));

      // ── 5. 토글 고문 — 순서를 바꿔 여러 번 눌러도 상태가 쌓이지 않는가 ────
      // **인코딩 모드** 토글만 겨냥한다. 아무 .seg-btn이나 누르면 회차 버튼을 눌러
      // 페이지를 갈아치우고, 정작 위험한 지도↔격자↔원형 전환은 한 번도 안 거친다.
      // (상태가 쌓이는 사고는 같은 호스트를 다시 그릴 때 난다.)
      const MODE_LABELS = ['균등', '지도', '격자', '원형', '단색', '투표율',
        '여론조사 1위', '실제 1위', '연령 순', '변화 순', '집단 → 후보', '후보 → 지지층'];
      const toggles = [];
      for (const el of await page.$$('[data-view],[data-sgmode],.seg-btn,.enc-btn,[data-swsort],[data-swm]')) {
        const txt = (await el.textContent() || '').trim();
        if (MODE_LABELS.includes(txt) && await el.isVisible()) toggles.push(el);
      }
      // 재보궐 archive는 시각화 구조가 달라 인코딩 토글이 없다 — 요구하지 않는다.
      ck('인코딩 모드 토글을 찾았다',
        toggles.length >= 2 || !/^(archive-(local|pres|gen)|history|polls)$/.test(spec.id),
        `${toggles.length}개`);
      if (toggles.length >= 2) {
        const before = await page.evaluate(() => ({
          legend: document.querySelectorAll('.vz-gap-legend').length,
          tip: document.querySelectorAll('.hex-tip').length,
        }));
        // 순서를 섞어 왕복한다 — 같은 순서로만 누르면 '되돌아올 때'만 나는 버그를 놓친다.
        const n = toggles.length;
        const order = [0, n - 1, 0, (n / 2) | 0, n - 1, (n / 2) | 0, 0, n - 1];
        for (const i of order) {
          try { await toggles[i].click({ timeout: 2000 }); await page.waitForTimeout(180); } catch { /* 가려진 버튼 */ }
        }
        await page.waitForTimeout(500);
        const after = await page.evaluate(() => ({
          legend: document.querySelectorAll('.vz-gap-legend').length,
          tip: document.querySelectorAll('.hex-tip').length,
          scrollW: document.documentElement.scrollWidth,
          clientW: document.documentElement.clientWidth,
        }));
        ck(`토글 ${order.length}회 후 범례 중복 없음`,
          after.legend <= Math.max(before.legend, 1) + 1,
          `${before.legend} → ${after.legend}`);
        ck('토글 후 툴팁 중복 없음', after.tip <= 1, `${after.tip}개`);
        ck('토글 후 가로 넘침 없음', after.scrollW <= after.clientW + 1,
          `${after.scrollW} > ${after.clientW}`);
        ck('토글 후 예외 없음', errors.length === 0, errors.slice(0, 2).join(' | '));
      }
    }
    await ctx.close();
  }
}

// ── 못 받았을 때 화면이 뭐라고 말하는가 ─────────────────────────────────────
//
// data/** 를 전부 끊고 연다. 이때 '조사가 없습니다'라고 **단언하면 거짓말**이다 —
// 읽는 사람은 여론조사가 없었던 것과 우리가 못 받은 것을 구별할 수 없다.
// 실제로 polls·tracker·홈이 그렇게 말하고 있었다. 이 저장소가 반복해서 겪은
// '그럴듯한 기본값이 결손을 덮는' 결함의 UI 판이다.
//
// 규칙: **'없음'을 말해도 되는 건 실제로 받아왔을 때뿐이다.** 못 받았으면 그
// 사실이 화면에 있어야 한다(.data-fail-banner 또는 '불러오지 못했습니다').
const OFFLINE = ['home', 'polls', 'poll-round', 'tracker',
  'history', 'chronology', 'history-local', 'byelection'];
console.log('\n[오프라인] 데이터를 못 받았을 때의 진술');
for (const id of OFFLINE.filter((i) => pages.some((p) => p.id === i))) {
  curPage = id + '/offline';
  const spec = pages.find((p) => p.id === id);
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  let blocked = 0;
  await page.route('**/data/**', (r) => { blocked++; r.abort(); });
  try {
    await page.goto(srv.url + spec.url, { waitUntil: 'load', timeout: 25000 });
  } catch { /* 자원이 죽은 채 여는 게 목적이라 load 실패는 무시 */ }
  await page.waitForTimeout(2200);
  const seen = await page.evaluate(() => {
    const t = (document.querySelector('main') || document.body).innerText;
    const lo = document.getElementById('loading');
    return {
      claimsEmpty: /없습니다|데이터 없음|조사 없음|자료 없음/.test(t),
      admits: !!document.querySelector('.data-fail-banner') || /불러오지 못했습니다/.test(t),
      // 걷히지 않은 로딩 오버레이 = '기다리면 온다'는 암시. 오지 않는다.
      stuck: !!(lo && !lo.hidden && !lo.dataset.failed),
    };
  });
  // 차단이 0이면 그 페이지는 data/를 안 쓴 것 — 검사가 공허하게 통과하지 않게 막는다.
  ck(`${id}: 데이터 요청이 실제로 차단됐다`, blocked > 0, `${blocked}건`);
  ck(`${id}: 못 받았으면 '없음'이라 단언하지 않는다`,
    !seen.claimsEmpty || seen.admits,
    "빈 상태 문구는 있는데 실패 고지가 없다");
  ck(`${id}: 로딩이 영원히 돌지 않는다`, !seen.stuck,
    "'불러오는 중…'이 걷히지 않았다 — 실패했는데 기다리라고 한다");
  await ctx.close();
}

await browser.close();
await srv.close();
console.log(`\n총 ${pass + fails.length}건: ${pass} pass, ${fails.length} fail`);
if (fails.length) { console.log('\n실패:'); fails.forEach((f) => console.log('  ✗ ' + f)); }
process.exit(fails.length ? 1 : 0);
