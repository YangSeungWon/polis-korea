"""data/view_registry.json → assets/view-registry.js의 VIEW_REGISTRY 블록 동기화.

지도 뷰 표는 Python(캡처·공유 페이지 생성)과 JS(내려받기·공유 링크) 양쪽에서 쓴다.
사본을 각자 들고 있다가 어긋났으므로(key 'result'가 '시군구 결과' vs '시군구 1위')
JSON을 단일 출처로 두고 JS 쪽은 이 스크립트가 만든 const 블록을 쓴다.

sync_satellites_js.py와 같은 방식이다 — 그 스크립트가 이미 regen_check.sh의 DERIVED에
있어 멱등성 검사를 받고 있고, 여기도 같은 자리에 넣는다.

assets/view-registry.js 안에 아래 마커 사이를 자동 갱신:

  // === VIEW_REGISTRY auto-generated ===
  ...
  // === /VIEW_REGISTRY ===

사용:
  python3 scripts/build/sync_view_registry_js.py
"""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "data/view_registry.json"
JS_PATH = ROOT / "assets/view-registry.js"

START = "// === VIEW_REGISTRY auto-generated ==="
END = "// === /VIEW_REGISTRY ==="

# 타임라인 호버 미니맵은 index.html에서도 도는데, 그 한 쪽만 view-registry.js를
# 안 부른다. 우선순위 표를 거기 두면 index에서 window.VIEW_THUMBS가 undefined가 되어
# 미니맵이 조용히 사라진다 — 그래서 **소비자 파일 안에** 생성 블록을 박는다.
TL_PATH = ROOT / "assets/election-timeline.js"
TL_START = "// === VIEW_THUMBS auto-generated ==="
TL_END = "// === /VIEW_THUMBS ==="


def render_thumbs(d: dict) -> str:
    body = ",\n".join(
        "    %s: [%s]" % (k, ", ".join(f"'{x}'" for x in v))
        for k, v in d["thumb_priority"].items())
    return "\n".join([
        TL_START,
        "  // data/view_registry.json thumb_priority에서 sync. 손으로 고치지 말 것 —",
        "  // scripts/build/sync_view_registry_js.py 재실행으로 갱신.",
        "  // 목록 썸네일·og 카드·타임라인 호버가 같은 그림을 고르게 하는 표다.",
        "  const VIEW_THUMBS = {",
        body + ",",
        "  };",
        TL_END,
    ])


def sync_block(path: Path, start: str, end: str, block: str) -> str:
    js = path.read_text(encoding="utf-8")
    pat = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if not pat.search(js):
        raise SystemExit(f"{path}: 마커 {start} 를 못 찾았다")
    path.write_text(pat.sub(lambda _: block, js), encoding="utf-8")
    return "갱신"


def render_block(d: dict) -> str:
    lines = [
        START,
        "// data/view_registry.json에서 sync. 손으로 수정하지 말 것 —",
        "// scripts/build/sync_view_registry_js.py 재실행으로 갱신.",
        "// ⚠️ 배열 순서가 load-bearing: 분류는 첫 substring 매칭이 이긴다.",
        "//    한 SVG가 여러 클래스를 함께 갖는다(시군구 결과 = council-hex-svg result-map).",
        "//    근거는 JSON 각 항목의 note에 있다.",
        "const VIEW_REGISTRY = [",
    ]
    for v in d["views"]:
        cls = ", ".join(f"'{c}'" for c in v["classes"])
        lines.append(
            f"  {{ key: '{v['key']}', classes: [{cls}], "
            f"label: '{v['label']}', fname: '{v['fname']}' }},")
    lines += [
        "];",
        "// SVG class 문자열 → 뷰 키. archive 뷰가 아니면(빈 키) '' 를 준다.",
        "function viewKeyOf(cls) {",
        "  const s = cls || '';",
        "  for (const v of VIEW_REGISTRY) if (v.classes.some(c => s.includes(c))) return v.key;",
        "  return null;",
        "}",
        "function viewMetaOf(key) {",
        "  return VIEW_REGISTRY.find(v => v.key === key) || null;",
        "}",
        "window.VIEW_REGISTRY = VIEW_REGISTRY;",
        "window.viewKeyOf = viewKeyOf;",
        "window.viewMetaOf = viewMetaOf;",
        END,
    ]
    return "\n".join(lines)


def main() -> None:
    d = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    block = render_block(d)
    if JS_PATH.exists():
        js = JS_PATH.read_text(encoding="utf-8")
        pat = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
        new = pat.sub(block, js) if pat.search(js) else js.rstrip() + "\n\n" + block + "\n"
        action = "갱신"
    else:
        new = ("// 지도 뷰 표 — 생성 파일. 편집 금지.\n"
               "// 정본: data/view_registry.json · 생성: scripts/build/sync_view_registry_js.py\n"
               "(function () {\n  'use strict';\n\n" + block + "\n})();\n")
        action = "신규 생성"
    JS_PATH.write_text(new, encoding="utf-8")
    sync_block(TL_PATH, TL_START, TL_END, render_thumbs(d))
    print(f"→ {JS_PATH.relative_to(ROOT)} {action}: 뷰 {len(d['views'])}개 · "
          f"{TL_PATH.relative_to(ROOT)} 썸네일 우선순위 {len(d['thumb_priority'])}종")


if __name__ == "__main__":
    main()
