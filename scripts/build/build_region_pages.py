"""지역 entity 페이지 → /region/{시도}-{시군구}/index.html.

polis에는 이미 선거·인물·정당이 있는데 **지역**만 entity가 아니었다. 같은 시군구가
역대 대선·총선·지선에서 어떻게 갈렸는지는 데이터에 다 있지만 한곳에 모이지 않았다.

새 데이터를 만들지 않는다. data/results/*.json의 시군구 단위 race를 모아 재배열할 뿐이다.

본문은 빌드 시점에 HTML로 찍는다. 7월 색인 사고(2,190페이지 미색인)의 원인이 '데이터는
있는데 HTML에 없음'이었고, 같은 실수를 새 표면에서 반복하지 않는다.

Output:
  region/{시도}-{시군구}/index.html
  data/sitemap_region.txt
"""
from __future__ import annotations
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data/results"
OUT_DIR = ROOT / "region"
SITEMAP_OUT = ROOT / "data/sitemap_region.txt"
SITE = "https://polis.ysw.kr"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_nav_html import render_nav, menu_for_path  # noqa: E402

# 회차가 이보다 적으면 페이지를 만들지 않는다 — 한두 번 스친 옛 지명까지 만들면
# 내용도 없고 검색 노이즈만 된다(오늘 배운 thin content 문제).
MIN_ROUNDS = 3

KIND_LABEL = {"presidential": "대선", "national_assembly": "총선",
              "general_election": "총선", "local": "지선", "byelection": "재보궐"}


def esc(s) -> str:
    return (str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def load_all() -> list:
    out = []
    for fp in sorted(RESULTS.glob("*.json")):
        if ".sigungu." in fp.name:
            continue
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        races = list(d.get("races") or [])
        if d.get("_meta", {}).get("chunked"):
            cp = fp.with_name(fp.stem + ".sigungu.json")
            if cp.exists():
                races += json.loads(cp.read_text(encoding="utf-8")).get("races") or []
        out.append((fp.stem, d.get("_meta") or {}, races))
    return out


def election_meta(eid: str) -> dict:
    p = ROOT / "data/elections" / f"{eid}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def collect() -> dict:
    """(시도, 시군구) → [{eid, date, kind, label, party, name, pct, turnout}]"""
    by_region = defaultdict(list)
    for eid, meta, races in load_all():
        em = election_meta(eid)
        kind = em.get("kind") or ""
        date = em.get("date") or meta.get("election_date") or ""
        name = em.get("name") or meta.get("election") or eid
        # 시군구 단위 대표 race — 그 지역의 '1위'가 무엇이었는지.
        # 지선은 기초단체장(4), 대선·총선은 시군구 분해 row.
        for r in races:
            sg, sd = r.get("sigungu"), r.get("sido")
            if not sg or not sd:
                continue
            scope, tc = r.get("scope"), r.get("sg_typecode")
            if not ((tc == "4" and scope == "sigungu")
                    or (tc == "1" and scope == "sigungu")
                    or (tc in ("3", "11") and scope == "sigungu")):
                continue
            cs = sorted((r.get("candidates") or []),
                        key=lambda c: -(c.get("votes") or 0))
            if not cs:
                continue
            top = cs[0]
            el, vo = r.get("electors") or 0, r.get("voters") or 0
            by_region[(sd, sg)].append({
                "eid": eid, "date": date, "kind": kind,
                "election": name,
                "office": {"1": "대통령", "3": "광역단체장", "4": "기초단체장",
                           "11": "교육감"}.get(tc, tc),
                "party": top.get("party") or "무소속", "name": top.get("name"),
                "pct": top.get("pct"),
                "turnout": round(vo / el * 100, 1) if el else None,
            })
    return by_region


TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<script>try{{var _m=localStorage.getItem('vote-ysw-theme');if(_m==='dark')document.documentElement.setAttribute('data-theme','dark');else if(_m==='light')document.documentElement.setAttribute('data-theme','light');}}catch(_e){{}}</script>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="theme-color" content="#5b54d6">
<base href="/">
<title>polis · {sido} {sigungu} 선거 기록</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="polis · {sido} {sigungu}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="https://polis.ysw.kr/og.png">
<link rel="canonical" href="/region/{slug}/">
{jsonld}
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.min.css">
<link rel="stylesheet" href="assets/common.css">
<link rel="stylesheet" href="assets/components.css">
<link rel="stylesheet" href="assets/person.css">
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
    <h1>{sido} {sigungu}</h1>
    <p class="lede">{lede}</p>
  </section>
  <section>{table}</section>
  <footer class="foot">
    <p class="fine">시군구 단위로 1위를 집계한 기록입니다. 회차별 상세는 각 아카이브에서 볼 수 있습니다.</p>
  </footer>
</main>
<script src="assets/parties.js"></script>
<script src="assets/theme.js"></script>
<script src="assets/nav.js"></script>
</body>
</html>
"""


def build_page(sd: str, sg: str, rows: list) -> str:
    rows = sorted(rows, key=lambda r: (r["date"] or "", r["office"]), reverse=True)
    slug = f"{sd}-{sg}"
    years = [r["date"][:4] for r in rows if r.get("date")]
    span = f"{min(years)}~{max(years)}년 " if years else ""
    parties = {}
    for r in rows:
        parties[r["party"]] = parties.get(r["party"], 0) + 1
    top_parties = " · ".join(p for p, _ in sorted(parties.items(), key=lambda x: -x[1])[:3])
    lede = esc(f"{span}선거 {len(rows)}건 — 1위 정당 {top_parties}")
    desc = esc(f"{sd} {sigungu_short(sg)} 역대 선거 기록. {span}{len(rows)}건 · {top_parties}")

    trs = []
    for r in rows:
        kl = KIND_LABEL.get(r["kind"], "")
        trs.append(
            f'<tr><td>{esc((r.get("date") or "")[:4])}</td>'
            f'<td><a href="/archive/{esc(r["eid"])}/">{esc(r["election"])}</a></td>'
            f'<td>{esc(r["office"])}</td>'
            f'<td>{esc(r["party"])}</td>'
            f'<td>{esc(r.get("name") or "")}</td>'
            f'<td>{f"{r['pct']:.1f}%" if r.get("pct") is not None else "—"}</td>'
            f'<td>{f"{r['turnout']:.1f}%" if r.get("turnout") is not None else "—"}</td></tr>')
    table = ('<table class="pp-static"><caption>역대 선거 — 이 지역 1위</caption><thead><tr>'
             '<th>연도</th><th>선거</th><th>직</th><th>1위 정당</th><th>1위 후보</th>'
             '<th>득표율</th><th>투표율</th></tr></thead><tbody>'
             + "".join(trs) + "</tbody></table>")

    ld = {"@context": "https://schema.org", "@type": "BreadcrumbList",
          "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": "모든 선거",
               "item": f"{SITE}/elections.html"},
              {"@type": "ListItem", "position": 2, "name": f"{sd} {sg}"}]}
    return TEMPLATE.format(
        sido=esc(sd), sigungu=esc(sg), slug=esc(slug), desc=desc, lede=lede, table=table,
        nav=render_nav(menu_for_path(f"region/{slug}/index.html")),
        jsonld='<script type="application/ld+json">'
               + json.dumps(ld, ensure_ascii=False) + "</script>")


def sigungu_short(sg: str) -> str:
    return sg


HUB = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<script>try{{var _m=localStorage.getItem('vote-ysw-theme');if(_m==='dark')document.documentElement.setAttribute('data-theme','dark');else if(_m==='light')document.documentElement.setAttribute('data-theme','light');}}catch(_e){{}}</script>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<base href="/">
<title>polis · 지역별 선거 기록</title>
<meta name="description" content="시군구별 역대 대선·총선·지선 1위와 투표율. {n}개 지역.">
<link rel="canonical" href="/region/">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.min.css">
<link rel="stylesheet" href="assets/common.css">
<link rel="stylesheet" href="assets/components.css">
<link rel="stylesheet" href="assets/person.css">
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
    <h1>지역별 선거 기록</h1>
    <p class="lede">시군구 {n}곳 — 역대 대선·총선·지선에서 그 지역이 어떻게 갈렸는지.</p>
  </section>
{body}
</main>
<script src="assets/parties.js"></script>
<script src="assets/theme.js"></script>
<script src="assets/nav.js"></script>
</body>
</html>
"""


def build_hub(entries: list) -> str:
    """시도별로 묶은 전체 목록. 400개를 한 페이지에서 직접 링크해 크롤 경로를 1-hop으로 둔다."""
    by_sido = defaultdict(list)
    for sd, sg, slug in entries:
        by_sido[sd].append((sg, slug))
    blocks = []
    for sd in sorted(by_sido):
        items = "".join(
            f'<a class="rg-item" href="/region/{slug}/">{esc(sg)}</a>'
            for sg, slug in sorted(by_sido[sd]))
        blocks.append(f'<section class="dash-section"><h2 class="dash-section-title">{esc(sd)}'
                      f'<span class="rg-count">{len(by_sido[sd])}</span></h2>'
                      f'<div class="rg-grid">{items}</div></section>')
    return "\n".join(blocks)


def main():
    by_region = collect()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    urls, n = [], 0
    for (sd, sg), rows in sorted(by_region.items()):
        if len(rows) < MIN_ROUNDS:
            continue
        slug = f"{sd}-{sg}"
        d = OUT_DIR / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(build_page(sd, sg, rows), encoding="utf-8")
        urls.append(f"/region/{slug}/")
        n += 1
    entries = [(u.split("/")[2].split("-", 1)[0], u.split("/")[2].split("-", 1)[1],
                u.split("/")[2]) for u in urls]
    (OUT_DIR / "index.html").write_text(
        HUB.format(n=len(entries), body=build_hub(entries),
                   nav=render_nav(menu_for_path("region/index.html"))), encoding="utf-8")
    urls.insert(0, "/region/")
    SITEMAP_OUT.write_text("\n".join(urls) + "\n", encoding="utf-8")
    print(f"→ region/ : {n} pages (회차 {MIN_ROUNDS}건 이상)", file=sys.stderr)
    print(f"→ {SITEMAP_OUT.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
