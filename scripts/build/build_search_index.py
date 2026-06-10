"""Archive 통합 검색 인덱스 — 모든 회차의 당선인·지역·정당을 한 파일로.

Output: assets/search-index.json
포맷:
  {
    "_meta": {"built_at": "...", "n": ...},
    "items": [
      {"n": "이재명", "p": "더불어민주당", "y": 2022, "e": "20th-pres-2022",
       "r": "대선", "d": "전국", "w": 0},   # name/party/year/election_id/round/district/won
      ...
    ]
  }
"""
from __future__ import annotations
import json
import glob
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets/search-index.json"

# election_id → 카테고리 라벨
def round_label(eid: str) -> str:
    if 'pres' in eid: return '대선'
    if 'general' in eid: return '총선'
    if 'local' in eid: return '지선'
    if eid.startswith('byelection'): return '재보궐'
    return '기타'


def main():
    # 인물 인덱스 로드 — (eid, name) → assembly_id·dob 룩업.
    person_lookup = {}
    pi_path = ROOT / "assets/person-index.json"
    if pi_path.exists():
        pi = json.loads(pi_path.read_text(encoding="utf-8"))
        for p in pi.get('persons', []):
            aid = p.get('assembly_id')
            dob = p.get('dob')
            if not aid or not dob:
                continue
            for r in p.get('races', []):
                person_lookup[(r['eid'], p['name'])] = {'aid': aid, 'dob': dob}

    items = []
    seen = set()

    for f in sorted(glob.glob(str(ROOT / 'data/results/*.json'))):
        name = Path(f).name
        if '.sigungu' in name: continue
        eid = name.replace('.json', '')
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        meta = d.get('_meta', {})
        date = meta.get('election_date', '')
        year = int(date[:4]) if date and date[:4].isdigit() else None
        rlbl = round_label(eid)

        # tc별 canonical scope — 그 외 scope의 race는 인덱스에서 제외.
        # 대선 시도별·총선 시도 summary 같은 보조 row가 1위 entries로
        # 잡혀 한 사람 한 회차가 17건이 되는 문제 방지.
        CANON_SCOPE = {
            '1': 'nation',     # 대선 전국
            '2': 'district',   # 총선 지역구
            '3': 'sido',       # 지선 광역단체장
            '4': 'sigungu',    # 지선 기초단체장
        }

        for race in d.get('races', []):
            tc = race.get('sg_typecode', '')
            scope = race.get('scope', '')
            expected = CANON_SCOPE.get(tc)
            if expected and scope != expected:
                continue
            sido = race.get('sido', '')
            sigungu = race.get('sigungu', '') or ''
            district = race.get('district', '') or ''
            place = sigungu or district or sido or '전국'
            cands = race.get('candidates', [])
            if not cands: continue
            # 당선자 전원 + 알려진 정치인(person-index 매칭)의 낙선 인덱싱.
            #   낙선 이력도 검색 결과에 보이게(인물 카드에 당선+낙선). 무명 낙선자는 제외(인덱스 비대 방지).
            sorted_cs = sorted(cands, key=lambda c: c.get('rank') or 99)
            for c in sorted_cs:
                nm = (c.get('name') or '').strip()
                if not nm: continue
                won = bool(c.get('won')) or c.get('rank') == 1
                pl = person_lookup.get((eid, nm))
                if not won and not pl:
                    continue
                key = (eid, scope, sido, sigungu, district, tc, nm)
                if key in seen: continue
                seen.add(key)
                entry = {
                    'n': nm,
                    'p': (c.get('party') or '').strip(),
                    'y': year,
                    'e': eid,
                    'r': rlbl,
                    'd': f"{sido} {place}".strip() if sido and place != sido else place,
                    'tc': tc,
                    'pct': c.get('pct'),
                    'w': 1 if won else 0,
                }
                if pl:
                    entry['aid'] = pl['aid']
                    entry['dob'] = pl['dob']
                items.append(entry)

    items.sort(key=lambda x: (x.get('y') or 0, x['e']), reverse=True)
    out = {
        '_meta': {'n': len(items), 'description': '회차별 당선인 + 정치인 낙선 이력 통합 검색 인덱스'},
        'items': items,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    sz = OUT.stat().st_size
    print(f"→ {OUT.relative_to(ROOT)}: {len(items)} items, {sz/1024:.1f} KB")


if __name__ == '__main__':
    main()
