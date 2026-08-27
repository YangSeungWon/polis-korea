"""data/view_registry.json thumb_priority → assets/election-timeline.js 생성 블록.

목록 썸네일·og 대표 카드·타임라인 호버 미니맵이 **같은 그림을 고르게** 하는 표다.
사본을 각자 들고 있으면 어긋난다 — 실제로 election-timeline.js가 'dorling' 폴백을
손으로 들고 있었고, 뷰 이름이 바뀌면 실패 경로가 스스로를 display:none으로 숨겨
**조용히** 사라지는 자리였다.

⚠️ 표를 소비자 파일 **안에** 박는다. 공용 assets/view-registry.js에 두던 시절이
있었는데, 타임라인이 도는 index.html만 그 파일을 안 불러서 거기서만
window.VIEW_THUMBS가 undefined가 됐다. 그 view-registry.js는 2026-08-27에 지웠다 —
남은 소비자가 죽은 내려받기 버튼뿐이었다(scripts/build/view_registry.py 주석 참조).

sync_satellites_js.py와 같은 방식이고, 같이 regen_check.sh의 DERIVED에 있어
멱등성 검사를 받는다.

사용:
  python3 scripts/build/sync_view_thumbs_js.py
"""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "data/view_registry.json"
TL_PATH = ROOT / "assets/election-timeline.js"
START = "// === VIEW_THUMBS auto-generated ==="
END = "// === /VIEW_THUMBS ==="


def render(d: dict) -> str:
    body = ",\n".join(
        "    %s: [%s]" % (k, ", ".join(f"'{x}'" for x in v))
        for k, v in d["thumb_priority"].items())
    return "\n".join([
        START,
        "  // data/view_registry.json thumb_priority에서 sync. 손으로 고치지 말 것 —",
        "  // scripts/build/sync_view_thumbs_js.py 재실행으로 갱신.",
        "  // 목록 썸네일·og 카드·타임라인 호버가 같은 그림을 고르게 하는 표다.",
        "  const VIEW_THUMBS = {",
        body + ",",
        "  };",
        END,
    ])


def main() -> None:
    d = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    js = TL_PATH.read_text(encoding="utf-8")
    pat = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if not pat.search(js):
        raise SystemExit(f"{TL_PATH}: 마커 {START} 를 못 찾았다")
    TL_PATH.write_text(pat.sub(lambda _: render(d), js), encoding="utf-8")
    print(f"→ {TL_PATH.relative_to(ROOT)}: 썸네일 우선순위 {len(d['thumb_priority'])}종")


if __name__ == "__main__":
    main()
