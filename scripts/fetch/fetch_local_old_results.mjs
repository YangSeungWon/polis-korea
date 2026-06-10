// info.nec.go.kr 개표현황(VCCP09) → 옛 지선 1·2회(1995·1998) 광역장·기초장 전체 후보·득표.
// 투개표 OpenAPI·LOD가 3회(2002)부터라 1·2회만 여기서. 폼 cascade(JS value+change) + #searchBtn → 표 스크랩.
//   광역장(electionCode=3): 시도별 1 race(합계 행 = 시도 전체).
//   기초장(electionCode=4): 시도 표 안 시군구별 (헤더행+득표행) 세트. 시군구마다 후보 다름.
// 후보 헤더 셀 = 정당<br>성명. 브라우저는 ~10 setup마다 재시작(누적 크래시 회피, [[nec_lod]]).
// 출력: data/raw/nec/local_old_{n}.json = {gov:{시도:{...}}, gicho:{"시도|시군구":{...}}}
//   각 entry: {electors, voted, candidates:[{name,party,votes}]}
// 사용: node scripts/fetch/fetch_local_old_results.mjs   (1·2회 둘 다)
import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const URL = 'https://info.nec.go.kr/main/showDocument.xhtml?electionId=0000000000&topMenuId=VC&secondMenuId=VCCP09';
const ROUNDS = { 1: '19950627', 2: '19980604' };
const CITY = { '11': '서울특별시', '26': '부산광역시', '27': '대구광역시', '28': '인천광역시',
  '29': '광주광역시', '30': '대전광역시', '31': '울산광역시', '41': '경기도', '42': '강원도',
  '43': '충청북도', '44': '충청남도', '45': '전라북도', '46': '전라남도', '47': '경상북도',
  '48': '경상남도', '49': '제주도' };

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
async function setup(name, code, city) {
  if (setups >= 10 || !page) await fresh();
  setups++;
  await page.goto(URL, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(600);
  await setSel('electionType', '4');
  await setSel('electionName', name);
  await setSel('electionCode', code);
  await setSel('cityCode', city);
  await page.evaluate(() => document.querySelector('#searchBtn').click());
  // 검색 AJAX 완료 대기 — 후보 헤더(strong 안 <br>) 또는 '합계' 행이 뜰 때까지.
  await page.waitForFunction(() =>
    [...document.querySelectorAll('table td strong, table th strong')].some((s) => s.querySelector('br')),
    { timeout: 12000 }).catch(() => {});
  await page.waitForTimeout(400);
}

// 표를 [{cells:[{text,html}]}] 행 배열로
async function grab() {
  return await page.evaluate(() => {
    const t = [...document.querySelectorAll('table')]
      .sort((a, b) => b.querySelectorAll('tr').length - a.querySelectorAll('tr').length)[0];
    if (!t) return [];
    return [...t.querySelectorAll('tr')].map((tr) =>
      [...tr.querySelectorAll('th,td')].map((c) => ({
        text: c.textContent.replace(/\s+/g, ' ').trim(),
        html: c.innerHTML,
      })));
  });
}
const num = (s) => { const n = parseInt((s || '').replace(/[^0-9]/g, ''), 10); return isNaN(n) ? 0 : n; };
// 그룹 헤더 셀도 <br>를 가짐('무효<br>투표수'·'후보자별<br>득표수') → 후보로 오인 방지 블록리스트.
const HDR = new Set(['후보자별', '득표수', '무효', '무효투표수', '투표수', '선거인수',
  '기권자수', '기권', '구시군명', '선거구명', '계']);
function splitCand(html) {           // "정당<br>성명" → {party,name}
  const parts = html.replace(/<[^>]+>/g, '§').split('§').map((x) => x.trim()).filter(Boolean);
  if (parts.length < 2) return null;
  if (HDR.has(parts[0]) || HDR.has(parts[1])) return null;
  return { party: parts[0], name: parts.slice(1).join('') };
}

async function fetchGov(name) {       // 광역장: 시도별 합계 행
  const out = {};
  for (const [cc, sido] of Object.entries(CITY)) {
    await setup(name, '3', cc);
    const rows = await grab();
    const cand = rows.find((r) => r.some((c) => splitCand(c.html)));
    if (!cand) continue;              // 그 회차에 그 시도 없음(울산 1995 등)
    const cands = [];
    for (const c of cand) { const s = splitCand(c.html); if (s) cands.push(s); }
    const sumRow = rows.find((r) => r[0] && r[0].text === '합계');
    if (!sumRow) continue;
    const cells = sumRow.map((c) => c.text);
    const electors = num(cells[1]), voted = num(cells[2]);
    cands.forEach((c, i) => { c.votes = num(cells[3 + i]); });
    out[sido] = { electors, voted, candidates: cands.filter((c) => c.name) };
    console.error(`  광역 ${sido}: ${cands.length}명`);
  }
  return out;
}

async function fetchGicho(name) {     // 기초장: 시도 표 안 시군구별 (헤더행 다음 득표행)
  const out = {};
  for (const [cc, sido] of Object.entries(CITY)) {
    await setup(name, '4', cc);
    const rows = await grab();
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i];
      // 헤더행: 첫 셀(선거구명) 채워짐 + 후보 셀 존재
      const cells = r.map((c) => c.text);
      const hasCand = r.some((c) => splitCand(c.html));
      if (!(cells[0] && hasCand)) continue;
      const sgg = cells[0];
      const cands = [];
      for (const c of r) { const s = splitCand(c.html); if (s) cands.push(s); }
      // 득표행 = 헤더 바로 다음 행(시군구 총계). 구시군명은 '소계'(성동구 등 다선거구) 또는
      // '중구(서울)'(접미사)일 수 있어 sgg와 일치 안 해도 됨 — 위치(i+1)로 잡는다.
      const vr = rows[i + 1];
      if (!vr) continue;
      const vc = vr.map((c) => c.text);
      const electors = num(vc[2]), voted = num(vc[3]);
      cands.forEach((c, k) => { c.votes = num(vc[4 + k]); });
      out[`${sido}|${sgg}`] = { electors, voted, candidates: cands.filter((c) => c.name) };
    }
    console.error(`  기초 ${sido}: ${Object.keys(out).filter((k) => k.startsWith(sido + '|')).length}곳`);
  }
  return out;
}

for (const [n, name] of Object.entries(ROUNDS)) {
  console.error(`=== ${n}회 (${name}) ===`);
  await fresh();
  const gov = await fetchGov(name);
  const gicho = await fetchGicho(name);
  const path = `/home/whysw/Documents/vote-via-data/data/raw/nec/local_old_${n}.json`;
  writeFileSync(path, JSON.stringify({ gov, gicho }, null, 1), 'utf-8');
  console.error(`→ ${path}: 광역 ${Object.keys(gov).length}시도, 기초 ${Object.keys(gicho).length}곳`);
}
await browser.close();
