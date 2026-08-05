// 지도 타임랩스 UI — 데이터가 맞아도 화면이 잘못 말할 수 있다.
//
// 이 화면이 지켜야 할 것은 하나다: **결과가 있다고 지금 경계에 칠할 수 있는 게 아니다.**
// 그래서 검사도 거기 집중한다.
//
//   · 한 번에 한 프레임만 — 보간 없는 이산 상태
//   · 사건 전후로 polygon 개수가 실제로 바뀐다 (형태 morphing 아님)
//   · unavailable 폴리곤에 계열색이 새지 않는다
//   · 화면 문장이 backend의 displayable_claim과 같다
//   · series를 섞지 않는다
//
// 렌더 회귀는 픽셀이 아니라 **SVG path·채움 골든**으로 잡는다. 폰트 렌더링 차이로
// 흔들리지 않으면서 좌표·투영·색이 바뀌면 반드시 걸린다 — 지도에서 중요한 건 그거다.
// 사람이 볼 PNG는 shoot.mjs가 따로 찍는다.
import { chromium } from 'playwright';
import { serve } from './server.mjs';
import fs from 'fs';
import path from 'path';

const ROOT = path.resolve(process.cwd());
const REGIONS = ['포항'];
const VIEWPORTS = [
  { name: 'mobile', width: 390, height: 844 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1440, height: 900 },
];
const FAM_HEX = ['#d2352b', '#0a5cb8', '#e8a300', '#00875a', '#7a5cc0'];
const GOLDEN = path.join(ROOT, 'tests/golden/map_timelapse');
const update = process.argv.includes('--update');
let fails = [];
const ck = (n, c, d = '') => {
  if (!c) { fails.push(`${n}${d ? ' — ' + d : ''}`); console.log(`  ✗ ${n}${d ? ' — ' + d : ''}`); }
};
const data = (r) => JSON.parse(fs.readFileSync(
  path.join(ROOT, 'data/map_timelapse', `${r}.json`), 'utf-8'));

const srv = await serve(ROOT, 8112);
const browser = await chromium.launch();
console.log(`\n[지도 타임랩스 UI] ${REGIONS.length}곳 × ${VIEWPORTS.length}뷰포트`);

for (const region of REGIONS) {
  const d = data(region);
  const nStates = d.series_blocks.reduce((a, b) => a + b.states.length, 0);

  for (const vp of VIEWPORTS) {
    const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
    await page.goto(`${srv.url}/map-timelapse/${encodeURIComponent(region)}.html`,
      { waitUntil: 'load' });
    await page.waitForSelector('.mt-frame', { timeout: 5000 });
    const tag = `${region}/${vp.name}`;

    ck(`${tag}: 프레임 수 = 상태 수`,
      await page.locator('.mt-frame').count() === nStates, `${nStates}`);
    // 보간하지 않는다 — 한 번에 하나의 이산 상태만 보인다
    ck(`${tag}: 한 번에 한 프레임`,
      await page.locator('.mt-frame:not([hidden])').count() === 1);

    // 기본 진입은 집계 단위가 지도 단위와 같은 series
    const first = d.series_blocks[0];
    ck(`${tag}: 기본 series = ${first.comparison_series_id}`,
      await page.locator('.mt-frame:not([hidden])').first().getAttribute('data-series')
      === first.comparison_series_id);

    const box = await page.locator('.mt-frame:not([hidden]) .mt-svg').first().boundingBox();
    ck(`${tag}: 지도가 그려짐`, box && box.height > 80, JSON.stringify(box));
    ck(`${tag}: 가로 넘침 없음`,
      await page.evaluate(() =>
        document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1));

    // ── 상태를 하나씩 돌며 backend와 대조 ────────────────────────────────
    for (const b of d.series_blocks) {
      await page.click(`[data-set="series=${b.comparison_series_id}"]`);
      for (const s of b.states) {
        await page.click(`[data-set="role=${s.role}"]`);
        const f = page.locator('.mt-frame:not([hidden])').first();
        ck(`${tag}/${s.state_id}: 그 상태가 보인다`,
          await f.getAttribute('data-state') === s.state_id,
          await f.getAttribute('data-state'));

        // 경계는 사건일에 이산 전환한다 — polygon 개수가 실제로 바뀐다
        const nPoly = await f.locator('.mt-u').count();
        ck(`${tag}/${s.state_id}: 폴리곤 = 경계 feature`,
          nPoly === s.geography_at_date.features.length, `${nPoly}`);
        ck(`${tag}/${s.state_id}: 모든 폴리곤에 이름표`,
          await f.locator('.mt-u[aria-label]').count() === nPoly);

        // 화면 문장이 backend가 허용한 문장과 같아야 한다
        ck(`${tag}/${s.state_id}: 문장이 backend와 일치`,
          (await f.locator('.mt-claim').innerText()).trim() === s.displayable_claim);

        // **핵심** — 칠할 수 없는 경계에 계열색이 새지 않는다
        const unav = Object.values(s.political_projection.per_unit)
          .filter((p) => p.method === 'unavailable').length;
        const nNone = await f.locator('.mt-u.mt-unavailable').count();
        ck(`${tag}/${s.state_id}: 표시 불가 폴리곤 수 (${nNone}/${unav})`, nNone === unav);
        const leaked = await f.locator('.mt-u.mt-unavailable').evaluateAll(
          (els, hexes) => els.filter((e) => hexes.includes(
            (e.getAttribute('fill') || '').toLowerCase())).length, FAM_HEX);
        ck(`${tag}/${s.state_id}: 표시 불가에 계열색 없음`, leaked === 0, `${leaked}`);
        if (unav && unav === Object.keys(s.political_projection.per_unit).length) {
          ck(`${tag}/${s.state_id}: 전부 불가면 문장도 그렇게 말한다`,
            (await f.locator('.mt-claim').innerText()).includes('표시할 수 없'));
        }
      }
    }

    // ── 사건 전후 topology가 진짜로 바뀌는가 ────────────────────────────
    await page.click(`[data-set="series=${d.series_blocks[0].comparison_series_id}"]`);
    await page.click('[data-set="role=before_geo_event"]');
    const nBefore = await page.locator('.mt-frame:not([hidden]) .mt-u').count();
    const dBefore = await page.locator('.mt-frame:not([hidden]) .mt-u').first()
      .getAttribute('d');
    await page.click('[data-set="role=after_geo_event"]');
    const nAfter = await page.locator('.mt-frame:not([hidden]) .mt-u').count();
    ck(`${tag}: 사건에서 폴리곤 수가 바뀐다 (${nBefore}→${nAfter})`, nBefore !== nAfter);
    const dAfter = await page.locator('.mt-frame:not([hidden]) .mt-u').first()
      .getAttribute('d');
    ck(`${tag}: 같은 폴리곤을 이름만 바꿔 쓰지 않는다`, dBefore !== dAfter);

    // ── 렌더 골든 (좌표·채움) ────────────────────────────────────────────
    if (vp.name === 'desktop') {
      const shot = await page.evaluate(() => {
        const out = {};
        document.querySelectorAll('.mt-frame').forEach((f) => {
          out[f.dataset.state] = [...f.querySelectorAll('.mt-u')].map((p) => ({
            fill: p.getAttribute('fill'), cls: p.getAttribute('class'),
            d: p.getAttribute('d').slice(0, 160), len: p.getAttribute('d').length,
            label: p.getAttribute('aria-label'),
          }));
        });
        return out;
      });
      fs.mkdirSync(GOLDEN, { recursive: true });
      const gf = path.join(GOLDEN, `${region}.json`);
      const txt = JSON.stringify(shot, null, 1) + '\n';
      if (update || !fs.existsSync(gf)) {
        fs.writeFileSync(gf, txt);
        console.log(`  → 골든 ${update ? '갱신' : '생성'}: ${gf}`);
      } else {
        ck(`${region}: 렌더 골든 일치`, fs.readFileSync(gf, 'utf-8') === txt,
          '좌표·채움·라벨이 바뀌었다 (의도한 것이면 --update)');
      }
    }
    await page.close();
  }

  // ── JS 없이도 정확히 한 프레임 ─────────────────────────────────────────
  // 다 보이면 series와 시점을 한꺼번에 섞어 보여주는 셈이다.
  const ctx = await browser.newContext({ javaScriptEnabled: false,
    viewport: { width: 1440, height: 900 } });
  const nj = await ctx.newPage();
  await nj.goto(`${srv.url}/map-timelapse/${encodeURIComponent(region)}.html`,
    { waitUntil: 'load' });
  const nVis = await nj.locator('.mt-frame:not([hidden])').count();
  ck(`${region}/no-js: 한 프레임만 (${nVis})`, nVis === 1);
  ck(`${region}/no-js: 기본 series의 첫 시점`,
    await nj.locator('.mt-frame:not([hidden])').first().getAttribute('data-state')
    === d.series_blocks[0].states[0].state_id);
  await ctx.close();
}

await browser.close();
await srv.close();
console.log(`\n[지도 타임랩스 UI] 실패 ${fails.length}`);
process.exit(fails.length ? 1 : 0);
