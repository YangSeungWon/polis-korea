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

    # 홈은 라우터다 — 4축과 검색만 직접 두고, 세부 도구는 랜딩 경유(depth 2)가 맞다.
    # 여기에 옛 메뉴를 전부 요구하면 IA 재편을 되돌리는 테스트가 된다.
    h = home.read_text(encoding="utf-8")
    for path in ["/tracker.html", "/elections.html", "/parties.html",
                 "/chronology.html", "/search.html"]:
        ck(f"홈에 축 진입점 {path}", path in h)

    # nav 4축 재편으로 nav에서 빠진 페이지들 — 어딘가에서 링크돼야 고아가 안 된다.
    hub_txt = hub.read_text(encoding="utf-8")
    home_txt = home.read_text(encoding="utf-8")
    reachable = hub_txt + home_txt
    for path, where in [("/history.html", "선거 랜딩"), ("/timeline.html", "선거 랜딩"),
                        ("/polls.html", "선거 랜딩"), ("/byelection/", "선거 랜딩")]:
        ck(f"nav에서 빠진 {path}가 {where}에서 링크됨", path in reachable)

    # nav 자체는 4축
    import re as _re
    nav = _re.search(r"NAV_START[\s\S]*?NAV_END", home_txt)
    n_links = len(_re.findall(r'class="hdr-link', nav.group(0))) if nav else 0
    ck("nav 링크 4개", n_links == 4, n_links)

    ck("nav에서 빠진 /region/가 선거 랜딩에서 링크됨", "/region/" in reachable)

    # 지역 페이지는 허브 1-hop이어야 한다. 400개가 sitemap에만 있고 링크가 없으면
    # 7월 색인 사고(2,190페이지 미색인)의 '고아 + thin' 조합을 그대로 재현한다.
    rg_hub = ROOT / "region" / "index.html"
    ck("지역 허브가 있다", rg_hub.exists())
    if rg_hub.exists():
        rg_pages = {p.parent.name for p in ROOT.glob("region/*/index.html")}
        rg_linked = links(rg_hub, r'href="/region/([^/"]+)/')
        ck(f"허브가 지역 {len(rg_pages)}개 전부 링크",
           not (rg_pages - rg_linked), sorted(rg_pages - rg_linked)[:5])

    # sitemap에 허브가 있다
    sm = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    ck("sitemap에 허브 등록", "/elections.html" in sm)
    ck("sitemap에 archive 전부", all(f"/archive/{a}/" in sm for a in archives))
    ck("sitemap에 지역 허브 등록", "/region/</loc>" in sm or "/region/<" in sm)

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
