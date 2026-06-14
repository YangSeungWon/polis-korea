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
    if 'byelection' in eid: return '재보궐'
    return '기타'


def main():
    # 인물 인덱스 로드 — (eid, name) → assembly_id·dob 룩업.
    person_lookup = {}
    multi_race_names = set()   # 2회+ 출마자 — 의원 당선 없어도(황교안 등) 낙선 이력 검색 포함
    pi_path = ROOT / "assets/person-index.json"
    if pi_path.exists():
        pi = json.loads(pi_path.read_text(encoding="utf-8"))
        for p in pi.get('persons', []):
            if len(p.get('races', [])) >= 2:
                multi_race_names.add(p['name'])
            aid = p.get('assembly_id')
            dob = p.get('dob')
            if not aid or not dob:
                continue
            for r in p.get('races', []):
                # 키에 tc·지역 포함 — 같은 선거 같은 이름 동명이인(강원지사 최문순 vs 화천군수 최문순) 구분.
                person_lookup[(r['eid'], p['name'], str(r.get('tc')), r.get('place', ''))] = {'aid': aid, 'dob': dob}

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

        # 기초장(tc4)·의원 등 sigungu-level race는 별도 청크 파일에 — 같이 읽는다.
        # (안 읽으면 5~8회·1~4회 기초단체장 당선자가 검색에서 통째로 누락됨.)
        races = list(d.get('races', []))
        sgg_f = Path(f).with_suffix('').as_posix() + '.sigungu.json'
        if Path(sgg_f).exists():
            try:
                races += json.load(open(sgg_f, encoding='utf-8')).get('races', [])
            except Exception:
                pass

        # tc별 canonical scope — 이 5종(대통령·국회의원·광역장·기초장·교육감)만 인덱싱.
        #   의원(5·6)은 수천 명 minor, 비례(7·8·9)는 '이름'이 정당명이라 인물검색 부적합 → 제외.
        #   보조 scope row(시도별 breakdown 등)도 canonical scope만 통과시켜 중복 방지.
        CANON_SCOPE = {
            '1': 'nation',     # 대선 전국
            '2': 'district',   # 총선 지역구
            '3': 'sido',       # 지선 광역단체장
            '4': 'sigungu',    # 지선 기초단체장
            '11': 'sido',      # 지선 교육감
        }

        for race in races:
            tc = race.get('sg_typecode', '')
            scope = race.get('scope', '')
            expected = CANON_SCOPE.get(tc)
            if not expected or scope != expected:
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
                pl = person_lookup.get((eid, nm, str(tc), place))
                # 낙선 포함 조건: 의원ID 보유 or 2회+ 출마하며 이 선거 득표 5%↑(군소 난립 제외)
                if not won and not pl and not (nm in multi_race_names and (c.get('pct') or 0) >= 5):
                    continue
                key = (eid, scope, sido, sigungu, district, tc, nm)
                if key in seen: continue
                seen.add(key)
                entry = {
                    'n': nm,
                    'p': (c.get('party') or '').strip(),
                    'y': year,
                    'dt': date,   # 정렬용(같은 해 대선 3월·재보궐 6월 구분) — 정렬 후 제거.
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

    # 실제 선거일 내림차순(최신 먼저) — 같은 해는 월까지 구분. 정렬 후 dt 제거(용량).
    items.sort(key=lambda x: (x.get('dt') or str(x.get('y') or ''), x['e']), reverse=True)
    for it in items:
        it.pop('dt', None)
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
