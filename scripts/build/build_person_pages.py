"""인물 정적 페이지 빌드 — 의원(assembly_id 보유) entry만 prerender.

각 인물별 /person/{name}-{dob}/index.html 생성. 페이지에 그 인물 데이터만
inline JSON으로 박아 fetch 없이 즉시 렌더. 비의원은 /person.html?name= dynamic.

URL slug: `이재명-1964-12-22` 식. URL은 한글 그대로 (브라우저가 percent-encoding 처리).

Output:
  person/{slug}/index.html × ~807
  data/sitemap_person.txt — sitemap 추가용 URL list
"""
from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "assets/person-index.json"
OUT_DIR = ROOT / "person"
SITEMAP_OUT = ROOT / "data/sitemap_person.txt"
SITE = "https://polis.ysw.kr"
PLEDGE_BY_PERSON = ROOT / "data/pledges/by-person"

# nav는 sync_nav_html.py가 정본 — 여기서 사본을 들고 있으면 메뉴가 바뀔 때마다 어긋난다
# (실제로 '역대 판세'가 '타임라인'으로 굳어 있었다). 생성 시점에 정본을 불러 쓴다.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_nav_html import render_nav, menu_for_path  # noqa: E402
from party_canon import disambiguate_party  # noqa: E402



TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<script>try{{var _m=localStorage.getItem('vote-ysw-theme');if(_m==='dark')document.documentElement.setAttribute('data-theme','dark');else if(_m==='light')document.documentElement.setAttribute('data-theme','light');}}catch(_e){{}}</script>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#5b54d6">
<base href="/">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="profile">
<meta property="og:url" content="https://polis.ysw.kr/person/{slug}/">
<meta property="og:image" content="https://polis.ysw.kr/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:image" content="https://polis.ysw.kr/og.png">
<link rel="canonical" href="/person/{slug}/">
{jsonld}
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.min.css">
<link rel="stylesheet" href="assets/common.css">
<link rel="stylesheet" href="assets/components.css">
<link rel="stylesheet" href="assets/person.css">
<script id="person-data" type="application/json">{data_json}</script>
<script id="region-slugs" type="application/json">{region_slugs}</script>
</head>
<body>
<header class="site-hdr">
  <div class="brand">
    <a href="/" class="logo-link"><span class="logo">polis</span><span class="domain">ysw.kr</span></a>
  </div>
  <nav class="hdr-nav">
{nav}
  </nav>
  <div class="hdr-meta">
    <button id="theme-toggle" class="theme-toggle" type="button" aria-label="테마 토글"></button>
  </div>
</header>
<main class="page">
  <section class="intro">
    <h1 id="person-title">{name}</h1>
    <p class="lede" id="person-sub">{lede}</p>
  </section>
  <section id="person-body">{static_body}</section>
  <footer class="foot">
    <p class="fine">비의원·낙선 이력은 <a href="/person.html?name={name}">검색</a>에서.</p>
  </footer>
</main>
<script src="assets/parties.js"></script>
<script src="assets/person.js"></script>
<script src="assets/theme.js"></script>
<script src="assets/nav.js"></script>
</body>
</html>
"""


SIDO_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원",
    "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주", "제주도": "제주",
}


def _short_sidos(p: dict) -> list:
    """시도 약칭 목록 — 개명 전후를 겹쳐 적지 않는다.

    전라북도와 전북특별자치도는 둘 다 '전북'이라, 두 이름 시절에 다 나온 사람은
    '전북 · 전북'으로 찍혔다(박경철). 줄인 **뒤에** 중복을 걷어낸다. 순서는
    원본 순서를 지킨다.
    """
    out = []
    for x in (p.get("sidos") or []):
        v = SIDO_SHORT.get(x, x)
        if v not in out:
            out.append(v)
    return out[:2]


def page_title(p: dict) -> str:
    """이름만으로는 4,326개가 서로 구별되지 않는다.

    'polis · 가기산'은 위키와 같은 말을 걸고 이기지 못할뿐더러, 이 사람이 어디서
    무엇에 나왔는지 한 글자도 말하지 않는다. 지역·기간·전적을 붙이면 제목이 서로
    달라지고(동명이인 포함) 검색어와도 맞는다.

    데이터에 없는 것은 붙이지 않는다 — 지역이 비면 지역 없이, 연도가 비면 연도 없이.
    """
    name = p["name"]
    bits = []
    sidos = _short_sidos(p)
    if sidos:
        bits.append(" · ".join(sidos))
    elif p.get("parties"):
        # 비례대표는 지역이 없다. 그 자리를 정당으로 채우지 않으면 같은 해 한 번
        # 당선된 동명이인 둘이 글자 하나 다르지 않은 제목을 갖는다(이영애 2008).
        bits.append(" · ".join(p["parties"][:2]))
    years = [r.get("year") for r in (p.get("races") or []) if r.get("year")]
    if years:
        lo, hi = min(years), max(years)
        bits.append(f"{lo}~{hi}년" if lo != hi else f"{lo}년")
    n, wins = len(p.get("races") or []), p.get("wins", 0)
    if n:
        bits.append(f"{n}회 출마·{wins}회 당선")
    tail = " ".join(bits)
    return f"{name} 선거 이력 — {tail} | polis" if tail else f"{name} 선거 이력 | polis"


def slugify(name: str, dob: str) -> str:
    """URL slug: 한글 그대로 + dob. e.g. '이재명-1964-12-22'."""
    return f"{name}-{dob}"


# ── 엔티티 링크 ────────────────────────────────────────────────────────────
# 인물 페이지가 archive로만 나가고 정당·지역으로는 못 갔다(측정: party 4·region 0).
# 있는 데이터를 잇는 일이라 새로 만드는 것이 없다.
_REGION_BY_NAME: dict | None = None
_PARTY_PAGES: set | None = None


def region_slug_index() -> dict:
    """시군구명 → slug. **모호하지 않은 것만** — '중구'처럼 여러 시도에 있는 이름은
    person-index의 place에 시도가 없어 어디인지 정할 수 없다. 억지로 하나 고르면
    틀린 지역으로 보내는 링크가 된다."""
    global _REGION_BY_NAME
    if _REGION_BY_NAME is None:
        by: dict = {}
        d = ROOT / "region"
        if d.exists():
            # sorted() 필수 — iterdir()는 파일시스템 순서라 기계마다 다르다.
            # 이 dict가 그대로 JSON으로 페이지에 박히므로, 정렬하지 않으면 같은 입력에서
            # 다른 출력이 나온다(CI가 로컬과 다른 결과를 내며 잡아냈다).
            for sub in sorted(d.iterdir(), key=lambda x: x.name):
                if sub.is_dir() and "-" in sub.name:
                    by.setdefault(sub.name.split("-", 1)[1], []).append(sub.name)
        _REGION_BY_NAME = {k: by[k][0] for k in sorted(by) if len(by[k]) == 1}
    return _REGION_BY_NAME


def region_href(place: str, tc: str) -> str | None:
    """시군구명 → 지역 페이지. person-index의 place에는 시도가 없어서
    '중구'처럼 여러 시도에 있는 이름은 **어디인지 정할 수 없다** — 잇지 않는다.
    억지로 하나 고르면 틀린 지역으로 보내는 링크가 된다.
    광역 단위(tc 1·3·11)의 place는 시도명이고 시도 페이지는 없으므로 대상이 아니다."""
    if tc not in ("4", "6") or not place:
        return None
    slug = region_slug_index().get(place)
    return f"/region/{quote(slug)}/" if slug else None


def party_cell(name: str | None, date: str) -> str:
    """정당 페이지가 있는 이름만 링크. 동음이의(민주당 등)는 날짜로 가른다."""
    global _PARTY_PAGES
    if not name:
        return ""
    if _PARTY_PAGES is None:
        try:
            _PARTY_PAGES = set(json.loads(
                (ROOT / "data/parties/registry.json").read_text(encoding="utf-8"))["parties"])
        except Exception:
            _PARTY_PAGES = set()
    canon = disambiguate_party(name, date or "")
    if canon in _PARTY_PAGES:
        return f'<a href="/party/{quote(canon)}/">{esc(name)}</a>'
    return esc(name)


_ARCHIVE_PAGES: set | None = None


def archive_cell(r: dict) -> str:
    """회차 이름 — archive 페이지가 **실재할 때만** 링크한다.

    eid가 archive 디렉터리명과 어긋나면 죽은 링크가 된다. 실제로 비례대표 이력이
    'general-20'(archive는 20th-general-2016)을 써서 452건, archive가 없는
    9회 재보궐이 46건 죽어 있었다. 원인은 고쳤지만 새 회차가 생길 때 또 어긋날 수
    있으므로 여기서 실재를 확인하고, 없으면 링크 없이 글자로 둔다.
    """
    global _ARCHIVE_PAGES
    if _ARCHIVE_PAGES is None:
        d = ROOT / "archive"
        _ARCHIVE_PAGES = ({x.name for x in d.iterdir()
                           if x.is_dir() and (x / "index.html").exists()}
                          if d.exists() else set())
    eid = r.get("eid") or ""
    label = esc(r.get("round") or eid)
    if eid in _ARCHIVE_PAGES:
        return f'<a href="/archive/{quote(eid)}/">{label}</a>'
    return label


def place_cell(r: dict) -> str:
    place = r.get("place") or ""
    h = region_href(place, r.get("tc") or "")
    return f'<a href="{h}">{esc(place)}</a>' if h else esc(place)


def esc(s) -> str:
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def jsonld(p: dict, slug: str, desc: str) -> str:
    """Person + BreadcrumbList — 검색 결과에 URL 대신 경로가, 인물엔 개체 정보가 붙는다.

    단언할 수 없는 값(직위·소속 현재형)은 넣지 않는다. 이름·생년월일·한자·설명처럼
    데이터로 확실한 것만 싣는다 — 구조화 데이터의 오류는 신뢰도 페널티로 돌아온다.
    """
    url = f"{SITE}/person/{slug}/"
    person = {"@type": "Person", "name": p["name"], "url": url, "description": desc}
    if p.get("dob"):
        person["birthDate"] = p["dob"]
    if p.get("hanja"):
        person["alternateName"] = p["hanja"]
    crumbs = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "인물 검색", "item": f"{SITE}/search.html"},
        {"@type": "ListItem", "position": 2, "name": p["name"]},
    ]}
    data = {"@context": "https://schema.org", "@graph": [person, crumbs]}
    return ('<script type="application/ld+json">'
            + json.dumps(data, ensure_ascii=False) + '</script>')


def pledge_block(pid: str) -> str:
    """공약 제목을 정적 HTML로. 본문은 길어서 넣지 않고 제목만 — 제목만으로도 인물마다
    완전히 고유한 수십~수백 자가 생긴다. 상세 본문은 person.js가 접이식으로 지연 로드한다."""
    fp = PLEDGE_BY_PERSON / f"{pid}.json"
    if not fp.exists():
        return ""
    try:
        doc = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return ""
    blocks = []
    for e in doc.get("entries", []):
        where = " ".join(x for x in (e.get("sido"), e.get("sigungu")) if x)
        items = "".join(f"<li>{esc(pl.get('title'))}</li>" for pl in e.get("pledges", []))
        if not items:
            continue
        blocks.append(f'<h3>{esc(e.get("round"))} · {esc(where)} {esc(e.get("office"))}</h3>'
                      f'<ol class="pp-static-pledges">{items}</ol>')
    if not blocks:
        return ""
    return ('<section class="pp-static-sec"><h2>선거공약</h2>' + "".join(blocks)
            + '</section>')


def rival_cell(r: dict) -> str:
    """이 판에서 맞붙은 상대와 표차 — 이 페이지에만 있는 사실.

    1위면 2위가, 아니면 1위가 상대다(build_person_index가 정한다). 이겼으면 +,
    졌으면 −. 표차를 모르는 옛 회차(득표수 없음)는 이름만 적는다. 상대가 없는
    무투표당선은 그렇게 적는다 — 빈칸은 자료가 없는 것처럼 보인다.
    """
    opp = r.get("opp")
    if not opp:
        return "무투표" if r.get("n_cand") == 1 else "—"
    who = party_cell(opp.get("party"), r.get("date") or "") or ""
    who = f'{esc(opp.get("name") or "")}' + (f' ({who})' if who else "")
    m = opp.get("margin")
    if not m:
        return who
    sign = "+" if r.get("won") or r.get("rank") == 1 else "−"
    return f'{who} <span class="pp-margin">{sign}{m:,}표</span>'


def static_body(p: dict) -> tuple[str, str]:
    """(lede, 본문 HTML) — 렌더 전에도 읽히는 실제 내용.

    이 페이지들은 원래 inline JSON + person.js로만 내용을 만들었다. 데이터는 HTML 안에
    있었지만 <script> 안이라 렌더 전에는 텍스트가 아니고, 검색엔진의 렌더 예산은 4,000
    페이지에 배분되지 않는다. 실제로 구글이 '크롤링됨 - 색인 생성되지 않음'으로 2,190건을
    보류했다(본문이 nav 빼면 40자). 그래서 같은 내용을 빌드 시점에 HTML로도 찍는다.
    person.js는 로드되면 #person-body를 자기 렌더로 덮어쓰므로 화면 동작은 그대로다.
    """
    races = sorted(p.get("races", []), key=lambda r: (r.get("date") or str(r.get("year") or "")))
    years = [r.get("year") for r in races if r.get("year")]
    span = f"{min(years)}~{max(years)}년 " if years else ""
    parties = p.get("parties") or []
    wins, losses = p.get("wins", 0), p.get("losses", 0)
    lede_bits = [f"{span}{len(races)}회 출마 · {wins}회 당선 · {losses}회 낙선"]
    if parties:
        lede_bits.append(" · ".join(parties[:4]))
    lede = esc(" — ".join(lede_bits))

    rows = []
    for r in races:
        tag = "당선" if r.get("won") else "낙선"
        pct = f"{float(r['pct']):.1f}%" if r.get("pct") is not None else "—"
        rank = f"{r['rank']}위" if r.get("rank") and r["rank"] < 99 else ""
        votes = f"{r['votes']:,}" if r.get("votes") else "—"
        rows.append(
            f'<tr><td>{esc(r.get("year") or "")}</td>'
            f'<td>{archive_cell(r)}</td>'
            f'<td>{place_cell(r)}</td>'
            f'<td>{party_cell(r.get("party"), r.get("date") or "")}</td>'
            f'<td>{votes}</td><td>{pct}</td><td>{esc(rank)}</td><td>{tag}</td>'
            f'<td>{rival_cell(r)}</td></tr>')
    table = (
        '<table class="pp-static"><caption>출마 이력</caption><thead><tr>'
        '<th>연도</th><th>선거</th><th>지역</th><th>정당</th><th>득표</th>'
        '<th>득표율</th><th>순위</th><th>결과</th><th>상대·표차</th>'
        '</tr></thead><tbody>'
        + "".join(rows) + "</tbody></table>")
    return lede, table + pledge_block(p["id"])


HUB_TEMPLATE = '''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<script>try{{var _m=localStorage.getItem('vote-ysw-theme');if(_m==='dark')document.documentElement.setAttribute('data-theme','dark');else if(_m==='light')document.documentElement.setAttribute('data-theme','light');}}catch(_e){{}}</script>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#5b54d6">
<base href="/">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
<meta property="og:image" content="https://polis.ysw.kr/og.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="https://polis.ysw.kr/og.png">
<link rel="canonical" href="{canon}">
{jsonld}
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.min.css">
<link rel="stylesheet" href="assets/common.css">
<link rel="stylesheet" href="assets/components.css">
<link rel="stylesheet" href="assets/person.css">
</head>
<body>
<header class="site-hdr">
  <div class="brand">
    <a href="/" class="logo-link"><span class="logo">polis</span><span class="domain">ysw.kr</span></a>
  </div>
  <nav class="hdr-nav">
{nav}
  </nav>
  <div class="hdr-meta">
    <button id="theme-toggle" class="theme-toggle" type="button" aria-label="테마 토글"></button>
  </div>
</header>
<main class="page">
  <section class="intro">
    <h1>{h1}</h1>
    <p class="lede">{lede}</p>
  </section>
{body}
</main>
<script src="assets/theme.js"></script>
<script src="assets/nav.js"></script>
</body>
</html>
'''

# 초성 14갈래. 쌍자음은 홑자음에 합친다(ㄲ→ㄱ) — 사람이 이름을 찾을 때 'ㄲ' 칸을
# 따로 뒤지지 않는다. 한글로 시작하지 않는 이름은 '기타'.
_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_FOLD = {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}
GROUPS = ["ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅅ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ", "기타"]


def chosung(name: str) -> str:
    """이름 첫 글자의 초성. 한글이 아니면 '기타'."""
    if not name:
        return "기타"
    c = ord(name[0])
    if not (0xAC00 <= c <= 0xD7A3):
        return "기타"
    return _FOLD.get(_CHO[(c - 0xAC00) // 588], _CHO[(c - 0xAC00) // 588])


def group_slug(g: str) -> str:
    return f"초성-{g}"

def hub_jsonld(items: list, canon: str) -> str:
    """ItemList — 이 페이지가 목록이라는 것을 밝힌다. 실제 링크 순서와 같게 싣는다."""
    ld = {"@context": "https://schema.org", "@type": "ItemList",
          "url": f"{SITE}{canon}", "numberOfItems": len(items)}
    return ('<script type="application/ld+json">'
            + json.dumps(ld, ensure_ascii=False) + '</script>')


def person_line(p: dict) -> str:
    """목록 한 줄 — 이름만 늘어놓으면 4,326줄이 서로 구별되지 않는다.
    전적·지역·기간을 함께 적어 고르는 데 쓸 수 있게 한다."""
    slug = slugify(p["name"], p["dob"])
    bits = []
    sidos = _short_sidos(p)
    if sidos:
        bits.append(" · ".join(sidos))
    years = [r.get("year") for r in (p.get("races") or []) if r.get("year")]
    if years:
        lo, hi = min(years), max(years)
        bits.append(f"{lo}~{hi}" if lo != hi else str(lo))
    bits.append(f'{len(p.get("races") or [])}회 출마·{p.get("wins", 0)}회 당선')
    return (f'<li><a href="/person/{quote(slug)}/">{esc(p["name"])}</a>'
            f'<span class="ph-meta">{esc(" · ".join(bits))}</span></li>')


def build_hub(persons: list, valid_slugs: set, sitemap_urls: list) -> int:
    """인물 허브 + 초성별 목록.

    4,326개 중 1,820개(42%)가 **어느 정적 페이지에서도 링크되지 않았다**. 지역
    페이지는 회차별 1위만, 정당 페이지는 소속 인물 일부만 잇는다. 나머지는
    sitemap에만 있었다 — 지난 7월 미색인 사고의 '고아 + 얇음' 조합 그대로다.

    한 페이지에 4,326줄을 넣지 않는다. 초성 14갈래로 나눠 갈래마다 수백 줄로 두고,
    허브가 갈래를 잇는다. 사람도 그렇게 찾는다.
    """
    by_group: dict = {g: [] for g in GROUPS}
    for p in persons:
        by_group[chosung(p["name"])].append(p)
    for g in by_group:
        by_group[g].sort(key=lambda p: (p["name"], p.get("dob") or ""))

    live = [g for g in GROUPS if by_group[g]]
    n_made = 0

    for i, g in enumerate(live):
        group = by_group[g]
        slug = group_slug(g)
        valid_slugs.add(slug)
        canon = f"/person/{quote(slug)}/"
        nav_bits = []
        if i:
            nav_bits.append(f'<a href="/person/{quote(group_slug(live[i-1]))}/">'
                            f'← {esc(live[i-1])}</a>')
        nav_bits.append('<a href="/person/">인물 전체</a>')
        if i < len(live) - 1:
            nav_bits.append(f'<a href="/person/{quote(group_slug(live[i+1]))}/">'
                            f'{esc(live[i+1])} →</a>')
        body = (f'<section class="ph-sec"><ul class="ph-list">'
                + "".join(person_line(p) for p in group)
                + '</ul></section>'
                f'<nav class="ph-pager">{" ".join(nav_bits)}</nav>')
        label = f"{g}으로" if g != "기타" else "그 밖의 이름으로"
        title = f'{g} 인물 — 역대 선거 출마·당선 {len(group)}명 | polis' if g != "기타" \
            else f'그 밖의 인물 — 역대 선거 출마·당선 {len(group)}명 | polis'
        desc = (f'이름이 {label} 시작하는 역대 선거 출마자 {len(group)}명. '
                f'사람마다 출마 회차·지역·정당과 득표율을 볼 수 있습니다.')
        html = HUB_TEMPLATE.format(
            nav=render_nav(menu_for_path(f"person/{slug}/index.html")),
            title=esc(title), desc=esc(desc), canon=canon,
            jsonld=hub_jsonld(group, canon),
            h1=esc(f'{g} — 인물 {len(group)}명'),
            lede=esc(f'이름이 {label} 시작하는 역대 선거 출마자입니다. '
                     f'전체 {len(persons):,}명 중 {len(group):,}명.'),
            body=body)
        d = OUT_DIR / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(html, encoding="utf-8")
        sitemap_urls.append(canon)
        n_made += 1

    # 허브 — 갈래로 가는 길 + 많이 출마한 사람. 갈래 링크만 있으면 허브 자체가
    # 얇은 페이지가 된다.
    cards = "".join(
        f'<li><a href="/person/{quote(group_slug(g))}/">'
        f'<b class="ph-cho">{esc(g)}</b>'
        f'<span class="ph-meta">{len(by_group[g]):,}명</span></a></li>'
        for g in live)
    most = sorted(persons, key=lambda p: (-len(p.get("races") or []),
                                          -p.get("wins", 0), p["name"]))[:30]
    body = (
        f'<section class="ph-sec"><h2>이름으로 찾기</h2>'
        f'<ul class="ph-groups">{cards}</ul></section>'
        f'<section class="ph-sec"><h2>가장 많이 출마한 인물</h2>'
        f'<ul class="ph-list">{"".join(person_line(p) for p in most)}</ul></section>'
        f'<section class="ph-sec"><h2>다른 길로 찾기</h2><ul class="ph-list">'
        f'<li><a href="/region/">지역별 선거 기록</a>'
        f'<span class="ph-meta">시군구에서 그 지역 당선인으로</span></li>'
        f'<li><a href="/parties.html">정당 계보</a>'
        f'<span class="ph-meta">정당에서 소속 인물로</span></li>'
        f'<li><a href="/search.html">통합 검색</a>'
        f'<span class="ph-meta">이름·지역·정당을 한 번에</span></li>'
        f'</ul></section>')
    title = f'역대 선거 인물 {len(persons):,}명 — 출마·당선 기록 | polis'
    desc = (f'역대 대선·총선·지방선거에 나온 인물 {len(persons):,}명의 출마·당선 기록. '
            f'이름 초성으로 찾거나 지역·정당에서 따라갈 수 있습니다.')
    html = HUB_TEMPLATE.format(
        nav=render_nav(menu_for_path("person/index.html")),
        title=esc(title), desc=esc(desc), canon="/person/",
        jsonld=hub_jsonld(persons, "/person/"),
        h1="역대 선거 인물",
        lede=esc(f'대선·총선·지방선거에 나온 {len(persons):,}명. '
                 f'사람마다 언제 어디서 누구와 붙어 몇 표 차로 갈렸는지.'),
        body=body)
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    sitemap_urls.append("/person/")
    return n_made + 1


def main():
    pi = json.loads(INDEX.read_text(encoding="utf-8"))
    # 당선 선출직(국회의원·단체장·교육감·대통령 등) — dob 있고 + 의원이거나 무언가 당선.
    # 낙선만 한 후보는 원래 페이지 없이 검색에만 뒀다(노이즈 방지). 다만 **공약이 있으면**
    # 예외 — 공약 5~10건은 1회 출마 당선자보다 고유 콘텐츠가 많고, 낙선자 공약은 선거 후
    # 일정 기간이 지나면 NEC에서 사라져 여기 아니면 볼 곳이 없다.
    has_pledge = {f.stem for f in PLEDGE_BY_PERSON.glob("*.json")} if PLEDGE_BY_PERSON.exists() else set()
    persons = [p for p in pi["persons"]
               if p.get("dob") and (p.get("assembly_id")
                                    or any(r.get("won") for r in p.get("races", []))
                                    or p["id"] in has_pledge)]
    print(f"의원 entry: {len(persons)} (전체 {len(pi['persons'])} 중)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sitemap_urls = []
    # 시군구→slug 색인은 모든 페이지가 같다 — 한 번만 만들어 심는다(4,326회 반복 금지).
    _REGION_JSON = json.dumps(region_slug_index(), ensure_ascii=False, separators=(",", ":"))
    n_written = 0
    valid_slugs = set()
    for p in persons:
        slug = slugify(p["name"], p["dob"])
        valid_slugs.add(slug)
        page_dir = OUT_DIR / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        # 그 인물 entry만 inline (소형)
        data = {"persons": [p]}
        data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        # description: 다회차·정당 요약
        rounds = sorted({r.get("round", "") for r in p["races"] if r.get("round")})
        parties = p.get("parties", [])[:3]
        desc = (
            f"{p['name']} 선거 이력. {len(p['races'])}회 출마해 {p['wins']}회 당선"
            f"·{p['losses']}회 낙선 — 회차별 지역·정당·득표율·순위까지."
            + (f" 소속: {' · '.join(parties)}." if parties else "")
        )
        lede, body = static_body(p)
        ld = jsonld(p, slug, desc)
        html = TEMPLATE.format(
            nav=render_nav(menu_for_path(f"person/{slug}/index.html")),
            name=p["name"],
            title=esc(page_title(p)),
            desc=desc,
            slug=slug,
            data_json=data_json,
            lede=lede,
            static_body=body,
            region_slugs=_REGION_JSON,
            jsonld=ld,
        )
        (page_dir / "index.html").write_text(html, encoding="utf-8")
        sitemap_urls.append(f"/person/{slug}/")
        n_written += 1

    n_hub = build_hub(persons, valid_slugs, sitemap_urls)

    # stale 디렉터리 제거 — 옛 빌드(생년월일 보정·동명이인 분리 등)로 슬러그가 바뀐 잔존분.
    import shutil
    n_stale = 0
    for dch in OUT_DIR.iterdir():
        if dch.is_dir() and dch.name not in valid_slugs:
            shutil.rmtree(dch)
            n_stale += 1

    SITEMAP_OUT.write_text("\n".join(sitemap_urls) + "\n", encoding="utf-8")
    print(f"→ {OUT_DIR.relative_to(ROOT)}/ : {n_written} pages "
          f"+ 허브 {n_hub} (stale 제거 {n_stale})")
    print(f"→ {SITEMAP_OUT.relative_to(ROOT)} : {len(sitemap_urls)} URLs "
          f"(인물 {n_written} + 허브 {n_hub}, sitemap 통합용)")


if __name__ == "__main__":
    main()
