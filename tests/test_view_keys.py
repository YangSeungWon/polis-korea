"""뷰 키 규칙이 스스로 성립하는가 (레지스트리 v2).

**막는 사고.** 뷰 키는 og/maps/{회차}/{키}.png 파일명이자 <figure id>이자 이미지
sitemap 항목이다. 규칙이 흔들리면 그림·글·색인이 서로 다른 것을 가리킨다.

지금 검사하는 것은 **표 자체의 성질**이다 — 사용 중인 키가 규칙에 맞는가(C1)는
대개명이 끝난 뒤에 붙는다. 그때까지 디스크엔 옛 키(dorling·sgg-prop…)가 있다.

가장 조용한 함정은 **키 충돌**이다. host에도 mode에도 하이픈이 있어서
(metro-prop, grid)와 (metro, prop-grid)가 둘 다 'metro-prop-grid'가 된다 —
파일 하나가 두 뷰가 되고, 나중에 만든 쪽이 앞의 것을 조용히 덮는다.
(sgg, sggturn) 같은 접두사 쌍은 하이픈 구분자 덕에 안전하다: 'sggturn-geo'와
'sgg-turn-geo'는 다른 문자열이다. 위험한 건 접두사가 아니라 **하이픈 경계**다.
parse_key가 긴 토큰을 먼저 맞추고, 여기서 전량 왕복으로 고정한다.

실행: .venv/bin/python tests/test_view_keys.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "build"))
import view_registry as V  # noqa: E402

fails: list[str] = []


def bad(msg: str) -> None:
    fails.append(msg)
    print(f"  ✗ {msg}")


def check_tables() -> None:
    """host·mode 표가 유일하고 파일명으로 쓸 수 있는 모양인가."""
    if not V.HOSTS or not V.MODES:
        bad("레지스트리 v2 표(hosts·modes)가 비었다")
        return
    seen: set[str] = set()
    for h in V.HOSTS:
        tok = h.get("token", "")
        if tok in seen:
            bad(f"host 토큰 중복: {tok}")
        seen.add(tok)
        if not V.KEY_RE.match(tok):
            bad(f"host 토큰이 파일명으로 못 쓸 모양: {tok!r} (소문자·숫자·하이픈만)")
        if not h.get("label"):
            bad(f"host {tok}: 한글 라벨 없음")
        if not h.get("kinds"):
            bad(f"host {tok}: 어느 선거 계열인지 없음")
        for m in h.get("page") or []:
            if m is not None and m not in {x["mode"] for x in V.MODES}:
                bad(f"host {tok}: page에 모르는 모드 {m!r}")
    encs: set[str] = set()
    for m in V.MODES:
        mode = m.get("mode", "")
        if not V.KEY_RE.match(mode):
            bad(f"mode가 파일명으로 못 쓸 모양: {mode!r}")
        if not m.get("label"):
            bad(f"mode {mode}: 한글 라벨 없음")
        for e in m.get("enc") or []:
            if e in encs:
                bad(f"enc 중복 — 한 토글 값이 두 모드로 접힌다: {e!r}")
            encs.add(e)
    # 한글 enc(단색·격자)는 여기서 라틴으로 바뀌어야 한다. 파일명에 닿으면 퍼센트
    # 인코딩이 되어 sed·grep·sitemap 대조가 전부 어긋난다(2026-08 실제 사고).
    for e in encs:
        if not e.isascii() and V.mode_of(e) is None:
            bad(f"한글 enc {e!r}가 어느 모드로도 안 접힌다")


def check_roundtrip() -> None:
    """key_for → parse_key가 제자리로 돌아오고, 접두사로 헷갈리지 않는가."""
    keys: dict[str, tuple[str, str | None]] = {}
    for h in V.HOSTS:
        tok = h["token"]
        for m in [None] + [x["mode"] for x in V.MODES]:
            key = V.key_for(tok, m)
            got = V.parse_key(key)
            if got != (tok, m):
                bad(f"왕복 실패: ({tok}, {m}) → {key!r} → {got}")
            if key in keys and keys[key] != (tok, m):
                bad(f"키 충돌 — {key!r}가 {keys[key]}와 {(tok, m)} 둘 다다")
            keys[key] = (tok, m)
    print(f"  키 {len(keys)}가지 왕복 확인 (host {len(V.HOSTS)} × mode {len(V.MODES)}+단일)")


def check_labels() -> None:
    """라벨을 물었을 때 슬러그가 되돌아오지 않는가.

    옛 view_meta()는 모르는 키를 **그대로 라벨로 돌려줬다** — 그래서 'sgg-prop'
    같은 슬러그가 한글 캡션 자리에 찍혀도 아무도 안 잡았다.
    """
    for h in V.HOSTS:
        if V.host_label(h["token"]) == h["token"]:
            bad(f"host {h['token']}: 라벨이 토큰 그대로다")
    for m in V.MODES:
        if V.mode_label(m["mode"]) == m["mode"]:
            bad(f"mode {m['mode']}: 라벨이 토큰 그대로다")
    if V.mode_of("없는enc") is not None:
        bad("모르는 enc에 None이 아닌 답을 준다")
    if V.parse_key("모르는키") is not None:
        bad("모르는 키에 None이 아닌 답을 준다")


def main() -> int:
    print("뷰 키 규칙 (레지스트리 v2)")
    check_tables()
    check_roundtrip()
    check_labels()
    if fails:
        print(f"\n실패 {len(fails)}건")
        return 1
    print("통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
