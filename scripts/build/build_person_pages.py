"""인물 정적 페이지 빌드 — 의원(assembly_id 보유) entry만 prerender.

각 인물별 /person/{name}-{dob}/index.html 생성. 페이지에 그 인물 데이터만
inline JSON으로 박아 fetch 없이 즉시 렌더. 비의원은 /person.html?name= dynamic.

URL slug: `이재명-1964-12-22` 식. URL은 한글 그대로 (브라우저가 percent-encoding 처리).

Output:
  person/{slug}/index.html × ~807
  data/sitemap_person.txt — sitemap 추가용 URL list
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "assets/person-index.json"
OUT_DIR = ROOT / "person"
SITEMAP_OUT = ROOT / "data/sitemap_person.txt"
SITE = "https://polis.ysw.kr"

# nav는 sync_nav_html.py가 정본 — 여기서 사본을 들고 있으면 메뉴가 바뀔 때마다 어긋난다
# (실제로 '역대 판세'가 '타임라인'으로 굳어 있었다). 생성 시점에 정본을 불러 쓴다.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_nav_html import render_nav, menu_for_path  # noqa: E402



TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<script>try{{var _m=localStorage.getItem('vote-ysw-theme');if(_m==='dark')document.documentElement.setAttribute('data-theme','dark');else if(_m==='light')document.documentElement.setAttribute('data-theme','light');}}catch(_e){{}}</script>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#5b54d6">
<base href="/">
<title>polis · {name}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="polis · {name}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="profile">
<meta property="og:url" content="https://polis.ysw.kr/person/{slug}/">
<meta property="og:image" content="https://polis.ysw.kr/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="polis · {name}">
<meta name="twitter:image" content="https://polis.ysw.kr/og.png">
<link rel="canonical" href="/person/{slug}/">
{jsonld}
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.min.css">
<link rel="stylesheet" href="assets/common.css">
<link rel="stylesheet" href="assets/components.css">
<link rel="stylesheet" href="assets/person.css">
<script id="person-data" type="application/json">{data_json}</script>
</head>
<body>
<header class="site-hdr">
  <div class="brand">
    <a href="/" class="logo-link"><span class="logo">polis</span><span class="domain">ysw.kr</span></a>
  </div>
  <nav class="hdr-nav">
{nav}
  </nav>
  <div class="hdr-meta">
    <button id="theme-toggle" class="theme-toggle" type="button" aria-label="테마 토글"></button>
  </div>
</header>
<main class="page">
  <section class="intro">
    <h1 id="person-title">{name}</h1>
    <p class="lede" id="person-sub">{lede}</p>
  </section>
  <section id="person-body">{static_body}</section>
  <footer class="foot">
    <p class="fine">비의원·낙선 이력은 <a href="/person.html?name={name}">검색</a>에서.</p>
  </footer>
</main>
<script src="assets/parties.js"></script>
<script src="assets/person.js"></script>
<script src="assets/theme.js"></script>
<script src="assets/nav.js"></script>
</body>
</html>
"""


def slugify(name: str, dob: str) -> str:
    """URL slug: 한글 그대로 + dob. e.g. '이재명-1964-12-22'."""
    return f"{name}-{dob}"


def esc(s) -> str:
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def jsonld(p: dict, slug: str, desc: str) -> str:
    """Person + BreadcrumbList — 검색 결과에 URL 대신 경로가, 인물엔 개체 정보가 붙는다.

    단언할 수 없는 값(직위·소속 현재형)은 넣지 않는다. 이름·생년월일·한자·설명처럼
    데이터로 확실한 것만 싣는다 — 구조화 데이터의 오류는 신뢰도 페널티로 돌아온다.
    """
    url = f"{SITE}/person/{slug}/"
    person = {"@type": "Person", "name": p["name"], "url": url, "description": desc}
    if p.get("dob"):
        person["birthDate"] = p["dob"]
    if p.get("hanja"):
        person["alternateName"] = p["hanja"]
    crumbs = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "인물 검색", "item": f"{SITE}/search.html"},
        {"@type": "ListItem", "position": 2, "name": p["name"]},
    ]}
    data = {"@context": "https://schema.org", "@graph": [person, crumbs]}
    return ('<script type="application/ld+json">'
            + json.dumps(data, ensure_ascii=False) + '</script>')


def static_body(p: dict) -> tuple[str, str]:
    """(lede, 본문 HTML) — 렌더 전에도 읽히는 실제 내용.

    이 페이지들은 원래 inline JSON + person.js로만 내용을 만들었다. 데이터는 HTML 안에
    있었지만 <script> 안이라 렌더 전에는 텍스트가 아니고, 검색엔진의 렌더 예산은 4,000
    페이지에 배분되지 않는다. 실제로 구글이 '크롤링됨 - 색인 생성되지 않음'으로 2,190건을
    보류했다(본문이 nav 빼면 40자). 그래서 같은 내용을 빌드 시점에 HTML로도 찍는다.
    person.js는 로드되면 #person-body를 자기 렌더로 덮어쓰므로 화면 동작은 그대로다.
    """
    races = sorted(p.get("races", []), key=lambda r: (r.get("date") or str(r.get("year") or "")))
    years = [r.get("year") for r in races if r.get("year")]
    span = f"{min(years)}~{max(years)}년 " if years else ""
    parties = p.get("parties") or []
    wins, losses = p.get("wins", 0), p.get("losses", 0)
    lede_bits = [f"{span}{len(races)}회 출마 · {wins}회 당선 · {losses}회 낙선"]
    if parties:
        lede_bits.append(" · ".join(parties[:4]))
    lede = esc(" — ".join(lede_bits))

    rows = []
    for r in races:
        tag = "당선" if r.get("won") else "낙선"
        pct = f"{float(r['pct']):.1f}%" if r.get("pct") is not None else "—"
        rank = f"{r['rank']}위" if r.get("rank") and r["rank"] < 99 else ""
        rows.append(
            f'<tr><td>{esc(r.get("year") or "")}</td>'
            f'<td><a href="/archive/{esc(r.get("eid"))}/">{esc(r.get("round") or r.get("eid"))}</a></td>'
            f'<td>{esc(r.get("place") or "")}</td>'
            f'<td>{esc(r.get("party") or "")}</td>'
            f'<td>{pct}</td><td>{esc(rank)}</td><td>{tag}</td></tr>')
    table = (
        '<table class="pp-static"><caption>출마 이력</caption><thead><tr>'
        '<th>연도</th><th>선거</th><th>지역</th><th>정당</th><th>득표율</th>'
        '<th>순위</th><th>결과</th></tr></thead><tbody>'
        + "".join(rows) + "</tbody></table>")
    return lede, table


def main():
    pi = json.loads(INDEX.read_text(encoding="utf-8"))
    # 당선 선출직(국회의원·단체장·교육감·대통령 등) — dob 있고 + 의원이거나 무언가 당선.
    # 낙선만 한 후보는 페이지 없이 검색에만(노이즈 방지).
    persons = [p for p in pi["persons"]
               if p.get("dob") and (p.get("assembly_id") or any(r.get("won") for r in p.get("races", [])))]
    print(f"의원 entry: {len(persons)} (전체 {len(pi['persons'])} 중)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sitemap_urls = []
    n_written = 0
    valid_slugs = set()
    for p in persons:
        slug = slugify(p["name"], p["dob"])
        valid_slugs.add(slug)
        page_dir = OUT_DIR / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        # 그 인물 entry만 inline (소형)
        data = {"persons": [p]}
        data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        # description: 다회차·정당 요약
        rounds = sorted({r.get("round", "") for r in p["races"] if r.get("round")})
        parties = p.get("parties", [])[:3]
        desc = (
            f"{p['name']} 출마·당선 이력. {p['wins']}당선·{p['losses']}낙선 "
            f"· {' · '.join(parties)} · {len(p['races'])}회"
        )
        lede, body = static_body(p)
        ld = jsonld(p, slug, desc)
        html = TEMPLATE.format(
            nav=render_nav(menu_for_path(f"person/{slug}/index.html")),
            name=p["name"],
            desc=desc,
            slug=slug,
            data_json=data_json,
            lede=lede,
            static_body=body,
            jsonld=ld,
        )
        (page_dir / "index.html").write_text(html, encoding="utf-8")
        sitemap_urls.append(f"/person/{slug}/")
        n_written += 1

    # stale 디렉터리 제거 — 옛 빌드(생년월일 보정·동명이인 분리 등)로 슬러그가 바뀐 잔존분.
    import shutil
    n_stale = 0
    for dch in OUT_DIR.iterdir():
        if dch.is_dir() and dch.name not in valid_slugs:
            shutil.rmtree(dch)
            n_stale += 1

    SITEMAP_OUT.write_text("\n".join(sitemap_urls), encoding="utf-8")
    print(f"→ {OUT_DIR.relative_to(ROOT)}/ : {n_written} pages (stale 제거 {n_stale})")
    print(f"→ {SITEMAP_OUT.relative_to(ROOT)} : {n_written} URLs (sitemap 통합용)")


if __name__ == "__main__":
    main()
