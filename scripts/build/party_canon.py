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
