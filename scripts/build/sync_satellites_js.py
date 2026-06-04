"""data/parties/satellites.json → assets/parties.js의 SATELLITE_TO_MAIN 블록 동기화.

위성정당 매핑은 JS·Python 양쪽에서 쓰여서 단일 출처(JSON)에서 derive.
Python은 직접 JSON read, JS는 이 스크립트가 만든 const 블록을 사용.

assets/parties.js 안에 아래 마커 사이를 자동 갱신:

  // === SATELLITE_TO_MAIN auto-generated ===
  ... 여기는 절대 손대지 말 것 (data/parties/satellites.json + sync_satellites_js.py로) ...
  // === /SATELLITE_TO_MAIN ===

사용:
  python3 scripts/build/sync_satellites_js.py
"""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "data/parties/satellites.json"
JS_PATH = ROOT / "assets/parties.js"

START = "// === SATELLITE_TO_MAIN auto-generated ==="
END = "// === /SATELLITE_TO_MAIN ==="


def render_block(mapping: dict) -> str:
    lines = [START,
             "// data/parties/satellites.json에서 sync. 손으로 수정하지 말 것 —",
             "// scripts/build/sync_satellites_js.py 재실행으로 갱신.",
             "const SATELLITE_TO_MAIN = {"]
    for sat, main in mapping.items():
        lines.append(f"  '{sat}': '{main}',")
    lines.append("};")
    lines.append("const mainParty = (p) => SATELLITE_TO_MAIN[p] || p;")
    lines.append(END)
    return "\n".join(lines)


def main():
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    mapping = data["satellite_to_main"]
    block = render_block(mapping)

    js = JS_PATH.read_text(encoding="utf-8")
    pat = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if pat.search(js):
        new = pat.sub(block, js)
        action = "갱신"
    else:
        # 끝에 추가
        new = js.rstrip() + "\n\n" + block + "\n"
        action = "신규 추가"
    JS_PATH.write_text(new, encoding="utf-8")
    print(f"→ {JS_PATH.relative_to(ROOT)} {action}: {len(mapping)}개 매핑")


if __name__ == "__main__":
    main()
