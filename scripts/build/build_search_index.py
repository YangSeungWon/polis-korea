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

        for race in d.get('races', []):
            tc = race.get('sg_typecode', '')
            scope = race.get('scope', '')
            sido = race.get('sido', '')
            sigungu = race.get('sigungu', '') or ''
            district = race.get('district', '') or ''
            place = sigungu or district or sido or '전국'
            cands = race.get('candidates', [])
            if not cands: continue
            # 당선자(rank=1)만 인덱싱 — 후보 전체는 너무 큼
            sorted_cs = sorted(cands, key=lambda c: c.get('rank') or 99)
            top = sorted_cs[0]
            nm = (top.get('name') or '').strip()
            party = (top.get('party') or '').strip()
            if not nm: continue
            key = (eid, scope, sido, sigungu, district, tc, nm)
            if key in seen: continue
            seen.add(key)
            items.append({
                'n': nm,
                'p': party,
                'y': year,
                'e': eid,
                'r': rlbl,
                'd': f"{sido} {place}".strip() if sido and place != sido else place,
                'tc': tc,
                'pct': top.get('pct'),
            })

    items.sort(key=lambda x: (x.get('y') or 0, x['e']), reverse=True)
    out = {
        '_meta': {'n': len(items), 'description': '회차별 당선인 통합 검색 인덱스'},
        'items': items,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    sz = OUT.stat().st_size
    print(f"→ {OUT.relative_to(ROOT)}: {len(items)} items, {sz/1024:.1f} KB")


if __name__ == '__main__':
    main()
