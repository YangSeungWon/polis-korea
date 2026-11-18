// 추출(Extract) — 화면에서 가져간 것이 화면과 같은가.
//
// 막는 사고:
//   · 링크 복사가 상태 없는 주소를 준다(받은 사람이 다른 화면을 본다).
//   · '그림'이 지금 보이는 모드가 아니라 첫 모드의 PNG를 연다.
//   · 그림이 없는 모드에서 버튼이 조용히 아무것도 안 한다(결손을 숨긴다).
//   · CSV가 원자료와 행 수·값이 다르다. 모르는 득표(null)를 0으로 적는다.
//   · 당선자 CSV가 화면의 500명 제한을 그대로 따라 잘린다. 조건이 안 적힌다.
//
// 실행: node tests/ui/test_extract.mjs
import { chromium } from 'playwright';
import fs from 'fs';
import { serve } from './server.mjs';

const ROOT = new URL('../..', import.meta.url).pathname;
let pass = 0; const fails = [];
const ck = (n, c, d) => {
  if (c) { pass++; console.log(`  ✓ ${n}`); }
  else { fails.push(n); console.log(`  ✗ ${n}${d ? ' — ' + d : ''}`); }
};

const srv = await serve(ROOT, 8293);
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, acceptDownloads: true });
await ctx.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: srv.url });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', (e) => errs.push(String(e)));
const clip = () => page.evaluate(() => navigator.clipboard.readText());

// CSV 파서 — 따옴표·쉼표·줄바꿈. '# ' 줄은 머리 주석.
function parseCSV(text) {
  const body = text.replace(/^﻿/, '');
  const notes = [];
  const lines = body.split('\r\n');
  while (lines[0] && lines[0].startsWith('# ')) notes.push(lines.shift().slice(2));
  const rows = [];
  const src = lines.join('\r\n');
  let row = [], cur = '', q = false;
  for (let i = 0; i < src.length; i++) {
    const ch = src[i];
    if (q) {
      if (ch === '"' && src[i + 1] === '"') { cur += '"'; i++; }
      else if (ch === '"') q = false;
      else cur += ch;
    } else if (ch === '"') q = true;
    else if (ch === ',') { row.push(cur); cur = ''; }
    else if (ch === '\r' && src[i + 1] === '\n') { row.push(cur); rows.push(row); row = []; cur = ''; i++; }
    else cur += ch;
  }
  if (cur || row.length) { row.push(cur); rows.push(row); }
  const [header, ...data] = rows;
  return { notes, header, data, bom: text.startsWith('﻿') };
}
async function grab(clickSel) {
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 15000 }), page.click(clickSel)]);
  const p = await dl.path();
  return { name: dl.suggestedFilename(), csv: parseCSV(fs.readFileSync(p, 'utf8')) };
}

// ── archive: 링크·그림 ───────────────────────────────────────────
console.log('archive 도구줄');
const ID = '21st-pres-2025';
await page.goto(srv.url + `/archive/${ID}/`);
await page.waitForSelector('[data-map-host="sgg"]');
await page.waitForTimeout(800);
const sggSec = await page.$eval('[data-map-host="sgg"]', (e) => e.closest('.ar-section').id);
const tools = `#${sggSec} .fig-tools`;
ck('시군구 지도 섹션 제목에 도구줄', !!(await page.$(tools)), sggSec);
await page.click('.sgg-mode-toggle [data-enc="격자"]');
await page.waitForTimeout(300);
await page.click(`${tools} .fig-tool:has-text("링크 복사")`);
await page.waitForTimeout(200);
const copied = new URL(await clip());
ck('링크에 섹션 앵커', copied.hash === '#' + sggSec, copied.hash);
ck('링크에 지금 모드(?v=sgg-grid)', copied.searchParams.getAll('v').includes('sgg-grid'), copied.search);

const manifest = JSON.parse(fs.readFileSync(ROOT + 'data/map_manifest.json', 'utf8')).elections[ID].views;
const [pop] = await Promise.all([
  ctx.waitForEvent('page', { timeout: 5000 }).catch(() => null),
  page.click(`${tools} .fig-tool:has-text("그림")`),
]);
if (pop) await pop.waitForLoadState().catch(() => {});
const popURL = pop ? decodeURIComponent(new URL(pop.url()).pathname) : '(안 열림)';
ck('그림 = 지금 보이는 모드의 PNG', popURL === `/og/maps/${ID}/sgg-grid.png`, popURL);
const r = pop ? await page.request.get(srv.url + popURL) : null;
ck('그 PNG가 실제로 있다', !!r && r.status() === 200 && manifest.includes('sgg-grid'), r ? String(r.status()) : '안 열림');
if (pop) await pop.close();

// 그림 없는 모드 — 숨기지 않고 말한다. 매니페스트에 없는 모드로 바꿔 끼운다.
await page.$eval('[data-map-host="sgg"]', (e) => { e.dataset.mode = 'turnout'; });
await page.click(`${tools} .fig-tool:has-text("그림")`);
await page.waitForTimeout(400);
ck('그림 없는 모드 → 없다고 말한다', /없음/.test(await page.$eval(`${tools}`, (e) => e.textContent)));

// ── archive: 결과 CSV ─────────────────────────────────────────────
console.log('결과 CSV');
const main = JSON.parse(fs.readFileSync(ROOT + `data/results/${ID}.json`, 'utf8'));
let races = main.races;
if (main._meta && main._meta.chunked) races = races.concat(JSON.parse(fs.readFileSync(ROOT + `data/results/${ID}.sigungu.json`, 'utf8')).races);
const nCand = races.reduce((a, x) => a + (x.candidates || []).length, 0);
const res = await grab('#ar-results-csv');
ck('파일명 = 회차 id', res.name === `${ID}-results.csv`, res.name);
ck('UTF-8 BOM(엑셀 한글)', res.csv.bom);
ck('머리 주석에 출처', res.csv.notes.some((n) => /출처/.test(n)), res.csv.notes.join(' | '));
ck('행 수 = 원자료 후보 수', res.csv.data.length === nCand, `${res.csv.data.length} vs ${nCand}`);
const H = res.csv.header;
const col = (n) => H.indexOf(n);
const nation = res.csv.data.find((row) => row[col('집계단위')] === 'nation' && row[col('순위')] === '1');
const nat0 = races.find((x) => x.scope === 'nation').candidates.find((c) => c.rank === 1);
ck('전국 1위 득표가 원자료와 같다', nation && nation[col('득표수')] === String(nat0.votes), nation && nation[col('득표수')]);

// 모르는 득표(null) → 빈칸. 이 회차에 null이 없으면 다른 파일로 확인한다.
const pickNull = () => {
  for (const f of fs.readdirSync(ROOT + 'data/results')) {
    if (!/^[0-9a-z-]+\.json$/.test(f) || f.includes('sigungu')) continue;
    let d; try { d = JSON.parse(fs.readFileSync(ROOT + 'data/results/' + f, 'utf8')); } catch { continue; }
    const hit = (d.races || []).some((x) => (x.candidates || []).some((c) => c.votes == null));
    if (hit && fs.existsSync(ROOT + 'archive/' + f.replace('.json', '') + '/index.html')) return { id: f.replace('.json', ''), d };
  }
  return null;
};
const nul = pickNull();
if (nul) {
  await page.goto(srv.url + `/archive/${nul.id}/`);
  await page.waitForSelector('#ar-results-csv:not([disabled])', { timeout: 20000 });
  const n2 = await grab('#ar-results-csv');
  let rs = nul.d.races;
  if (nul.d._meta && nul.d._meta.chunked) {
    try { rs = rs.concat(JSON.parse(fs.readFileSync(ROOT + `data/results/${nul.id}.sigungu.json`, 'utf8')).races); } catch {}
  }
  const nullCount = rs.reduce((a, x) => a + (x.candidates || []).filter((c) => c.votes == null).length, 0);
  const vi = n2.csv.header.indexOf('득표수');
  const blank = n2.csv.data.filter((row) => row[vi] === '').length;
  const zeroFromNull = n2.csv.data.filter((row) => row[vi] === '0').length
    - rs.reduce((a, x) => a + (x.candidates || []).filter((c) => c.votes === 0).length, 0);
  ck(`모르는 득표는 빈칸(0 아님) — ${nul.id}`, blank === nullCount && zeroFromNull === 0, `빈칸 ${blank} · null ${nullCount} · 늘어난 0 ${zeroFromNull}`);
} else {
  console.log('  · null 득표가 있는 회차 없음 — 빈칸 검사 생략');
}

// ── 당선자 CSV ────────────────────────────────────────────────────
console.log('당선자 CSV');
await page.goto(srv.url + '/archive/9th-local-2026/?wsido=' + encodeURIComponent('경기도'));
await page.waitForSelector('#ar-winners-csv', { timeout: 20000 });
await page.waitForTimeout(500);
const shown = +((await page.$eval('#ar-winners-count', (e) => e.textContent)).replace(/[^0-9]/g, ''));
const w = await grab('#ar-winners-csv');
ck('당선자 CSV 행 수 = 화면 필터 결과(500 제한 없음)', w.csv.data.length === shown && shown > 0, `${w.csv.data.length} vs ${shown}`);
ck('당선자 CSV 머리에 조건', w.csv.notes.some((n) => /조건: .*경기도/.test(n)), w.csv.notes.join(' | '));
await page.selectOption('#ar-winners-sido', '');
await page.waitForTimeout(300);
const all = +((await page.$eval('#ar-winners-count', (e) => e.textContent)).replace(/[^0-9]/g, ''));
const wa = await grab('#ar-winners-csv');
ck('필터 없으면 전체(500 넘어도)', wa.csv.data.length === all && all > 500, `${wa.csv.data.length} vs ${all}`);
ck('필터 없으면 조건에 그렇게 적힌다', wa.csv.notes.some((n) => /필터 없음/.test(n)));

// ── 트래커 CSV ────────────────────────────────────────────────────
console.log('트래커 CSV');
await page.goto(srv.url + '/tracker.html');
await page.waitForSelector('.tk-section-head .fig-tool', { timeout: 30000 });
for (const id of ['tk-approval', 'tk-party', 'tk-cand']) {
  const sel = `.tk-section:has(#${id}) .tk-section-head .fig-tool`;
  if (!(await page.$(sel))) { ck(`${id} CSV 버튼`, false); continue; }
  const t = await grab(sel);
  const ui = t.csv.header.indexOf('출처');
  ck(`${id} CSV — 개별 조사 행·출처 열`, t.csv.data.length > 50 && ui >= 0, `${t.csv.data.length}행`);
  const vi = t.csv.header.indexOf('값(%)');
  ck(`${id} CSV — 값 칸이 비지 않는다`, t.csv.data.every((row) => row[vi] !== ''));
}

// ── history 링크 복사 ─────────────────────────────────────────────
console.log('history 링크 복사');
await page.goto(srv.url + '/history/presidential/21/?view=dorling');
await page.waitForSelector('.hist-copy-link');
await page.waitForTimeout(500);
await page.click('.hist-copy-link');
await page.waitForTimeout(200);
ck('history 링크 = 지금 주소(방식 포함)', (await clip()) === (await page.evaluate(() => location.href)) && /view=dorling/.test(await clip()));

// ── 데이터 안내 ───────────────────────────────────────────────────
console.log('데이터 안내');
const about = await page.goto(srv.url + '/about/data/');
ck('/about/data/ 열린다', about.status() === 200);
const files = await page.$$eval('.dl-table code', (els) => els.map((e) => e.textContent).filter((t) => t.startsWith('/data/') && !t.includes('{') && !t.includes('*')));
for (const f of files) {
  const rr = await page.request.get(srv.url + f, { failOnStatusCode: false });
  ck(`안내한 파일이 있다 ${f}`, rr.status() === 200 || (f.endsWith('/') && fs.existsSync(ROOT + f.slice(1))), String(rr.status()));
}
const ar0 = JSON.parse(fs.readFileSync(ROOT + 'data/archive_index.json', 'utf8'))[0].slug;
ck('안내한 이름 규칙 /data/results/{slug}.json이 맞다', fs.existsSync(ROOT + `data/results/${ar0}.json`) || fs.existsSync(ROOT + `data/elections/${ar0}.json`), ar0);

ck('페이지 오류 없음', errs.length === 0, errs.slice(0, 3).join(' | '));

await browser.close();
srv.close();
console.log(`\n${pass} 통과 · ${fails.length} 실패`);
process.exit(fails.length ? 1 : 0);
