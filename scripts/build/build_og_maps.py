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

# 뷰 표는 data/view_registry.json이 정본이다. 사본을 두면 어긋난다 — 실제로 어긋났었다
# (key 'result'가 한쪽은 '시군구 결과', 다른 쪽은 '시군구 1위'였다).
#
# ⚠️ classify()는 **더 이상 캡처 경로에 없다.** 그리는 쪽이 data-map-host로 자기 정체를
# 밝히므로, 다 그려진 SVG를 클래스로 되짚어 추측할 이유가 없다. 아래 _capture_views 참조.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from view_registry import (PRIMARY_ORDER, key_for, mode_of, host_label,  # noqa: E402
                           is_page_view)



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


# 브라우저 쪽 규칙은 **한 군데**에 둔다. 파이썬에서 셀렉터를 조립하면 여기와 어긋난다.
CAP_JS = r"""
window.__cap = (() => {
  const MIN = 200;                    // 범례·아이콘 SVG를 거른다(토글 안 enc-ic는 15x15)
  const info = b => ({enc: b.dataset.enc || null, label: (b.textContent || '').trim()});

  function toggles(h) {
    const inner = [...h.querySelectorAll('.seg-btn')];
    if (inner.length) return inner;
    // 없으면 **직계 부모까지만** 본다. sgg·sggprop은 토글이 host의 형제다.
    // 한 단계만 더 올라가면 페이지 전체를 긁는다 — 토글이 정말 없는 기초의회에서
    // 18개가 잡혔다(2026-08-27 관측). 그래서 depth 0에서 멈춘다.
    return h.parentElement ? [...h.parentElement.querySelectorAll('.seg-btn')] : [];
  }
  function biggest(h) {
    return [...h.querySelectorAll('svg')]
      .map(s => { const r = s.getBoundingClientRect();
                  return {s, w: Math.round(r.width), h: Math.round(r.height)}; })
      .filter(o => o.w >= MIN && o.h >= MIN)
      .sort((a, b) => b.w * b.h - a.w * a.h)[0] || null;
  }
  return {
    hosts() {
      return [...document.querySelectorAll('[data-map-host]')].map(h => {
        const sec = h.closest('section');
        const h2 = sec && sec.querySelector('h2');
        let title = null, desc = null;
        if (h2) {
          // h2의 **자기 텍스트**만. 안에 물음표 툴팁(.info-pop)이 들어 있어
          // textContent를 쓰면 제목에 설명이 들러붙는다.
          title = [...h2.childNodes].filter(n => n.nodeType === 3)
                    .map(n => n.textContent).join('').trim() || null;
          const pop = h2.querySelector('.info-pop');
          if (pop) desc = pop.textContent.trim();
        }
        return {token: h.dataset.mapHost, section: (sec && sec.id) || null,
                title, desc, toggles: toggles(h).map(info)};
      });
    },
    click(token, enc) {
      const h = document.querySelector('[data-map-host="' + token + '"]');
      if (!h) return 'no-host';
      const b = toggles(h).find(x => (x.dataset.enc || null) === enc);
      if (!b) return 'no-btn';
      b.click();
      return 'ok';
    },
    pick(token) {
      document.querySelectorAll('[data-cap]').forEach(n => n.removeAttribute('data-cap'));
      const h = document.querySelector('[data-map-host="' + token + '"]');
      if (!h) return null;
      const o = biggest(h);
      if (!o) return null;
      o.s.setAttribute('data-cap', '1');
      return {w: o.w, h: o.h, mode: h.dataset.mode || null};
    }
  };
})();
"""


def _capture_views(page, slug: str = ""):
    """{키: {png, ...}} — **발견이 아니라 열거로** 캡처한다.

    옛 방식은 다 그려진 SVG를 클래스로 되짚어 분류했다. 그런데 한 클래스가 여러
    (섹션, 모드)에 붙어 있어서, 같은 키를 여러 그림이 다투고 **바이트 큰 쪽이**
    이겼다 — og/maps/{회차}/dorling.png가 무엇인지를 PNG 압축률이 정했다
    (2026-08-27 관측: 한 키에 최대 14가지, 15대 총선 district는 후보들이
    18~37바이트 차이라 조건이 조금만 달라도 승자가 뒤집혔다).

    이제 캡처는 **자기가 무엇을 눌렀는지 안다.** 지도가 data-map-host로 정체를
    밝히고, 토글 버튼의 data-enc가 모드를 말한다. 키는 그 둘의 곱이다.

    라벨도 여기서 기록한다. 눌린 버튼의 글씨와 섹션 제목·설명을 그대로 적어 두면
    페이지의 캡션이 거기서 나온다 — 글과 그림이 한 출처에서 나오면 어긋날 자리가
    없다. 레지스트리에 한글 라벨을 손으로 적지 않는 이유다.
    """
    import hashlib
    page.evaluate(CAP_JS)
    out: dict[str, dict] = {}
    by_img: dict[str, list[str]] = {}     # 픽셀 해시 → 키들
    problems: list[str] = []

    for h in page.evaluate("() => __cap.hosts()"):
        token = h["token"]
        # 토글이 있으면 각 enc를, 없으면 단일 뷰 하나를. 다만 **토글이 없는 것과
        # 모드를 모르는 것은 다르다** — 모드가 하나뿐이면 토글이 안 그려지는데,
        # 그때도 렌더러는 data-mode로 무엇을 그렸는지 말한다. 그걸 안 읽으면 같은
        # 그림이 어느 회차에선 sggturn-hex, 어느 회차에선 sggturn이 된다.
        # (enc, label, 눌러야 하나) — 선언으로 안 모드는 이미 화면에 떠 있으므로
        # 누를 버튼이 없다. 그걸 구분 안 하면 '버튼을 못 눌렀다'며 그 뷰를 버린다.
        plan = [(b["enc"], b["label"], True) for b in h["toggles"] if b["enc"]]
        if not plan:
            declared = (page.evaluate("(t) => __cap.pick(t)", token) or {}).get("mode")
            plan = [(declared, None, False)] if declared else [(None, None, False)]
        for enc, label, press in plan:
            mode = None
            if enc is not None:
                mode = mode_of(enc)
                if mode is None:
                    # 레지스트리가 모르는 토글 값. 조용히 넘기면 그 뷰가 통째로
                    # 사라지므로 시끄럽게 군다.
                    problems.append(f"{token}: 모르는 enc {enc!r} — 레지스트리 modes에 없다")
                    continue
                if press:
                    if page.evaluate("([t,e]) => __cap.click(t,e)", [token, enc]) != "ok":
                        problems.append(f"{token}/{enc}: 버튼을 못 눌렀다")
                        continue
                    _settle(page)
            got = page.evaluate("(t) => __cap.pick(t)", token)
            if not got:
                problems.append(f"{token}/{enc}: 200px 넘는 SVG가 없다")
                continue
            # 렌더러가 data-mode를 찍는 곳(기초의회 계열)에선 **클릭이 먹었는지**를
            # 공짜로 확인할 수 있다. 안 먹으면 앞 모드의 그림이 다음 키로 저장된다.
            if got.get("mode") and enc and got["mode"] != enc:
                problems.append(f"{token}/{enc}: 클릭 후에도 data-mode={got['mode']!r}")
                continue
            el = page.query_selector('[data-cap="1"]')
            if el is None:
                problems.append(f"{token}/{enc}: 캡처 대상을 못 잡았다")
                continue
            try:
                png = el.screenshot(omit_background=True)
            except Exception as e:
                problems.append(f"{token}/{enc}: screenshot 실패 {e}")
                continue
            key = key_for(token, mode)
            if key in out:
                problems.append(f"{key}: 키가 두 번 나왔다 — host 토큰이 중복이다")
                continue
            out[key] = {
                "png": png, "host": token, "mode": mode, "enc": enc,
                "label": label, "section": h["section"],
                "title": h["title"] or host_label(token),
                "title_src": "h2" if h["title"] else "registry",
                "desc": h["desc"], "w": got["w"], "h": got["h"],
                "page": is_page_view(token, mode),
            }
            by_img.setdefault(hashlib.sha1(png).hexdigest()[:12], []).append(key)

    # 옛 모호함(한 키에 여러 그림)은 열거식에선 구조적으로 불가능하다. 대신 **반대**를
    # 잰다 — 서로 다른 키가 같은 그림이면 토글 클릭이 조용히 안 먹은 것이다.
    _capture_views.same_image = {k: v for k, v in
                                 ((h, ks) for h, ks in by_img.items() if len(ks) > 1)}
    _capture_views.problems = problems
    for msg in problems:
        print(f"    ⚠️ {slug} {msg}", flush=True)
    return out


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


def _make_card(pg, mark_svg, kicker, headline, subline, map_png, out: Path):
    """지도 PNG 하나로 1200×630 공유 카드를 만든다."""
    pg.set_content(_card_html(mark_svg, kicker, headline, subline, map_png),
                   wait_until="networkidle")
    pg.wait_for_timeout(350)
    out.parent.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": 1200, "height": 630})


def _card_sub(slug: str, key: str) -> str:
    """카드 부제. 캡처가 적어 둔 라벨에서 나온다(data/map_captures.json)."""
    v = (_captures().get(slug) or {}).get(key) or {}
    ttl, lbl = v.get("title"), v.get("label")
    return " · ".join(x for x in (ttl, lbl) if x) or key


_CAP_CACHE = None


def _captures() -> dict:
    global _CAP_CACHE
    if _CAP_CACHE is None:
        f = ROOT / "data" / "map_captures.json"
        try:
            _CAP_CACHE = json.loads(f.read_text(encoding="utf-8"))["slugs"]
        except Exception:
            _CAP_CACHE = {}
    return _CAP_CACHE


def recompose():
    """캐시된 지도(og/maps/{slug}/*.png)로 **대표 카드만** 다시 만든다 — favicon이
    바뀔 때 페이지 재렌더·지도 재캡처 없이 chrome만 동기화.

    2026-08까지는 뷰마다 카드를 하나씩(og/{slug}/{key}.png, 402장) 만들었다. 그걸
    쓰던 share/ 402쪽이 사라지면서 소비자가 없어졌다 — 아무도 안 보는 그림을
    회차당 8장씩 굽고 있었다. 페이지 og:image로 쓰는 og/{slug}.png만 남긴다."""
    from playwright.sync_api import sync_playwright
    meta = {e["slug"]: e for e in json.loads(
        (ROOT / "data/archive_index.json").read_text(encoding="utf-8"))}
    mark_svg = FAVICON.read_text(encoding="utf-8")
    made = 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
        for slug_dir in sorted(d for d in MAPS.iterdir() if d.is_dir()):
            slug = slug_dir.name
            keys = sorted(f.stem for f in slug_dir.glob("*.png"))
            if not keys:
                continue
            m = meta.get(slug, {})
            primary = next((k for k in PRIMARY_ORDER if k in keys), keys[0])
            _make_card(pg, mark_svg, (m.get("date") or "")[:10], m.get("name") or slug,
                       _card_sub(slug, primary), (slug_dir / f"{primary}.png").read_bytes(),
                       OG / f"{slug}.png")
            made += 1
        b.close()
    print(f"recompose: 대표 카드 {made}장 (캐시 지도 재사용)")


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
    cap_all: dict = {}   # 회차 → {뷰 키: 캡처가 기록한 라벨·크기}
    dup_all: dict = {}   # 회차 → 같은 그림이 된 키들·문제 목록
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
                views = _capture_views(pg, slug)
                dup_all[slug] = {
                    "same_image": getattr(_capture_views, 'same_image', {}) or {},
                    "problems": getattr(_capture_views, 'problems', []) or [],
                }
                if not views:
                    print(f"  {slug}: 지도 없음 — skip"); pg.close(); continue
                mdate = re.search(r"\d{4}-\d{2}-\d{2}", date_s)
                kicker = mdate.group(0) if mdate else date_s[:10]
                headline = title or slug
                raw_dir = MAPS / slug
                raw_dir.mkdir(parents=True, exist_ok=True)
                # 옛 키의 PNG를 남겨 두면 매니페스트가 디스크를 관측해서 그것까지
                # 뷰로 적는다 — 페이지가 사라진 이름의 그림을 걸게 된다.
                for stale in raw_dir.glob("*.png"):
                    if stale.stem not in views:
                        stale.unlink()
                rec = {}
                for key, v in views.items():
                    f = raw_dir / f"{key}.png"
                    f.write_bytes(v["png"])              # 원본(투명)
                    # 재압축을 캡처 경로에 둔다. --shrink-only에만 두면 파이프라인
                    # 산출물이 '찍은 것'과 '커밋된 것' 두 형태로 갈린다.
                    shrink(f)
                    rec[key] = {k: v[k] for k in
                                ("host", "mode", "enc", "label", "section",
                                 "title", "title_src", "desc", "w", "h", "page")}
                cap_all[slug] = dict(sorted(rec.items()))
                # 대표 카드 og/{slug}.png (archive·poll 페이지 기본 og:image).
                # 뷰별 카드는 안 만든다 — share/가 사라져 소비자가 없다.
                primary = next((k for k in PRIMARY_ORDER if k in views), next(iter(views)))
                _make_card(pg, mark_svg, kicker, headline,
                           " · ".join(x for x in (views[primary].get("title"),
                                                  views[primary].get("label")) if x) or primary,
                           views[primary]["png"], OG / f"{slug}.png")
                made.append((slug, list(views)))
                print(f"  {slug}: {len(views)} views {sorted(views)} ✓", flush=True)
            except Exception as e:
                print(f"  {slug}: ERROR {e}")
            finally:
                pg.close()
        b.close()
    # 캡처가 기록한 것을 파일로 남긴다. 페이지의 alt·figcaption이 여기서 나온다 —
    # 레지스트리에 한글 라벨을 손으로 적지 않는 이유다(build_map_manifest가 읽는다).
    def _merge(path: Path, key: str, add: dict, note: str) -> None:
        prev = {}
        if path.is_file():
            try:
                prev = json.loads(path.read_text(encoding="utf-8")).get(key) or {}
            except Exception:
                prev = {}
        prev.update(add)
        path.write_text(json.dumps({"_note": note, key: dict(sorted(prev.items()))},
                                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    if cap_all:
        _merge(ROOT / "data" / "map_captures.json", "slugs", cap_all,
               "빌드 생성물 — scripts/build/build_og_maps.py가 캡처하며 적는다. "
               "눌린 토글 버튼의 글씨(label)와 섹션 제목·설명(title·desc)이 그대로 "
               "페이지의 figcaption·alt가 된다. 손으로 고치지 말 것 — 다음 캡처가 덮는다.")
    if dup_all:
        worst = max((len(ks) for d in dup_all.values()
                     for ks in d["same_image"].values()), default=0)
        nprob = sum(len(d["problems"]) for d in dup_all.values())
        _merge(ROOT / "data" / "capture_ambiguity.json", "slugs", dup_all,
               "빌드 생성물. **옛 모호함(한 키에 여러 그림)은 열거식 캡처에서 구조적으로 "
               "불가능해졌다** — 키가 (host, mode)로 확정되고 각 조합을 정확히 한 번 찍는다. "
               "대신 반대를 잰다: same_image는 서로 다른 키가 **같은 그림**이 된 경우로, "
               "토글 클릭이 조용히 안 먹었다는 뜻이다. problems는 캡처가 건너뛴 뷰다. "
               "둘 다 0이어야 한다.")
        if worst or nprob:
            print(f"⚠️ 같은 그림이 된 키 최대 {worst}개 · 건너뛴 뷰 {nprob}개 "
                  f"→ data/capture_ambiguity.json", flush=True)
        else:
            print("모호함 0 · 건너뛴 뷰 0", flush=True)

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
