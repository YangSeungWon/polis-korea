"""회차가 아닌 화면의 그림을 페이지 본문에 넣는다 (og/static/ → STATIC_FIG 블록).

지지율 추이·정당 계보도·홈 판세는 **이 사이트에서만 볼 수 있는 그림**인데 2026-08까지
JS 안에만 있었다 — 검색엔진도 공유 카드도 못 봤다(tracker.html 정적 그림 0장).
archive·history·polls에 한 것을 여기에도 한다.

라벨은 캡처가 적어 둔 것을 쓴다(data/static_map_captures.json). 섹션 제목이 곧
캡션이라 글과 그림이 한 출처에서 나온다.

⚠️ 그림이 없으면 **마커만 남긴다**. 없는 것을 만들지 않는다(docs/absence.md).

사용: python3 scripts/build/sync_static_figures.py
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import result_tables as _rt  # noqa: E402
import view_registry as _vr  # noqa: E402

CAPS = ROOT / "data" / "static_map_captures.json"
START = "<!-- STATIC_FIG_START — scripts/build/sync_static_figures.py 자동 갱신. 손수정 X. -->"
END = "<!-- STATIC_FIG_END -->"
PAT = re.compile(re.escape("<!-- STATIC_FIG_START") + r"[\s\S]*?" + re.escape(END))

# 화면 이름 → (페이지 파일, 그림 위 제목)
PAGES = {
    "tracker": ("tracker.html", "지표 그림"),
    "parties": ("parties.html", "정당 계보"),
    "home": ("index.html", "최근 회차 판세"),
    "byelection": ("byelection.html", "재보궐 지역"),
}


def main() -> int:
    try:
        caps = json.loads(CAPS.read_text(encoding="utf-8"))["slugs"]
    except Exception:                                            # noqa: BLE001
        caps = {}
    n = 0
    for name, (fname, heading) in PAGES.items():
        page = ROOT / fname
        if not page.is_file():
            continue
        html = page.read_text(encoding="utf-8")
        if not PAT.search(html):
            print(f"  ! {fname}에 STATIC_FIG 마커가 없다", file=sys.stderr)
            continue
        figs = []
        for key, m in sorted((caps.get(name) or {}).items(),
                             key=lambda kv: _vr.page_rank(kv[1].get("host") or "",
                                                          kv[1].get("mode"))):
            f = ROOT / "og" / "static" / name / f"{key}.png"
            wh = _rt.png_size(f) if f.is_file() else None
            if wh:
                figs.append(_rt.fig(name, key, m, wh[0], wh[1], "", base="/og/static"))
        body = (f'\n  <section class="ar-section" id="static-figs">\n'
                f'    <h2 class="ar-section-title">{heading}</h2>\n'
                f'    <div class="map-fig-grid">{"".join(figs)}</div>\n'
                f'  </section>\n  ') if figs else ""
        new = PAT.sub(lambda _: START + body + END, html, count=1)
        if new != html:
            page.write_text(new, encoding="utf-8")
        n += len(figs)
    print(f"→ 정적 화면 그림 {n}장")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
