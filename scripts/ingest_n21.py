"""21대 총선 비례대표 xlsx (NEC 공지 첨부) → 시군구 broadcast JSON.

소스: nec.go.kr 위원회소식 게시판 (2020-04-23, bcIdx=2083, cbIdx=1084).
파일: 제21대 국선 지역구 및 비례대표 정당별 득표수 현황.xlsx
시트: '지역구', '비례대표' — 둘 다 시도 단위 합계만.

→ 비례대표 시도 결과를 시군구 hex에 broadcast (같은 시도의 모든 시군구를 같은 색).
지역구는 의석 분포만 있어 hex 단위 매핑 불가 — 무시.
"""
from __future__ import annotations
import json
import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "wwolf"
OUT = ROOT / "data" / "results"
URL = "https://img.nec.go.kr/common/board/Download.do?bcIdx=2083&cbIdx=1084&streFileNm=BBS_202004231043297701.xlsx"

SIDO_FULL = {
    '서울':'서울특별시','부산':'부산광역시','대구':'대구광역시','인천':'인천광역시',
    '광주':'광주광역시','대전':'대전광역시','울산':'울산광역시','세종':'세종특별자치시',
    '경기':'경기도','강원':'강원특별자치도','충북':'충청북도','충남':'충청남도',
    '전북':'전북특별자치도','전남':'전라남도','경북':'경상북도','경남':'경상남도',
    '제주':'제주특별자치도',
}


def parse_votes_pct(cell):
    """'9,441,520\n(33.84)' → (9441520, 33.84). NaN/dash → (0, 0)."""
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return 0, 0.0
    s = str(cell).strip()
    m = re.search(r'([\d,]+)\s*\(([0-9.]+)\)', s)
    if m:
        return int(m.group(1).replace(',', '')), float(m.group(2))
    # 단일 숫자
    try:
        return int(s.replace(',', '')), 0.0
    except ValueError:
        return 0, 0.0


def parse_xlsx(path: Path):
    df = pd.read_excel(path, sheet_name='비례대표', header=None)
    # row 3 = 컬럼 헤더 ('시도명','선거인수','투표수','비례대표...정당별 득표수'+빈 컬럼)
    # row 4 = 정당명 (col 3부터)
    # row 5 = '합계' 행 (전국)
    # row 7~ = 시도별 행 (col 0 = '서울', '부산', ...)
    party_cols = []
    parties = []
    party_row = df.iloc[4]
    for i, v in enumerate(party_row):
        if i < 3: continue
        if pd.isna(v): continue
        p = str(v).strip().replace('\n', '')
        if p and p not in {'계', '합계', '무효투표수', '기권수'}:
            party_cols.append(i)
            parties.append(p)
    print(f'정당 {len(parties)}: {parties}', file=sys.stderr)

    # 시도별 행 추출
    sido_data = {}  # sido_short → {electors, voted, candidates: {party: (votes, pct)}}
    for i in range(5, df.shape[0]):
        row = df.iloc[i]
        name = row.iloc[0]
        if pd.isna(name): continue
        name = str(name).strip()
        if name == '합계':
            continue
        if name not in SIDO_FULL:
            continue
        electors = int(row.iloc[1]) if not pd.isna(row.iloc[1]) else 0
        voted = int(row.iloc[2]) if not pd.isna(row.iloc[2]) else 0
        cands = {}
        for j, p in zip(party_cols, parties):
            votes, pct = parse_votes_pct(row.iloc[j])
            if votes > 0:
                cands[p] = (votes, pct)
        sido_data[SIDO_FULL[name]] = {
            'electors': electors, 'voted': voted, 'candidates': cands,
        }
    return sido_data


def build():
    RAW.mkdir(parents=True, exist_ok=True)
    cache = RAW / 'n21_natl.xlsx'
    if not cache.exists() or cache.stat().st_size < 10000:
        req = urllib.request.Request(URL, headers={'User-Agent':'Mozilla/5.0'})
        cache.write_bytes(urllib.request.urlopen(req, timeout=60).read())

    sido_data = parse_xlsx(cache)
    print(f'시도 {len(sido_data)}개 파싱', file=sys.stderr)

    # hex의 시군구 목록 (broadcast 대상)
    hex_data = json.loads((ROOT / 'data/geo/sigungu_hex.json').read_text(encoding='utf-8'))

    # 시군구별 = 그 시도의 결과
    sigungu_list = []
    for h in hex_data:
        sido = h['sido']
        sd = sido_data.get(sido)
        if not sd: continue
        valid = sum(v[0] for v in sd['candidates'].values())
        turnout = (sd['voted'] / sd['electors'] * 100) if sd['electors'] else 0
        cand_list = []
        for party, (votes, pct_official) in sorted(sd['candidates'].items(), key=lambda x: -x[1][0]):
            pct = (votes / valid * 100) if valid else 0
            cand_list.append({
                'name': '비례', 'party': party,
                'votes': votes, 'pct': round(pct, 2),
            })
        sigungu_list.append({
            'sido': sido, 'name': h['name'],
            'electors': sd['electors'], 'voted': sd['voted'],
            'invalid': 0,
            'turnout': round(turnout, 2),
            'candidates': cand_list,
            'broadcast_note': '시도 단위 결과 (NEC 공지 자료)',
        })

    # national 합계
    nat_electors = sum(v['electors'] for v in sido_data.values())
    nat_voted = sum(v['voted'] for v in sido_data.values())
    nat_cands = {}
    for sd in sido_data.values():
        for p, (v, _) in sd['candidates'].items():
            nat_cands[p] = nat_cands.get(p, 0) + v
    nat_valid = sum(nat_cands.values())
    national = {
        'electors': nat_electors,
        'voted': nat_voted,
        'invalid': 0,
        'turnout': round(nat_voted / nat_electors * 100, 2) if nat_electors else 0,
        'candidates': sorted([
            {'name': '비례', 'party': p, 'votes': v,
             'pct': round(v / nat_valid * 100, 2) if nat_valid else 0}
            for p, v in nat_cands.items()
        ], key=lambda x: -x['votes']),
    }

    out = {
        '_meta': {
            'type': 'national_assembly', 'n': 21,
            'date': '2020-04-15', 'label': '21대 국회의원선거 (비례대표)',
            'source': 'nec.go.kr 위원회소식 첨부 (제21대 정당별 득표수 현황)',
            'granularity': 'sido_broadcast',
            'note': '시도 단위 NEC 공지 → 시군구 broadcast. 같은 시도의 시군구는 같은 색.',
        },
        'national': national,
        'sigungu': sigungu_list,
    }
    out_path = OUT / 'national_assembly_21.json'
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'→ {out_path.name} ({len(sigungu_list)} 시군구 broadcast, {len(national["candidates"])} 정당)', file=sys.stderr)

    # manifest 업데이트
    manifest = {'presidential': [], 'national_assembly': [], 'local': []}
    for f in OUT.glob('*_*.json'):
        m = re.match(r'(presidential|national_assembly|local)_(\d+)\.json', f.name)
        if m:
            manifest[m.group(1)].append(int(m.group(2)))
    for k in manifest:
        manifest[k] = sorted(set(manifest[k]))
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'manifest: {manifest}', file=sys.stderr)


if __name__ == '__main__':
    build()
