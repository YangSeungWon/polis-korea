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
    print(f"→ {JS_PATH.relative_to(ROOT)} {action}: 뷰 {len(d['views'])}개")


if __name__ == "__main__":
    main()
