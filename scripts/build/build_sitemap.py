"""sitemap.xml 자동 생성.

소스:
  - 정적 메인 페이지 (수동 list)
  - archive/{eid}/index.html (디렉토리 자동 스캔)
  - history 24 prerender (data/elections/index.json 또는 디렉토리 스캔)
  - byelection/, about/data-coverage/

lastmod:
  - archive·history: data/elections/{id}.json의 archive.fetched_at 또는 date
  - 정적: 오늘 (changefreq에 의존)

priority:
  1.0  /  (홈)
  0.9  주요 진입 (governor/mayor/byelection/history/timeline/polls)
  0.7  archive 활성 회차 (9th-local-2026)
  0.6  archive 옛 회차 / history prerender
  0.5  about·기타

사용: python3 scripts/build/build_sitemap.py
"""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://polis.ysw.kr"
TODAY = date.today().isoformat()

# 정적 메인 페이지
STATIC = [
    ("/", "daily", "1.0"),
    ("/governor/", "daily", "0.9"),
    ("/mayor/", "daily", "0.9"),
    ("/superintendent/", "daily", "0.9"),
    ("/byelection.html", "daily", "0.9"),
    ("/byelection/", "weekly", "0.8"),
    ("/history.html", "weekly", "0.9"),
    ("/timeline.html", "weekly", "0.8"),
    ("/polls.html", "daily", "0.8"),
    ("/party/", "weekly", "0.7"),
    ("/about/data-coverage/", "weekly", "0.5"),
]


def archive_urls() -> list[tuple[str, str, str]]:
    out = []
    arch_root = ROOT / "archive"
    active = set()
    try:
        idx = json.loads((ROOT / "data/elections/index.json").read_text(encoding="utf-8"))
        active = set(idx.get("active", []))
    except Exception:
        pass
    for d in sorted(arch_root.iterdir()):
        if not (d / "index.html").exists():
            continue
        eid = d.name
        meta_path = ROOT / f"data/elections/{eid}.json"
        lastmod = TODAY
        if meta_path.exists():
            try:
                m = json.loads(meta_path.read_text(encoding="utf-8"))
                fetched = (m.get("archive") or {}).get("results_fetched_at") or m.get("date")
                if fetched:
                    lastmod = fetched[:10]
            except Exception:
                pass
        priority = "0.7" if eid in active else "0.6"
        freq = "daily" if eid in active else "monthly"
        out.append((f"/archive/{eid}/", freq, priority, lastmod))
    return out


def history_urls() -> list[tuple[str, str, str]]:
    """history/{type}/{n}/[office]/ prerender 디렉토리 스캔."""
    out = []
    hroot = ROOT / "history"
    if not hroot.exists():
        return out
    for p in sorted(hroot.rglob("index.html")):
        rel = p.relative_to(ROOT).parent.as_posix()
        out.append((f"/{rel}/", "monthly", "0.6", TODAY))
    return out


def url_block(loc: str, freq: str, priority: str, lastmod: str) -> str:
    return (
        f"  <url>\n"
        f"    <loc>{BASE}{loc}</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"    <changefreq>{freq}</changefreq>\n"
        f"    <priority>{priority}</priority>\n"
        f"  </url>"
    )


def main():
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, freq, priority in STATIC:
        lines.append(url_block(loc, freq, priority, TODAY))
    for loc, freq, priority, lastmod in archive_urls():
        lines.append(url_block(loc, freq, priority, lastmod))
    for loc, freq, priority, lastmod in history_urls():
        lines.append(url_block(loc, freq, priority, lastmod))
    lines.append('</urlset>')
    out = "\n".join(lines) + "\n"
    (ROOT / "sitemap.xml").write_text(out, encoding="utf-8")
    print(f"→ sitemap.xml: {len(STATIC)} static + "
          f"{len(archive_urls())} archive + {len(history_urls())} history")


if __name__ == "__main__":
    main()
