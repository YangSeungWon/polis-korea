"""nav 헤더를 모든 HTML에 동기화 — single source of truth.

구조:
  <!-- NAV_START — scripts/build/sync_nav_html.py 자동 갱신. 손수정 X. -->
  <a href="/" class="hdr-link">홈</a>
  <span data-nav-urgent></span>
  <a href="/polls.html" class="hdr-link">여론조사</a>
  ...
  <!-- NAV_END -->

is-current는 파일 경로 → menu 매핑으로 자동 (예: /governor/ → '여론조사').
urgent slot (<span data-nav-urgent>)은 assets/nav.js가 client-side 채움.

사용:
  .venv/bin/python scripts/build/sync_nav_html.py [--dry]
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 캐노니컬 메뉴 — 회차 번호·시간 의존 표현 금지 (장기 안정).
MENU = [
    # 홈은 좌측 polis 로고가 이미 / 링크 — nav 중복 제거 (모바일 폭 절약).
    ("여론조사", "/polls.html", "polls"),
    ("재·보궐", "/byelection/", "byelection"),
    ("지지율 추이", "/tracker.html", "tracker"),
    ("역대 결과", "/history.html", "history"),
    ("타임라인", "/timeline.html", "timeline"),
    ("근현대사", "/chronology.html", "chronology"),
    # '검색'은 nav 링크 대신 헤더 우측 검색창(nav.js가 .hdr-meta에 주입)으로 대체.
]

# 파일 경로 → 활성 메뉴 키 매핑. 매치 안되면 is-current 없음 (archive 등).
def menu_for_path(rel_path: str) -> str | None:
    p = "/" + rel_path.lstrip("/")
    if p == "/index.html" or p == "/":
        return "home"
    if p == "/polls.html" or any(p.startswith(x) for x in ("/governor/", "/mayor/", "/party/", "/superintendent/")):
        return "polls"
    if p == "/byelection.html" or p.startswith("/byelection/"):
        return "byelection"
    if p == "/tracker.html":
        return "tracker"
    if p == "/history.html" or p.startswith("/archive/"):
        return "history"
    if p == "/timeline.html":
        return "timeline"
    if p == "/chronology.html":
        return "chronology"
    if p == "/search.html":
        return "search"
    return None


MARKER_RE = re.compile(
    r"(<!--\s*NAV_START[^>]*-->)(.*?)(<!--\s*NAV_END\s*-->)",
    re.DOTALL,
)
# 기존(마커 없는) hdr-nav 블록 — 첫 동기화에 자동 마커 삽입용.
LEGACY_NAV_RE = re.compile(
    r'(<nav class="hdr-nav">)(.*?)(</nav>)',
    re.DOTALL,
)


def render_nav(current_key: str | None) -> str:
    # NAV_START 줄은 prefix 없이 — MARKER_RE가 줄 앞 들여쓰기를 보존하므로, 여기 prefix를
    # 두면 매 실행마다 누적돼 비멱등이 됨. 들여쓰기는 페이지의 기존 NAV_START 위치를 따름.
    lines = ['<!-- NAV_START — scripts/build/sync_nav_html.py 자동 갱신. 손수정 X. -->']
    for i, (label, href, key) in enumerate(MENU):
        cls = "hdr-link is-current" if key == current_key else "hdr-link"
        lines.append(f'  <a href="{href}" class="{cls}">{label}</a>')
        if i == 0:  # 홈 직후 urgent slot
            lines.append('  <span data-nav-urgent></span>')
    lines.append('  <!-- NAV_END -->')
    return "\n".join(lines)


def process(path: Path, dry: bool) -> str:
    rel = str(path.relative_to(ROOT))
    text = path.read_text(encoding="utf-8")
    key = menu_for_path(rel)
    nav_block = render_nav(key)
    if MARKER_RE.search(text):
        new = MARKER_RE.sub(lambda m: nav_block, text)
    elif LEGACY_NAV_RE.search(text):
        # 첫 마이그레이션 — <nav class="hdr-nav"> 안에 마커 삽입.
        new = LEGACY_NAV_RE.sub(lambda m: f"{m.group(1)}\n{nav_block}\n{m.group(3)}", text)
    else:
        return "skip"
    if new == text:
        return "same"
    if not dry:
        path.write_text(new, encoding="utf-8")
    return "changed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    htmls = sorted(ROOT.glob("*.html")) + sorted(ROOT.glob("*/index.html")) + sorted(ROOT.glob("archive/*/index.html")) + sorted(ROOT.glob("about/*/index.html"))
    counts = {"changed": 0, "same": 0, "skip": 0}
    for p in htmls:
        if "node_modules" in str(p) or "/.git/" in str(p):
            continue
        r = process(p, args.dry)
        counts[r] += 1
        if r == "changed":
            print(f"  {p.relative_to(ROOT)}")
    print(f"\n변경 {counts['changed']} · 동일 {counts['same']} · 스킵 {counts['skip']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
