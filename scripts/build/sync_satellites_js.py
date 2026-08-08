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


def render_block(mapping: dict, coalition: dict) -> str:
    lines = [START,
             "// data/parties/satellites.json에서 sync. 손으로 수정하지 말 것 —",
             "// scripts/build/sync_satellites_js.py 재실행으로 갱신.",
             "// 순수 위성 — 당선자가 전원 본당으로 복귀했다. 의석을 합산한다.",
             "const SATELLITE_TO_MAIN = {"]
    for sat, main in mapping.items():
        lines.append(f"  '{sat}': '{main}',")
    lines.append("};")
    lines.append("// 연합 명부 — 여러 정당 몫이 섞여 있다. **합산하지 않는다.**")
    lines.append("// 관계만 기록한다: 화면에서 어느 당의 명부였는지 밝히되 의석은 더하지 않는다.")
    lines.append("const COALITION_TO_MAIN = {")
    for sat, main in coalition.items():
        lines.append(f"  '{sat}': '{main}',")
    lines.append("};")
    lines.append("const mainParty = (p) => SATELLITE_TO_MAIN[p] || p;")
    lines.append(END)
    return "\n".join(lines)


def main():
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    mapping = data["satellite_to_main"]
    block = render_block(mapping, data.get("coalition_to_main") or {})

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
