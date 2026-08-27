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
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_sitemap as _sitemap   # noqa: E402  포괄 sitemap(+robots) 단일 출처
import result_tables as _rt        # noqa: E402  결과 표 — archive와 같은 것을 쓴다
import view_registry as _vr        # noqa: E402  뷰 라벨 — 네 번째 표를 만들지 않는다

ROOT = Path(__file__).resolve().parents[2]
INDEX_TEMPLATE = ROOT / 'polls.html'   # 지선 직위 페이지(/governor/ 등) 템플릿. 루트 index.html은 대시보드(별도, 프리렌더 안 함)
HISTORY_TEMPLATE = ROOT / 'history.html'
MANIFEST = ROOT / 'data/results/manifest.json'
ELECTIONS = ROOT / 'data/elections.json'

SITE = 'https://polis.ysw.kr'  # canonical base. robots/sitemap에 사용.

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
# 제목 앞머리용 — 사람이 검색창에 치는 이름. TYPE_LABEL은 화면 라벨용 내부 약어라
# 제목에 쓰면 아무도 찾지 않는 말이 제일 좋은 자리를 차지한다('지선 결과' 0회 검색).
TYPE_QUERY = {
    'presidential':      '대통령선거',
    'national_assembly': '총선',
    'local':             '지방선거',
}
# 회차 단위 — 대선·총선은 '대'(사람·기관 연속), 지선은 '회'(반복 행사).
TYPE_UNIT = {'presidential': '대', 'national_assembly': '대', 'local': '회'}
TYPE_SLUG = {
    'presidential':      'presidential',
    'national_assembly': 'national-assembly',
    'local':             'local',
}


def replace_meta(html: str, title: str, description: str, canonical: str, init_state: dict, og_image: str = None) -> str:
    """템플릿에서 title/desc/og/canonical/initial-state 부분을 새 값으로 치환.
    og_image 주면 선거별 결과지도 카드로 og:image·twitter:image 교체."""
    import re
    html = re.sub(r'<title>[^<]*</title>', f'<title>{title}</title>', html, count=1)
    if og_image:
        html = re.sub(r'<meta property="og:image" content="[^"]*">',
                      f'<meta property="og:image" content="{og_image}">', html, count=1)
        html = re.sub(r'<meta name="twitter:image" content="[^"]*">',
                      f'<meta name="twitter:image" content="{og_image}">', html, count=1)
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




def _eul(word: str) -> str:
    """받침 유무로 을/를. '광역단체장을(를)'처럼 두 개를 다 적으면 기계가 쓴 티가 난다."""
    if not word:
        return '를'
    c = ord(word[-1])
    if not (0xAC00 <= c <= 0xD7A3):     # 한글 음절이 아니면 판단하지 않는다
        return '를'
    return '을' if (c - 0xAC00) % 28 else '를'


# 시군구명 → /region/ slug. 모호하지 않은 것만 — '중구'는 여러 시도에 있어
# sido 없이는 어디인지 정할 수 없다(build_person_pages와 같은 규칙).
_REGION_SLUG: dict | None = None


def _region_slug(sido: str, sigungu: str) -> str:
    global _REGION_SLUG
    if _REGION_SLUG is None:
        _REGION_SLUG = {d.name for d in sorted((ROOT / 'region').iterdir())
                        if d.is_dir()} if (ROOT / 'region').exists() else set()
    cand = f'{sido}-{sigungu}'
    return cand if cand in _REGION_SLUG else ''


def office_static_block(office_ko: str) -> str:
    """직위 페이지(/governor/ 등)의 그 직위만의 정적 내용.

    네 페이지가 polls.html 한 틀에서 나오면서 렌더 전 본문이 1,228자로 **완전히
    같았다**(감사: top 중복 4). 화면에서는 JS가 직위별로 다른 것을 그리지만,
    크롤러가 보는 문서는 넷 다 같은 문서다 — 그중 셋은 sitemap priority 0.9다.
    /polls/{slug}/에서 쓴 방법(PE_STATIC)을 그대로 직위에도 적용한다.

    없는 것은 적지 않는다 — 조사가 0건이면 빈 문자열을 돌려주고 마커만 지워진다.
    """
    path = ROOT / 'data' / 'polls' / 'aggregated.json'
    if not path.exists():
        return ''
    try:
        polls = json.loads(path.read_text(encoding='utf-8')).get('polls') or []
    except Exception:                                            # noqa: BLE001
        return ''
    sel = [p for p in polls
           if p.get('office_level') == office_ko and not p.get('is_self_poll')]
    if not sel:
        return ''
    ends = sorted(p['period_end'] for p in sel if p.get('period_end'))
    agencies = sorted({p.get('agency', '') for p in sel if p.get('agency')})
    span = (f'조사 기간 {_esc(ends[0])} ~ {_esc(ends[-1])} · ' if ends else '')

    # 지역 분포 — 조사가 많이 몰린 곳부터. 지역 페이지로 나가는 길이기도 하다.
    counts: dict = {}
    for p in sel:
        sido, sigungu = p.get('sido') or '', p.get('sigungu') or ''
        key = (sido, sigungu) if office_ko == '기초단체장' else (sido, '')
        if key[0]:
            counts[key] = counts.get(key, 0) + 1
    top = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:12]
    items = []
    for (sido, sigungu), c in top:
        label = f'{sido} {sigungu}'.strip()
        slug = _region_slug(sido, sigungu) if sigungu else ''
        inner = (f'<a href="/region/{quote(slug)}/">{_esc(label)}</a>'
                 if slug else _esc(label))
        items.append(f'<li>{inner} <span class="pe-n">{c}건</span></li>')
    region_html = (f'<details class="pe-static-more"><summary>조사가 많은 지역 '
                   f'{len(counts)}곳 중 {len(top)}곳</summary>'
                   f'<ul class="pe-agency-list">{"".join(items)}</ul></details>'
                   ) if items else ''

    li = ''.join(f'<li>{_esc(a)}</li>' for a in agencies[:8])
    more = f'<li>외 {len(agencies) - 8}곳</li>' if len(agencies) > 8 else ''
    return (
        f'<section class="pe-static"><h2 class="pe-static-title">'
        f'2026 지방선거 {_esc(office_ko)} 여론조사</h2>'
        f'<p class="pe-static-lede">2026년 6월 3일 제9회 전국동시지방선거 '
        f'{_esc(office_ko)}{_eul(office_ko)} 대상으로 중앙선거여론조사심의위원회(NESDC)에 '
        f'등록·공표된 조사 <b>{len(sel):,}건</b>입니다. {span}'
        f'조사기관 {len(agencies)}곳.</p>'
        f'<p class="pe-static-lede">기관마다 표본·방법이 달라 같은 지역에서도 값이 '
        f'갈립니다. 아래에서 조사별 표본수·응답률·표본오차를 함께 봅니다.</p>'
        f'{region_html}'
        f'<details class="pe-static-more"><summary>조사기관 {len(agencies)}곳</summary>'
        f'<ul class="pe-agency-list">{li}{more}</ul></details>'
        f'<p class="pe-static-links"><a href="/archive/9th-local-2026/">'
        f'제9회 지방선거 아카이브 — 결과·여론조사·출구조사</a></p></section>'
    )


def build_polls(urls: list):
    template = INDEX_TEMPLATE.read_text(encoding='utf-8')
    n_made = 0
    # 루트 / 도 sitemap에 포함 (가장 높은 priority)
    urls.append(('/', '1.0', 'daily'))
    for office_ko, slug in OFFICE_SLUG.items():
        # 정당지지는 후보를 묻는 조사가 아니다 — 꼬리말을 직위에 맞춘다.
        tail = '정당 지지율' if office_ko == '정당지지' else '후보 지지율'
        title = f'2026 지방선거 {office_ko} 여론조사 — 제9회 지선 {tail} | polis'
        desc = (f'2026 제9회 전국동시지방선거 {office_ko} 여론조사를 시도·시군구 단위로. '
                f'후보별 지지율과 판세를 NESDC 등록 조사만 인용해.')
        canon = f'/{slug}/'
        html = replace_meta(template, title, desc, canon, {'office': office_ko})
        blk = office_static_block(office_ko)
        if not blk:
            raise SystemExit(f'office_static_block 비었음: {office_ko} — '
                             '네 직위 페이지가 다시 같은 문서가 된다')
        html = html.replace('<!-- PE_STATIC --><!-- /PE_STATIC -->', blk, 1)
        write_page(ROOT / slug / 'index.html', html)
        urls.append((canon, '0.9', 'daily'))
        n_made += 1
    print(f'polls: {n_made}')


ELECTIONS_DIR = ROOT / 'data' / 'elections'


# 폴 viz 지원 종류 — 지선(시도/시군구)·대선(시도 비례+후보추이)·총선(정당추이; 지역구 hex는 후속).
POLL_VIZ_KINDS = ('local', 'presidential', 'general_election')


def _poll_election_meta(el: dict) -> dict | None:
    """elections/{id}.json → per-election 폴 페이지 __INITIAL_STATE__.election.
    aggregated 폴 데이터가 실재하고 viz 지원 종류인 회차만."""
    kind = el.get('kind')
    if kind not in POLL_VIZ_KINDS:
        return None
    ar = el.get('archive') or {}
    polls_path = ar.get('polls_path')
    if not polls_path or not (ROOT / polls_path).exists():
        return None
    bo = el.get('blackout') or {}
    date_s = el.get('date', '')
    # 블랙아웃 없으면(옛 회차) 선거일 기준 기본값 — 과거라 어차피 비활성.
    bstart = bo.get('start') or (date_s + 'T00:00:00+09:00')
    bend = bo.get('end') or (date_s + 'T18:00:00+09:00')
    roster = f'data/raw/nec_roster_{el.get("n")}th.json' if kind == 'local' else None
    results_path = ar.get('results_path') or ''
    # 기초단체장 등 시군구 단위 결과가 별도 파일(.sigungu.json)에 있는 회차(7·8회) — 있으면 함께 주입해 병합 로드.
    sigungu_results = results_path[:-5] + '.sigungu.json' if results_path.endswith('.json') else ''
    return {
        'slug': el['id'],
        'name': el['name'],
        'date': date_s,
        'n': el.get('n'),
        'blackout_start': bstart,
        'blackout_end': bend,
        'polls_path': polls_path,
        'results_path': results_path,
        'results_sigungu_path': sigungu_results if (sigungu_results and (ROOT / sigungu_results).exists()) else None,
        'roster_path': roster if (roster and (ROOT / roster).exists()) else None,
        'kind': kind,
    }


def poll_election_block(meta: dict, el: dict) -> str:
    """그 회차 여론조사의 실측 요약 — 건수·기간·기관.

    **meta는 평탄화된 dict다**(polls_path가 최상위, archive 키 없음). 원본 el에서만
    polls_window를 얻을 수 있어 둘 다 받는다 — 여기서 meta['archive']를 찾다가
    빈 문자열을 돌려줬고, 그러면 마커만 지워져 아무 티도 나지 않았다.
    """
    ar = el.get('archive') or {}
    win = ar.get('polls_window') or []
    path = ROOT / (meta.get('polls_path') or '')
    if len(win) < 2 or not path.exists():
        return ''
    try:
        polls = json.loads(path.read_text(encoding='utf-8')).get('polls') or []
    except Exception:                                            # noqa: BLE001
        return ''
    sel = [p for p in polls if p.get('period_end')
           and win[0] <= p['period_end'] <= win[1] and not p.get('is_self_poll')]
    if not sel:
        return ''
    ends = sorted(p['period_end'] for p in sel)
    agencies = sorted({p.get('agency', '') for p in sel if p.get('agency')})
    offices = sorted({p.get('office_level', '') for p in sel if p.get('office_level')})
    name, date_s = _esc(meta['name']), _esc(meta['date'])
    li = ''.join(f'<li>{_esc(a)}</li>' for a in agencies[:8])
    more = f'<li>외 {len(agencies) - 8}곳</li>' if len(agencies) > 8 else ''
    off = ' · '.join(_esc(o) for o in offices[:5])
    return (
        f'<section class="pe-static"><h2 class="pe-static-title">{name} 여론조사</h2>'
        f'<p class="pe-static-lede">{date_s} 선거를 앞두고 중앙선거여론조사심의위원회'
        f'(NESDC)에 등록·공표된 조사 <b>{len(sel):,}건</b>을 실제 결과와 대조합니다. '
        f'조사 기간 {_esc(ends[0])} ~ {_esc(ends[-1])} · 조사기관 {len(agencies)}곳'
        + (f' · 직위 {off}' if off else '') + '.</p>'
        f'<p class="pe-static-lede">기관마다 방법·표본이 달라 값이 갈립니다(house '
        f'effect). 아래에서 조사별 표본수·응답률·표본오차를 실제 득표와 나란히 봅니다.</p>'
        f'<details class="pe-static-more"><summary>조사기관 {len(agencies)}곳</summary>'
        f'<ul class="pe-agency-list">{li}{more}</ul></details>'
        f'<p class="pe-static-links"><a href="/archive/{_esc(meta["slug"])}/">'
        f'{name} 결과 아카이브 →</a></p></section>')


def build_poll_elections(urls: list):
    """선거별 여론조사 vs 실제 페이지 /polls/{id}/ + 디렉터리 index.json 생성."""
    template = INDEX_TEMPLATE.read_text(encoding='utf-8')
    made = []
    for fp in sorted(ELECTIONS_DIR.glob('*.json')):
        if fp.name in ('index.json',):
            continue
        try:
            el = json.loads(fp.read_text(encoding='utf-8'))
        except Exception:
            continue
        meta = _poll_election_meta(el)
        if not meta:
            continue
        slug = meta['slug']
        n, date_s = meta['n'], meta['date']
        unit = '회' if meta['kind'] == 'local' else '대'
        short = {'presidential': '대선', 'general_election': '총선'}.get(meta['kind'], '지선')
        query = {'presidential': '대통령선거', 'general_election': '총선'}.get(meta['kind'], '지방선거')
        title = (f'{date_s[:4]} {query} 여론조사 vs 실제 결과 — '
                 f'{n}{unit} {short} 조사 적중률 | polis')
        desc = (f'{meta["name"]} 여론조사와 실제 개표 결과 비교. NESDC 등록 조사가 '
                f'시도별로 얼마나 맞았는지 비례로.')
        canon = f'/polls/{slug}/'
        # 선거별 결과지도 카드(build_og_maps.py). 없으면 일반 카드(템플릿 기본값 유지).
        _og = ROOT / 'og' / f'{slug}.png'
        og_image = f'{SITE}/og/{slug}.png' if _og.exists() else None
        # __INITIAL_STATE__.election 주입 — core.js POLL_ELECTION 기본값을 덮어씀.
        html = replace_meta(template, title, desc, canon, {'election': meta}, og_image=og_image)
        # **회차 고유 내용을 정적으로.** 없으면 9개 페이지의 정적 본문이 전부 같다
        # (허브 껍데기 1,228자). 각 회차는 다른 사실을 담는 문서인데 크롤러에겐 같은
        # 페이지로 보였다. 블록이 비면 마커만 지워지고 티가 안 나므로 아래에서 검사한다.
        html = html.replace('<!-- PE_STATIC --><!-- /PE_STATIC -->',
                            poll_election_block(meta, el), 1)
        write_page(ROOT / 'polls' / slug / 'index.html', html)
        urls.append((canon, '0.6', 'monthly'))
        made.append({'slug': slug, 'name': meta['name'], 'date': date_s, 'n': n})
    # 디렉터리 — 루트 /polls.html·각 페이지가 fetch (날짜 desc).
    made_sorted = sorted(made, key=lambda m: m['date'], reverse=True)
    idx_path = ROOT / 'data' / 'polls' / 'election_index.json'
    idx_path.write_text(json.dumps(made_sorted, ensure_ascii=False), encoding='utf-8')
    _write_poll_index_block(made_sorted)
    print(f'poll-elections: {len(made)} ({", ".join(m["slug"] for m in made_sorted)})')


def _write_poll_index_block(made_sorted: list):
    """polls.html의 정적 시드 목록 갱신 — 손으로 관리하면 회차가 늘 때마다 어긋난다."""
    src = ROOT / 'polls.html'
    if not src.exists():
        return
    html = src.read_text(encoding='utf-8')
    items = ''.join(
        f'<li><a href="/polls/{m["slug"]}/">{_esc(m["name"])} 여론조사 vs 실제</a> '
        f'<span>{m["date"]}</span></li>' for m in made_sorted)
    block = ('<!-- POLL_INDEX_START — build_static.py 자동 갱신. 손수정 X.\n'
             '           election-index.js가 로드되면 타임라인으로 교체한다. JS 없이도(그리고 크롤러가\n'
             '           렌더하기 전에도) 회차별 페이지로 가는 링크가 HTML에 남게 하는 것이 목적. -->\n'
             f'      <ul class="poll-tl-fallback">{items}</ul>\n'
             '      <!-- POLL_INDEX_END -->')
    new = re.sub(r'<!-- POLL_INDEX_START[\s\S]*?POLL_INDEX_END -->', block, html, count=1)
    if new != html:
        src.write_text(new, encoding='utf-8')



# --- 프리렌더 본문 주입 -------------------------------------------------------
# history 프리렌더 66개는 title/desc만 다르고 <body> 텍스트가 서로 완전히 같았다.
# 구글이 '크롤링됨 - 색인 생성되지 않음'으로 대거 보류한 직접 원인이다(중복 콘텐츠).
# 회차별 사실(당선인·투표율·날짜)을 intro에 찍어 페이지마다 다른 내용을 갖게 하고,
# 해당 회차 아카이브로 나가는 링크도 함께 넣는다(내부 링크 심도 개선).

def _esc(x) -> str:
    return (str(x if x is not None else '').replace('&', '&amp;')
            .replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;'))


def archive_slug_map() -> dict:
    """(type, n) → archive slug. 없으면 링크를 걸지 않는다."""
    try:
        idx = json.loads((ROOT / 'data/archive_index.json').read_text(encoding='utf-8'))
    except Exception:
        return {}
    return {(a.get('type'), a.get('n')): a.get('slug') for a in idx if a.get('slug')}


def intro_block(h1: str, lede: str, extra: str = '') -> str:
    return (f'<section class="intro">\n    <h1>{h1}</h1>\n'
            f'    <p class="lede">{lede}</p>\n{extra}  </section>')



# history 회차 페이지는 archive와 **같은 선거를 다른 축으로** 보는 화면이다. 그래서
# 표도 같은 것을 쓴다(scripts/build/result_tables.py). 직위 축이 하나 더 있을 뿐이다.
#
# 이 페이지들은 원래 본문이 "데이터 불러오는 중…" 648자가 전부였다 — 66쪽이 서로
# 거의 같은 문서였고, 2026-07에 대거 '크롤링됨-미색인'으로 묶인 자리다.
# 표의 단위는 **그 화면이 보여주는 단위**와 맞춘다. 대선 회차 페이지는 시군구 hex를
# 그리므로 표도 시군구다(시도 17행만 적으면 화면과 글이 다른 걸 말한다).
#   (type, office) → (tc, scope, 지역 열 키, 지역 열 이름, 표 제목)

# history 회차 페이지의 그림은 **새로 만들지 않는다.** {type,n}은 archive slug 하나로
# 정확히 대응하므로(archive_slug_map) 같은 PNG를 가리키면 된다. 회차는 같은 선거를
# 다른 축으로 보는 화면이지 다른 선거가 아니다.
#
# 어느 그림을 걸지는 **레지스트리가 정한다**(data/view_registry.json):
#   hosts[].offices  직위별 페이지가 어느 지도를 걸지. 지선 기초단체장 쪽에
#                    광역단체장 지도를 걸면 화면과 그림이 다른 걸 말한다.
#   hosts[].page     그 host의 어느 모드를 본문에 낼지. 캡처는 모든 모드를 찍지만
#                    전부 걸면 총선 회차 페이지가 8장에서 13장이 된다.
# 옛 HIST_VIEW_PREFER(여기 손으로 적힌 11개 키)를 레지스트리로 옮긴 것 —
# 네 번째 표를 만들지 않으려고.


def round_figures(slug: str, off_slug: str, title: str) -> str:
    if not slug:
        return ''
    mf = ROOT / 'data' / 'map_manifest.json'
    if not mf.is_file():
        return ''
    try:
        e = (json.loads(mf.read_text(encoding='utf-8')).get('elections') or {}).get(slug) or {}
    except Exception:
        return ''
    meta = e.get('meta') or {}
    if not meta:
        return ''
    want = _vr.hosts_for_office(off_slug)
    figs = []
    order = sorted((e.get('views') or []),
                   key=lambda v: _vr.page_rank((meta.get(v) or {}).get('host') or '',
                                               (meta.get(v) or {}).get('mode')))
    for v in order:
        m = meta.get(v)
        if not m or not m.get('page'):
            continue
        if want is not None and m.get('host') not in want:
            continue
        f = ROOT / 'og' / 'maps' / slug / f'{v}.png'
        if not f.is_file():
            continue
        wh = _rt.png_size(f)
        if not wh:
            continue
        figs.append(_rt.fig(slug, v, m, wh[0], wh[1], title))
    if not figs:
        return ''
    return ('\n  <section class="ar-section" id="hx-map-figures">\n'
            '    <h2 class="ar-section-title">결과 지도</h2>\n'
            f'    <div class="map-fig-grid">{"".join(figs)}</div>\n'
            '  </section>\n')

HIST_TC = {
    ('presidential', ''):        ('1', 'sigungu', ['sido', 'sigungu'], ['시도', '시군구'], '시군구별 1위'),
    ('national_assembly', ''):   ('2', 'district', ['sido', 'district'], ['시도', '선거구'], '지역구 당선인'),
    ('local', 'governor'):       ('3', 'sido', ['sido'], ['시도'], '광역단체장 당선인'),
    ('local', 'mayor'):          ('4', 'sigungu', ['sido', 'sigungu'], ['시도', '시군구'], '기초단체장 당선인'),
    ('local', 'superintendent'): ('11', 'sigungu', ['sido', 'sigungu'], ['시도', '시군구'], '교육감 당선인'),
}


def round_table(slug: str, type_key: str, off_slug: str = '') -> str:
    """회차 × 직위 → 정적 결과 표. archive slug가 없으면 표도 없다."""
    spec = HIST_TC.get((type_key, off_slug))
    if not slug or not spec:
        return ''
    tc, scope, place_cols, head_pre, cap = spec
    races = _rt.load_races(slug)
    if not races:
        return ''
    # 링크는 걸지 않는다 — person-links 색인은 archive 쪽 규칙(동명이인 배제)을 따르는데
    # 여기서 같은 판단을 두 벌 두면 어긋난다. 이 페이지의 목적은 내용이 읽히는 것이고,
    # 인물·정당으로 나가는 길은 바로 위 '이 회차 아카이브' 링크가 잇는다.
    rows = _rt.winner_rows(races, tc, scope, place_cols=place_cols,
                           link=lambda kind, place, name: _rt._esc(name or ''))
    head = head_pre + ['당선인', '정당', '득표율', '투표율']
    return _rt.table_html('hx-round-table', cap, head, rows)

def breadcrumb_ld(trail: list) -> str:
    """BreadcrumbList — 검색 결과에 URL 대신 경로가 표시되게 한다."""
    items = [{'@type': 'ListItem', 'position': i + 1, 'name': name,
              **({'item': SITE + url} if url else {})}
             for i, (name, url) in enumerate(trail)]
    data = {'@context': 'https://schema.org', '@type': 'BreadcrumbList',
            'itemListElement': items}
    return ('<script type="application/ld+json">'
            + json.dumps(data, ensure_ascii=False) + '</script>')


def inject_body(html: str, intro: str, jsonld: str = '') -> str:
    html = re.sub(r'<section class="intro">[\s\S]*?</section>', intro, html, count=1)
    if jsonld:
        html = html.replace('</head>', jsonld + '\n</head>', 1)
    return html


# 실제로 생성한 history 경로. 클라이언트가 링크를 **추측하지 않게** 내보낸다.
#   {type: {n: [office_slug, ...]}}  — 빈 리스트면 /history/{type}/{n}/ 자체가 페이지
ROUTES: dict = {}
HISTORY_ROUTES = ROOT / 'data/results/history_routes.json'


def build_history(manifest: dict, elections: dict, urls: list):
    template = HISTORY_TEMPLATE.read_text(encoding='utf-8')
    # 회차별 색인(HS_ROUNDS)은 **허브에만** 둔다. 템플릿이 history.html이라 그냥 두면
    # 66쪽 전부에 같은 66개 링크가 복사되는데, 이 프리렌더들은 원래 서로 <body>가
    # 완전히 같아서 대거 '크롤링됨-미색인'으로 보류됐던 자리다(eedd49da6). 회차별
    # 사실을 넣어 겨우 갈라놨는데 85줄짜리 동일 블록을 얹으면 그 비율이 다시 나빠진다.
    # 프리렌더끼리는 이미 서로 링크하므로 크롤 이득도 없다 — 필요한 건 바깥 입구였다.
    # build_history_static.py가 이 블록을 언제 넣든 여기서 걷어내므로 순서에 안 걸린다.
    # 앞의 빈 줄까지 함께 걷는다 — 안 그러면 프리렌더에 빈 줄 하나가 남아 66쪽이
    # 매번 diff에 뜬다(멱등성 검사가 그걸 '생성물 드리프트'로 읽는다).
    template = re.sub(r'\n?[ \t]*<!-- HS_ROUNDS_START[\s\S]*?HS_ROUNDS_END -->[ \t]*\n?',
                      '', template, count=1)
    slugs = archive_slug_map()
    n_made = 0
    urls.append(('/history.html', '0.7', 'monthly'))
    # manifest(지도 데이터 보유분) 대신 elections.json 전체 회차를 페이지로 — 간선 대선(1·4·8~12 등)
    # 도 직접 URL 접근 가능. variant(4대 3·15)·predicted(예측)는 별도 URL 없음.
    for type_key in ('presidential', 'national_assembly', 'local'):
        els = elections.get(type_key, {}).get('elections', [])
        type_short = TYPE_LABEL.get(type_key, type_key)
        type_slug = TYPE_SLUG.get(type_key, type_key)
        seen = set()
        for meta in els:
            n = meta.get('n')
            if n is None or n in seen or meta.get('variant') or meta.get('predicted'):
                continue
            seen.add(n)
            el_date = meta.get('date', '')
            if type_key == 'local':
                for office_ko, off_slug in LOCAL_OFFICE_SLUG.items():
                    # 교육감 전국 직선 동시선거는 5회(2010)부터 — 1~4회 교육감 페이지는 생성 안 함.
                    if off_slug == 'superintendent' and n < 5:
                        continue
                    title = (f'{el_date[:4]} 지방선거 {office_ko} 결과 지도 — '
                             f'제{n}회 시군구별 개표 | polis')
                    desc = (f'{el_date[:4]}년 제{n}회 전국동시지방선거 {office_ko} 결과. '
                            f'시군구 hex 격자로 지역별 1위 정당과 득표율을 한눈에.')
                    canon = f'/history/{type_slug}/{n}/{off_slug}/'
                    init_state = {'type': type_key, 'n': n, 'office': office_ko}
                    turnout = meta.get('turnout')
                    bits = [f'{el_date} 실시']
                    if turnout:
                        bits.append(f'투표율 {turnout}%')
                    slug = slugs.get((type_key, n))
                    # 정적 링크를 남기되 id를 붙여, 사용자가 회차를 바꾸면 JS가 갱신한다.
                    extra = ('    <p class="lede hx-archive-link" id="hx-archive-link">'
                             '<a href="/archive/' + slug + '/">'
                             f'이 회차 아카이브 — 결과·여론조사·출구조사</a></p>\n') if slug else ''
                    intro = (intro_block(f'{n}회 {type_short} {office_ko}',
                                         _esc(' · '.join(bits)) + ' — 시군구 hex 격자.', extra)
                             + round_figures(slug, off_slug, f'{n}회 {type_short} {office_ko}')
                             + round_table(slug, type_key, off_slug))
                    ld = breadcrumb_ld([('역대 결과', '/history.html'),
                                        (f'{n}회 {type_short}', None),
                                        (office_ko, None)])
                    html = inject_body(replace_meta(template, title, desc, canon, init_state),
                                       intro, ld)
                    write_page(ROOT / 'history' / type_slug / str(n) / off_slug / 'index.html', html)
                    urls.append((canon, '0.6', 'yearly'))
                    # 실제로 만든 경로를 남긴다 — 클라이언트(lens-switcher)가 링크를
                    # 조립할 때 추측하지 않게. 지선은 /history/local/{n}/ 자체가 없고
                    # 직위 세그먼트까지 있어야 하는데, 그걸 모르고 만들어 404가 났다.
                    ROUTES.setdefault(type_key, {}).setdefault(str(n), []).append(off_slug)
                    n_made += 1
            else:
                winner = meta.get('winner', '')
                winner_str = f' · {winner} 당선' if winner else ''
                unit = TYPE_UNIT.get(type_key, '대')
                type_query = TYPE_QUERY.get(type_key, type_short)
                title = (f'{el_date[:4]} {type_query} 결과 지도 — '
                         f'제{n}{unit} 지역별 1위 정당{winner_str} | polis')
                desc = (f'{el_date[:4]}년 제{n}{unit} {type_short} 결과. hex 격자로 '
                        f'지역별 1위 정당과 득표 격차를 한눈에.')
                canon = f'/history/{type_slug}/{n}/'
                ROUTES.setdefault(type_key, {}).setdefault(str(n), [])
                init_state = {'type': type_key, 'n': n}
                turnout = meta.get('turnout')
                bits = [f'{el_date} 실시']
                if winner:
                    wp = meta.get('winner_party')
                    bits.append(f'{winner}({wp}) 당선' if wp else f'{winner} 당선')
                if meta.get('seats'):
                    bits.append(f"의석 {meta['seats']}")
                if turnout:
                    bits.append(f'투표율 {turnout}%')
                if meta.get('indirect'):
                    bits.append('간선')
                if meta.get('note'):
                    bits.append(str(meta['note']))
                slug = slugs.get((type_key, n))
                extra = ('    <p class="lede hx-archive-link" id="hx-archive-link">'
                         '<a href="/archive/' + slug + '/">'
                         f'이 회차 아카이브 — 결과·여론조사·출구조사</a></p>\n') if slug else ''
                intro = (intro_block(f'{n}{unit} {type_short}',
                                     _esc(' · '.join(bits)), extra)
                         + round_figures(slug, '', f'{n}{unit} {type_short}')
                         + round_table(slug, type_key))
                ld = breadcrumb_ld([('역대 결과', '/history.html'),
                                    (f'{n}{unit} {type_short}', None)])
                html = inject_body(replace_meta(template, title, desc, canon, init_state),
                                   intro, ld)
                write_page(ROOT / 'history' / type_slug / str(n) / 'index.html', html)
                urls.append((canon, '0.6', 'yearly'))
                n_made += 1
    print(f'history: {n_made}')


def main():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    elections = json.loads(ELECTIONS.read_text(encoding='utf-8'))
    urls = []
    # 순서 주의: build_poll_elections가 polls.html의 정적 회차 목록 블록을 갱신하므로
    # 그 뒤에 build_polls를 돌려야 /governor/ 등 파생 페이지에도 목록이 들어간다.
    build_poll_elections(urls)    # /polls/{id}/ 선거별 여론조사 vs 실제 + 디렉터리
    build_polls(urls)             # /, /governor/ 등 페이지 생성
    build_history(manifest, elections, urls)   # history/**/index.html 생성
    HISTORY_ROUTES.write_text(
        json.dumps(ROUTES, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n',
        encoding='utf-8')
    print(f'→ {HISTORY_ROUTES.relative_to(ROOT)}: '
          f'{sum(len(v) for v in ROUTES.values())} 회차', file=sys.stderr)
    # 홈 능력 블록 — 수치를 손으로 적으면 데이터가 늘 때마다 어긋난다(nav와 같은 이유).
    try:
        import build_home_capabilities as _caps
        _caps.main()
    except SystemExit:
        pass
    except Exception as e:
        print(f'  ! 홈 능력 블록 갱신 실패: {e}')
    # sitemap·robots는 포괄 생성기에 위임 — archive·person 포함 전수(56개로 덮어쓰던 버그 수정).
    # build_polls/build_history가 페이지를 먼저 써야 디렉터리 스캔이 잡힘.
    _sitemap.main()


if __name__ == '__main__':
    main()
