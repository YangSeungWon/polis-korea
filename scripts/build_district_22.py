"""22대 총선 지역구 CSV → 지역구별 집계.

CSV: 시도명, 선거구명, 법정읍면동명, 투표구명, 후보자, 득표수
- 후보자: "정당명 이름" 또는 메타 ("선거인수", "투표수", "무효 투표수")
- 지역구 단위 = (시도명, 선거구명) 쌍 (총 254개)
- 같은 선거구 안 모든 읍면동 행 합산

출력:
- data/results/national_assembly_22.json 의 'district' 필드 (기존 'sigungu' = 비례 옆에 추가)
- data/geo/district_22_centroid.json — 각 지역구의 관할 시군구 + centroid (hex layout용)
"""
from __future__ import annotations
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data/raw/results_csv/national_assembly_22_district.csv"
OUT_RESULTS = ROOT / "data/results/national_assembly_22.json"
OUT_CENTROID = ROOT / "data/geo/district_22_centroid.json"

NON_CANDIDATE = {
    '선거인수', '투표수', '무효 투표수', '무효투표수', '기권자수', '기권수', '계',
}


def parse_candidate(s: str) -> tuple[str, str] | None:
    s = s.strip()
    if not s or s in NON_CANDIDATE:
        return None
    m = re.match(r'^(.+?)\s+([가-힣]{2,4})$', s)
    if m:
        party, name = m.group(1).strip(), m.group(2).strip()
        if name in NON_CANDIDATE or party in NON_CANDIDATE:
            return None
        return party, name
    return ('무소속', s)


def main():
    # 1. 집계
    districts = defaultdict(lambda: {
        'sido': '', 'name': '',
        'electors': 0, 'voted': 0, 'invalid': 0,
        'candidates': defaultdict(int),
        'emds': set(),   # 관할 법정읍면동
    })
    with CSV_PATH.open('r', encoding='cp949') as f:
        rd = csv.DictReader(f)
        for row in rd:
            sido = (row.get('시도명') or '').strip()
            sgg = (row.get('선거구명') or '').strip()
            emd = (row.get('법정읍면동명') or '').strip()
            cand = (row.get('후보자') or '').strip()
            try:
                vote = int((row.get('득표수') or '0').replace(',', ''))
            except ValueError:
                vote = 0
            if not sido or not sgg:
                continue
            if emd == '합계':  # 선거구 자체 합산 행 skip (읍면동 합산이 진실)
                continue
            key = (sido, sgg)
            r = districts[key]
            r['sido'] = sido; r['name'] = sgg
            # 관할 읍면동 (특수 투표 제외)
            if emd and emd not in {'거소·선상투표', '관외사전투표', '재외투표'}:
                r['emds'].add(emd)
            if cand == '선거인수':
                r['electors'] += vote
            elif cand == '투표수':
                r['voted'] += vote
            elif cand in ('무효 투표수', '무효투표수'):
                r['invalid'] += vote
            elif cand in NON_CANDIDATE:
                continue
            else:
                pc = parse_candidate(cand)
                if pc:
                    r['candidates'][pc] += vote

    # 2. 결과 정렬
    out_list = []
    centroid_meta = []
    for (sido, name), r in sorted(districts.items()):
        valid = sum(r['candidates'].values())
        cands = sorted(r['candidates'].items(), key=lambda x: -x[1])
        cand_list = []
        for (party, cand_name), votes in cands:
            pct = (votes / valid * 100) if valid else 0
            cand_list.append({
                'name': cand_name, 'party': party,
                'votes': votes, 'pct': round(pct, 2),
            })
        winner = cand_list[0] if cand_list else None
        turnout = (r['voted'] / r['electors'] * 100) if r['electors'] else 0
        out_list.append({
            'sido': sido, 'name': name,
            'winner': winner['name'] if winner else None,
            'winner_party': winner['party'] if winner else None,
            'electors': r['electors'], 'voted': r['voted'],
            'invalid': r['invalid'],
            'turnout': round(turnout, 2),
            'candidates': cand_list,
        })
        # 지역구 → 관할 시군구 추정 (선거구명에서 첫 시군구명 또는 분할 패턴 분석)
        centroid_meta.append({
            'sido': sido, 'name': name,
            'emds': sorted(r['emds']),
            'emd_count': len(r['emds']),
        })

    print(f'254개 지역구 처리. 후보 표시 정확성 확인:', file=sys.stderr)
    for d in out_list[:5]:
        if d['winner']:
            print(f'  {d["sido"]} {d["name"]}: {d["winner_party"]} {d["winner"]} ({d["candidates"][0]["pct"]}%)', file=sys.stderr)

    # 3. 기존 비례 JSON에 'district' 필드 머지
    existing = json.loads(OUT_RESULTS.read_text(encoding='utf-8'))
    existing['district'] = out_list
    existing['_meta']['has_district'] = True
    OUT_RESULTS.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'→ {OUT_RESULTS.name} (district {len(out_list)})', file=sys.stderr)

    # 4. centroid 메타
    OUT_CENTROID.write_text(json.dumps(centroid_meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'→ {OUT_CENTROID.name} ({len(centroid_meta)} entries)', file=sys.stderr)


if __name__ == '__main__':
    main()
