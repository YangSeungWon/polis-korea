#!/usr/bin/env python3
"""루트 OG 공유 카드(og.png, 1200×630) 생성 — favicon 마크 + 사이트 슬로건.

전 페이지 기본 og:image. favicon.svg가 바뀌면 재실행해 파생 일치(투표함 아이콘 동기화).
재현: python scripts/build/build_og_root.py  (Playwright + Pretendard CDN)
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAVICON = ROOT / "favicon.svg"
OUT = ROOT / "og.png"


def card_html(mark_svg: str) -> str:
    mark = mark_svg.replace("<svg ", '<svg width="96" height="96" ', 1)
    return f"""<!doctype html><html><head><meta charset=utf-8>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.min.css">
<style>
*{{margin:0;box-sizing:border-box}}
body{{width:1200px;height:630px;font-family:Pretendard,sans-serif;background:#f6f7fb;position:relative;overflow:hidden}}
.hex{{position:absolute;top:-90px;right:-70px;opacity:.5}}
.wrap{{position:absolute;inset:0;padding:64px 70px;display:flex;flex-direction:column}}
.brand{{display:flex;align-items:center;gap:18px}}
.brand .txt{{display:flex;flex-direction:column;line-height:1}}
.brand .b{{font-size:54px;font-weight:800;letter-spacing:-2px;color:#0a0e1a}}
.brand .d{{font-size:26px;font-weight:600;color:#8a93a3;margin-top:4px}}
.ttl{{font-size:74px;font-weight:800;letter-spacing:-3px;line-height:1.1;color:#0a0e1a;margin-top:auto;word-break:keep-all}}
.ttl .accent{{color:#5b54d6}}
.sub{{font-size:33px;font-weight:600;color:#4a5160;margin-top:20px}}
.foot{{display:flex;align-items:center;gap:18px;margin-top:36px}}
.pill{{font-size:24px;font-weight:700;color:#5b54d6;background:rgba(91,84,214,.1);padding:8px 18px;border-radius:24px;letter-spacing:.3px}}
.src{{font-size:26px;font-weight:600;color:#8a93a3}}
.bar{{position:absolute;left:0;bottom:0;width:100%;height:12px;background:#5b54d6}}
</style></head><body>
<div class="hex"><svg width="520" height="520" viewBox="0 0 100 100" fill="none">
  <path d="M50 4 L90 27 V73 L50 96 L10 73 V27 Z" stroke="#168f8f" stroke-width="1.4" opacity="0.28"/>
  <path d="M50 18 L78 34 V66 L50 82 L22 66 V34 Z" stroke="#8a93a3" stroke-width="1.4" opacity="0.22"/>
</svg></div>
<div class="wrap">
  <div class="brand">{mark}<div class="txt"><span class="b">polis</span><span class="d">ysw.kr</span></div></div>
  <div class="ttl">한국 선거, <span class="accent">데이터</span>로 본다</div>
  <div class="sub">선거 결과 · 여론조사를 지도와 추세로</div>
  <div class="foot"><span class="pill">NEC · NESDC</span><span class="src">공식 데이터 · 1948–2026</span></div>
</div>
<div class="bar"></div>
</body></html>"""


def main():
    from playwright.sync_api import sync_playwright
    html = card_html(FAVICON.read_text(encoding="utf-8"))
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
        pg.set_content(html, wait_until="networkidle")
        pg.wait_for_timeout(450)
        pg.screenshot(path=str(OUT), clip={"x": 0, "y": 0, "width": 1200, "height": 630})
        b.close()
    print(f"→ {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
