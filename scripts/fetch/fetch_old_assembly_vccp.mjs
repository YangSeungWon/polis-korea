// NEC info.nec.go.kr VCCP09(개표현황) → 9~13대 총선 선거구별 "전체 후보" 득표 수집.
//
// LOD(data.nec SPARQL)는 14대~만 후보를 노출. 9~13대는 EPEI01(당선인명부)에서 당선자만
// 받아와 카드가 "단독 출마"로 오표시되고 낙선자가 누락됐음. VCCP09는 제헌(1948)~ 선거구별
// 전체 후보 득표(낙선 포함)·선거인수·투표수를 보유 → 14대처럼 완전한 race로 재구성.
//
// 표 구조(선거구당): 헤더행[선거구명,,,,후보1..K("정당<br>이름"),"계",,] →
//   헤더 다음 행 = 선거구 총계(단일 시군이면 시군행, 다중이면 "소계"행):
//   [,라벨,선거인수,투표수,v1..vK,유효,무효,기권] → pct행 → 시군별 행들.
//   후보수 K = 헤더 "계" 컬럼 index − 4. 헤더 col0만 채워짐(데이터행은 col0 빈칸).
//
// 출력: data/results/{id}.json — 기존 _meta·비(tc2·district) race는 보존, tc2/district race를
//   전체후보로 교체. 당선: 중선거구 9~12=상위 2(1구 2인), 소선거구 13=상위 1.
//
// 사용: node scripts/fetch/fetch_old_assembly_vccp.mjs [9 10 11 12 13]
import { chromium } from 'playwright';
import { readFileSync, writeFileSync, existsSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const RES = join(ROOT, 'data', 'results');

const ELECTIONS = {
  9: { id: '9th-general-1973', name: '19730227', winners: 2 },
  10: { id: '10th-general-1978', name: '19781212', winners: 2 },
  11: { id: '11th-general-1981', name: '19810325', winners: 2 },
  12: { id: '12th-general-1985', name: '19850212', winners: 2 },
  13: { id: '13th-general-1988', name: '19880426', winners: 1 },
};

const SIDO = { 11: '서울특별시', 26: '부산광역시', 27: '대구광역시', 28: '인천광역시', 29: '광주광역시',
  41: '경기도', 42: '강원특별자치도', 43: '충청북도', 44: '충청남도', 45: '전북특별자치도',
  46: '전라남도', 47: '경상북도', 48: '경상남도', 49: '제주특별자치도' };

const ns = process.argv.slice(2).map(Number).filter(Boolean);
const rounds = ns.length ? ns : [9, 10, 11, 12, 13];

const b = await chromium.launch();
const pg = await b.newPage();
await pg.goto('https://info.nec.go.kr/main/showDocument.xhtml?electionId=0000000000&topMenuId=VC&secondMenuId=VCCP09',
  { waitUntil: 'networkidle', timeout: 45000 });
await pg.waitForTimeout(800);

for (const n of rounds) {
  const E = ELECTIONS[n];
  const races = [];
  for (const [cc, sidoName] of Object.entries(SIDO)) {
    const parsed = await pg.evaluate(async ({ name, cc }) => {
      const body = new URLSearchParams({
        electionId: '0000000000', requestURI: '/electioninfo/0000000000/vc/vccp09.jsp',
        topMenuId: 'VC', secondMenuId: 'VCCP09', menuId: 'VCCP09', statementId: 'VCCP09_#2',
        oldElectionType: '0', electionType: '2', electionName: name, electionCode: '2',
        cityCode: cc, proportionalRepresentationCode: '-1', townCode: '-1', x: '50', y: '15',
      }).toString();
      const r = await fetch('/electioninfo/electionInfo_report.xhtml',
        { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body });
      const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
      const tbl = doc.querySelector('table');
      if (!tbl) return [];
      const trs = [...tbl.querySelectorAll('tbody tr')];
      const num = (s) => parseInt((s || '').replace(/[\s,]/g, ''), 10) || 0;
      const out = [];
      for (let i = 0; i < trs.length; i++) {
        const tds = [...trs[i].querySelectorAll('td')];
        const c0 = (tds[0]?.textContent || '').replace(/\s+/g, ' ').trim();
        if (!c0) continue;  // 헤더만 col0 채워짐
        const texts = tds.map((td) => (td.textContent || '').replace(/\s+/g, ' ').trim());
        const gye = texts.indexOf('계', 4);
        if (gye < 5) continue;
        const cands = [];
        for (let j = 4; j < gye; j++) {
          const parts = (tds[j].innerHTML || '').replace(/<\/?strong>/gi, '')
            .split(/<br\s*\/?>/i).map((s) => s.replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').trim()).filter(Boolean);
          if (!parts.length) continue;
          cands.push(parts.length >= 2 ? { party: parts[0], name: parts.slice(1).join(' ') } : { party: '', name: parts[0] });
        }
        if (!cands.length) continue;
        const tot = [...(trs[i + 1]?.querySelectorAll('td') || [])].map((td) => (td.textContent || '').trim());
        const electors = num(tot[2]), voters = num(tot[3]);
        const valid = num(tot[4 + cands.length]), invalid = num(tot[5 + cands.length]);
        cands.forEach((c, k) => { c.votes = num(tot[4 + k]); });
        out.push({ district: c0, electors, voters, valid, invalid, candidates: cands });
      }
      return out;
    }, { name: E.name, cc });

    for (const d of parsed) {
      const valid = d.valid || d.candidates.reduce((s, c) => s + c.votes, 0);
      const cands = d.candidates
        .map((c) => ({ ...c, pct: valid > 0 ? +((c.votes / valid) * 100).toFixed(2) : 0 }))
        .sort((a, b) => b.votes - a.votes)
        .map((c, idx) => ({ name: c.name, party: c.party, votes: c.votes, pct: c.pct, rank: idx + 1 }));
      cands.forEach((c) => { if (c.rank <= E.winners) c.won = true; });
      races.push({
        sg_typecode: '2', scope: 'district', sido: sidoName, district: d.district,
        electors: d.electors, voters: d.voters, valid_votes: valid, invalid_votes: d.invalid,
        candidates: cands,
      });
    }
    process.stderr.write(`${n}대 ${sidoName}(${cc}): ${parsed.length} 선거구\n`);
  }

  // 기존 archive와 병합: _meta + 비(tc2 district) race 보존, tc2 district 교체
  const path = join(RES, `${E.id}.json`);
  let prev = { _meta: {}, races: [] };
  if (existsSync(path)) prev = JSON.parse(readFileSync(path, 'utf-8'));
  const keep = (prev.races || []).filter((r) => !(r.scope === 'district' && String(r.sg_typecode) === '2'));
  const meta = { ...(prev._meta || {}), source: 'nec-vccp09-개표현황', _district_source: 'info.nec.go.kr VCCP09 (전체 후보)' };
  delete meta._note;
  writeFileSync(path, JSON.stringify({ _meta: meta, races: [...keep, ...races] }, null, 1));
  const ncand = races.reduce((s, r) => s + r.candidates.length, 0);
  const nwon = races.reduce((s, r) => s + r.candidates.filter((c) => c.won).length, 0);
  process.stderr.write(`✓ ${n}대: ${races.length} 선거구, 후보 ${ncand}, 당선 ${nwon} → ${E.id}.json\n`);
}

await b.close();
