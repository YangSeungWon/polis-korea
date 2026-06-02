"""OhmyNews 22대 GeoJSON SGG_Code ↔ hex/results district name 매핑 생성.

OhmyNews는 SGG (예: '수원갑'), 우리 hex/results는 풀네임 (예: '수원시갑').
sigungus list 기반으로 매칭하고 결과를 data/geo/district_22_geojson_map.json에 저장.

매칭 규칙:
1. sigungus 같은 시 prefix 공유 → 시명 short + suffix(갑/을…)
2. sigungus 단일 → 시·구·군 정규식 정리 (양구군의 양구는 보존)
3. sigungus 복수 다른 시 → 각 시군구 short concat + suffix
"""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SIDO_MAP = {
    '서울특별시': '서울', '부산광역시': '부산', '대구광역시': '대구', '인천광역시': '인천',
    '광주광역시': '광주', '대전광역시': '대전', '울산광역시': '울산', '세종특별자치시': '세종',
    '경기도': '경기', '강원특별자치도': '강원', '충청북도': '충북', '충청남도': '충남',
    '전북특별자치도': '전북', '전라남도': '전남', '경상북도': '경북', '경상남도': '경남',
    '제주특별자치도': '제주',
}


def strip_one(s):
    return re.sub(r'(특별자치시|특별자치도|광역시|특별시|도)$', '', re.sub(r'(시|군|구)$', '', s))


def common_city_prefix(sigungus):
    """sigungus 모두 같은 시 prefix면 그 prefix(시명 포함) 반환."""
    if len(sigungus) < 2:
        return None
    first = sigungus[0]
    for end in range(2, len(first) + 1):
        prefix = first[:end]
        if prefix.endswith('시') and all(sg.startswith(prefix) for sg in sigungus):
            return prefix
    return None


def short_name(hex_entry):
    sigungus = hex_entry.get('sigungus', [])
    name = hex_entry['name']
    suffix_m = re.search(r'([갑을병정무])$', name)
    suffix = suffix_m.group(1) if suffix_m else ''

    if not sigungus:
        return strip_one(name) + suffix

    if len(sigungus) == 1:
        sg = sigungus[0]
        # 양구·연구·구리 등 도시명 안 '구'는 보존 — 끝의 행정 suffix만 떼기
        sg_short = re.sub(r'시(?=[가-힣])', '', sg)
        sg_short = re.sub(r'(구|군|시)$', '', sg_short)
        return sg_short + suffix

    common = common_city_prefix(sigungus)
    if common:
        return strip_one(common) + suffix
    # 다른 시군 concat
    return ''.join(strip_one(sg) for sg in sigungus) + suffix


def main():
    hex22 = json.loads((ROOT / 'data/geo/district_hex_22.json').read_text())
    oh = json.loads((ROOT / 'data/geo/district_22_geojson.json').read_text())

    oh_by = {}
    for f in oh['features']:
        p = f['properties']
        oh_by[(p['SIDO'], p['SGG'])] = p['SGG_Code']

    # OhmyNews 명명 불규칙 (광역시 단음절 구 일부만 보존 등) — 수동 매핑
    MANUAL = {
        ('경기', '시흥시갑'): '시흥갑',
        ('경기', '시흥시을'): '시흥을',
        ('경북', '영천시청도군'): '영천청도',
        ('경북', '포항시남구울릉군'): '포항남울릉',
        ('경북', '포항시북구'): '포항북구',
        ('대구', '동구군위군갑'): '동구군위갑',
        ('대구', '동구군위군을'): '동구군위을',
        ('부산', '중구영도구'): '중구영도',
        ('서울', '중구성동구갑'): '중구성동갑',
        ('서울', '중구성동구을'): '중구성동을',
        ('인천', '동구미추홀구갑'): '동구미추홀갑',
        ('인천', '동구미추홀구을'): '동구미추홀을',
        ('인천', '중구강화군옹진군'): '중구강화옹진',
    }

    def candidates(x):
        sigungus = x.get('sigungus', [])
        name = x['name']
        suffix_m = re.search(r'([갑을병정무])$', name)
        suffix = suffix_m.group(1) if suffix_m else ''
        base = name[:-1] if suffix else name
        cands = [short_name(x)]
        # 광역시·특별시: hex name에서 갑/을 떼고 그대로 (구 보존)
        if x['sido'].endswith('광역시') or x['sido'].endswith('특별시'):
            cands.append(name)  # 북구갑 그대로
            cands.append(base)   # 북구 (갑/을 뗀 단순)
        # 도 직속 시: 시 보존
        if sigungus:
            no_si_strip = ''.join(re.sub(r'(군|구)$', '', sg) for sg in sigungus)
            cands.append(no_si_strip + suffix)
        # name 그대로 (갑/을 포함)
        cands.append(name)
        # name (갑/을 떼고)
        cands.append(base)
        return cands

    mapping = {}
    unmatched = []
    for x in hex22:
        sido_short = SIDO_MAP.get(x['sido'], x['sido'])
        found = None
        man = MANUAL.get((sido_short, x['name']))
        if man:
            key = (sido_short, man)
            if key in oh_by:
                found = oh_by[key]
        if not found:
            for short in candidates(x):
                key = (sido_short, short)
                if key in oh_by:
                    found = oh_by[key]
                    break
        if found:
            mapping[f"{x['sido']}|{x['name']}"] = found
        else:
            unmatched.append((x['name'], sido_short, candidates(x)))

    print(f'매칭: {len(mapping)}/{len(hex22)}')
    if unmatched:
        print(f'unmatched {len(unmatched)}:')
        for n, sd, cands in unmatched[:20]:
            print(f'  {n} → ({sd}, 시도: {cands})')

    out = {
        '_meta': {
            'description': 'hex/results district key "{sido}|{name}" → OhmyNews SGG_Code (NEC 7자리). 22대 chloropleth 매칭용. 광역시 일반구 중복명("북구을" 등) 때문에 sido 포함 key.',
            'source_hex': 'data/geo/district_hex_22.json',
            'source_geojson': 'data/geo/district_22_geojson.json (© OhmyNews, MIT)',
            'matched': len(mapping),
            'total': len(hex22),
            'unmatched': [n for n, _, _ in unmatched],
            'note': 'unmatched 일부는 OhmyNews 명명 불규칙(광역시 일부 구만 보존)으로 자동 매칭 실패. polygon 렌더는 가능하나 chloropleth 색칠 안 됨.',
        },
        'name_to_sgg_code': mapping,
    }
    (ROOT / 'data/geo/district_22_geojson_map.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(f'\nwritten: data/geo/district_22_geojson_map.json')


if __name__ == '__main__':
    main()
