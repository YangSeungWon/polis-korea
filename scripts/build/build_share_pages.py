"""뷰별 공유 페이지 생성 — share/{slug}/{view}/index.html.

정적 호스팅에선 크롤러가 JS·쿼리를 안 가리므로, "링크 공유 시 그 뷰 사진"을 위해선
뷰마다 별도 URL이 필요하다. 각 og/{slug}/{view}.png 카드에 대해 머리(head)만 있는
초경량 페이지를 깔고: 크롤러껜 그 뷰 og:image를 주고, 사람은 archive 인터랙티브로 즉시
리다이렉트. 결과 불변이라 한 번 생성하면 끝. 검색 인덱스엔 canonical로 archive를 가리켜
중복을 막고, sitemap엔 넣지 않는다(공유 전용).

사용: python scripts/build/build_share_pages.py   (og/ 카드 생성 후 실행)
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OG = ROOT / "og"
SHARE = ROOT / "share"
SITE = "https://polis.ysw.kr"

VIEW_LABEL = {
    "governor": "광역단체장", "council": "광역의원", "dorling": "의석 비례",
    "geo": "지리 지도", "seats": "의석수", "turnout": "투표율",
    "result": "시군구 1위", "sgg-geo": "시군구 지도", "sgg-prop": "시군구 비례",
    "sido1": "시도 1위", "district": "선거구 1위", "district-geo": "선거구 지도",
}

TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex,follow">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
<meta property="og:url" content="{share_url}">
<meta property="og:image" content="{img}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{img}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="canonical" href="{target}">
<meta http-equiv="refresh" content="0; url={target_hash}">
<script>location.replace("{target_hash}");</script>
</head>
<body style="font-family:Pretendard,sans-serif;padding:40px">
<p>{title} — <a href="{target}">결과 보기 →</a></p>
</body>
</html>
"""


def main():
    idx = {e["slug"]: e for e in json.loads((ROOT / "data" / "archive_index.json").read_text(encoding="utf-8"))}
    n_pages = 0
    n_elec = 0
    for slug_dir in sorted(OG.iterdir()):
        if not slug_dir.is_dir() or slug_dir.name == "maps":
            continue
        slug = slug_dir.name
        meta = idx.get(slug, {})
        name = meta.get("name", slug)
        date = meta.get("date", "")
        target = f"/archive/{slug}/"
        any_view = False
        for card in sorted(slug_dir.glob("*.png")):
            view = card.stem
            label = VIEW_LABEL.get(view, view)
            share_url = f"{SITE}/share/{slug}/{view}/"
            html = TEMPLATE.format(
                title=f"{name} · {label} — polis",
                desc=f"{name}({date}) {label} 결과 지도. NEC 공식 개표.",
                img=f"{SITE}/og/{slug}/{view}.png",
                share_url=share_url,
                target=target,
                target_hash=f"{target}#{view}",
            )
            out = SHARE / slug / view / "index.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(html, encoding="utf-8")
            n_pages += 1
            any_view = True
        if any_view:
            n_elec += 1
    print(f"공유 페이지 {n_pages}개 / {n_elec} 선거 생성 → share/")


if __name__ == "__main__":
    main()
