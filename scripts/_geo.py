"""시도·시군구 코드 정규화 공통 모듈.

이 파일은 build_polls, build_sigungu_hex, eval_sigungu_hex,
build_sigungu_adjacency, build_sigungu_coastal 등에서 공통으로 import.
시도 코드, 시군구 alias, 시도 약어 한곳 관리.
"""
from __future__ import annotations

# 시군구 code 첫 2자리 → 시도 캐노니컬 이름
SIDO_CODE_TO_NAME = {
    '11': '서울특별시',
    '21': '부산광역시',
    '22': '대구광역시',
    '23': '인천광역시',
    '24': '광주광역시',
    '25': '대전광역시',
    '26': '울산광역시',
    '29': '세종특별자치시',
    '31': '경기도',
    '32': '강원특별자치도',
    '33': '충청북도',
    '34': '충청남도',
    '35': '전북특별자치도',
    '36': '전라남도',
    '37': '경상북도',
    '38': '경상남도',
    '39': '제주특별자치도',
}

# 행정구역 변경 alias — GeoJSON이 2018 baseline이라 최신 편입 반영 필요
# 군위군: 2023-07-01 경북 → 대구 편입 (코드 37310은 옛 경북 안)
SIGUNGU_SIDO_OVERRIDE = {
    '37310': '대구광역시',  # 군위군
}

# 시도 짧은 약어 (UI 라벨용)
SIDO_LABEL_SHORT = {
    '서울특별시': '서울', '부산광역시': '부산', '대구광역시': '대구',
    '인천광역시': '인천', '광주광역시': '광주', '대전광역시': '대전',
    '울산광역시': '울산', '세종특별자치시': '세종',
    '경기도': '경기', '강원특별자치도': '강원',
    '충청북도': '충북', '충청남도': '충남',
    '전북특별자치도': '전북', '전라남도': '전남',
    '경상북도': '경북', '경상남도': '경남',
    '제주특별자치도': '제주',
}

# 옛 시도명 → 현행 캐노니컬 (GeoJSON base_year=2018 매핑)
SIDO_NAME_CANONICAL = {
    '강원도': '강원특별자치도',
    '전라북도': '전북특별자치도',
}


def sigungu_to_sido(code: str) -> str:
    """시군구 코드 → 시도 캐노니컬 이름. alias 적용."""
    if not code:
        return ''
    return SIGUNGU_SIDO_OVERRIDE.get(code) or SIDO_CODE_TO_NAME.get(code[:2], '')


def canon_sido(name: str) -> str:
    """옛 시도명을 현행 캐노니컬로."""
    return SIDO_NAME_CANONICAL.get(name, name)
