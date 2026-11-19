// 관계(Relate) — 화면에서 본 곳에서 관련된 곳으로 건너갈 수 있는가.
//
// 막는 사고:
//   · 지도에서 고른 시군구에서 그 지역 페이지로 가는 길이 없다(history 상세 패널).
//   · 선거구 집계(동대문갑구)를 이름 모양으로 잘라 없는 지역으로 보낸다.
//   · 지도 칸과 당선자 표가 서로를 모른다 — 한쪽에 손을 올려도 다른 쪽이 그대로다.
//   · 연동이 지도를 '지운다'(Overview를 잃는다). 지도에 손을 올리면 다른 지도까지 흐린다.
//   · 비교 페이지가 URL 조건을 안 읽는다 / 모르는 칸을 0으로 쓴다 / 지역 1위가
//     '같았다'를 센다(대선은 지역 승부가 아니다, 교육감 무소속=무소속은 같은 편이 아니다).
//   · 시도를 비교하면 대선 막대가 전부 '자료 없음'이다(자료가 있는데 모른다고 보인다).
//   · 검색이 사람만 찾는다 — '성남'으로 성남의 선거 기록에 못 간다.
//
// 실행: node tests/ui/test_relate.mjs
import { chromium } from 'playwright';
import { serve } from './server.mjs';

let pass = 0; const fails = [];
const ck = (n, c, d) => {
  if (c) { pass++; console.log(`  ✓ ${n}`); }
  else { fails.push(n); console.log(`  ✗ ${n}${d ? ' — ' + d : ''}`); }
};

const ROOT = new URL('../..', import.meta.url).pathname;
const srv = await serve(ROOT, 8294);
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', (e) => errs.push(String(e)));
const enc = encodeURIComponent;

// ── 1. history 상세 → 지역 페이지 ──────────────────────────────────────────
console.log('\n[history 상세 → /region/]');
await page.goto(srv.url + '/history/presidential/21/?sel=' + enc('서울특별시|강남구'));
const link = await page.waitForSelector('#detail-pane .region-page-link', { timeout: 20000 }).catch(() => null);
const href = link ? await link.getAttribute('href') : '';
ck('시군구 선택 → 지역 페이지 링크', decodeURIComponent(href || '') === '/region/서울특별시-강남구/', href);
await page.goto(srv.url + '/history/presidential/21/?sel=' + enc('서울특별시'));
const l2 = await page.waitForSelector('#detail-pane .region-page-link', { timeout: 20000 }).catch(() => null);
ck('시도 선택 → 시도 페이지', decodeURIComponent((l2 && await l2.getAttribute('href')) || '') === '/region/서울특별시/');

// 해소표는 이름 모양이 아니라 containment·개명을 따른다.
const res = await page.evaluate(async () => {
  const ix = await window.RegionPaths.load();
  const R = (a, b) => window.RegionPaths.resolveWith(ix, a, b);
  return {
    seon: R('서울특별시', '동대문갑구'),
    renamed: R('강원도', '홍천군'),
    unknown: R('서울특별시', '없는구'),
    gu: R('경기도', '성남시분당구'),
  };
});
ck('선거구 집계 → 실재 구(동대문갑구 → 동대문구)', res.seon === '서울특별시-동대문구', res.seon);
ck('옛 시도명 → 지금 이름(강원도 홍천군)', res.renamed === '강원특별자치도-홍천군', res.renamed);
ck('없는 곳은 링크하지 않는다', res.unknown === null, res.unknown);
ck('일반구는 제 페이지(접지 않는다)', res.gu === '경기도-성남시분당구', res.gu);

// ── 2. archive 지도 ↔ 당선자 표 연동 ───────────────────────────────────────
console.log('\n[archive 지도 ↔ 당선자 표]');
await page.goto(srv.url + '/archive/8th-local-2022/?wsido=' + enc('강원특별자치도') + '&wlv=' + enc('기초의원'));
await page.waitForSelector('.ar-winner-row[data-region]', { timeout: 30000 });
await page.waitForSelector('#ar-council-hex [data-region]', { timeout: 30000 });
const key = await page.$eval('.ar-winner-row[data-region*="|"]', (e) => e.dataset.region);
await page.hover(`.ar-winner-row[data-region="${key}"]`);
await page.waitForTimeout(250);   // 흐림 전환(.12s)이 끝난 뒤 잰다
const hov = await page.evaluate((k) => {
  const cells = [...document.querySelectorAll('#ar-council-hex [data-region]')];
  const on = cells.filter((c) => c.classList.contains('is-brushed')).map((c) => c.dataset.region);
  const svg = document.querySelector('#ar-council-hex svg');
  const other = cells.find((c) => !c.classList.contains('is-brushed'));
  return { on, dim: svg.classList.contains('brushing'), op: other ? getComputedStyle(other).opacity : null, n: cells.length, k };
}, key);
ck('표 행에 손 → 같은 시군구 지도 칸이 밝아진다', hov.on.length >= 1 && hov.on.every((r) => r === key), JSON.stringify(hov.on));
ck('나머지 칸은 지우지 않고 흐린다', hov.dim && hov.op !== null && +hov.op > 0 && +hov.op < 1, hov.op);

// 반대 방향 — 지도 칸에 손을 올리면 그 시군구의 행이 밝아진다.
await page.mouse.move(0, 0);
const cellSel = `#ar-council-hex [data-region="${key}"]`;
await page.$eval(cellSel, (e) => e.scrollIntoView({ block: 'center' }));
await page.hover(cellSel, { force: true });
const back = await page.evaluate((k) => {
  const rows = [...document.querySelectorAll('.ar-winner-row[data-region]')];
  return {
    on: rows.filter((r) => r.classList.contains('is-brushed')).map((r) => r.dataset.region),
    off: rows.filter((r) => !r.classList.contains('is-brushed')).map((r) => r.dataset.region),
  };
}, key);
ck('지도 칸에 손 → 그 시군구 당선자 행이 밝아진다', back.on.length >= 1 && back.on.every((r) => r === key), JSON.stringify(back.on.slice(0, 3)));
ck('다른 시군구 행은 밝아지지 않는다', back.off.every((r) => r !== key));
ck('지도에 손 → 지도들은 흐리지 않는다(표만 따라온다)', await page.evaluate(() => !document.querySelector('svg.brushing')));
// 상관없는 지도는 흐리지 않는다 — 시도 단위만 있는 지도(광역)는 시군구 키와 직접 맞지 않으면 그대로.
await page.mouse.move(0, 0);
await page.waitForTimeout(50);
ck('손을 떼면 원래대로', await page.evaluate(() => !document.querySelector('.is-brushed, .brushing')));

// 당선자 행 → 지역 페이지
const locHref = await page.$eval(`.ar-winner-row[data-region="${key}"] .ar-winner-loc a`, (a) => a.getAttribute('href')).catch(() => null);
ck('당선자 선거구 → 그 시군구 지역 페이지', decodeURIComponent(locHref || '') === `/region/${key.replace('|', '-')}/`, locHref);

// ── 3. 지역 페이지: 비교 진입 ──────────────────────────────────────────────
console.log('\n[지역 페이지]');
await page.goto(srv.url + '/region/' + enc('경기도-성남시분당구') + '/');
const cmpIn = await page.$eval('.rg-relate .rg-cmp-link a', (a) => decodeURIComponent(a.getAttribute('href'))).catch(() => '');
ck('나란히 보기 진입점(a=이 지역)', cmpIn === '/region/compare.html?a=경기도-성남시분당구', cmpIn);
ck('자동 \'비슷한 지역\' 목록은 없다', !(await page.$('.rg-sim, #similar')));

// ── 4. 비교 페이지 ─────────────────────────────────────────────────────────
console.log('\n[두 지역 나란히]');
await page.goto(srv.url + '/region/compare.html?a=' + enc('서울특별시-강남구') + '&b=' + enc('광주광역시-북구'));
await page.waitForSelector('.cmp-table tbody tr', { timeout: 20000 }).catch(() => null);  // 없으면 아래 검사가 이름을 대고 실패한다
const cmp = await page.evaluate(() => (!document.querySelector('.cmp-table') ? { a: '', b: '', rows: 0, pres: 0, bars: [], zero: false, sum: '' } : {
  a: document.querySelector('#cmp-a').value, b: document.querySelector('#cmp-b').value,
  rows: document.querySelectorAll('.cmp-table tbody tr').length,
  pres: document.querySelectorAll('.cmp-pres tbody tr').length,
  bars: [...document.querySelectorAll('.cmp-pres .cmp-bar span')].map((s) => parseFloat(s.style.width)),
  zero: /(^|[^0-9.])0\.0%/.test(document.querySelector('.cmp-table').textContent),
  sum: document.querySelector('#cmp-out .rg-swing')?.textContent || '',
}));
ck('URL ?a=&b= → 두 입력이 채워진다', cmp.a === '서울 강남구' && cmp.b === '광주 북구', `${cmp.a} / ${cmp.b}`);
ck('같은 선거끼리 맞춘 표', cmp.rows > 10, String(cmp.rows));
ck('대선 득표율 막대(단색 아님 — 두 후보 비례)', cmp.pres > 3 && cmp.bars.length >= 2 * 3 && cmp.bars.every((w) => w >= 0 && w <= 100));
ck('요약 한 줄 = 대선 득표율 차이(제곱평균제곱근이라고 밝힌다)', /%p/.test(cmp.sum) && /제곱평균/.test(cmp.sum) && !/평균 <b>|평균 \d/.test(cmp.sum), cmp.sum);
ck('지역 1위가 같았는지는 세지 않는다', !/1위 정당이 같았/.test(cmp.sum), cmp.sum);
// 표의 값이 지역 JSON과 같다(새 값을 만들지 않는다).
const same = await page.evaluate(async () => {
  const j = await (await fetch('/data/regions/' + encodeURIComponent('서울특별시-강남구') + '.json')).json();
  const r = j.rows.find((x) => x.pct != null);
  const cellTxt = [...document.querySelectorAll('.cmp-table tbody tr')]
    .find((tr) => tr.querySelector('a') && tr.querySelector('a').getAttribute('href') === `/archive/${r.eid}/`
      && tr.querySelector('.cmp-office').textContent === r.office);
  return cellTxt ? cellTxt.children[1].textContent.includes(r.pct.toFixed(1) + '%') : false;
});
ck('표 값 = 지역 JSON 값', same);
// 시도끼리 — 대선 막대가 '자료 없음'으로 비지 않는다.
await page.goto(srv.url + '/region/compare.html?a=' + enc('서울특별시') + '&b=' + enc('경기도'));
await page.waitForSelector('.cmp-pres tbody tr', { timeout: 20000 }).catch(() => null);
const sd = await page.evaluate(() => ({
  bars: document.querySelectorAll('.cmp-pres .cmp-bar:not(.cmp-bar-none)').length,
  none: document.querySelectorAll('.cmp-pres .cmp-bar-none').length,
}));
ck('시도 비교 — 대선 득표율 막대가 있다', sd.bars >= 20 && sd.none <= 4, JSON.stringify(sd));
await page.goto(srv.url + '/region/compare.html?a=' + enc('서울특별시-강남구') + '&b=' + enc('광주광역시-북구'));
await page.waitForSelector('.cmp-table tbody tr', { timeout: 20000 }).catch(() => null);
// 입력을 바꾸면 URL이 따라간다(replace — 히스토리 길이 불변).
const h0 = await page.evaluate(() => history.length);
await page.fill('#cmp-b', '부산 해운대구');
await page.dispatchEvent('#cmp-b', 'change');
await page.waitForFunction(() => /해운대/.test(document.querySelector('.cmp-title')?.textContent || ''), null, { timeout: 10000 }).catch(() => null);
const u = new URL(page.url());
ck('지역을 바꾸면 ?b= 갱신', u.searchParams.get('b') === '부산광역시-해운대구', u.searchParams.get('b'));
ck('바꿔도 히스토리 길이 불변', (await page.evaluate(() => history.length)) === h0);
// 모호한 이름은 정하지 않고 그렇다고 말한다.
await page.fill('#cmp-b', '중구');
await page.dispatchEvent('#cmp-b', 'change');
await page.waitForTimeout(100);
ck('모호한 이름(중구)은 고르지 않고 말한다', /하나로 정하지 못했/.test(await page.$eval('#cmp-out', (e) => e.textContent)));

// ── 5. 검색: 지역·선거 카드 ────────────────────────────────────────────────
console.log('\n[검색]');
await page.goto(srv.url + '/search.html?q=' + enc('분당'));
await page.waitForSelector('.s-entity-card', { timeout: 20000 }).catch(() => null);  // 없으면 아래 검사가 이름을 대고 실패한다
const rc = await page.$$eval('.s-entity-card a', (as) => as.map((a) => decodeURIComponent(a.getAttribute('href'))));
ck('“분당” → 지역 카드', rc.includes('/region/경기도-성남시분당구/'), rc.join(' '));
await page.goto(srv.url + '/search.html?q=' + enc('20대 대선'));
await page.waitForSelector('.s-entity-card', { timeout: 20000 }).catch(() => null);  // 없으면 아래 검사가 이름을 대고 실패한다
const ec = await page.$$eval('.s-entity-card a', (as) => as.map((a) => a.getAttribute('href')));
ck('“20대 대선” → 선거 카드', ec.includes('/archive/20th-pres-2022/'), ec.join(' '));
await page.goto(srv.url + '/search.html?q=' + enc('2022') + '&round=' + enc('지선'));
await page.waitForSelector('#list li', { timeout: 20000 });
const ec2 = await page.$$eval('.s-entity-card a', (as) => as.map((a) => a.getAttribute('href')));
ck('종류 필터가 선거 카드에도 걸린다(2022·지선 → 지선만)', ec2.length >= 1 && ec2.every((h) => /local/.test(h)), ec2.join(' '));

// ── 6. 휴대폰 폭 ───────────────────────────────────────────────────────────
console.log('\n[390px]');
await page.setViewportSize({ width: 390, height: 844 });
for (const path of ['/region/compare.html?a=' + enc('서울특별시-강남구') + '&b=' + enc('광주광역시-북구'),
  '/region/' + enc('경기도-성남시분당구') + '/']) {
  await page.goto(srv.url + path);
  await page.waitForTimeout(800);
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  ck(`가로 스크롤 없음 ${decodeURIComponent(path).slice(0, 40)}`, over <= 1, String(over));
}

ck('페이지 오류 없음', errs.length === 0, errs.slice(0, 3).join(' | '));
await browser.close();
srv.close();
console.log(`\n${pass} 통과 · ${fails.length} 실패`);
process.exit(fails.length ? 1 : 0);
