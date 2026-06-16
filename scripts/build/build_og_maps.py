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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OG = ROOT / "og"
MAPS = OG / "maps"
FAVICON = ROOT / "favicon.svg"

# 카드 대표 뷰 우선순위(유형별 가장 상징적인 지도). 없으면 가장 큰 SVG로 폴백.
PRIMARY_PREF = ["governor-hex-svg", "ar-sidocluster-svg", "council-hex-svg", "parliament-chart"]


def list_slugs() -> list[str]:
    return sorted(p.name for p in (ROOT / "archive").iterdir()
                  if p.is_dir() and (p / "index.html").exists())


def _capture_views(page):
    """현재 페이지의 지도 뷰들을 {view_label: png_bytes}로 캡처. 토글 눌러 대체 뷰도.
    내용 동일(토글로 안 바뀐 섹션 재캡처)분은 해시로 dedup."""
    import hashlib
    views = {}
    seen = set()

    def grab_svgs(prefix):
        for el in page.query_selector_all("svg, .leaflet-container"):
            try:
                bb = el.bounding_box()
            except Exception:
                bb = None
            if not bb or bb["width"] < 200 or bb["height"] < 200:
                continue
            cls = (el.get_attribute("class") or "svg").split()[0]
            label = f"{prefix}{cls}"
            if label in views:
                continue
            try:
                png = el.screenshot(omit_background=True)
            except Exception:
                continue
            h = hashlib.md5(png).hexdigest()
            if h in seen:   # 토글로 안 바뀐 동일 지도 — 중복 저장 안 함
                continue
            seen.add(h)
            views[label] = png

    grab_svgs("")
    # 토글 그룹마다 비활성 탭을 눌러 대체 뷰 캡처
    groups = page.query_selector_all(".ar-sido-toggle")
    for gi in range(len(groups)):
        groups = page.query_selector_all(".ar-sido-toggle")
        if gi >= len(groups):
            break
        tabs = groups[gi].query_selector_all(".ar-sido-tab")
        for tab in tabs:
            try:
                if "is-active" in (tab.get_attribute("class") or ""):
                    continue
                label = (tab.text_content() or "view").strip()
                tab.click()
                page.wait_for_timeout(700)
                grab_svgs(f"{label}-")
            except Exception:
                pass
    return views


def _descriptor(slug: str) -> str:
    if "pres" in slug:
        return "시도별 득표 · 면적=득표수"
    if "general" in slug:
        return "시도별 의석 분포"
    if "local" in slug:
        return "광역단체장 · 시도별 1위"
    return "시도별 결과"


def _card_html(mark_svg, kicker, headline, subline, map_png):
    b64 = base64.b64encode(map_png).decode()
    mark = mark_svg.replace("<svg ", '<svg width="60" height="60" ', 1)
    return f"""<!doctype html><html><head><meta charset=utf-8>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.min.css">
<style>*{{margin:0;box-sizing:border-box}}
body{{width:1200px;height:630px;font-family:Pretendard,sans-serif;background:#f6f7fb;display:flex;overflow:hidden;position:relative}}
.left{{width:500px;padding:60px 44px 60px 64px;display:flex;flex-direction:column;justify-content:space-between}}
.brand{{display:flex;align-items:center;gap:13px}}.brand .b{{font-size:32px;font-weight:800;letter-spacing:-1px}}
.brand .d{{font-size:19px;color:#8a93a3;font-weight:600}}
.ttl .k{{font-size:27px;font-weight:700;color:#5b54d6;margin-bottom:10px;line-height:1.2}}
.ttl .h{{font-size:47px;font-weight:800;letter-spacing:-2px;line-height:1.12;word-break:keep-all}}
.ttl .s{{font-size:27px;font-weight:600;color:#4a5160;margin-top:14px}}
.tag{{font-size:22px;font-weight:600;color:#6b7384}}
.right{{flex:1;display:flex;align-items:center;justify-content:center;padding:28px 36px 28px 0}}
.right img{{max-width:100%;max-height:540px;filter:drop-shadow(0 8px 24px rgba(40,40,80,.12))}}
.accent{{position:absolute;left:0;bottom:0;width:100%;height:12px;background:#5b54d6}}</style></head><body>
<div class="left"><div class="brand">{mark}<span class="b">polis</span><span class="d">ysw.kr</span></div>
<div class="ttl"><div class="k">{kicker}</div><div class="h">{headline}</div><div class="s">{subline}</div></div>
<div class="tag">NEC 공식 개표 · polis.ysw.kr</div></div>
<div class="right"><img src="data:image/png;base64,{b64}"></div><div class="accent"></div></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", help="한 선거만")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--port", type=int, default=8911)
    args = ap.parse_args()
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
                title = (pg.text_content("#ar-title") or "").strip() if pg.query_selector("#ar-title") else ""
                date_s = (pg.text_content("#ar-date") or "").strip() if pg.query_selector("#ar-date") else ""
                views = _capture_views(pg)
                if not views:
                    print(f"  {slug}: 지도 없음 — skip"); pg.close(); continue
                # 원본 PNG 저장
                outdir = MAPS / slug
                outdir.mkdir(parents=True, exist_ok=True)
                for label, png in views.items():
                    safe = re.sub(r"[^0-9a-zA-Z가-힣_-]", "_", label)
                    (outdir / f"{safe}.png").write_bytes(png)
                # 대표 뷰 선택
                primary = next((views[k] for pref in PRIMARY_PREF for k in views if k == pref), None)
                if primary is None:
                    primary = max(views.values(), key=len)
                # 카드 합성 — kicker=깨끗한 날짜, headline=선거명, subline=뷰 설명
                mdate = re.search(r"\d{4}-\d{2}-\d{2}", date_s)
                kicker = mdate.group(0) if mdate else date_s[:10]
                headline = title or slug
                html = _card_html(mark_svg, kicker, headline, _descriptor(slug), primary)
                pg.set_content(html, wait_until="networkidle"); pg.wait_for_timeout(400)
                (OG).mkdir(exist_ok=True)
                pg.screenshot(path=str(OG / f"{slug}.png"), clip={"x": 0, "y": 0, "width": 1200, "height": 630})
                made.append(slug)
                print(f"  {slug}: {len(views)} views + card ✓")
            except Exception as e:
                print(f"  {slug}: ERROR {e}")
            finally:
                pg.close()
        b.close()
    print(f"완료: {len(made)} 선거 카드 생성")


if __name__ == "__main__":
    main()
