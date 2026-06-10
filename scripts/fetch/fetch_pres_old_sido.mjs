// info.nec 개표현황(VCCP09) → 옛 대선 13~15(1987·92·97) 시도별 후보·득표.
// 결과파일이 nation(전국 합산)만 있어 시도 hex/지도·timeline sidoWinners 불가했던 회차.
// 구조는 광역장(시도 합계 행)과 동일: electionType=1(대통령)·electionCode=1·cityCode별 합계 행.
// 출력: data/raw/nec/pres_old_sido_{n}.json = { 시도명: {electors, voted, candidates:[{name,party,votes}]} }
import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const URL = 'https://info.nec.go.kr/main/showDocument.xhtml?electionId=0000000000&topMenuId=VC&secondMenuId=VCCP09';
const ROUNDS = { 13: '19871216', 14: '19921218', 15: '19971218' };
const CITY = { '11': '서울특별시', '26': '부산광역시', '27': '대구광역시', '28': '인천광역시',
  '29': '광주광역시', '30': '대전광역시', '31': '울산광역시', '41': '경기도', '42': '강원도',
  '43': '충청북도', '44': '충청남도', '45': '전라북도', '46': '전라남도', '47': '경상북도',
  '48': '경상남도', '49': '제주도' };
const HDR = new Set(['후보자별', '득표수', '무효', '무효투표수', '투표수', '선거인수',
  '기권자수', '기권', '구시군명', '선거구명', '계']);
function splitCand(html) {
  const p = html.replace(/<[^>]+>/g, '§').split('§').map((x) => x.trim()).filter(Boolean);
  if (p.length < 2) return null;
  if (HDR.has(p[0]) || HDR.has(p[1])) return null;
  return { party: p[0], name: p.slice(1).join('') };
}
const num = (s) => { const n = parseInt((s || '').replace(/[^0-9]/g, ''), 10); return isNaN(n) ? 0 : n; };

let browser, page, setups = 0;
async function fresh() {
  if (browser) await browser.close().catch(() => {});
  browser = await chromium.launch();
  page = await browser.newPage();
  setups = 0;
}
async function setSel(id, val) {
  await page.evaluate(({ id, val }) => {
    const s = document.getElementById(id);
    if (s) { s.value = val; s.dispatchEvent(new Event('change', { bubbles: true })); }
  }, { id, val });
  await page.waitForTimeout(1000);
}
async function setup(name, city) {
  if (setups >= 10 || !page) await fresh();
  setups++;
  await page.goto(URL, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(600);
  await setSel('electionType', '1');   // 대통령
  await setSel('electionName', name);
  await setSel('electionCode', '1');   // 대통령선거
  await setSel('cityCode', city);
  await page.evaluate(() => document.querySelector('#searchBtn').click());
  await page.waitForFunction(() =>
    [...document.querySelectorAll('table td strong, table th strong')].some((s) => s.querySelector('br')),
    { timeout: 12000 }).catch(() => {});
  await page.waitForTimeout(400);
}
async function grab() {
  return await page.evaluate(() => {
    const t = [...document.querySelectorAll('table')]
      .sort((a, b) => b.querySelectorAll('tr').length - a.querySelectorAll('tr').length)[0];
    if (!t) return [];
    return [...t.querySelectorAll('tr')].map((tr) =>
      [...tr.querySelectorAll('th,td')].map((c) => ({ text: c.textContent.replace(/\s+/g, ' ').trim(), html: c.innerHTML })));
  });
}

for (const [n, name] of Object.entries(ROUNDS)) {
  console.error(`=== ${n}대 대선 (${name}) ===`);
  await fresh();
  const out = {};
  // 가용 시도 cityCode는 회차마다 다름(대전 1989·울산 1997 승격 전) — 페이지 옵션으로 확인.
  await page.goto(URL, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(600);
  await setSel('electionType', '1'); await setSel('electionName', name); await setSel('electionCode', '1');
  const codes = await page.evaluate(() => [...document.getElementById('cityCode').options]
    .map((o) => o.value).filter((v) => v !== '-1' && v !== '0'));
  for (const cc of codes) {
    const sido = CITY[cc];
    if (!sido) continue;
    await setup(name, cc);
    const rows = await grab();
    const cand = rows.find((r) => r.some((c) => splitCand(c.html)));
    const sumRow = rows.find((r) => r[0] && r[0].text === '합계');
    if (!cand || !sumRow) { console.error(`  ${sido}: 표 없음`); continue; }
    const cands = [];
    for (const c of cand) { const s = splitCand(c.html); if (s) cands.push(s); }
    const cells = sumRow.map((c) => c.text);
    cands.forEach((c, i) => { c.votes = num(cells[3 + i]); });
    out[sido] = { electors: num(cells[1]), voted: num(cells[2]), candidates: cands.filter((c) => c.name) };
    console.error(`  ${sido}: ${cands.length}명`);
  }
  const path = `/home/whysw/Documents/vote-via-data/data/raw/nec/pres_old_sido_${n}.json`;
  writeFileSync(path, JSON.stringify(out, null, 1), 'utf-8');
  console.error(`→ ${path}: ${Object.keys(out).length}시도`);
}
await browser.close();
