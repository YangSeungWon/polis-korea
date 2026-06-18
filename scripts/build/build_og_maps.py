"""선거별 결과 지도 이미지 생성 — 원본 지도 PNG + 1200×630 og 공유 카드.

각 archive/{slug} 페이지를 헤드리스로 열어 결과 지도 SVG(hex·dorling·geo)를 캡처한다.
지도는 전부 SVG라 타일 의존 없이 깨끗하게 떠진다. 뷰 토글(.ar-sido-tab: 헥스/지도/dorling)을
눌러가며 각 뷰를 따로 저장하고, 대표 뷰로 og 카드를 합성한다.

산출물:
  og/maps/{slug}/{view}.png   — 원본 지도(투명 배경). 타임라인·허브 썸네일·임베드용.
  og/{slug}.png               — 1200×630 공유 카드(지도 + 제목 + polis 마크).

사용(로컬 서버 필요):
  python -m http.server 8911 &
  python scripts/build/build_og_maps.py [--slug 9th-local-2026] [--limit N] [--port 8911]
의존: playwright(chromium), pillow.
"""
from __future__ import annotations
import argparse
import base64
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OG = ROOT / "og"
MAPS = OG / "maps"
FAVICON = ROOT / "favicon.svg"

# SVG 클래스 substring → 깔끔한 뷰 키·라벨·설명. 토글 캡처분도 같은 클래스라 일관 분류.
# turnout-map은 governor-hex/council-hex 클래스를 공유(투표율 채색)하므로 반드시 먼저 매칭.
# 순서 주의 — _classify는 첫 substring 매칭이 이김. 더 구체적인 클래스를 위로.
#   시군구 결과 svg는 'council-hex-svg result-map'·'council-hex-svg cartogram-map'라 'council-hex'(광역의원
#   의석)보다 result-map·cartogram-map을 먼저 매칭해야 오분류 안 됨. turnout-map도 governor/council 공유라 맨 위.
VIEW_DEFS = [
    ("turnout-map", "turnout", "투표율", "지역별 투표율(짙을수록 높음)"),
    ("result-map", "result", "시군구 결과", "1위 후보·격차 명도"),
    ("cartogram-map", "sgg-prop", "시군구 비례", "표(인구) 비례 격자·원형"),
    ("sigungu-map", "sgg-geo", "시군구 지도", "시군구 경계·격차 명도"),
    ("governor-hex", "governor", "광역단체장", "시도별 당선 정당"),
    ("council-hex", "council", "광역의원", "시도별 의석"),
    ("ar-sidocluster", "dorling", "의석 비례", "면적·점=의석수·색=정당"),
    ("sido-map", "geo", "지리 지도", "실제 시도 경계"),
    ("parliament-chart", "seats", "의석수", "정당별 총 의석"),
]
# 대표(overview) 카드로 쓸 뷰 우선순위.
PRIMARY_ORDER = ["governor", "dorling", "council", "seats", "geo"]


def list_slugs() -> list[str]:
    return sorted(p.name for p in (ROOT / "archive").iterdir()
                  if p.is_dir() and (p / "index.html").exists())


def _classify(cls_full: str):
    for sub, key, _label, _desc in VIEW_DEFS:
        if sub in cls_full:
            return key
    return None


def view_meta(key: str):
    for _sub, k, label, desc in VIEW_DEFS:
        if k == key:
            return label, desc
    return key, ""


def _capture_views(page):
    """{view_key: png_bytes} — 지도 SVG를 깔끔한 키로 분류해 캡처. 토글로 대체 뷰도.
    같은 키 여러 번 잡히면 가장 큰(바이트) 것 유지."""
    views = {}

    def grab():
        for el in page.query_selector_all("svg"):
            key = _classify(el.get_attribute("class") or "")
            if not key:
                continue
            try:
                bb = el.bounding_box()
            except Exception:
                bb = None
            if not bb or bb["width"] < 200 or bb["height"] < 200:
                continue
            try:
                png = el.screenshot(omit_background=True)
            except Exception:
                continue
            if key not in views or len(png) > len(views[key]):
                views[key] = png

    grab()
    # 인맵 방식 토글을 눌러가며 대체 뷰도 캡처(EncodingToggle/.seg 통일 후 버튼=.seg-btn).
    #   .ar-sido-toggle = 시도뷰·비례·광역의원, .sgg-mode-toggle = 시군구 결과(단색/지도/격자/원형).
    #   지도(geo)는 sigungu_{year} geojson 로드라 대기 넉넉히.
    for sel in (".ar-sido-toggle", ".sgg-mode-toggle"):
        groups = page.query_selector_all(sel)
        for gi in range(len(groups)):
            groups = page.query_selector_all(sel)
            if gi >= len(groups):
                break
            for tab in groups[gi].query_selector_all(".seg-btn"):
                try:
                    if "is-active" in (tab.get_attribute("class") or ""):
                        continue
                    tab.click()
                    page.wait_for_timeout(1000)
                    grab()
                except Exception:
                    pass
    return views


def _card_html(mark_svg, kicker, headline, subline, map_png):
    b64 = base64.b64encode(map_png).decode()
    mark = mark_svg.replace("<svg ", '<svg width="60" height="60" ', 1)
    return f"""<!doctype html><html><head><meta charset=utf-8>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.min.css">
<style>*{{margin:0;box-sizing:border-box}}
body{{width:1200px;height:630px;font-family:Pretendard,sans-serif;background:#f6f7fb;display:flex;overflow:hidden;position:relative}}
.left{{width:500px;padding:60px 44px 60px 64px;display:flex;flex-direction:column;justify-content:space-between}}
.brand{{display:flex;align-items:center;gap:13px}}.brand .b{{font-size:34px;font-weight:800;letter-spacing:-1px;white-space:nowrap}}
.brand .d{{color:#6b73d6;font-weight:800}}
.ttl .k{{font-size:27px;font-weight:700;color:#5b54d6;margin-bottom:10px;line-height:1.2}}
.ttl .h{{font-size:47px;font-weight:800;letter-spacing:-2px;line-height:1.12;word-break:keep-all}}
.ttl .s{{font-size:27px;font-weight:600;color:#4a5160;margin-top:14px}}
.tag{{font-size:21px;font-weight:700;color:#4a5160;white-space:nowrap}}.tag .u{{color:#5b54d6}}
.right{{flex:1;display:flex;align-items:center;justify-content:center;padding:28px 36px 28px 0}}
.right img{{max-width:100%;max-height:540px;filter:drop-shadow(0 8px 24px rgba(40,40,80,.12))}}
.accent{{position:absolute;left:0;bottom:0;width:100%;height:12px;background:#5b54d6}}</style></head><body>
<div class="left"><div class="brand">{mark}<span class="b">polis<span class="d">.ysw.kr</span></span></div>
<div class="ttl"><div class="k">{kicker}</div><div class="h">{headline}</div><div class="s">{subline}</div></div>
<div class="tag">NEC 공식 개표 · <span class="u">polis.ysw.kr</span></div></div>
<div class="right"><img src="data:image/png;base64,{b64}"></div><div class="accent"></div></body></html>"""


def recompose():
    """캐시된 원본 지도(og/maps/{slug}/*.png)로 카드만 재합성 — favicon 마크 바뀔 때 빠른 동기화
    (아카이브 페이지 재렌더·지도 재캡처 없이 카드 chrome만 다시). 제목·날짜는 archive_index.json."""
    import json
    from playwright.sync_api import sync_playwright
    meta = {e["slug"]: e for e in json.loads((ROOT / "data/archive_index.json").read_text(encoding="utf-8"))}
    mark_svg = FAVICON.read_text(encoding="utf-8")
    made = 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
        for slug_dir in sorted(d for d in MAPS.iterdir() if d.is_dir()):
            slug = slug_dir.name
            m = meta.get(slug, {})
            kicker = (m.get("date") or "")[:10]
            headline = m.get("name") or slug
            views = {}
            for png_path in sorted(slug_dir.glob("*.png")):
                key = png_path.stem
                label, desc = view_meta(key)
                html = _card_html(mark_svg, kicker, headline, f"{label} · {desc}", png_path.read_bytes())
                pg.set_content(html, wait_until="networkidle"); pg.wait_for_timeout(300)
                out = OG / slug / f"{key}.png"
                out.parent.mkdir(parents=True, exist_ok=True)
                pg.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": 1200, "height": 630})
                views[key] = out; made += 1
            if views:
                primary = next((k for k in PRIMARY_ORDER if k in views), next(iter(views)))
                shutil.copyfile(OG / slug / f"{primary}.png", OG / f"{slug}.png")
        b.close()
    print(f"recompose: {made} cards (캐시 지도 재사용)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", help="한 선거만")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--port", type=int, default=8911)
    ap.add_argument("--recompose", action="store_true", help="캐시 지도로 카드만 재합성(favicon 동기화)")
    args = ap.parse_args()
    if args.recompose:
        recompose(); return
    from playwright.sync_api import sync_playwright

    mark_svg = FAVICON.read_text(encoding="utf-8")
    slugs = [args.slug] if args.slug else list_slugs()
    if args.limit:
        slugs = slugs[:args.limit]
    base = f"http://localhost:{args.port}/archive"
    MAPS.mkdir(parents=True, exist_ok=True)

    made = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for slug in slugs:
            pg = b.new_page(viewport={"width": 1320, "height": 1700})
            try:
                pg.goto(f"{base}/{slug}/", wait_until="networkidle", timeout=20000)
                pg.wait_for_timeout(2200)
                # 지도 위 오버레이가 캡처에 찍히지 않게 숨김(element.screenshot은 겹친 요소 포함).
                #   저장버튼은 display:none. 인맵 방식 토글은 opacity:0 — 뷰 전환 클릭은 유지하되 화면엔 안 찍힘.
                #   시도·시군구명 라벨은 썸네일·카드서 안 읽히는 잡음 → 캡처서 숨김(제목은 카드 헤드라인).
                pg.add_style_tag(content=(
                    ".svg-save-btn{display:none!important}"
                    ".ar-sido-toggle,.sgg-mode-toggle{opacity:0!important}"
                    ".gov-hex-label,.hist-sido-edge-label,.hist-sigungu-label,"
                    ".sido-map-label,.metro-hex-label,.council-hex-sido-label{display:none!important}"
                ))
                title = (pg.text_content("#ar-title") or "").strip() if pg.query_selector("#ar-title") else ""
                date_s = (pg.text_content("#ar-date") or "").strip() if pg.query_selector("#ar-date") else ""
                views = _capture_views(pg)
                if not views:
                    print(f"  {slug}: 지도 없음 — skip"); pg.close(); continue
                mdate = re.search(r"\d{4}-\d{2}-\d{2}", date_s)
                kicker = mdate.group(0) if mdate else date_s[:10]
                headline = title or slug
                raw_dir = MAPS / slug
                card_dir = OG / slug
                raw_dir.mkdir(parents=True, exist_ok=True)
                card_dir.mkdir(parents=True, exist_ok=True)
                for key, png in views.items():
                    (raw_dir / f"{key}.png").write_bytes(png)   # 원본(투명)
                    label, desc = view_meta(key)
                    html = _card_html(mark_svg, kicker, headline, f"{label} · {desc}", png)
                    pg.set_content(html, wait_until="networkidle"); pg.wait_for_timeout(350)
                    pg.screenshot(path=str(card_dir / f"{key}.png"),
                                  clip={"x": 0, "y": 0, "width": 1200, "height": 630})
                # 대표 카드 og/{slug}.png (archive·poll 페이지 기본 og:image)
                primary = next((k for k in PRIMARY_ORDER if k in views), next(iter(views)))
                shutil.copyfile(card_dir / f"{primary}.png", OG / f"{slug}.png")
                made.append((slug, list(views)))
                print(f"  {slug}: {len(views)} views {list(views)} ✓")
            except Exception as e:
                print(f"  {slug}: ERROR {e}")
            finally:
                pg.close()
        b.close()
    print(f"완료: {len(made)} 선거 카드 생성")


if __name__ == "__main__":
    main()
