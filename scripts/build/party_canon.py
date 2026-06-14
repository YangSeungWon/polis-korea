"""정당명 정규화 — data/parties/registry.json 단일 출처.

같은 정당이 회차별로 약칭/정식명 혼용된 케이스를 정식명으로 dedup
(예: 자민련 → 자유민주연합). 동음이의(민정당1963·공화당1997·신민당1967·
민주당 다수)는 registry의 aliases에서 제외돼 있어 병합되지 않는다.

소비: build_timeline.py, build_old_assembly.py, build_old_local.py,
build_person_pages.py 등 정당명을 출력하는 모든 빌드 스크립트.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = ROOT / "data/parties/registry.json"

_registry = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))

# 별칭(약칭/이형) → 정식명
PARTY_ALIAS: dict[str, str] = {
    alias: name
    for name, info in _registry["parties"].items()
    for alias in info.get("aliases", [])
}

# 정식명 → 등록약칭 (표시 토글용; 동음이의 가능 → dedup엔 사용 금지)
PARTY_ABBR: dict[str, str] = {
    name: info["abbr"]
    for name, info in _registry["parties"].items()
    if info.get("abbr")
}


def canon_party(p):
    """정당명 정규화 — 별칭을 정식명으로. None/빈값은 그대로."""
    if not p:
        return p
    return PARTY_ALIAS.get(p, p)


# "민주당" 동명 정당 — 선거일 기준 시기별 정당으로 분기(이름 재사용 11회+).
# 상한(YYYY-MM) 미만이면 해당 시기. None=그 구간엔 분기 안 함(그대로 '민주당').
_MINJOO_ERAS = [
    ("1991-01", "민주당(1955)"),       # ~1990: 장면·박순천 민주당계(1955·63·67 재편 포함)
    ("1995-09", "민주당(1991)"),       # 1991~1995.08: 이기택·DJ (DJ 탈당 전)
    ("1997-11", "통합민주당(1995)"),   # 1995.09~1997: 이기택·조순 (DJ 탈당 후)
    ("2005-05", None),                  # 1998~2005.04: 데이터 없음
    ("2008-02", "민주당(2005)"),       # 2005~2008.01: 새천년민주당 후신(호남계)
    ("2011-12", "통합민주당"),         # 2008~2011: 손학규(2008 통합민주당, 명칭 '민주당')
    ("2014-03", "민주통합당"),         # 2011.12~2014: 민주통합당(2013 '민주당' 개명)
]


def disambiguate_minjoo(date):
    """'민주당' → 선거일(YYYY-MM-DD/YYYY) 기준 시기별 정당. 분기 불가면 None."""
    ym = (date or "")[:7]
    if not ym:
        return None
    for upper, name in _MINJOO_ERAS:
        if ym < upper:
            return name
    return "더불어민주당"   # 2014-03 이후


def disambiguate_party(name, date):
    """정당명 정규화 + '민주당' 날짜 분기. date 없으면 별칭 정규화만."""
    if name == "민주당":
        return disambiguate_minjoo(date) or name
    return canon_party(name)
