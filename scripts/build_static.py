"""정적 HTML prerender — SEO 위해 회차·직위별 페이지 생성.

polls.html(지선 도구) / history.html을 템플릿으로, manifest.json + elections.json 읽어
서브 디렉터리에 각각 고유 title·meta·OG·initial state 가 박힌 HTML 출력.
루트 index.html은 대시보드(별도 손작성, 프리렌더 안 함).

생성 경로:
  polls 페이지 (지선 9회 여론조사):
    /governor/index.html      (광역단체장)
    /mayor/index.html         (기초단체장)
    /superintendent/index.html(교육감)
    /party/index.html         (정당지지)

  history 페이지:
    /history/presidential/{n}/index.html
    /history/national-assembly/{n}/index.html
    /history/local/{n}/{office_slug}/index.html

polls.html / history.html 자체는 그대로 — 기본(광역/대선) 페이지로 동작.
"""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_TEMPLATE = ROOT / 'polls.html'   # 지선 직위 페이지(/governor/ 등) 템플릿. 루트 index.html은 대시보드(별도, 프리렌더 안 함)
HISTORY_TEMPLATE = ROOT / 'history.html'
MANIFEST = ROOT / 'data/results/manifest.json'
ELECTIONS = ROOT / 'data/elections.json'

SITE = 'https://vote.ysw.kr'  # canonical base. robots/sitemap에 사용.

# polls office → URL slug + Korean label
OFFICE_SLUG = {
    '광역단체장': 'governor',
    '기초단체장': 'mayor',
    '교육감':     'superintendent',
    '정당지지':   'party',
}

# history 지선 office (5/6/7/8회) — 광역·기초·교육감만
LOCAL_OFFICE_SLUG = {
    '광역단체장': 'governor',
    '기초단체장': 'mayor',
    '교육감':     'superintendent',
}

TYPE_LABEL = {
    'presidential':      '대선',
    'national_assembly': '총선',
    'local':             '지선',
}
TYPE_SLUG = {
    'presidential':      'presidential',
    'national_assembly': 'national-assembly',
    'local':             'local',
}


def replace_meta(html: str, title: str, description: str, canonical: str, init_state: dict) -> str:
    """템플릿에서 title/desc/og/canonical/initial-state 부분을 새 값으로 치환."""
    import re
    html = re.sub(r'<title>[^<]*</title>', f'<title>{title}</title>', html, count=1)
    html = re.sub(
        r'<meta name="description" content="[^"]*">',
        f'<meta name="description" content="{description}">',
        html, count=1,
    )
    html = re.sub(
        r'<meta property="og:title" content="[^"]*">',
        f'<meta property="og:title" content="{title}">',
        html, count=1,
    )
    html = re.sub(
        r'<meta property="og:description" content="[^"]*">',
        f'<meta property="og:description" content="{description}">',
        html, count=1,
    )
    html = re.sub(
        r'<link rel="canonical" href="[^"]*">',
        f'<link rel="canonical" href="{canonical}">',
        html, count=1,
    )
    html = re.sub(
        r'<script id="initial-state">[^<]*</script>',
        f'<script id="initial-state">window.__INITIAL_STATE__ = {json.dumps(init_state, ensure_ascii=False)};</script>',
        html, count=1,
    )
    return html


def write_page(path: Path, html: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding='utf-8')


def build_polls(urls: list):
    template = INDEX_TEMPLATE.read_text(encoding='utf-8')
    n_made = 0
    # 루트 / 도 sitemap에 포함 (가장 높은 priority)
    urls.append(('/', '1.0', 'daily'))
    for office_ko, slug in OFFICE_SLUG.items():
        title = f'vote · 9회 지선 {office_ko} 여론조사'
        desc = f'2026 제9회 전국동시지방선거 {office_ko} 여론조사를 시도·시군구 단위로. NESDC 등록 조사 인용.'
        canon = f'/{slug}/'
        html = replace_meta(template, title, desc, canon, {'office': office_ko})
        write_page(ROOT / slug / 'index.html', html)
        urls.append((canon, '0.9', 'daily'))
        n_made += 1
    print(f'polls: {n_made}')


def build_history(manifest: dict, elections: dict, urls: list):
    template = HISTORY_TEMPLATE.read_text(encoding='utf-8')
    n_made = 0
    urls.append(('/history.html', '0.7', 'monthly'))
    for type_key, ns in manifest.items():
        type_short = TYPE_LABEL.get(type_key, type_key)
        type_slug = TYPE_SLUG.get(type_key, type_key)
        for n in ns:
            meta = next((e for e in elections[type_key]['elections'] if e['n'] == n), None)
            if not meta:
                continue
            el_date = meta.get('date', '')
            if type_key == 'local':
                for office_ko, off_slug in LOCAL_OFFICE_SLUG.items():
                    title = f'vote · {n}회 {type_short} {office_ko} ({el_date})'
                    desc = f'{n}회 전국동시지방선거 {office_ko} 결과 ({el_date}) — 시군구 hex 격자 시각화.'
                    canon = f'/history/{type_slug}/{n}/{off_slug}/'
                    init_state = {'type': type_key, 'n': n, 'office': office_ko}
                    html = replace_meta(template, title, desc, canon, init_state)
                    write_page(ROOT / 'history' / type_slug / str(n) / off_slug / 'index.html', html)
                    urls.append((canon, '0.6', 'yearly'))
                    n_made += 1
            else:
                winner = meta.get('winner', '')
                winner_str = f' · {winner} 당선' if winner else ''
                title = f'vote · {n}{type_short} ({el_date}){winner_str}'
                desc = f'{n}{type_short} 결과 ({el_date}) — hex 격자로 지역별 1위 정당·격차 시각화.'
                canon = f'/history/{type_slug}/{n}/'
                init_state = {'type': type_key, 'n': n}
                html = replace_meta(template, title, desc, canon, init_state)
                write_page(ROOT / 'history' / type_slug / str(n) / 'index.html', html)
                urls.append((canon, '0.6', 'yearly'))
                n_made += 1
    print(f'history: {n_made}')


def build_sitemap(urls: list):
    """sitemap.xml · robots.txt 생성."""
    today = date.today().isoformat()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, priority, changefreq in urls:
        lines.append('  <url>')
        lines.append(f'    <loc>{SITE}{path}</loc>')
        lines.append(f'    <lastmod>{today}</lastmod>')
        lines.append(f'    <changefreq>{changefreq}</changefreq>')
        lines.append(f'    <priority>{priority}</priority>')
        lines.append('  </url>')
    lines.append('</urlset>')
    (ROOT / 'sitemap.xml').write_text('\n'.join(lines), encoding='utf-8')

    robots = f"""User-agent: *
Allow: /

Sitemap: {SITE}/sitemap.xml
"""
    (ROOT / 'robots.txt').write_text(robots, encoding='utf-8')
    print(f'sitemap: {len(urls)} URLs, robots.txt')


def main():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    elections = json.loads(ELECTIONS.read_text(encoding='utf-8'))
    urls = []
    build_polls(urls)
    build_history(manifest, elections, urls)
    build_sitemap(urls)


if __name__ == '__main__':
    main()
