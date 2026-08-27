"""뷰 키 규칙이 스스로 성립하는가 (레지스트리 v2).

**막는 사고.** 뷰 키는 og/maps/{회차}/{키}.png 파일명이자 <figure id>이자 이미지
sitemap 항목이다. 규칙이 흔들리면 그림·글·색인이 서로 다른 것을 가리킨다.

두 가지를 본다. (1) 표 자체의 성질 — 유일한가, 파일명으로 쓸 수 있는가, 왕복하는가.
(2) **실제로 쓰이는 키가 전부 규칙에 맞는가** — 디스크의 PNG, 매니페스트, 페이지의
<figure id>, 대표 뷰 우선순위까지.

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
import result_tables as _rt  # noqa: E402
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
        # 회차가 아닌 화면(지지율 추이·계보도·홈)은 선거 계열에 안 매인다.
        if not h.get("kinds") and "static" not in (h.get("pages") or []):
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


def check_keys_in_use() -> None:
    """디스크·매니페스트·페이지가 쓰는 키가 전부 레지스트리 규칙으로 읽히는가.

    옛 view_meta()는 모르는 키를 **그대로 라벨로 돌려줬다** — 'sgg-prop' 같은 슬러그가
    한글 캡션 자리에 찍혀도 아무 검사도 안 잡았다. 여기서 잡는다.
    """
    import json
    import re
    bad_keys: dict[str, list[str]] = {}

    def note(where: str, key: str) -> None:
        if V.parse_key(key) is None:
            bad_keys.setdefault(key, []).append(where)

    n_png = 0
    for d in ("maps", "polls", "static"):   # 결과 지도 · 여론조사 지도 · 회차 아닌 화면
        root = ROOT / "og" / d
        if not root.is_dir():
            continue
        for f in root.rglob("*.png"):
            n_png += 1
            note(f"디스크 og/{d}/{f.parent.name}", f.stem)
    mf = ROOT / "data" / "map_manifest.json"
    n_view = 0
    if mf.is_file():
        els = json.loads(mf.read_text(encoding="utf-8")).get("elections") or {}
        for eid, e in els.items():
            for v in e.get("views") or []:
                n_view += 1
                note(f"매니페스트 {eid}", v)
            if e.get("unlabeled"):
                bad("매니페스트 %s: 무엇인지 모르는 그림 %s장 — 캡처 기록이 없다"
                    % (eid, len(e["unlabeled"])))
    for k in V.PRIMARY_ORDER:
        note("primary_order", k)
    for kind, ks in V.THUMB_PRIORITY.items():
        for k in ks:
            note(f"thumb_priority[{kind}]", k)
    n_fig = 0
    pat = re.compile(r'<figure class="map-fig" id="([^"]+)"')
    for d in ("archive", "history", "polls"):
        for f in (ROOT / d).rglob("index.html"):
            for m in pat.finditer(f.read_text(encoding="utf-8")):
                n_fig += 1
                note(f"{d}/{f.parent.name}", m.group(1))
    for key, wheres in sorted(bad_keys.items()):
        bad(f"규칙에 없는 키 {key!r} — {wheres[0]}{' 외 %d곳' % (len(wheres) - 1) if len(wheres) > 1 else ''}")
    print(f"  쓰이는 키 확인: PNG {n_png}장 · 매니페스트 뷰 {n_view} · <figure> {n_fig}")


def check_captions() -> None:
    """페이지의 figcaption이 **캡처가 적어 둔 글**에서 나왔는가.

    막는 사고: 캡션을 손으로 쓰기 시작하면 그림과 어긋난다. 옛 view_meta()는 모르는
    키에 키 자신을 라벨로 돌려줘서 'sgg-prop' 같은 슬러그가 한글 캡션 자리에 찍혀도
    아무 검사도 안 잡았다. 여기서는 매니페스트의 title·label로 캡션을 **다시 만들어**
    페이지의 것과 글자 그대로 맞는지 본다 — 한쪽만 고치면 실패한다.
    """
    import html
    import json
    import re
    mf = ROOT / "data" / "map_manifest.json"
    if not mf.is_file():
        bad("매니페스트가 없다")
        return
    els = json.loads(mf.read_text(encoding="utf-8")).get("elections") or {}
    # 여론조사 지도는 다른 디렉터리·다른 기록이다(og/polls/, poll_map_captures.json).
    pc = ROOT / "data" / "poll_map_captures.json"
    polls_caps = {}
    if pc.is_file():
        polls_caps = json.loads(pc.read_text(encoding="utf-8")).get("slugs") or {}
    # history는 archive slug 하나에 대응한다 — 어느 회차의 그림인지는 <img src>가 말한다.
    pat = re.compile(r'<figure class="map-fig" id="([^"]+)">'
                     r'<img src="/og/(maps|polls)/([^/]+)/[^"]+"[^>]*>'
                     r'<figcaption>([^<]*)</figcaption>')
    n = 0
    seen_bad = 0
    for d in ("archive", "history", "polls"):
        for f in sorted((ROOT / d).rglob("index.html")):
            for key, kind, eid, cap in pat.findall(f.read_text(encoding="utf-8")):
                n += 1
                m = (polls_caps.get(eid, {}).get(key) if kind == "polls"
                     else ((els.get(eid) or {}).get("meta") or {}).get(key))
                if not m:
                    bad(f"{f.parent.name}: {key}의 캡처 기록이 없는데 그림을 걸었다")
                    seen_bad += 1
                    continue
                want = _rt.caption(key, m)
                if html.unescape(cap) != want:
                    bad(f"{f.parent.name}/{key}: 캡션 {cap!r} ≠ 기록 {want!r}")
                    seen_bad += 1
                if seen_bad > 5:
                    return
    print(f"  캡션 {n}개가 캡처 기록과 일치")


def check_capture_health() -> None:
    """캡처가 건너뛴 뷰가 있거나, 서로 다른 키가 같은 그림이 되지 않았는가.

    옛 모호함(한 키에 여러 그림)은 열거식 캡처에서 구조적으로 불가능하다 — 키가
    (host, mode)로 확정되고 각 조합을 정확히 한 번 찍는다. 그래서 **반대**를 잰다:
    두 키가 같은 픽셀이면 토글 클릭이 조용히 안 먹어 앞 모드의 그림이 다음 키로
    저장된 것이다. 이름만 바꾸고 그림은 안 바뀌는 실패라 눈으로는 거의 안 보인다.
    """
    import json
    d = {}
    for name, tag in (("capture_ambiguity.json", "결과"),
                      ("poll_capture_ambiguity.json", "여론조사"),
                      ("static_capture_ambiguity.json", "정적화면")):
        f = ROOT / "data" / name
        if not f.is_file():
            bad(f"{tag} 캡처 기록이 없다 — build_og_maps를 안 돌렸다")
            continue
        for k, v in (json.loads(f.read_text(encoding="utf-8")).get("slugs") or {}).items():
            d[f"{tag}/{k}"] = v
    dup = {s: v["same_image"] for s, v in d.items() if v.get("same_image")}
    prob = {s: v["problems"] for s, v in d.items() if v.get("problems")}
    for s, v in sorted(dup.items()):
        for ks in v.values():
            bad(f"{s}: 서로 다른 키가 같은 그림이다 — {', '.join(ks)}")
    for s, v in sorted(prob.items()):
        for m in v:
            bad(f"{s}: 캡처가 건너뛴 뷰 — {m}")
    print(f"  캡처 {len(d)}회차 · 같은 그림 {len(dup)} · 건너뜀 {len(prob)}")


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
    check_keys_in_use()
    check_captions()
    check_capture_health()
    if fails:
        print(f"\n실패 {len(fails)}건")
        return 1
    print("통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
