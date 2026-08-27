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



def _settle(pg, quiet_ms: int = 900, cap_ms: int = 12000) -> None:
    """SVG 수·크기가 멎을 때까지 기다린다. 고정 대기(2200ms)를 대신한다.

    하네스는 nav·hero·표가 없어 콘텐츠가 가볍다. 그래서 networkidle이 공개 페이지보다
    **일찍** 뜨고, 그 뒤 고정 대기 2,200ms가 렌더 완료 전에 끝났다. 결과가 조용히
    달라진다 — 시군구 비례(sgg-prop)의 헥스 안 점 배치가 매번 다르게 찍혔다.
    같은 하네스를 두 번 찍으면 완전히 동일하므로(평균차 0.00) 렌더러는 결정적이다.
    문제는 '언제 다 그려졌나'를 시간으로 짐작한 것이었다.
    """
    import time
    prev, stable_since, t0 = None, None, time.monotonic()
    while (time.monotonic() - t0) * 1000 < cap_ms:
        sig = pg.evaluate("""()=>{
            const s=[...document.querySelectorAll('svg')].map(n=>{
                const b=n.getBoundingClientRect();
                return Math.round(b.width)+'x'+Math.round(b.height);});
            return s.length+':'+s.join(',')+':'+document.documentElement.scrollHeight;}""")
        now = time.monotonic()
        if sig == prev:
            if stable_since and (now - stable_since) * 1000 >= quiet_ms:
                return
            stable_since = stable_since or now
        else:
            prev, stable_since = sig, None
        pg.wait_for_timeout(150)

def _meta_of(slug: str) -> dict:
    """회차 제목·날짜. **archive_index.json이 정본이다.**

    예전엔 main()이 살아있는 페이지의 #ar-title·#ar-date를 긁고, recompose()는 같은
    값을 archive_index.json에서 읽었다 — 한 파일 안에 사본이 둘이었다. 하네스는 hero를
    안 그리므로 긁을 것도 없고, 애초에 DOM에서 읽을 이유가 없었다.
    """
    global _META_CACHE
    if _META_CACHE is None:
        try:
            _META_CACHE = {e["slug"]: e for e in json.loads(
                (ROOT / "data/archive_index.json").read_text(encoding="utf-8"))}
        except Exception:
            _META_CACHE = {}
    return _META_CACHE.get(slug, {})


_META_CACHE = None

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
    """{view_key: png_bytes} — 지도 SVG를 깔끔한 키로 분류해 캡처.

    ⚠️ **한 키를 여러 그림이 다툰다.** 2026-08-27 관측(4개 회차, 픽셀 해시로 셈):

        dorling      서로 다른 내용 최대 14가지
        sgg-prop                       13가지
        sgg-turnout                     6가지
        result·council                  5가지
        district                        4가지

    이유가 둘이다. (1) _classify는 SVG **클래스만** 보는데 한 클래스가 여러 섹션의
    서로 다른 SVG에 붙어 있다 — 9회 지선은 토글을 누르기도 전에(init) 이미 dorling이
    두 가지다(시도 dorling·시군구 dorling이 같은 ar-sidocluster를 쓴다).
    (2) 거기에 토글 상태가 곱해진다.

    그런데 승자를 **바이트 크기**로 뽑는다. 즉 og/maps/{회차}/dorling.png가 무엇인지를
    지금까지 PNG 압축률이 정해 왔다. 15대 총선 district는 후보들이 18~37바이트 차이라
    조건이 조금만 달라도 승자가 뒤집혔다.

    이건 결정성 문제 이전에 **정확성 문제**다. 페이지의 <figure alt="의석 비례 —
    면적·점=의석수·색=정당">이 실제로 그 그림인지 보증되지 않는다.

    제대로 고치려면 뷰 키를 (섹션 id, 토글 상태)로 식별해야 하는데, 지금 레지스트리는
    그걸 표현하지 못한다 — 클래스 하나가 전부다. 재설계 전까지는 **모호함을 적어 두고
    새로 생기면 잡는다**(아래 ambiguity, tests/test_capture_ambiguity.py).
    """
    views = {}
    seen: dict = {}          # key -> {sha1: 처음 잡힌 태그}

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
            import hashlib
            seen.setdefault(key, {}).setdefault(hashlib.sha1(png).hexdigest()[:8], len(png))
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
                    # 고정 대기가 아니라 **멎을 때까지** 기다린다. 1500ms는 큰 geojson을
                    # 노린 매직 넘버였는데, 뷰마다 완료 시점이 달라 그 시점의 중간 상태가
                    # 찍혔다. 그래서 같은 페이지를 두 번 캡처해도 결과가 달랐다 —
                    # 하네스가 비결정적이라고 판단했던 것의 실제 정체다(2026-08-27 관측:
                    # DOM 마크업은 4회 전부 동일했는데 픽셀만 달랐다).
                    _settle(page)
                    grab()
                except Exception:
                    pass
    _capture_views.ambiguity = {k: len(v) for k, v in seen.items() if len(v) > 1}

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
    # ⚠️ 기본은 archive다. 하네스(render)는 **미완이다** — 아래 write_render_only 주석 참조.
    ap.add_argument("--source", choices=("render", "archive"), default="archive",
                    help="캡처 원본. archive=공개 페이지(현재 정본), "
                         "render=빌드 시점 하네스(.render/ — 미완, 비결정적)")
    ap.add_argument("--keep-render", action="store_true", help=".render/를 지우지 않는다(디버깅)")
    args = ap.parse_args()
    if args.recompose:
        recompose(); return

    mark_svg = FAVICON.read_text(encoding="utf-8")
    slugs = [args.slug] if args.slug else list_slugs()
    amb_all: dict = {}   # 회차 → {뷰 키: 서로 다른 그림 수}
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

    # 하네스 생성은 순수 파이썬이라 playwright import보다 **위**에 둔다 —
    # --list가 브라우저 없이 도는 성질을 지키기 위해서다(3e4603c44에서 그걸 놓쳤다).
    render_root = ROOT / ".render"
    if args.source == "render":
        import importlib.util as _il
        _s = _il.spec_from_file_location("sync_archive_html",
                                         ROOT / "scripts/build/sync_archive_html.py")
        _sa = _il.module_from_spec(_s)
        _s.loader.exec_module(_sa)
        metas = [json.loads(f.read_text(encoding="utf-8"))
                 for f in sorted((ROOT / "data/elections").glob("*.json"))
                 if f.name != "index.json"]
        n = _sa.write_render_only(metas, render_root, only=set(slugs))
        print(f"하네스 {n}회차 생성 → .render/", flush=True)
    base = (f"http://localhost:{args.port}/.render" if args.source == "render"
            else f"http://localhost:{args.port}/archive")
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
                _settle(pg)
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
                _m = _meta_of(slug)
                title = (_m.get("name") or "").strip()
                date_s = (_m.get("date") or "").strip()
                views = _capture_views(pg)
                amb_all[slug] = getattr(_capture_views, 'ambiguity', {}) or {}
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
                    # 재압축을 캡처 경로에 둔다. --shrink-only에만 두면 파이프라인
                    # 산출물이 '찍은 것'과 '커밋된 것' 두 형태로 갈리고, 하네스가
                    # 같은 픽셀을 내놓는지 바이트로 확인할 수가 없다.
                    shrink(raw_dir / f"{key}.png")
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
    # 모호함을 파일로 남긴다. 지금은 고칠 수 없지만(재설계 필요) **새로 생기는 것은
    # 잡을 수 있다** — tests/test_capture_ambiguity.py가 이 파일을 읽는다.
    if amb_all:
        amb_p = ROOT / "data" / "capture_ambiguity.json"
        prev = {}
        if amb_p.is_file():
            try:
                prev = json.loads(amb_p.read_text(encoding="utf-8")).get("slugs") or {}
            except Exception:
                prev = {}
        prev.update(amb_all)
        amb_p.write_text(json.dumps(
            {"_note": "한 뷰 키를 여러 그림이 다툰 횟수(회차별). _capture_views 주석 참조. "
                      "숫자가 2 이상이면 og/maps/{회차}/{키}.png가 무엇인지 PNG 압축률이 "
                      "정하고 있다는 뜻이다. 재설계 전까지 기록만 하고, 새로 생기면 검사가 잡는다.",
             "slugs": dict(sorted(prev.items()))}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        worst = max((max(v.values()) for v in amb_all.values() if v), default=0)
        print(f"⚠️ 모호한 뷰 키가 있는 회차 {len(amb_all)} · 한 키 최대 {worst}가지 "
              f"→ data/capture_ambiguity.json", flush=True)

    if args.source == "render" and not args.keep_render:
        shutil.rmtree(render_root, ignore_errors=True)

    # 전멸에 exit 0을 주지 않는다. 사진은 렌더 능력의 유일한 사본이라, 캡처가 조용히
    # 실패하면 매니페스트가 빈 디렉터리를 관측하고 52쪽이 그림을 잃는다.
    print(f"완료: {len(made)} 선거 카드 생성")
    if len(made) < len(slugs):
        print(f"✗ {len(slugs)}회차 중 {len(made)}개만 만들어졌다 — 하네스를 의심할 것",
              flush=True)
        return 1


if __name__ == "__main__":
    main()
