"""지도 뷰 레지스트리 — data/view_registry.json의 단일 진입점.

같은 표가 세 벌 있었다:

    scripts/build/build_og_maps.py     VIEW_DEFS      (class, key, label, desc)
    scripts/build/build_share_pages.py VIEW_LABEL     (key → label)
    assets/svg-export.js               VIEW_DEFS      (class, key, fname)

그리고 이미 어긋나 있었다 — key `result`가 og_maps에선 "시군구 결과", share에선
"시군구 1위"였다. 같은 뷰를 두 이름으로 부르고 있었고 아무도 몰랐다. 표가 하나면
어긋날 자리가 없다.

⚠️ **순서가 load-bearing이다.** 분류는 첫 substring 매칭이 이긴다. 한 SVG가 여러
클래스를 함께 갖기 때문이다(시군구 결과 = "council-hex-svg result-map"). 근거는
JSON 각 항목의 note에 적혀 있다 — 줄을 옮기기 전에 읽을 것.

사용:
    from view_registry import classify, view_meta, VIEW_DEFS, PRIMARY_ORDER
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data" / "view_registry.json"

_D = json.loads(REGISTRY.read_text(encoding="utf-8"))

VIEWS: list[dict] = _D["views"]
PRIMARY_ORDER: list[str] = _D["primary_order"]
THUMB_PRIORITY: dict[str, list[str]] = _D["thumb_priority"]

# 옛 build_og_maps.VIEW_DEFS 모양 — (class, key, label, desc). 호출부를 안 고치고
# 갈아끼우기 위한 어댑터다. 빈 키(hex-pane)는 archive 뷰가 아니라 뺀다.
VIEW_DEFS: list[tuple[str, str, str, str]] = [
    (v["classes"][0], v["key"], v["label"], v["desc"]) for v in VIEWS if v["key"]
]


def classify(class_attr: str) -> str | None:
    """SVG class 문자열 → 뷰 키. 못 찾으면 None.

    빈 키(hex-pane)는 None을 준다 — '분류는 됐지만 archive 뷰가 아니다'와
    '아예 모르는 svg'를 호출부가 구분할 이유가 지금은 없다.
    """
    cls = class_attr or ""
    for v in VIEWS:
        if any(c in cls for c in v["classes"]):
            return v["key"] or None
    return None


def view_meta(key: str) -> tuple[str, str]:
    """뷰 키 → (label, desc). 모르는 키는 키 자신을 라벨로 돌려준다."""
    for v in VIEWS:
        if v["key"] == key:
            return v["label"], v["desc"]
    return key, ""


def label_of(key: str) -> str:
    return view_meta(key)[0]


def fname_of(key: str) -> str:
    for v in VIEWS:
        if v["key"] == key:
            return v["fname"]
    return key


def primary_for(kind: str, available: list[str]) -> str | None:
    """선거 종류·보유 뷰 → 대표 뷰 하나. 목록 썸네일과 og 카드가 같은 걸 고르게 한다."""
    for k in THUMB_PRIORITY.get(kind, []) + PRIMARY_ORDER:
        if k in available:
            return k
    return available[0] if available else None
