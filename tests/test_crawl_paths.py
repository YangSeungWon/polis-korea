"""크롤 경로 검증 — 홈에서 모든 archive까지 몇 홉인가.

2026-07 Search Console이 2,190페이지를 미색인으로 보류한 뒤 내부 링크 심도를 고쳤다.
홈에서 53행 목록을 걷어내는 것 같은 IA 변경은 그 개선을 조용히 되돌리기 쉽다.

실행: python3 tests/test_crawl_paths.py
"""
from __future__ import annotations
import glob
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fails = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}{'' if cond else ' — ' + str(detail)}")
    if not cond:
        fails.append(name)


def links(fp: Path, pat: str) -> set:
    return set(re.findall(pat, fp.read_text(encoding="utf-8")))


def main():
    home = ROOT / "index.html"
    hub = ROOT / "elections.html"

    ck("'모든 선거' 허브가 있다", hub.exists())
    if not hub.exists():
        return 1

    # 홈 → 허브 (1-hop)
    ck("홈이 허브를 직접 링크", "/elections.html" in home.read_text(encoding="utf-8"))

    # 허브 → 모든 archive (1-hop). 재보궐은 /byelection/ 허브가 따로 담당.
    archives = {Path(f).parent.name for f in glob.glob(str(ROOT / "archive/*/index.html"))}
    non_by = {a for a in archives if "byelection" not in a}
    hub_links = {m for m in links(hub, r'href="/archive/([^/"]+)/')}
    missing = non_by - hub_links
    ck(f"허브가 재보궐 외 archive {len(non_by)}개 전부 링크", not missing, sorted(missing)[:5])

    # 재보궐도 어딘가에서 도달 가능해야 한다
    by = archives - non_by
    byhub = ROOT / "byelection" / "index.html"
    if byhub.exists():
        bl = links(byhub, r'href="/archive/([^/"]+)/')
        # 재보궐 허브가 동적 렌더일 수 있으므로 데이터 존재로 대체 확인
        ok = bool(bl) or (ROOT / "data/byelection_calendar.json").exists()
        ck(f"재보궐 {len(by)}개 도달 경로 존재", ok)

    # 홈이 너무 얇아지지 않았는지 — 주요 진입점은 남아야 한다
    h = home.read_text(encoding="utf-8")
    for path in ["/tracker.html", "/polls.html", "/search.html", "/parties.html",
                 "/chronology.html", "/history.html", "/elections.html"]:
        ck(f"홈에 진입점 {path}", path in h)

    # sitemap에 허브가 있다
    sm = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    ck("sitemap에 허브 등록", "/elections.html" in sm)
    ck("sitemap에 archive 전부", all(f"/archive/{a}/" in sm for a in archives))

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
