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
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OG = ROOT / "og"
MAPS = OG / "maps"
FAVICON = ROOT / "favicon.svg"

# SVG 클래스 substring → 깔끔한 뷰 키·라벨·설명. 토글 캡처분도 같은 클래스라 일관 분류.
# 뷰 표는 data/view_registry.json이 정본이다. 여기 두면 svg-export.js·
# build_share_pages.py의 사본과 어긋난다 — 실제로 어긋나 있었다(key 'result'가
# 한쪽은 '시군구 결과', 다른 쪽은 '시군구 1위'였다).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from view_registry import VIEW_DEFS, PRIMARY_ORDER, classify as _classify, view_meta  # noqa: E402



def shrink(path: Path) -> tuple[int, int]:
    """PNG를 256색 팔레트로 다시 저장. (전, 후) 바이트.

    지도는 정당색 몇 가지 + 격차 명도 + 글씨가 전부라 원래 색이 6,449개쯤 나오는데,
    256색으로 줄여도 눈으로 구분이 안 된다(글씨 선명도·명도 단계 유지 확인). 대신
    57KB → 21KB로 3분의 1이 된다.

    글씨를 살리면서 og/가 78MB → 106MB로 늘었다 — 저장소가 GitHub Pages로 서빙되고
    커밋마다 새 blob이 쌓이는 구조라, 재압축은 선택이 아니라 필요다.
    """
    from PIL import Image
    before = path.stat().st_size
    im = Image.open(path)
    if im.mode == "RGBA":
        # 알파가 있으면 팔레트로 못 줄인다(투명이 깨진다). 지금 캡처는 전부 RGB지만
        # omit_background=True가 언젠가 실제로 먹으면 여기로 온다.
        return before, before
    im.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                               dither=Image.Dither.NONE).save(path, "PNG", optimize=True)
    return before, path.stat().st_size

def list_slugs() -> list[str]:
    """캡처 대상 회차. **매니페스트가 정본**이다(data/map_manifest.json).

    2026-08 S0에서 VIEW_DEFS를 걷어낼 때 이 함수가 같은 범위에 있어 함께 지워졌다.
    --slug 단일 실행은 이 함수를 안 타서 못 봤고, 전량 실행에서 NameError로 죽었다.
    build_og_maps는 playwright+로컬 서버가 필요해 regen_check에 없다 — 그래서
    아래 --list가 있다. 브라우저 없이 이 경로만 태워 보는 연기 시험용이다.

    '없는 게 맞는' 회차(재보궐·간선)는 건너뛴다. 매니페스트가 이유를 들고 있으므로
    여기서 다시 판단하지 않는다.
    """
    mf = ROOT / "data" / "map_manifest.json"
    if mf.is_file():
        try:
            els = json.loads(mf.read_text(encoding="utf-8"))["elections"]
        except Exception:
            els = {}
        if els:
            skip = ("재보궐", "간선")
            return sorted(k for k, v in els.items()
                          if not (v.get("absent") or "").startswith(skip))
    # 매니페스트가 아직 없으면(최초 1회) 디렉터리를 본다.
    return sorted(p.name for p in (ROOT / "archive").iterdir()
                  if p.is_dir() and (p / "index.html").exists())


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
                    page.wait_for_timeout(1500)   # 큰 geojson(선거구·시군구 geo) 로드 여유
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
    ap.add_argument("--list", action="store_true",
                    help="대상 회차만 출력하고 끝낸다(브라우저 안 띄움)")
    ap.add_argument("--shrink-only", action="store_true",
                    help="캡처 없이 og/ PNG 재압축만")
    args = ap.parse_args()
    if args.recompose:
        recompose(); return

    mark_svg = FAVICON.read_text(encoding="utf-8")
    slugs = [args.slug] if args.slug else list_slugs()
    if args.shrink_only:
        tot_b = tot_a = 0
        for f in sorted((ROOT / "og").rglob("*.png")):
            b, a = shrink(f)
            tot_b += b
            tot_a += a
        print(f"재압축 {tot_b/1024/1024:.0f}MB → {tot_a/1024/1024:.0f}MB "
              f"({tot_a/tot_b:.0%})")
        return 0
    if args.list:
        # 브라우저 없이 대상 산정까지만 — 연기 시험(tests/test_build_smoke.py)이 쓴다.
        print(f"대상 {len(slugs)}회차: {', '.join(slugs[:5])}…")
        return 0
    if args.limit:
        slugs = slugs[:args.limit]
    base = f"http://localhost:{args.port}/archive"
    MAPS.mkdir(parents=True, exist_ok=True)

    made = []
    # playwright import는 **여기**여야 한다. 위로 올리면 --list·--shrink-only가
    # 브라우저 없이 도는 경로가 아니게 된다 — 연기 시험이 그걸 잡았다(CI엔
    # playwright가 없다).
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        for slug in slugs:
            pg = b.new_page(viewport={"width": 1320, "height": 1700})
            try:
                pg.goto(f"{base}/{slug}/", wait_until="networkidle", timeout=20000)
                pg.wait_for_timeout(2200)
                # 지도 위 오버레이가 캡처에 찍히지 않게 숨김(element.screenshot은 겹친 요소 포함).
                #   저장버튼은 display:none. 인맵 방식 토글은 opacity:0 — 뷰 전환 클릭은 유지하되 화면엔 안 찍힘.
                #   지도·차트 내 모든 텍스트 라벨(시도·시군구명·후보명·득표율)은 썸네일·카드서 안 읽히는
                #   잡음 → 캡처서 전부 숨김. 캡처 대상은 전부 색지도/반원이라 텍스트 불필요(추이 라인차트는
                #   캡처 안 됨). 제목·날짜는 카드 헤드라인(HTML)이 따로 표시.
                pg.add_style_tag(content=(
                    ".svg-save-btn{display:none!important}"
                    ".ar-sido-toggle,.sgg-mode-toggle{opacity:0!important}"
                    # 2026-08까지는 여기서 svg text를 전부 숨겼다. 근거는 "썸네일·카드서
                    # 안 읽히는 잡음"이었고 48px 썸네일 기준으론 맞다. 그런데 같은 PNG를
                    # 본문 그림으로 쓰기 시작하면 반대가 된다 — 지역명·후보명·득표율이
                    # 빠진 색지도는 혼자서는 아무 말도 못 한다. 공유될 때도 마찬가지다.
                    # 글씨를 살리고, 잡음이 되는 건 썸네일 크기(48px)뿐이라 감수한다.
                    ""
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
