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


TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<base href="/">
<title>polis · {name}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="polis · {name}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="profile">
<link rel="canonical" href="/person/{slug}/">
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
    <!-- NAV_START — scripts/build/sync_nav_html.py 자동 갱신. 손수정 X. -->
  <a href="/tracker.html" class="hdr-link">지지율 추이</a>
  <a href="/polls.html" class="hdr-link">여론조사</a>
  <span data-nav-urgent></span>
  <a href="/byelection/" class="hdr-link">재·보궐</a>
  <a href="/history.html" class="hdr-link">역대 결과</a>
  <a href="/timeline.html" class="hdr-link">타임라인</a>
  <a href="/chronology.html" class="hdr-link">근현대사</a>
  <a href="/parties.html" class="hdr-link">정당사</a>
  <!-- NAV_END -->
  </nav>
  <div class="hdr-meta">
    <button id="theme-toggle" class="theme-toggle" type="button" aria-label="테마 토글"></button>
  </div>
</header>
<main class="page">
  <section class="intro">
    <h1 id="person-title">{name}</h1>
    <p class="lede" id="person-sub">불러오는 중…</p>
  </section>
  <section id="person-body">
    <div class="detail-empty">불러오는 중…</div>
  </section>
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
        html = TEMPLATE.format(
            name=p["name"],
            desc=desc,
            slug=slug,
            data_json=data_json,
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
