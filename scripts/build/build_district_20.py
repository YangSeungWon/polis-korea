"""20대 총선 지역구 (2016) — WWolf TSV → 지역구별 집계.

CSV (long format):
  광역 시군구 읍면동 투표소 후보자당 ID 선거구 선거인수 투표수 유효투표수 무효표 기권수
  후보자 후보자득표 득표율 총득표 순위 차순위득표차 권역 선거인수.비례 유효투표수.비례
  비례득표 교차투표 지역구

지역구별 합산 (광역+선거구) — 후보자별 득표 합산.
출력: data/results/national_assembly_20.json 의 'district' 필드 추가.
"""
from __future__ import annotations
import csv
import json
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
URL = "https://raw.githubusercontent.com/WWolf/korea-election/master/dataset/2016general_cand_full.tsv"
RAW = ROOT / "data/raw/wwolf/2016general_cand_full.tsv"
OUT_RESULTS = ROOT / "data/results/national_assembly_20.json"
OUT_CENTROID = ROOT / "data/geo/district_20_centroid.json"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _geo import SIDO_NAME_CANONICAL  # noqa


def main():
    if not RAW.exists() or RAW.stat().st_size < 100000:
        RAW.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(URL, headers={'User-Agent':'Mozilla/5.0'})
        RAW.write_bytes(urllib.request.urlopen(req, timeout=60).read())

    # 지역구별 (시도, 선거구) 집계
    districts = defaultdict(lambda: {
        'sido': '', 'name': '',
        'cand_votes': defaultdict(int),  # (party, name) → votes
        'cand_total': defaultdict(int),  # (party, name) → 총득표 (가장 큰 값 keep)
        'emds': set(),
        'electors_emd': 0,
        'voted_emd': 0,
    })
    with RAW.open('r', encoding='utf-8') as f:
        rd = csv.DictReader(f, delimiter='\t')
        for row in rd:
            sido = (row.get('광역') or '').strip()
            sgg = (row.get('시군구') or '').strip()
            sgn = (row.get('선거구') or '').strip()
            emd = (row.get('읍면동') or '').strip()
            cand = (row.get('후보자') or '').strip()
            party = (row.get('후보자당') or '').strip()
            # 시도 alias 정규화
            sido = SIDO_NAME_CANONICAL.get(sido, sido)
            try:
                votes = int((row.get('후보자득표') or '0').replace(',', ''))
                total = int((row.get('총득표') or '0').replace(',', ''))
            except ValueError:
                votes = 0; total = 0
            if not sido or not sgn:
                continue
            key = (sido, sgn)
            r = districts[key]
            r['sido'] = sido; r['name'] = sgn
            if emd and emd not in {'합계', '계'}:
                r['emds'].add(emd)
            if cand and cand not in {'합계'}:
                r['cand_votes'][(party, cand)] += votes
                r['cand_total'][(party, cand)] = max(r['cand_total'][(party, cand)], total)

    # 검증: cand_votes (summed by emd) vs cand_total (precomputed total) — 가능하면 일치
    # cand_total이 더 신뢰 (정확). 그걸 사용.
    out_list = []
    centroid_meta = []
    for (sido, name), r in sorted(districts.items()):
        cands = sorted(r['cand_total'].items(), key=lambda x: -x[1])
        valid = sum(v for _, v in cands)
        cand_list = []
        for (party, cand_name), votes in cands:
            pct = (votes / valid * 100) if valid else 0
            cand_list.append({
                'name': cand_name, 'party': party,
                'votes': votes, 'pct': round(pct, 2),
            })
        winner = cand_list[0] if cand_list else None
        out_list.append({
            'sido': sido, 'name': name,
            'winner': winner['name'] if winner else None,
            'winner_party': winner['party'] if winner else None,
            'electors': 0, 'voted': 0,  # WWolf 데이터에 정확한 지역구 합계 없음
            'invalid': 0, 'turnout': 0,
            'candidates': cand_list,
        })
        centroid_meta.append({
            'sido': sido, 'name': name,
            'emds': sorted(r['emds']),
            'emd_count': len(r['emds']),
        })

    print(f'20대 지역구: {len(out_list)}개', file=sys.stderr)
    for d in out_list[:5]:
        if d['winner']:
            print(f'  {d["sido"]} {d["name"]}: {d["winner_party"]} {d["winner"]} ({d["candidates"][0]["pct"]}%)', file=sys.stderr)

    # 기존 national_assembly_20.json (비례)에 머지
    existing = json.loads(OUT_RESULTS.read_text(encoding='utf-8'))
    existing['district'] = out_list
    existing['_meta']['has_district'] = True
    OUT_RESULTS.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'→ {OUT_RESULTS.name} (district 머지)', file=sys.stderr)

    OUT_CENTROID.write_text(json.dumps(centroid_meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'→ {OUT_CENTROID.name}', file=sys.stderr)


if __name__ == '__main__':
    main()
