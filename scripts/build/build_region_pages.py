"""지역 entity 페이지 → /region/{시도}-{시군구}/index.html.

polis에는 이미 선거·인물·정당이 있는데 **지역**만 entity가 아니었다. 같은 시군구가
역대 대선·총선·지선에서 어떻게 갈렸는지는 데이터에 다 있지만 한곳에 모이지 않았다.

새 데이터를 만들지 않는다. data/results/*.json의 시군구 단위 race를 모아 재배열할 뿐이다.

본문은 빌드 시점에 HTML로 찍는다. 7월 색인 사고(2,190페이지 미색인)의 원인이 '데이터는
있는데 HTML에 없음'이었고, 같은 실수를 새 표면에서 반복하지 않는다.

Output:
  region/{시도}-{시군구}/index.html
  data/sitemap_region.txt
"""
from __future__ import annotations
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data/results"
OUT_DIR = ROOT / "region"
SITEMAP_OUT = ROOT / "data/sitemap_region.txt"
SITE = "https://polis.ysw.kr"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_nav_html import render_nav, menu_for_path  # noqa: E402
from party_canon import disambiguate_party  # noqa: E402

# 정당 페이지가 있는 이름만 링크한다. 무소속·미등록 군소정당은 그냥 글자.
_REG = json.loads((ROOT / "data/parties/registry.json").read_text(encoding="utf-8"))["parties"]
PARTY_PAGES = set(_REG.keys())


# 후보 이름 → 인물 페이지. build_person_links의 (직|지역|이름) 색인을 그대로 쓴다.
# 동명이인으로 갈리는 키는 색인에 없으므로 억지로 잇지 않는다 — 죽은 링크보다 글자가 낫다.
_PERSON_LINKS: dict = {}


def person_href(eid: str, tc: str, place: str, name: str) -> str | None:
    if eid not in _PERSON_LINKS:
        fp = ROOT / "data/person-links" / f"{eid}.json"
        try:
            _PERSON_LINKS[eid] = json.loads(fp.read_text(encoding="utf-8")).get("links") or {}
        except Exception:
            _PERSON_LINKS[eid] = {}
    slug = _PERSON_LINKS[eid].get(f"{tc}|{place}|{name}")
    return f"/person/{quote(slug)}/" if slug else None


def party_cell(name: str, date: str) -> str:
    canon = disambiguate_party(name, date or "")
    if canon in PARTY_PAGES:
        return f'<a href="/party/{quote(canon)}/">{esc(name)}</a>'
    return esc(name)

# 회차가 이보다 적으면 페이지를 만들지 않는다 — 한두 번 스친 옛 지명까지 만들면
# 내용도 없고 검색 노이즈만 된다(오늘 배운 thin content 문제).
MIN_ROUNDS = 3

# 결손은 '—'로 쓰고 무엇인지 title로 밝힌다. 0으로 쓰면 사용자가 실제 값으로 읽는다.
NO_DATA = '<span class="rg-nd" title="원자료에 투표수가 없습니다">—</span>'
# 무투표는 결손이 아니라 도메인 사실이다 — 후보가 정수 이하라 투표 자체가 없었다.
UNCONTESTED = '<span class="rg-nv" title="후보가 정수 이하라 투표 없이 당선됐습니다">무투표</span>'

# 시도 개명은 같은 지역이다. 정규화하지 않으면 '강원도 홍천군'과 '강원특별자치도
# 홍천군'이 별개 페이지가 되어, 한 지역의 기록이 둘로 쪼개진다.
# (시군구 쪽 옛 이름 — 명주군·원성군 등 — 은 실제로 다른 행정단위였으므로 합치지 않는다.)
# 제주도→제주특별자치도(2006)는 강원·전북과 같은 개칭인데 빠져 있었다. 시군구
# 행이 없어 지역 페이지는 안 갈렸지만, 시도 단위로 보면 제주가 둘로 쪼개진다.
SIDO_CANON = {"강원도": "강원특별자치도", "전라북도": "전북특별자치도",
              "제주도": "제주특별자치도"}

# 동명 시군구(중구·서구·남구…)를 구분하려면 시도가 필요하다.
SIDO_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
    "제주특별자치도": "제주",
}


def sido_canon(sd: str) -> str:
    return SIDO_CANON.get(sd, sd)


def sido_short(sd: str) -> str:
    return SIDO_SHORT.get(sd, sd)

KIND_LABEL = {"presidential": "대선", "national_assembly": "총선",
              "general_election": "총선", "local": "지선", "byelection": "재보궐"}


def esc(s) -> str:
    return (str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def load_all() -> list:
    out = []
    for fp in sorted(RESULTS.glob("*.json")):
        if ".sigungu." in fp.name:
            continue
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        races = list(d.get("races") or [])
        if d.get("_meta", {}).get("chunked"):
            cp = fp.with_name(fp.stem + ".sigungu.json")
            if cp.exists():
                races += json.loads(cp.read_text(encoding="utf-8")).get("races") or []
        out.append((fp.stem, d.get("_meta") or {}, races))
    return out


def election_meta(eid: str) -> dict:
    p = ROOT / "data/elections" / f"{eid}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


CONTAINMENT = ROOT / "data/geography/containment.json"
_FOLD: dict | None = None


def fold_index() -> dict:
    """(시도, 하위 이름) → (상위 이름, 그 이름을 지역 페이지로 둘 것인가).

    **근거는 data/geography/containment.json이지 이름 모양이 아니다.** 예전에는
    '{X}시{Y}구'·'{Z}갑구' 같은 꼴로 추측했는데, 모양은 사실을 모른다 —
    '부천시오정구'의 정을 선거구 정으로 읽어 '부천시오구'를 만든 적이 있고,
    '성남시중원구·분당구'(국회의원 선거구)를 일반구로 셌다.

    containment.json은 exhaustive=true일 때만 합산을 허락한다. 그 판정은
    scripts/audit/verify_containment.py가 매 게이트마다 산술로 다시 확인한다.

    children_kind=electoral_district는 개표만 선거구 단위로 나온 것이다. 장소가
    아니므로 그 이름의 지역 페이지는 만들지 않는다(동대문갑구). 일반구는 실재하는
    행정단위라 제 페이지를 유지한다(성남시분당구).
    """
    global _FOLD
    if _FOLD is None:
        idx: dict = {}
        try:
            recs = json.loads(CONTAINMENT.read_text(encoding="utf-8"))["containments"]
        except Exception:                                        # noqa: BLE001
            recs = []
        for c in recs:
            if not c.get("exhaustive") or c.get("aggregation") != "sum":
                continue
            _k, sd, parent = c["parent"].split(":", 2)
            keep = c.get("children_kind", "admin_unit") != "electoral_district"
            for child in c["children"]:
                _ck, csd, cname = child.split(":", 2)
                if csd == sd:
                    idx[(sd, cname)] = (parent, keep)
        _FOLD = idx
    return _FOLD


def fold_target(sd: str, sg: str) -> tuple:
    """(합칠 상위 단위, 이 키 자체를 지역 페이지로 둘 것인가).

    원천 자료가 우리 '지역'과 다른 단위로 집계될 때가 두 가지 있다.

    **선거구 집계** — 5·6·7대 대선(과 2대)은 서울 5개 구·광주시·부산진구를
    국회의원 선거구 갑/을/병/정으로 나눠 집계한다. '동대문갑구'는 장소가 아니다.
    그런데 우리는 그걸 지역으로 만들어, 실재하지 않는 페이지 12개가 생기고 실재하는
    동대문구에서는 1963·1967·1971 대선이 통째로 비었다.

    **일반구** — 성남시수정구·중원구·분당구는 성남시의 일반구다. NEC는 대선·
    광역단체장·교육감을 구 단위로 개표하고 기초단체장만 시 단위로 낸다. 접지 않아
    성남시 페이지에 광역 0·교육감 0·대선 2건만 남았다(정상은 5~7·5~6·18~30).

    어느 쪽인지, 접어도 되는지는 containment.json이 정한다.
    """
    return fold_index().get((sd, sg or ""), (None, True))


def merge_rows(rows: list) -> dict:
    """여러 하위 단위 row를 하나로 — 표를 합치고 1위·투표율을 **다시 계산**한다.

    행을 옮기는 것으로는 안 된다. 구별 1위가 시 전체 1위와 다를 수 있다(2022
    경기지사: 도 전체는 김동연이 이겼지만 성남시 합산은 김은혜 51.8% vs 46.2%).
    """
    votes: dict = defaultdict(int)
    party: dict = {}
    el = vo = 0
    el_known = vo_known = False
    for r in rows:
        if r.get("electors"):
            el += r["electors"]
            el_known = True
        if r.get("voters") is not None:
            vo += r["voters"]
            vo_known = True
        for c in (r.get("candidates") or []):
            nm = (c.get("name") or "").strip()
            if not nm:
                continue
            votes[nm] += c.get("votes") or 0
            party.setdefault(nm, c.get("party"))
    if not votes:
        return {}
    total = sum(votes.values())
    top = max(votes.items(), key=lambda kv: kv[1])
    return {
        "candidates": [{"name": top[0], "party": party.get(top[0]),
                        "votes": top[1],
                        "pct": round(top[1] / total * 100, 2) if total else None}],
        "electors": el if el_known else None,
        "voters": vo if vo_known else None,
    }


# 이 지역 1위가 실제 당선자와 같았나 — 기사에서 '표심'이라 부르는 그것.
# 대통령은 전국 당선자와, 광역단체장·교육감은 그 시도 당선자와 견준다.
# 기초단체장은 지역 자체가 선거구라 늘 같으므로 견주지 않는다.
COMPARE_TC = {"1": "전국", "3": "sido", "11": "sido"}


def winners(races_by_eid: dict) -> dict:
    """(회차, 직위, 시도) → 실제 당선자 이름. 시도가 없으면(대통령) ''.

    없는 회차는 넣지 않는다 — 모르면 견주지 않는다. 옛 대선 일부는 전국 집계
    행이 아예 없어서, 억지로 시도별 1위를 모아 전국 1위를 만들면 그건 우리가
    계산한 값이지 당선 사실이 아니다.
    """
    out: dict = {}
    for eid, races in races_by_eid.items():
        for r in races:
            tc, scope = r.get("sg_typecode"), r.get("scope")
            cs = sorted((r.get("candidates") or []),
                        key=lambda c: -(c.get("votes") or 0))
            if not cs:
                continue
            if tc == "1" and scope == "nation":
                out[(eid, tc, "")] = cs[0].get("name")
            elif tc in ("3", "11") and scope == "sido":
                sd = sido_canon(r.get("sido"))
                if sd:
                    out[(eid, tc, sd)] = cs[0].get("name")
    return out


def collect() -> dict:
    """(시도, 시군구) → [{eid, date, kind, label, party, name, pct, turnout}]"""
    by_region = defaultdict(list)
    direct: dict = {}                       # (시도, 시군구, 회차, 직위) → 원천 row
    rolled: dict = defaultdict(list)        #   └ 모시로 접을 하위 구 row들
    ctx: dict = {}                          # (회차, 직위) → (날짜, 종류, 이름)
    all_rounds = list(load_all())
    won = winners({eid: races for eid, _meta, races in all_rounds})
    collect.won = won          # 시도 층도 같은 당선자 표를 쓴다
    for eid, meta, races in all_rounds:
        em = election_meta(eid)
        kind = em.get("kind") or ""
        date = em.get("date") or meta.get("election_date") or ""
        name = em.get("name") or meta.get("election") or eid
        # 시군구 단위 대표 race — 그 지역의 '1위'가 무엇이었는지.
        # 지선은 기초단체장(4), 대선·총선은 시군구 분해 row.
        for r in races:
            sg, sd = r.get("sigungu"), sido_canon(r.get("sido"))
            if not sg or not sd:
                continue
            scope, tc = r.get("scope"), r.get("sg_typecode")
            if not ((tc == "4" and scope == "sigungu")
                    or (tc == "1" and scope == "sigungu")
                    or (tc in ("3", "11") and scope == "sigungu")):
                continue
            direct[(sd, sg, eid, tc)] = r
            ctx[(eid, tc)] = (date, kind, name)
            # 일반구는 모시에도 담는다. 대선·광역단체장·교육감은 구 단위로만 오므로
            # 접지 않으면 모시 페이지에서 그 직위가 통째로 사라진다.
            pc, _keep = fold_target(sd, sg)
            if pc:
                rolled[(sd, pc, eid, tc)].append(r)

    OFFICE = {"1": "대통령", "3": "광역단체장", "4": "기초단체장", "11": "교육감"}

    def emit(sd, sg, eid, tc, r, merged):
        cs = sorted((r.get("candidates") or []), key=lambda c: -(c.get("votes") or 0))
        if not cs:
            return
        top = cs[0]
        # 없는 값은 0이 아니다. 1~4회 지선은 electors만 있고 voters가 없어서,
        # None을 0으로 강제하면 0/134603 = '투표율 0.0%'라는 있지도 않은 사실이 생긴다.
        el, vo = r.get("electors"), r.get("voters")
        date, kind, name = ctx[(eid, tc)]
        by_region[(sd, sg)].append({
            "eid": eid, "date": date, "kind": kind,
            "election": name,
            "office": OFFICE.get(tc, tc),
            "party": top.get("party") or "무소속", "name": top.get("name"),
            "uncontested": bool(r.get("is_uncontested") or top.get("uncontested")),
            # 인물 링크용 — person-links 색인의 (직|지역) 키를 그대로 보존한다.
            # 기초 단위(4·6)는 시군구명이, 광역 단위(1·3·11)는 시도명이 키다.
            "tc": tc,
            "place": sg if tc in ("4", "6") else sd,
            "pct": top.get("pct"),
            "turnout": (round(vo / el * 100, 1) if (el and vo is not None) else None),
            "merged": merged,
            # 실제 당선자 — 모르는 회차는 None으로 두고 아무 말도 하지 않는다.
            "won_by": won.get((eid, tc, "" if tc == "1" else sd)),
            "won_scope": ("전국" if tc == "1" else sido_short(sd)) if tc in COMPARE_TC else None,
        })

    for (sd, sg, eid, tc), r in direct.items():
        # 선거구는 장소가 아니다. 표는 위에서 실재 단위로 접었으니, 여기서 제 이름의
        # 지역을 또 만들면 같은 표가 두 페이지에 실린다.
        if not fold_target(sd, sg)[1]:
            continue
        emit(sd, sg, eid, tc, r, False)

    # 합산본은 **직접 행이 없는 (회차, 직위)에만** 넣는다. 있는데도 덮으면 이중
    # 집계다 — 청주 2014는 기초단체장이 통합 기준(상당+흥덕+청원군) 한 행으로
    # 이미 와 있고, 그 위에 구 합산을 얹으면 같은 표를 두 번 세게 된다.
    for (sd, pc, eid, tc), rows in rolled.items():
        if (sd, pc, eid, tc) in direct:
            continue
        m = merge_rows(rows)
        if m:
            emit(sd, pc, eid, tc, m, True)
    return by_region


TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<script>try{{var _m=localStorage.getItem('vote-ysw-theme');if(_m==='dark')document.documentElement.setAttribute('data-theme','dark');else if(_m==='light')document.documentElement.setAttribute('data-theme','light');}}catch(_e){{}}</script>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="theme-color" content="#5b54d6">
<base href="/">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="https://polis.ysw.kr/og.png">
<link rel="canonical" href="/region/{slug}/">
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
{swing}
  </section>
{kin}
  <section>{table}</section>
  <footer class="foot">
    <p class="fine">{foot}</p>
  </footer>
</main>
<script src="assets/parties.js"></script>
<script src="assets/theme.js"></script>
<script src="assets/nav.js"></script>
</body>
</html>
"""




# 합산한 행에 붙이는 표시. 모시 페이지에 '이 표는 합산이다'라고 통째로 적으면
# 거짓이 된다 — 기초단체장은 시 단위 원본이고, 대선도 회차에 따라 원본이 있다
# (성남시 1987). 합산한 행만 그렇다고 말한다.
MERGED = ('<sup class="rg-mg" title="구 단위 개표를 합산한 값입니다">'
          '합산</sup>')


def merged_mark(r: dict) -> str:
    return MERGED if r.get("merged") else ""


def kin_block(sd: str, sg: str, by_region: dict) -> str:
    """모시↔구를 잇는다. 지금은 양쪽 다 링크가 **하나도** 없다.

    구 페이지에 기초단체장이 0건인 것은 결손이 아니다 — 성남시장은 시 단위 선거라
    구에서 뽑지 않는다. 그런데 페이지는 그 사실을 말하지 않아서, 보는 사람에게는
    자료가 빠진 것과 구별되지 않는다. 없는 이유를 적고 있는 곳으로 보낸다.
    """
    # **페이지가 실제로 만들어지는 곳만** 센다. by_region에는 MIN_ROUNDS 미달로
    # 페이지가 안 생기는 지역도 들어 있어서, 그대로 링크하면 404가 된다
    # (대전시중구·인천시남구 등 18개를 이렇게 만들었다).
    names = {k[1] for k, rows in by_region.items()
             if k[0] == sd and len(rows) >= MIN_ROUNDS}
    m = re.match(r"^(.+?시)(.+구)$", sg)
    parent = m.group(1) if (m and m.group(1) in names) else None
    kids = sorted(x for x in names
                  if x != sg and x.startswith(sg)
                  and re.match(r"^" + re.escape(sg) + r".+구$", x))

    up = (f'<a href="/region/{quote(sd)}/">{esc(sd)} 전체</a>'
          if (ROOT / "region" / sd).exists() else "")
    if parent:
        return (f'<section class="rg-kin"><p>{esc(sg)}는 {esc(parent)}의 일반구입니다. '
                f'기초단체장({esc(parent)}장)은 시 전체가 한 선거구라 구별로 뽑지 '
                f'않습니다 — <a href="/region/{quote(f"{sd}-{parent}")}/">'
                f'{esc(parent)}</a>에서 볼 수 있습니다.'
                + (f' 광역단체장·교육감은 {up}.' if up else "")
                + '</p></section>')
    if kids:
        li = " · ".join(
            f'<a href="/region/{quote(f"{sd}-{k}")}/">{esc(k[len(sg):])}</a>'
            for k in kids)
        return (f'<section class="rg-kin"><p>{esc(sg)}의 일반구 {len(kids)}곳: {li}. '
                f'대선·광역단체장·교육감은 구 단위로 개표되므로, 그런 회차는 구별 '
                f'득표를 합산해 1위와 투표율을 다시 계산했습니다'
                f'(표에서 <span class="rg-mg">합산</span>으로 표시).'
                + (f' 광역 단위 결과는 {up}.' if up else "")
                + '</p></section>')
    # 관계가 없어도 시도로 올라가는 길은 남긴다 — 시군구 356곳 전부가 자기 시도로
    # 가는 링크를 갖게 된다.
    if up:
        return (f'<section class="rg-kin"><p>이 지역이 속한 광역단체의 역대 '
                f'광역단체장·교육감과 대선 판세는 {up}에서.</p></section>')
    return ""


def name_cell(r: dict) -> str:
    """1위 후보 — 인물 페이지가 있으면 링크. 지역에서 사람으로 넘어가는 길이다.
    (지역 페이지에서 인물로 나가는 링크가 하나도 없었다 — 측정: person 0)

    시도 표도 같은 칸을 쓴다. build_page 안에 숨어 있어 시도 쪽에서 부를 수 없었다.
    """
    nm = r.get("name") or ""
    if not nm:
        return ""
    h = person_href(r["eid"], r.get("tc") or "", r.get("place") or "", nm)
    return f'<a href="{h}">{esc(nm)}</a>' if h else esc(nm)


def num_cell(r: dict, key: str) -> str:
    """숫자 칸 — 세 상태를 구분한다: 값 / 무투표(사실) / 자료 없음(결손).
    셋을 다 0.0%로 쓰면 '아무도 안 찍었다'는 없던 사실이 만들어진다."""
    if r.get("uncontested"):
        return UNCONTESTED
    v = r.get(key)
    return f"{v:.1f}%" if v is not None else NO_DATA


def diverged(r: dict) -> bool:
    """이 지역 1위가 실제 당선자와 달랐는가. 모르면 False — 모름은 다름이 아니다."""
    w, n = r.get("won_by"), r.get("name")
    return bool(w and n and w != n)


def winner_note(r: dict) -> str:
    """다른 회차에만 실제 당선자를 덧붙인다. 같은 회차까지 적으면 표가 같은 이름으로
    가득 차서, 정작 갈린 회차가 눈에 안 띈다."""
    if not diverged(r):
        return ""
    return (f'<span class="rg-vs" title="이 지역 1위와 실제 당선자가 다릅니다">'
            f'{esc(r["won_scope"])} 당선 {esc(r["won_by"])}</span>')


def swing_line(rows: list) -> str:
    """'여기 표심은 전체와 달랐다' — 기사들이 하는 그 말을 숫자로.

    견줄 수 있는 것만 센다(대통령·광역단체장·교육감). 기초단체장은 지역 자체가
    선거구라 늘 같고, 실제 당선자를 모르는 옛 회차는 분모에서도 뺀다.
    """
    cmp_rows = [r for r in rows if r.get("won_by") and r.get("name")]
    if not cmp_rows:
        return ""
    diff = [r for r in cmp_rows if diverged(r)]
    if not diff:
        label = " · ".join(sorted({r["office"] for r in cmp_rows}))
        return (f'<p class="rg-swing">{esc(label)} {len(cmp_rows)}건 모두에서 이 지역 '
                f'1위가 실제 당선자와 같았습니다.</p>')
    offices = sorted({r["office"] for r in cmp_rows})
    # 견준 직위가 하나뿐이면 연도마다 그 이름을 되풀이하지 않는다
    # ('대통령 15건 중 4건 … 2022 대통령 · 1971 대통령').
    years = " · ".join(
        esc((r.get("date") or "")[:4]) + ("" if len(offices) == 1
                                          else " " + esc(r["office"]))
        for r in sorted(diff, key=lambda r: r.get("date") or "", reverse=True)[:4])
    more = f' 외 {len(diff) - 4}건' if len(diff) > 4 else ""
    # 라벨은 **실제로 견준 직위**에서 뽑는다. 고정 문구로 두면 시도 페이지에서
    # 거짓이 된다 — 거기선 대통령만 견주는데(광역단체장·교육감은 시도가 선거구
    # 자체라 견줄 상대가 없다) "대통령·광역단체장·교육감 15건"이라고 적혔다.
    label = " · ".join(offices)
    return (f'<p class="rg-swing">{esc(label)} {len(cmp_rows)}건 중 '
            f'<b>{len(diff)}건</b>에서 이 지역 1위가 실제 당선자와 달랐습니다 — '
            f'{years}{more}.</p>')


# ── 시도 층 ────────────────────────────────────────────────────────────────
# 시군구 366곳과 전국 사이가 비어 있었다. '경기도 지방선거 결과'는 실제로 찾는
# 말인데 착지할 페이지가 없었고, 광역단체장을 누가 했는지는 **어느 시군구
# 페이지에도 없다** — 시군구의 '광역단체장' 줄은 그 지역 1위지 당선자가 아니다.

SIDO_OFFICE = {"1": "대통령", "3": "광역단체장", "11": "교육감"}

# 꼬리말은 페이지 종류마다 다르다. 시도 페이지에 '시군구 단위로 집계한 기록'이라고
# 적으면 거짓이다 — 거기 광역단체장은 집계가 아니라 당선 결과다.
_NO_VOTE_NOTE = (
    '회차별 상세는 각 아카이브에서 볼 수 있습니다. 투표율의 '
    '<span class="rg-nd">—</span>는 원자료에 투표수가 없는 회차입니다(1~4회 지방선거).'
)
FOOT_SGG = '시군구 단위로 1위를 집계한 기록입니다. ' + _NO_VOTE_NOTE
FOOT_SIDO = ('광역단체장·교육감은 이 시도가 선거구 자체라 <b>당선 결과</b>이고, '
             '대통령은 이 시도에서 1위를 한 후보입니다. ') + _NO_VOTE_NOTE


def collect_sido(won: dict) -> dict:
    """시도 → 역대 선거 행. 시군구 페이지와 같은 모양으로 낸다.

    대통령은 시도 집계 행(scope=sido)이 있으면 그것을, 없으면 그 시도의 시군구
    행을 합산한다. 광역단체장·교육감은 시도가 선거구 자체라 scope=sido 행이 곧
    당선 결과다.
    """
    by_sido = defaultdict(list)
    for eid, meta, races in load_all():
        em = election_meta(eid)
        kind = em.get("kind") or ""
        date = em.get("date") or meta.get("election_date") or ""
        name = em.get("name") or meta.get("election") or eid

        direct: dict = {}
        parts: dict = defaultdict(list)
        for r in races:
            sd = sido_canon(r.get("sido"))
            tc, scope = r.get("sg_typecode"), r.get("scope")
            if not sd or tc not in SIDO_OFFICE:
                continue
            if scope == "sido":
                direct[(sd, tc)] = r
            elif tc == "1" and scope == "sigungu" and r.get("sigungu"):
                parts[(sd, tc)].append(r)

        for (sd, tc), r in list(direct.items()):
            merged = False
            _emit_sido(by_sido, sd, tc, r, eid, date, kind, name, won, merged)
        for (sd, tc), rows in parts.items():
            if (sd, tc) in direct:      # 시도 집계 행이 있으면 그것이 정본이다
                continue
            m = merge_rows(rows)
            if m:
                _emit_sido(by_sido, sd, tc, m, eid, date, kind, name, won, True)
    return by_sido


def _emit_sido(by_sido, sd, tc, r, eid, date, kind, name, won, merged):
    cs = sorted((r.get("candidates") or []), key=lambda c: -(c.get("votes") or 0))
    if not cs:
        return
    top = cs[0]
    el, vo = r.get("electors"), r.get("voters")
    by_sido[sd].append({
        "eid": eid, "date": date, "kind": kind, "election": name,
        "office": SIDO_OFFICE[tc], "tc": tc,
        "party": top.get("party") or "무소속", "name": top.get("name"),
        "uncontested": bool(r.get("is_uncontested") or top.get("uncontested")),
        "place": sd,
        "pct": top.get("pct"),
        "turnout": (round(vo / el * 100, 1) if (el and vo is not None) else None),
        "merged": merged,
        # 광역단체장·교육감은 시도가 선거구 자체라 견줄 상대가 없다 — 이 행이
        # 곧 당선 결과다. 대통령만 전국 당선자와 견준다.
        "won_by": won.get((eid, tc, "")) if tc == "1" else None,
        "won_scope": "전국" if tc == "1" else None,
    })


def build_page(sd: str, sg: str, rows: list, by_region: dict) -> str:
    rows = sorted(rows, key=lambda r: (r["date"] or "", r["office"]), reverse=True)
    slug = f"{sd}-{sg}"
    years = [r["date"][:4] for r in rows if r.get("date")]
    span = f"{min(years)}~{max(years)}년 " if years else ""
    parties = {}
    for r in rows:
        parties[r["party"]] = parties.get(r["party"], 0) + 1
    top_parties = " · ".join(p for p, _ in sorted(parties.items(), key=lambda x: -x[1])[:3])
    lede = esc(f"{span}선거 {len(rows)}건 — 1위 정당 {top_parties}")
    # 설명도 '선거 기록'이 아니라 사람이 치는 '선거 결과'로 연다. 뒤에는 이 페이지에
    # 실제로 있는 것(1위 정당·후보·득표율·투표율)을 적어 무엇을 보러 오는지 맞춘다.
    desc = esc(f"{sd} {sigungu_short(sg)} 선거 결과. {span}대선·총선·지선 {len(rows)}건의 "
               f"1위 정당·후보와 득표율·투표율. 최다 1위 {top_parties}.")

    trs = []
    for r in rows:
        kl = KIND_LABEL.get(r["kind"], "")
        trs.append(
            f'<tr><td>{esc((r.get("date") or "")[:4])}</td>'
            f'<td><a href="/archive/{esc(r["eid"])}/">{esc(r["election"])}</a></td>'
            f'<td>{esc(r["office"])}{merged_mark(r)}</td>'
            f'<td>{party_cell(r["party"], r.get("date"))}</td>'
            f'<td>{name_cell(r)}{winner_note(r)}</td>'
            f'<td>{num_cell(r, "pct")}</td>'
            f'<td>{num_cell(r, "turnout")}</td></tr>')
    table = ('<table class="pp-static"><caption>역대 선거 — 이 지역 1위</caption><thead><tr>'
             '<th>연도</th><th>선거</th><th>직</th><th>1위 정당</th><th>1위 후보</th>'
             '<th>득표율</th><th>투표율</th></tr></thead><tbody>'
             + "".join(trs) + "</tbody></table>")

    ld = {"@context": "https://schema.org", "@type": "BreadcrumbList",
          "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": "모든 선거",
               "item": f"{SITE}/elections.html"},
              {"@type": "ListItem", "position": 2, "name": f"{sd} {sg}"}]}
    return TEMPLATE.format(
        title=esc(f"{sg} 선거 결과 — {sd} 역대 대선·총선·지선 1위와 투표율 | polis"),
        og_title=esc(f"{sg} 선거 결과 — {sd}"),
        h1=esc(f"{sd} {sg}"),
        slug=esc(slug), desc=desc, lede=lede, table=table, foot=FOOT_SGG,
        kin=kin_block(sd, sg, by_region),
        swing=swing_line(rows),
        nav=render_nav(menu_for_path(f"region/{slug}/index.html")),
        jsonld='<script type="application/ld+json">'
               + json.dumps(ld, ensure_ascii=False) + "</script>")


# 2026 지선부터 전남+광주가 통합 광역단체를 이뤘다(elections.json의 sido_merge).
# 광역 선거만 통합 단위로 치르고 기초 선거는 종전 시군구로 치른다 — 그래서
# 시군구 목록은 옛 두 시도에서 가져와야 한다.
SIDO_MERGED_FROM = {"전남광주특별시": ["전라남도", "광주광역시"]}


def sido_sigungu(sd: str, by_region: dict) -> list:
    """이 시도에 속한 시군구 페이지 목록. 통합 시도는 옛 시도들에서 모은다."""
    srcs = SIDO_MERGED_FROM.get(sd, [sd])
    out = []
    for src in srcs:
        out += [k[1] for k, rows in by_region.items()
                if k[0] == src and len(rows) >= MIN_ROUNDS]
    return sorted(set(out))


def sido_kin(sd: str, kids: list) -> str:
    merged = SIDO_MERGED_FROM.get(sd)
    if merged:
        li = " · ".join(esc(x) for x in merged)
        return (f'<section class="rg-kin"><p>{esc(sd)}는 2026년 지방선거부터 '
                f'{li}가 광역 단위로 통합된 자치단체입니다. 광역단체장·교육감은 '
                f'통합 단위로 뽑고, 기초단체장·지방의원은 종전 시군구에서 그대로 '
                f'뽑습니다.</p></section>')
    if not kids:
        return ""
    return ""


def sido_units_block(sd: str, kids: list) -> str:
    """이 시도의 시군구 — **지금 있는 곳과 없어진 곳을 갈라서** 낸다.

    허브가 이미 쓰는 규칙(current_units)을 그대로 쓴다. 안 가르면 경기도 목록에
    고양군·광주군·부천군 같은 옛 지명과 고양시덕양구 같은 일반구가 현재 시군과
    한 줄에 섞여 68곳이 된다 — 내 지역을 찾으려는 사람에게는 목록이 아니라 벽이다.
    """
    if not kids:
        return ""
    cur = current_pairs()
    srcs = SIDO_MERGED_FROM.get(sd, [sd])

    def link(src, k):
        return f'<a href="/region/{quote(f"{src}-{k}")}/">{esc(k)}</a>'

    now, past = [], []
    for src in srcs:
        for k in sorted(x for x in kids
                        if (ROOT / "region" / f"{src}-{x}").exists()):
            # 일반구는 모시로 들어가 있으므로 목록에서는 뺀다 — 모시 페이지가
            # 자기 구를 따로 잇는다.
            if re.match(r"^(.+?시)(.+구)$", k) and re.match(
                    r"^(.+?시)(.+구)$", k).group(1) in kids:
                continue
            (now if (src, k) in cur else past).append(link(src, k))
    if not now and not past:
        return ""
    out = f'<section class="rg-sec"><h2>{esc(sd)}의 시군구 {len(now)}곳</h2>'
    out += f'<div class="rg-units">{" ".join(now)}</div>'
    if past:
        out += (f'<details class="rg-past"><summary>지금 이 시도의 시군구가 아닌 이름 {len(past)}곳</summary>'
                f'<div class="rg-units">{" ".join(past)}</div></details>')
    return out + "</section>"


def build_sido_page(sd: str, rows: list, by_region: dict) -> str:
    rows = sorted(rows, key=lambda r: (r["date"] or "", r["office"]), reverse=True)
    years = [r["date"][:4] for r in rows if r.get("date")]
    span = f"{min(years)}~{max(years)}년 " if years else ""
    n_gov = sum(1 for r in rows if r["office"] == "광역단체장")
    parties = {}
    for r in rows:
        parties[r["party"]] = parties.get(r["party"], 0) + 1
    top_parties = " · ".join(p for p, _ in sorted(parties.items(),
                                                  key=lambda x: -x[1])[:3])
    kids = sido_sigungu(sd, by_region)
    lede = esc(f"{span}선거 {len(rows)}건 — 광역단체장 {n_gov}회 · 1위 정당 {top_parties}")
    desc = esc(f"{sd} 선거 결과. 역대 광역단체장 {n_gov}명과 교육감, 대선에서 이 "
               f"시도가 어떻게 갈렸는지. {span}{len(rows)}건 · 시군구 {len(kids)}곳.")
    table = sido_table(rows)
    ld = {"@context": "https://schema.org", "@type": "BreadcrumbList",
          "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": "지역별 선거 결과",
               "item": f"{SITE}/region/"},
              {"@type": "ListItem", "position": 2, "name": sd}]}
    return TEMPLATE.format(
        title=esc(f"{sd} 선거 결과 — 역대 광역단체장·교육감과 대선 판세 | polis"),
        og_title=esc(f"{sd} 선거 결과"),
        h1=esc(sd),
        slug=esc(sd), desc=desc, lede=lede,
        swing=swing_line(rows),
        kin=sido_kin(sd, kids),
        table=table + sido_units_block(sd, kids), foot=FOOT_SIDO,
        nav=render_nav(menu_for_path(f"region/{sd}/index.html")),
        jsonld='<script type="application/ld+json">'
               + json.dumps(ld, ensure_ascii=False) + "</script>")


def sido_table(rows: list) -> str:
    trs = []
    for r in rows:
        trs.append(
            f'<tr><td>{esc((r.get("date") or "")[:4])}</td>'
            f'<td><a href="/archive/{esc(r["eid"])}/">{esc(r["election"])}</a></td>'
            f'<td>{esc(r["office"])}{merged_mark(r)}</td>'
            f'<td>{party_cell(r["party"], r.get("date"))}</td>'
            f'<td>{name_cell(r)}{winner_note(r)}</td>'
            f'<td>{num_cell(r, "pct")}</td>'
            f'<td>{num_cell(r, "turnout")}</td></tr>')
    return ('<table class="pp-static">'
            '<caption>역대 선거 — 광역단체장·교육감은 당선 결과, 대통령은 이 시도 1위'
            '</caption><thead><tr>'
            '<th>연도</th><th>선거</th><th>직</th><th>1위 정당</th><th>1위 후보</th>'
            '<th>득표율</th><th>투표율</th></tr></thead><tbody>'
            + "".join(trs) + "</tbody></table>")


def sigungu_short(sg: str) -> str:
    return sg


HUB = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<script>try{{var _m=localStorage.getItem('vote-ysw-theme');if(_m==='dark')document.documentElement.setAttribute('data-theme','dark');else if(_m==='light')document.documentElement.setAttribute('data-theme','light');}}catch(_e){{}}</script>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<base href="/">
<title>지역별 선거 결과 — 시도 {n_sido}곳·시군구 {n}곳의 대선·총선·지선 | polis</title>
<meta name="description" content="시도와 전국 시군구 {n}곳의 선거 결과. 역대 광역단체장·교육감과 지역마다의 대선·총선·지선 1위 정당·후보, 득표율·투표율.">
<link rel="canonical" href="/region/">
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
    <h1>지역별 선거 기록</h1>
    <p class="lede">시군구 {n}곳 — 역대 대선·총선·지선에서 그 지역이 어떻게 갈렸는지.</p>
    <form class="rg-find" role="search" onsubmit="return false">
      <label for="rg-q">지역 찾기</label>
      <input id="rg-q" type="search" autocomplete="off" placeholder="예: 성남, 분당, 김천"
             aria-describedby="rg-hit">
      <span id="rg-hit" class="rg-hit" aria-live="polite"></span>
    </form>
  </section>
{body}
</main>
<script src="assets/parties.js"></script>
<script src="assets/theme.js"></script>
<script src="assets/nav.js"></script>
<script src="assets/region-hub.js"></script>
</body>
</html>
"""


# 시도 2자리 코드 → canon 시도명 (build_sido_outlines.SIDO2_NAME와 같은 표).
SIDO2_NAME = {
    '11': '서울특별시', '21': '부산광역시', '22': '대구광역시', '23': '인천광역시',
    '24': '광주광역시', '25': '대전광역시', '26': '울산광역시', '29': '세종특별자치시',
    '31': '경기도', '32': '강원특별자치도', '33': '충청북도', '34': '충청남도',
    '35': '전북특별자치도', '36': '전라남도', '37': '경상북도', '38': '경상남도',
    '39': '제주특별자치도',
}

_CUR_PAIRS: set | None = None


def current_pairs() -> set:
    """지금 존재하는 (시도, 시군구) 짝.

    이름만 보면 시도를 가로지르는 오분류가 난다 — 강화군·옹진군은 옛 경기 소속
    시절 자료가 있어서, 이름만 대조하면 '지금도 경기에 있는 곳'으로 분류된다
    (지금은 인천이다). 광주시도 마찬가지로 경기 광주시 때문에 전남 광주시가
    현존으로 잡혔다. 경계 파일의 code 앞 두 자리가 시도이므로 짝으로 본다.
    """
    global _CUR_PAIRS
    if _CUR_PAIRS is None:
        pairs: set = set()
        for y in (2026, 2025):
            f = ROOT / f"data/geo/sigungu_{y}.json"
            if not f.exists():
                continue
            d = json.loads(f.read_text(encoding="utf-8"))
            for ft in (d.get("features") or d):
                pr = ft.get("properties") or {}
                sd = SIDO2_NAME.get(str(pr.get("code") or "")[:2])
                n = pr.get("name") or ""
                if not sd or not n:
                    continue
                pairs.add((sd, n))
                # 일반구(성남시분당구)는 시(성남시)로도 인정 — 지역 페이지가 시 단위다
                m = re.match(r"^([가-힣]+시)[가-힣]+구$", n)
                if m:
                    pairs.add((sd, m.group(1)))
            if pairs:
                break
        # 경계 파일이 개칭을 안 따라온 곳이 있다 — 인천 남구는 2018-07-01에
        # 미추홀구가 됐는데 2025·2026 경계에 아직 '남구'로 들어 있다. 그대로 쓰면
        # 지금 있는 미추홀구가 '없어진 이름'으로 분류된다. 저장소가 이미 그 사실을
        # geography/events.json에 갖고 있으니 거기서 가져온다(추정하지 않는다).
        try:
            ev = json.loads((ROOT / "data/geography/events.json")
                            .read_text(encoding="utf-8"))["events"]
            for e in (ev.values() if isinstance(ev, dict) else ev):
                if e.get("type") != "rename" or e.get("kind") != "admin_unit":
                    continue
                for t in (e.get("to") or []):
                    sd, n = t.get("parent"), t.get("name")
                    if sd and n and any(p[0] == sd for p in pairs):
                        pairs.add((sd, n))
                        # 개칭 전 이름은 지금 이름이 아니다. 둘 다 남기면 인천에
                        # 남구와 미추홀구가 나란히 서서 같은 곳이 둘로 보인다.
                        for f0 in (e.get("from") or []):
                            pairs.discard((f0.get("parent"), f0.get("name")))
        except Exception:                                        # noqa: BLE001
            pass
        _CUR_PAIRS = pairs
    return _CUR_PAIRS


def current_units() -> set:
    """지금 존재하는 시군구 이름. **목록을 손으로 적지 않는다** — 현행 경계 파일에서 읽는다.

    폐지·개칭된 곳(명주군·원성군·춘성군…)이 현재 지역과 같은 줄에 섞여 있으면 '내 지역
    찾기'가 어려워진다. 자료로서는 남아야 하지만 **찾는 동선에서는 갈라야** 한다.
    """
    names: set = set()
    for y in (2026, 2025):
        f = ROOT / f"data/geo/sigungu_{y}.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        for ft in (d.get("features") or d):
            n = (ft.get("properties") or {}).get("name") or ""
            if n:
                names.add(n)
                # 일반구(성남시분당구)는 시(성남시)로도 인정 — 지역 페이지가 시 단위다
                m = re.match(r"^([가-힣]+시)[가-힣]+구$", n)
                if m:
                    names.add(m.group(1))
        if names:
            break
    return names


def hub_sido_block(sidos: list) -> str:
    """허브 맨 위의 광역 층.

    시도 이름을 시군구 묶음의 제목에도 링크했지만, 그 방식으로는 시군구 항목이
    없는 시도가 허브에 아예 안 나온다 — 2026 출범한 전남광주특별시가 그렇다
    (광역 선거만 통합 단위로 치르고 기초는 종전 시군구에서 치른다). 광역 층을
    따로 두면 18곳이 전부 한 자리에서 잡힌다.
    """
    if not sidos:
        return ""
    items = "".join(f'<a class="rg-item" href="/region/{quote(sd)}/">{esc(sd)}</a>'
                    for sd in sorted(sidos))
    return ('<section class="dash-section">'
            f'<h2 class="dash-section-title">시도<span class="rg-count">'
            f'{len(sidos)}</span></h2>'
            '<p class="fine">역대 광역단체장·교육감과 대선에서 그 시도가 어떻게 '
            '갈렸는지.</p>'
            f'<div class="rg-grid">{items}</div></section>')


def build_hub(entries: list, sidos: list) -> str:
    """시도별로 묶은 전체 목록. 400개를 한 페이지에서 직접 링크해 크롤 경로를 1-hop으로 둔다.

    현재 지역이 먼저, 폐지·변경된 행정구역은 그 아래 따로. 둘을 섞으면 목록에서 자기
    지역을 찾는 게 어려워진다 — 자료는 그대로 두되 **동선만** 가른다.
    """
    # 이름만 대조하면 시도를 가로지르는 오분류가 난다(강화군이 경기 현존으로 잡혔다).
    cur_pairs = current_pairs()
    by_sido = defaultdict(list)
    for sd, sg, slug in entries:
        by_sido[sd].append((sg, slug))
    blocks = []
    for sd in sorted(by_sido):
        live = sorted((sg, slug) for sg, slug in by_sido[sd] if (sd, sg) in cur_pairs)
        past = sorted((sg, slug) for sg, slug in by_sido[sd] if (sd, sg) not in cur_pairs)
        item = (lambda sg, slug, past_: f'<a class="rg-item{" is-past" if past_ else ""}" '
                f'href="/region/{slug}/" data-name="{esc(sg)}">{esc(sg)}</a>')
        grid = "".join(item(sg, slug, False) for sg, slug in live)
        if past:
            grid += ('<details class="rg-past"><summary>폐지·변경된 행정구역 '
                     f'{len(past)}곳</summary><div class="rg-grid">'
                     + "".join(item(sg, slug, True) for sg, slug in past)
                     + '</div></details>')
        # 시도 이름 자체를 그 시도 페이지로 — 허브에서 광역 층으로 내려가는 길이
        # 없으면 시도 페이지는 sitemap에만 있는 셈이 된다.
        head = (f'<a href="/region/{quote(sd)}/">{esc(sd)}</a>'
                if (ROOT / "region" / sd).exists() else esc(sd))
        blocks.append(f'<section class="dash-section" data-sido="{esc(sd)}">'
                      f'<h2 class="dash-section-title">{head}'
                      f'<span class="rg-count">{len(live)}</span></h2>'
                      f'<div class="rg-grid">{grid}</div></section>')
    return hub_sido_block(sidos) + "\n" + "\n".join(blocks)


def main():
    by_region = collect()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    urls, n = [], 0
    for (sd, sg), rows in sorted(by_region.items()):
        if len(rows) < MIN_ROUNDS:
            continue
        slug = f"{sd}-{sg}"
        d = OUT_DIR / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(build_page(sd, sg, rows, by_region), encoding="utf-8")
        urls.append(f"/region/{slug}/")
        n += 1
    # 시도 층 — 시군구 366곳과 전국 사이가 비어 있었다. '경기도 지방선거 결과'는
    # 실제로 찾는 말인데 착지할 페이지가 없었고, 광역단체장을 누가 했는지는 어느
    # 시군구 페이지에도 없다(시군구의 '광역단체장' 줄은 그 지역 1위지 당선자가 아니다).
    n_sido, sido_slugs = 0, []
    for sd, srows in sorted(collect_sido(collect.won).items()):
        # 시군구의 MIN_ROUNDS(3)는 한두 번 스친 옛 지명을 걸러내려는 문턱이다.
        # 시도는 18곳뿐이고 전부 실재한 광역단체이며, 페이지가 시군구 목록을
        # 함께 이고 있어 얇지 않다. 2026 출범한 전남광주특별시(광역 2건 + 시군구
        # 27곳)를 그 문턱으로 지우면 지금 그곳에 사는 사람의 시도가 사라진다.
        if not srows:
            continue
        d = OUT_DIR / sd
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(build_sido_page(sd, srows, by_region),
                                      encoding="utf-8")
        urls.append(f"/region/{sd}/")
        sido_slugs.append(sd)
        n_sido += 1

    entries = [(u.split("/")[2].split("-", 1)[0], u.split("/")[2].split("-", 1)[1],
                u.split("/")[2]) for u in urls if "-" in u.split("/")[2]]
    (OUT_DIR / "index.html").write_text(
        HUB.format(n=len(entries), n_sido=len(sido_slugs),
                   body=build_hub(entries, sido_slugs),
                   nav=render_nav(menu_for_path("region/index.html"))), encoding="utf-8")
    # stale 제거 — 시도 정규화·MIN_ROUNDS 변경으로 더 이상 안 만드는 slug가 남으면
    # sitemap에 없는 페이지가 배포돼 크롤러에는 살아 있고 우리는 모르는 상태가 된다.
    import shutil
    keep = {u.split("/")[2] for u in urls}
    n_stale = 0
    for dch in OUT_DIR.iterdir():
        if dch.is_dir() and dch.name not in keep:
            shutil.rmtree(dch)
            n_stale += 1
    urls.insert(0, "/region/")
    SITEMAP_OUT.write_text("\n".join(urls) + "\n", encoding="utf-8")
    print(f"→ region/ : {n} 시군구 + {n_sido} 시도 "
          f"(회차 {MIN_ROUNDS}건 이상, stale 제거 {n_stale})",
          file=sys.stderr)
    print(f"→ {SITEMAP_OUT.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
