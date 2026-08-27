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


# ── v2: (host × mode) ────────────────────────────────────────────────────────
# v1(classify·view_meta)은 옛 키가 아직 디스크·페이지에 있어 남겨 둔다. 대개명이
# 끝나면 지운다. 두 벌이 공존하는 동안 **v1은 읽기 전용**이다 — 새 코드는 v2만 쓴다.
HOSTS: list[dict] = _D.get("hosts") or []
MODES: list[dict] = _D.get("modes") or []

_ENC2MODE = {e: m["mode"] for m in MODES for e in m["enc"]}
_MODE_LABEL = {m["mode"]: m["label"] for m in MODES}
_HOST = {h["token"]: h for h in HOSTS}

KEY_RE = __import__("re").compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def mode_of(enc: str) -> str | None:
    """토글 버튼의 data-enc → 정규화 모드. 모르는 enc는 None(호출부가 시끄럽게 굴 것)."""
    return _ENC2MODE.get((enc or "").strip())


def mode_label(mode: str) -> str:
    return _MODE_LABEL.get(mode, mode)


def host_label(token: str) -> str:
    h = _HOST.get(token)
    return h["label"] if h else token


def key_for(host: str, mode: str | None) -> str:
    """(host, mode) → 뷰 키. 토글 없는 단일 뷰는 host 그대로."""
    return f"{host}-{mode}" if mode else host


def parse_key(key: str) -> tuple[str, str | None] | None:
    """뷰 키 → (host, mode). 레지스트리에 없는 조합이면 None.

    ⚠️ 접두사 모호성을 막는다. host 'sgg'와 'sggturn'이 같이 있으므로 'sgg-turnout-geo'가
    (sgg, turnout-geo)인지 (sggturn, ...)인지 헷갈릴 수 있다 — **긴 토큰을 먼저** 맞춰
    한 가지로만 읽히게 한다. 검사(C1)가 이 성질을 따로 확인한다.
    """
    if key in _HOST:
        return key, None
    for token in sorted(_HOST, key=len, reverse=True):
        if key.startswith(token + "-"):
            mode = key[len(token) + 1:]
            return (token, mode) if mode in _MODE_LABEL else None
    return None


def hosts_for(kind: str) -> list[str]:
    return [h["token"] for h in HOSTS if kind in (h.get("kinds") or [])]


def hosts_for_office(office: str) -> set[str] | None:
    """직위 슬러그 → 그 직위 페이지가 걸 host 토큰들. 직위가 없으면 None(=전부).

    실재하는 직위 페이지는 셋뿐이다(governor·mayor·superintendent). 모르는 직위는
    None을 준다 — 옛 HIST_VIEW_PREFER의 .get(off, None)과 같은 뜻으로, 새 직위
    페이지가 생겼을 때 그림이 통째로 사라지는 것보다 전부 거는 쪽이 덜 나쁘다.
    """
    if not office:
        return None
    got = {h["token"] for h in HOSTS if office in (h.get("offices") or [])}
    return got or None


def page_rank(host: str, mode: str | None) -> tuple[int, int]:
    """본문 그림의 읽기 순서. 레지스트리에 적힌 순서 그대로다.

    파일명 알파벳 순으로 두면 district-geo가 district-hex보다 먼저 나오는 식으로,
    '지도'가 '균등'보다 앞서는 뒤집힌 차례가 된다. 순서도 표가 정한다.
    """
    toks = [h["token"] for h in HOSTS]
    hi = toks.index(host) if host in toks else len(toks)
    modes = (_HOST.get(host, {}).get("page") or [])
    mi = modes.index(mode) if mode in modes else len(modes)
    return hi, mi


def is_page_view(host: str, mode: str | None) -> bool:
    """본문 <figure>로 낼 뷰인가. 전부 내면 총선 history가 8→13장이 된다."""
    h = _HOST.get(host)
    return bool(h) and mode in (h.get("page") or [])
