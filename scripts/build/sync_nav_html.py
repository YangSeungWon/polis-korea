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
# 데이터 종류가 아니라 **사용자가 묻는 대상**으로 나눈다. 예전 메뉴(여론조사·역대 결과·
# 역대 판세·정당사…)는 만든 사람에겐 서로 다른 데이터셋이지만 사용자에겐 그렇지 않다.
#
# 여론은 두 축에 걸친다 — 데이터 원천이 같아도 목적이 다르다.
#   상시(국정평가·정당지지·차기주자) → '지금'
#   회차별(후보 지지·조사 vs 실제·출구조사) → '선거'
#
# 각 축은 실제 랜딩이 있어야 한다. 옛 페이지들은 URL 그대로 살아 있고 랜딩에서 링크된다
# (/elections.html이 역대 결과·역대 판세·여론조사·재보궐을 안내).
MENU = [
    ("지금", "/tracker.html", "now"),
    ("선거", "/elections.html", "elections"),
    ("인물·정당", "/parties.html", "people"),
    ("역사", "/chronology.html", "history"),
    # '검색'은 nav 링크 대신 헤더 우측 검색창(nav.js가 .hdr-meta에 주입)으로 대체.
]

# 파일 경로 → 활성 메뉴 키 매핑. 매치 안되면 is-current 없음 (archive 등).
def menu_for_path(rel_path: str) -> str | None:
    """파일 경로 → 활성 메뉴 키. 4축 재편 후에도 옛 경로가 어느 축에 속하는지 알아야
    is-current가 붙는다 — 예전 URL로 들어온 사용자도 자기 위치를 안다."""
    p = "/" + rel_path.lstrip("/")
    if p == "/index.html" or p == "/":
        return "home"
    # 회차별 여론조사는 '선거'에 속한다(상시 추세는 아래 tracker → '지금').
    if p == "/polls.html" or p.startswith("/polls/") or any(
            p.startswith(x) for x in ("/governor/", "/mayor/", "/superintendent/")):
        return "elections"
    # /party/index.html은 정당사가 아니라 '정당지지' 여론조사 페이지(build_static.py 생성)다.
    # /party/{정당명}/ 프로필만 정당사. 한 prefix로 뭉뚱그리면 여론조사 페이지에 '정당사'가
    # 활성으로 찍힌다.
    if p == "/party/index.html":
        return "elections"
    if p == "/parties.html" or p.startswith("/party/") or p.startswith("/person/") \
            or p == "/person.html" or p == "/search.html":
        return "people"
    if p == "/byelection.html" or p.startswith("/byelection/") or p.startswith("/archive/byelection-"):
        return "elections"
    if p == "/tracker.html":
        return "now"
    if p.startswith("/region/"):
        return "elections"
    if p in ("/history.html", "/elections.html", "/timeline.html") \
            or p.startswith("/archive/") or p.startswith("/history/"):
        return "elections"

    if p == "/chronology.html":
        return "history"

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
        if key == "elections":  # '선거' 직후 — 임박/방금끝난 선거 urgent 뱃지 자리
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
    ap.add_argument("--check", action="store_true",
                    help="쓰지 않고 검사만 — 어긋난 페이지가 있으면 exit 1 (CI 가드용)")
    args = ap.parse_args()
    if args.check:
        args.dry = True
    htmls = sorted(ROOT.glob("*.html")) + sorted(ROOT.glob("*/index.html")) + sorted(ROOT.glob("archive/*/index.html")) + sorted(ROOT.glob("about/*/index.html")) + sorted(ROOT.glob("party/*/index.html")) + sorted(ROOT.glob("person/*/index.html")) + sorted(ROOT.glob("region/*/index.html"))
    counts = {"changed": 0, "same": 0, "skip": 0}
    for p in htmls:
        if "node_modules" in str(p) or "/.git/" in str(p):
            continue
        r = process(p, args.dry)
        counts[r] += 1
        if r == "changed":
            print(f"  {p.relative_to(ROOT)}")
    print(f"\n변경 {counts['changed']} · 동일 {counts['same']} · 스킵 {counts['skip']}")
    if args.check and counts["changed"]:
        # 생성기가 nav 정본(render_nav·menu_for_path)을 쓰지 않고 사본을 박았다는 신호.
        # 사본은 메뉴가 바뀔 때마다 조용히 어긋나므로, 여기서 잡아 되돌아가게 한다.
        print(
            f"\n✗ nav가 정본과 어긋난 페이지 {counts['changed']}개.\n"
            "  원인은 대개 페이지 생성기가 nav HTML 사본을 템플릿에 박은 것이다.\n"
            "  생성기에서 sync_nav_html의 render_nav(menu_for_path(rel))를 쓰도록 고칠 것.\n"
            "  (정본 자체를 바꾼 경우라면 생성기를 다시 돌려 페이지를 갱신하고 커밋)",
            file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
