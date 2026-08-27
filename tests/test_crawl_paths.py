"""크롤 경로 검증 — 홈에서 모든 archive까지 몇 홉인가.

2026-07 Search Console이 2,190페이지를 미색인으로 보류한 뒤 내부 링크 심도를 고쳤다.
홈에서 53행 목록을 걷어내는 것 같은 IA 변경은 그 개선을 조용히 되돌리기 쉽다.

실행: python3 tests/test_crawl_paths.py
"""
from __future__ import annotations
import glob
import re
import sys
import pathlib
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
fails = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}{'' if cond else ' — ' + str(detail)}")
    if not cond:
        fails.append(name)


def links(fp: Path, pat: str) -> set:
    return set(re.findall(pat, fp.read_text(encoding="utf-8")))


def check_logo_home() -> None:
    """로고가 **홈**을 가리키는가 — 상대 경로면 자기 자신을 가리킨다.

    2026-08 GSC로 확인한 실제 사고다. 로고가 `href="index.html"`(상대)이었고,
    프리렌더 템플릿이 손작성 루트 페이지(polls.html·history.html)라 그 상대 경로가
    88쪽에 복사됐다. 결과가 위치마다 달랐다:

      /history/presidential/6/index.html  →  자기 자신. 홈으로 가는 링크가 아니다
      /index.html                          →  홈이지만 `/`의 중복 URL

    그래서 Google이 아는 홈은 `/`가 아니라 `/index.html`이었고(googleCanonical),
    `/`는 '알려지지 않은 URL'이었다. sitemap은 `/`를 냈는데 링크는 아무도 그리로
    가지 않은 것이다.

    눈으로는 안 보인다 — 로고를 누르면 페이지가 다시 뜨니 '동작'한다. 링크 그래프
    검사도 통과한다: 자기 링크는 깨진 링크가 아니다. 그래서 절대 경로만 허용한다.
    """
    bad = []
    for f in ROOT.rglob("*.html"):
        rel = str(f.relative_to(ROOT))
        if rel.split("/")[0] in {"node_modules", ".venv", "og"}:
            continue
        m = re.search(r'<a href="([^"]*)" class="logo-link"', f.read_text(encoding="utf-8"))
        if m and m.group(1) != "/":
            bad.append(f"{rel} → {m.group(1)}")
    ck("로고가 전부 홈(/)을 가리킨다", not bad,
       f"{len(bad)}쪽 상대 경로 — {bad[:3]}")


# (계열, 자식 glob, 허브 파일). 허브가 자식을 **정적 HTML로** 열거하는가.
#
# history는 섬이었다(바깥에서 링크가 0). party는 섬은 아니었지만 — 인물 20,254곳,
# 지역 6,775곳에서 링크가 들어온다 — **아무도 열거하지 않아** 깊이가 3~7홉으로
# 흩어져 있었다. 둘 다 "허브가 자기 자식을 안 센다"는 같은 결함의 두 얼굴이다.
#
# 검사가 history 하나에만 하드코딩돼 있어서 party는 모든 검사를 통과했다.
HUBS = [
    ("history", "history/*/*/**/index.html", "history.html"),
    ("party", "party/*/index.html", "parties.html"),
    ("region", "region/*/index.html", "region/index.html"),
]


def check_hub_enumerates() -> None:
    """허브가 자식 전부를 정적 HTML로 링크하는가.

    JS가 렌더 후에 같은 링크를 만드는 것으로는 부족하다 — 사용자 도달 가능성과
    크롤러 가시성은 다른 질문이다(docs/page-map.md gap-2의 교훈). 그래서 <script>를
    걷어내고 센다.
    """
    for label, child_glob, hub in HUBS:
        hub_f = ROOT / hub
        if not hub_f.exists():
            ck(f"{label} 허브가 있다", False, hub)
            continue
        html = re.sub(r"<script.*?</script>", "", hub_f.read_text(encoding="utf-8"), flags=re.S)
        linked = {unquote(h) for h in re.findall(r'href="(/[^"]+/)"', html)}
        children = {f"/{f.parent.relative_to(ROOT)}/" for f in ROOT.glob(child_glob)}
        children = {c for c in children if c != f"/{pathlib.PurePath(hub).parent}/"}
        missing = sorted(children - linked)
        ck(f"{hub}이 {label} {len(children)}쪽을 열거한다", not missing,
           f"{len(missing)}쪽 누락 — {missing[:3]}")


def check_history_island() -> None:
    """/history/ 프리렌더가 **바깥에서** 링크되는가.

    2026-08 URL Inspection에서 65쪽 중 41쪽이 'Google에 알려지지 않은 URL'로 나왔다.
    원인은 이 66쪽을 정적으로 가리키는 페이지가 저장소에 하나도 없었다는 것이다 —
    서로만 링크하는 섬이라 크롤러 입구가 sitemap뿐이었다. 인물 1,820쪽이 겪은 것과
    같은 구조다(4b10a4c0c).

    JS 타임라인이 같은 링크를 만들지만 렌더 후에만 존재한다. 사용자 도달 가능성과
    크롤러 가시성은 다른 질문이다 — 그래서 **정적 HTML만** 본다.

    자기들끼리의 링크는 세지 않는다. 섬 안에서 아무리 촘촘해도 입구가 아니다.
    """
    pages = {f"/{p.relative_to(ROOT).parent}/" for p in ROOT.glob("history/*/*/**/index.html")}
    pages |= {f"/{p.relative_to(ROOT).parent}/" for p in ROOT.glob("history/*/*/index.html")}
    outside = set()
    for f in ROOT.rglob("*.html"):
        rel = f.relative_to(ROOT)
        if rel.parts[0] in {"node_modules", ".venv", "history", "og"}:
            continue
        html = re.sub(r"<script.*?</script>", "", f.read_text(encoding="utf-8", errors="replace"),
                      flags=re.S)
        outside |= {unquote(h) for h in re.findall(r'href="(/history/[^"]+)"', html)}
    missing = sorted(p for p in pages if p not in outside)
    ck(f"history 프리렌더 {len(pages)}쪽이 바깥에서 링크됨", not missing,
       f"{len(missing)}쪽이 섬 — {missing[:3]}")


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
        # 링크는 퍼센트 인코딩으로 나갈 수 있다(시도 링크가 그렇다). 원문자와
        # 비교하려면 풀어야 한다 — 안 풀면 실재하는 링크를 '없다'고 읽는다.
        rg_linked = {unquote(u) for u in links(rg_hub, r'href="/region/([^/"]+)/')}
        ck(f"허브가 지역 {len(rg_pages)}개 전부 링크",
           not (rg_pages - rg_linked), sorted(rg_pages - rg_linked)[:5])

    # nav 4축이 **모든 페이지 유형**에 적용됐는지. sync_nav_html --check가 정본
    # 검사지만 '변경 N'만 알려줘서, 어느 유형이 새는지 보이지 않는다. 실제로
    # history/{종류}/{회차}/{직}/ 363개가 옛 메뉴로 굳어 있는데도 --check는
    # 통과했다(가드의 glob이 그 깊이를 안 봤다). 유형별로 못 박는다.
    import re as _re2
    AXES = ["지금", "선거", "인물·정당", "역사"]
    types = {
        "루트": "index.html", "여론조사": "polls.html", "선거 허브": "elections.html",
        "회차 폴": next((str(p.relative_to(ROOT)) for p in ROOT.glob("polls/*/index.html")), None),
        "역대 결과": next((str(p.relative_to(ROOT)) for p in ROOT.glob("history/*/*/index.html")), None),
        "역대 결과(직위)": next((str(p.relative_to(ROOT)) for p in ROOT.glob("history/*/*/*/index.html")), None),
        "archive": next((str(p.relative_to(ROOT)) for p in ROOT.glob("archive/*/index.html")), None),
        "인물": next((str(p.relative_to(ROOT)) for p in ROOT.glob("person/*/index.html")), None),
        "정당": next((str(p.relative_to(ROOT)) for p in ROOT.glob("party/*/index.html")), None),
        "지역": next((str(p.relative_to(ROOT)) for p in ROOT.glob("region/*/index.html")), None),
        "재보궐": "byelection.html", "연표": "chronology.html",
    }
    for label, rel in types.items():
        if not rel or not (ROOT / rel).exists():
            ck(f"{label} 페이지 존재", False, str(rel))
            continue
        t = (ROOT / rel).read_text(encoding="utf-8")
        m = _re2.search(r"NAV_START[\s\S]*?NAV_END", t)
        labs = _re2.findall(r'class="hdr-link[^"]*">([^<]+)<', m.group(0)) if m else []
        ck(f"{label} nav 4축", labs == AXES, f"{rel} → {'/'.join(labs) or '(마커 없음)'}")

    # sitemap에 허브가 있다 — sitemap.xml은 층별 파일을 가리키는 index이므로
    # index만 읽으면 URL이 하나도 안 보이고 아래 세 검사가 전부 거짓으로 떨어진다.
    _idx = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    sm = "\n".join(
        (ROOT / u.rsplit("/", 1)[-1]).read_text(encoding="utf-8")
        for u in re.findall(r"<loc>([^<]+)</loc>", _idx)
        if (ROOT / u.rsplit("/", 1)[-1]).exists())
    ck("sitemap에 허브 등록", "/elections.html" in sm)
    ck("sitemap에 archive 전부", all(f"/archive/{a}/" in sm for a in archives))
    ck("sitemap에 지역 허브 등록", "/region/</loc>" in sm or "/region/<" in sm)

    check_logo_home()
    check_history_island()
    check_hub_enumerates()

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
