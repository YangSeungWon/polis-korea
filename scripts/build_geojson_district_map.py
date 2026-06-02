"""OhmyNews 21·22대 GeoJSON SGG_Code ↔ hex/results district name 매핑 생성.

OhmyNews 22대는 SIDO+SGG short (예: '수원갑'), 21대는 SGG_2 풀명 (예: '경기도 고양시갑').
sigungus list 기반으로 매칭하고 결과를 data/geo/district_{n}_geojson_map.json에 저장.
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


# 시도 옛 이름 (21대 OhmyNews 시점) ↔ 현재 이름
SIDO_OLD = {
    '강원특별자치도': '강원도',
    '전북특별자치도': '전라북도',
}


def build_22(hex22, oh22, oh_by):
    """22대 매핑 — SIDO+SGG short 매칭."""

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
            unmatched.append((x['name'], sido_short))
    return mapping, unmatched


def build_21(hex21, oh21):
    """21대 매핑 — OhmyNews 21대는 SGG_2 = '{시도} {name}' 풀명 사용. 직접 매칭."""
    oh_by_sgg2 = {f['properties']['SGG_2']: f['properties']['SGG_Code'] for f in oh21['features']}
    mapping = {}
    unmatched = []
    for x in hex21:
        # 시도 옛 이름으로 변환 (강원특별자치도 → 강원도)
        old_sido = SIDO_OLD.get(x['sido'], x['sido'])
        key = f"{old_sido} {x['name']}"
        if key in oh_by_sgg2:
            mapping[f"{x['sido']}|{x['name']}"] = oh_by_sgg2[key]
        else:
            unmatched.append((x['name'], x['sido']))
    return mapping, unmatched


def main():
    # 22대
    hex22 = json.loads((ROOT / 'data/geo/district_hex_22.json').read_text())
    oh22 = json.loads((ROOT / 'data/geo/district_22_geojson.json').read_text())
    oh22_by = {(f['properties']['SIDO'], f['properties']['SGG']): f['properties']['SGG_Code'] for f in oh22['features']}
    m22, u22 = build_22(hex22, oh22, oh22_by)
    print(f'[22대] 매칭: {len(m22)}/{len(hex22)}, unmatched: {len(u22)}')

    out22 = {
        '_meta': {
            'description': 'hex key "{sido}|{name}" → OhmyNews SGG_Code (NEC 7자리). 22대 chloropleth.',
            'source_geojson': 'data/geo/district_22_geojson.json (© OhmyNews, MIT)',
            'matched': len(m22), 'total': len(hex22),
            'unmatched': [n for n, _ in u22],
        },
        'name_to_sgg_code': m22,
    }
    (ROOT / 'data/geo/district_22_geojson_map.json').write_text(
        json.dumps(out22, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )

    # 21대
    hex21 = json.loads((ROOT / 'data/geo/district_hex_21.json').read_text())
    oh21 = json.loads((ROOT / 'data/geo/district_21_geojson.json').read_text())
    m21, u21 = build_21(hex21, oh21)
    print(f'[21대] 매칭: {len(m21)}/{len(hex21)}, unmatched: {len(u21)}')
    for n, s in u21[:10]:
        print(f'  {s} | {n}')

    out21 = {
        '_meta': {
            'description': 'hex key "{sido}|{name}" → OhmyNews SGG_Code (NEC 7자리). 21대 chloropleth.',
            'source_geojson': 'data/geo/district_21_geojson.json (© OhmyNews, MIT)',
            'matched': len(m21), 'total': len(hex21),
            'unmatched': [n for n, _ in u21],
        },
        'name_to_sgg_code': m21,
    }
    (ROOT / 'data/geo/district_21_geojson_map.json').write_text(
        json.dumps(out21, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print('\nwritten: data/geo/district_22_geojson_map.json, data/geo/district_21_geojson_map.json')


if __name__ == '__main__':
    main()
