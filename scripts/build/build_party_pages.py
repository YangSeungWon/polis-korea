"""정당 페이지 정적 생성 — /party/{정식명}/index.html.

데이터 결합(전부 단일 출처):
  - data/parties/registry.json : 정식명·등록약칭·창당/해산·계보(전신/후신)·note
  - data/timeline.json         : 회차별 등장(총선 의석·대선 득표율·지선 시도수)
  - assets/person-index.json   : 정당 소속 인물(페이지 보유분 링크)

색은 서버에서 칠하지 않고 assets/parties.js의 partyColor()로 클라이언트에서 [data-party] 요소에 입힘.
사용: python3 scripts/build/build_party_pages.py
"""
from __future__ import annotations
import html
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]

# nav 정본은 sync_nav_html.py — 사본을 들고 있으면 메뉴 변경 때마다 어긋난다.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_nav_html import render_nav, menu_for_path
from build_region_pages import collect as collect_regions, sido_short  # noqa: E402
from party_canon import disambiguate_party  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from party_canon import canon_party  # noqa: E402

REGISTRY = ROOT / "data/parties/registry.json"
TIMELINE = ROOT / "data/timeline.json"
PERSON_INDEX = ROOT / "assets/person-index.json"
OUT_DIR = ROOT / "party"
SITEMAP_OUT = ROOT / "data/sitemap_party.txt"

KIND_LABEL = {"presidential": "대선", "national_assembly": "총선", "local": "지선"}
HISTORY_TYPE = {"presidential": "presidential", "national_assembly": "national_assembly", "local": "local"}


def esc(s):
    return html.escape(str(s if s is not None else ""))


def purl(name: str) -> str:
    """정당 페이지 URL (한글 경로, 인코딩)."""
    return f"/party/{quote(name)}/"


def party_link(name: str, known: set) -> str:
    """전신/후신 등 정당명 → 페이지 있으면 링크, 없으면 텍스트."""
    if name in known:
        return f'<a href="{purl(name)}" data-party="{esc(name)}" class="pty-rel">{esc(name)}</a>'
    return f'<span data-party="{esc(name)}" class="pty-rel">{esc(name)}</span>'


def build_appearances(timeline: dict) -> dict:
    """party → [{label, date, kind, n, metric}] (회차순)."""
    out = {}
    for r in timeline.get("rounds", []):
        kind, n, date = r.get("kind"), r.get("n"), r.get("date", "")
        label = r.get("label", "")
        rows = []  # (party, metric_html)
        if kind == "national_assembly" and r.get("partySeats"):
            for party, seats in r["partySeats"]:
                rows.append((party, f"{seats}석"))
        elif kind == "presidential" and r.get("presCandidates"):
            for c in r["presCandidates"]:
                if c.get("party"):
                    nm = f" ({c['name']})" if c.get("name") else ""
                    rows.append((c["party"], f"{c.get('pct', 0):.1f}%{nm}"))
        elif kind == "local" and r.get("sidoWinners"):
            cnt = {}
            for w in r["sidoWinners"].values():
                p = w.get("party")
                if p:
                    cnt[p] = cnt.get(p, 0) + 1
            for party, c in cnt.items():
                rows.append((party, f"광역 {c}곳"))
        for party, metric in rows:
            out.setdefault(party, []).append({
                "label": label, "date": date, "kind": kind, "n": n, "metric": metric,
            })
    for party in out:
        out[party].sort(key=lambda a: a["date"])
    return out


def member_title(races: list):
    """경력 전체에서 대표 직함 + 정렬 우선순위. (title, rank). 당선 기준."""
    tcs = {}
    for r in races:
        if r.get("won"):
            tcs.setdefault(str(r.get("tc")), []).append(r)
    if "1" in tcs:
        return "대통령", 6
    if "3" in tcs:  # 광역단체장
        pl = tcs["3"][-1].get("place", "")
        t = pl + "지사" if pl.endswith("도") else (pl + "장" if pl.endswith("시") else "광역단체장")
        return t, 5
    n = len(tcs.get("2", [])) + len(tcs.get("7", []))  # 국회의원(지역구+전국구) 선수
    if n:
        return f"{n}선", 4
    if "4" in tcs:  # 기초단체장
        pl = tcs["4"][-1].get("place", "")
        return (pl + " 단체장") if pl else "기초단체장", 3
    if "5" in tcs:
        return "광역의원", 2
    if "6" in tcs:
        return "기초의원", 1
    return None, 0  # 낙선만


def build_members(persons: list) -> dict:
    """party → [{name, dob, title, rank, wins}] (페이지 보유 인물만, 직위·당선순)."""
    out = {}
    for p in persons:
        if not (p.get("assembly_id") and p.get("dob")):
            continue
        title, rank = member_title(p.get("races", []))
        for party in set(canon_party(x) for x in p.get("parties", [])):
            out.setdefault(party, []).append({
                "name": p["name"], "dob": p["dob"],
                "title": title, "rank": rank, "wins": p.get("wins", 0),
            })
    for party in out:
        out[party].sort(key=lambda m: (-m["rank"], -m["wins"], m["name"]))
    return out


PAGE = """<!DOCTYPE html>
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
<title>{name} 선거 기록 — {life_span} 역대 득표와 소속 인물 | polis</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{name} 선거 기록 — {life_span}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
<meta property="og:image" content="https://polis.ysw.kr/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="https://polis.ysw.kr/og.png">
<link rel="canonical" href="{canon}">
{jsonld}
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.min.css">
<link rel="stylesheet" href="assets/common.css">
<link rel="stylesheet" href="assets/components.css">
<link rel="stylesheet" href="assets/party.css">
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
<main class="page pty-page">
  <section class="pty-hero" data-party="{name}">
    <div class="pty-bar" data-party="{name}"></div>
    <h1 class="pty-name">{name}{abbr_badge}</h1>
    <p class="pty-life">{life}</p>
    {note}
  </section>
  {lineage}
  {elections}
  {runs}
  {members}
  {regions}
  <footer class="foot">
    <p class="fine">소속 인물은 당선 국회의원 기준 — 낙선·기타 후보는 <a href="/search.html?q={qname}">검색</a>에서.</p>
  </footer>
</main>
<script src="assets/parties.js"></script>
<script src="assets/theme.js"></script>
<script src="assets/nav.js"></script>
<script>
// [data-party] 요소에 정당색 입히기 (parties.js partyColor).
(function () {{
  if (typeof partyColor !== 'function') return;
  document.querySelectorAll('[data-party]').forEach(function (el) {{
    var c = partyColor(el.dataset.party);
    var tc = (typeof partyTextColor === 'function') ? partyTextColor(el.dataset.party) : c;  // 정의당 노랑 등 가독 보정
    if (el.classList.contains('pty-bar')) el.style.background = c;
    else if (el.classList.contains('pty-rel')) {{ el.style.color = tc; el.style.borderColor = tc; }}
    else {{ el.style.setProperty('--pty-c', c); if (typeof pickTextColor === 'function') el.style.setProperty('--pty-text', pickTextColor(c)); }}
  }});
}})();
</script>
</body>
</html>
"""


SITE = "https://polis.ysw.kr"


def party_jsonld(name: str, info: dict, desc: str) -> str:
    """Organization + BreadcrumbList.

    정당은 schema.org에 PoliticalParty가 없어 Organization으로 낸다. 창당·해산 일자는
    레지스트리에 있는 것만 싣고, 없으면 생략 — 추정치를 구조화 데이터에 넣지 않는다.
    """
    org = {"@type": "Organization", "name": name,
           "url": f"{SITE}/party/{quote(name)}/", "description": desc}
    if info.get("founded"):
        org["foundingDate"] = info["founded"]
    if info.get("dissolved"):
        org["dissolutionDate"] = info["dissolved"]
    crumbs = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "정당사", "item": f"{SITE}/parties.html"},
        {"@type": "ListItem", "position": 2, "name": name},
    ]}
    return ('<script type="application/ld+json">'
            + json.dumps({"@context": "https://schema.org", "@graph": [org, crumbs]},
                         ensure_ascii=False) + '</script>')


def build_region_strength() -> dict:
    """정당 → {(시도, 시군구): 1위 횟수}.

    지역 페이지와 **같은 집계**를 쓴다(build_region_pages.collect). 정당 페이지와
    지역 페이지가 서로 다른 숫자를 말하면 둘 다 못 믿게 된다.

    무소속은 정당이 아니므로 registry에 없고 여기서 자연히 빠진다.
    """
    out = defaultdict(lambda: defaultdict(int))
    for (sd, sg), rows in collect_regions().items():
        for r in rows:
            out[disambiguate_party(r["party"], r.get("date") or "")][(sd, sg)] += 1
    return out


# 지역 페이지가 있는 시군구만 링크한다 — 회차 3건 미만은 페이지를 안 만들었다.
def render_regions(name: str, strength: dict, page_slugs: set) -> str:
    reg = strength.get(name)
    if not reg:
        return ""
    total = sum(reg.values())
    by_sido = defaultdict(int)
    for (sd, _sg), n in reg.items():
        by_sido[sd] += 1
    top = sorted(reg.items(), key=lambda x: (-x[1], x[0]))[:24]
    chips = []
    for (sd, sg), n in top:
        slug = f"{sd}-{sg}"
        # 중구·서구·남구는 여러 시도에 있다 — 시도 없이는 어디인지 알 수 없다.
        label = (f'<span class="pty-rg-sd">{esc(sido_short(sd))}</span>'
                 f'{esc(sg)}<span class="pty-rg-n">{n}</span>')
        chips.append(f'<a class="pty-rg" href="/region/{quote(slug)}/">{label}</a>'
                     if slug in page_slugs else f'<span class="pty-rg">{label}</span>')
    sido = " · ".join(f"{esc(sd)} {n}곳" for sd, n in
                      sorted(by_sido.items(), key=lambda x: (-x[1], x[0]))[:8])
    return (f'<section class="pty-sec"><h2>지역 기반 '
            f'<span class="pty-cnt">{len(reg)}</span></h2>'
            f'<p class="pty-rg-sum">시군구 1위 {total:,}회 · {len(reg)}곳</p>'
            f'<p class="pty-rg-sido">{sido}</p>'
            f'<div class="pty-rg-grid">{"".join(chips)}</div></section>')


_RUNS_CACHE: dict = {}


def build_runs() -> dict:
    """정당별 **출마 기록** — 선거마다 후보 수·득표.

    기존 '등장 선거'는 당선자 기준이라 원외 정당은 아무것도 안 나온다. 녹색당은
    16회 선거에 871명이 나와 318만표를 얻었는데 페이지에는 한 줄도 없었다.
    당선되지 않았다는 것과 참여하지 않았다는 것은 다르다.

    같은 선거의 다른 표현(.sigungu · national_assembly_* 등)을 두 번 세지 않는다 —
    family_vote_share.py와 같은 규칙이다.
    """
    if _RUNS_CACHE:
        return _RUNS_CACHE
    import collections
    # **같은 이름의 다른 정당을 한 덩어리로 세지 않는다.** 원자료의 '국민의당'은
    # 1963·2016·2020이 다 그 이름이라, 그대로 세면 1963~2022 · 35M표 · 당선 39가
    # 한 정당의 기록이 된다. registry의 괄호 표기(민주당(1991) 등)와도 안 맞아
    # 18종 중 14종이 조용히 빈 채로 남았다. 저장소의 단일 출처를 쓴다.
    from party_canon import disambiguate_party
    agg: dict = collections.defaultdict(dict)
    for f in sorted((ROOT / "data/results").glob("*.json")):
        if ".sigungu" in f.name or f.name.startswith(
                ("local_", "national_assembly_", "presidential_")):
            continue
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        meta = doc.get("_meta") or {}
        date = meta.get("election_date") or meta.get("date") or ""
        if not date:
            continue
        label = meta.get("election") or f.stem
        seen: dict = collections.defaultdict(lambda: [0, 0, 0])

        def walk(o):
            if isinstance(o, dict):
                for c in o.get("candidates") or []:
                    if not isinstance(c, dict):
                        continue
                    raw = c.get("party")
                    if not raw or raw == "무소속":
                        continue
                    party = disambiguate_party(raw, date)
                    row = seen[party]
                    row[0] += 1
                    row[1] += c.get("votes") or 0
                    if c.get("won"):
                        row[2] += 1
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(doc)
        for party, (n, votes, won) in seen.items():
            cur = agg[party].get(date)
            # 한 선거가 여러 파일에 있으면 후보 수가 가장 많은 쪽(가장 완전한 표현)
            if cur is None or n > cur["candidates"]:
                agg[party][date] = {"date": date, "label": label,
                                    "candidates": n, "votes": votes, "won": won}
    _RUNS_CACHE.update({k: sorted(v.values(), key=lambda r: r["date"], reverse=True)
                        for k, v in agg.items()})
    return _RUNS_CACHE


def render_runs(name: str) -> str:
    runs = build_runs().get(name) or []
    if not runs:
        return ""
    n_el = len(runs)
    tot_c = sum(r["candidates"] for r in runs)
    tot_v = sum(r["votes"] for r in runs)
    tot_w = sum(r["won"] for r in runs)
    rows = []
    for r in runs[:14]:
        won = f'<span class="pty-run-w">당선 {r["won"]}</span>' if r["won"] else ""
        rows.append(
            f'<li><span class="pty-run-d">{esc(r["date"])}</span>'
            f'<span class="pty-run-l">{esc(r["label"])}</span>'
            f'<span class="pty-run-n">후보 {r["candidates"]}</span>'
            f'<span class="pty-run-v">{r["votes"]:,}표</span>{won}</li>')
    more = (f'<li class="pty-run-more">외 {n_el - 14}회</li>' if n_el > 14 else "")
    head = (f'선거 {n_el}회 · 후보 {tot_c:,}명 · 득표 {tot_v:,}'
            + (f' · 당선 {tot_w:,}' if tot_w else " · 당선 없음"))
    return (f'<section class="pty-sec"><h2>출마 기록 <span class="pty-cnt">{n_el}</span></h2>'
            f'<p class="pty-run-sum">{head}</p>'
            f'<ul class="pty-runs">{"".join(rows)}{more}</ul>'
            f'<p class="fine">당선 여부와 무관하게 후보를 낸 선거 전부. '
            f'같은 선거의 중복 표현은 한 번만 셉니다.</p></section>')


def render(name, info, known, appearances, members, regions=""):
    abbr = info.get("abbr")
    abbr_badge = f' <span class="pty-abbr" data-party="{esc(name)}">{esc(abbr)}</span>' if abbr else ""
    founded = info.get("founded", "")
    dissolved = info.get("dissolved")
    life = esc(founded) + (f" ~ {esc(dissolved)}" if dissolved else " ~ 현재" if founded else "")
    # 제목에 쓸 짧은 존속기간 — life는 뒤에 관계(개명·분당)가 붙는 화면용 문자열이라
    # 제목에 그대로 넣으면 '2020-09 ~ 현재 · 개명 역대 득표와'로 읽힌다. 연도만 쓴다.
    life_span = (f"{founded[:4]}~{dissolved[:4]}" if founded and dissolved
                 else f"{founded[:4]}~현재" if founded else "")
    REL = {"new": "신설", "rename": "개명", "merge": "합당", "split": "분당", "dissolve": "해산/소멸"}
    rel = REL.get(info.get("relation"), "")
    if rel:
        life += f" · {rel}"
    note_html = f'<p class="pty-note">{esc(info["note"])}</p>' if info.get("note") else ""

    # 계보
    preds = info.get("predecessors", [])
    succs = info.get("successors", [])
    lineage = ""
    if preds or succs:
        parts = ['<section class="pty-sec"><h2>계보</h2><div class="pty-lineage">']
        if preds:
            parts.append('<div class="pty-lin-row"><span class="pty-lin-k">전신</span> '
                         + " · ".join(party_link(p, known) for p in preds) + "</div>")
        if succs:
            parts.append('<div class="pty-lin-row"><span class="pty-lin-k">후신</span> '
                         + " · ".join(party_link(s, known) for s in succs) + "</div>")
        parts.append("</div></section>")
        lineage = "\n".join(parts)

    # 등장 선거
    apps = appearances.get(name, [])
    elections = ""
    if apps:
        rows = []
        for a in apps:
            href = f'/history.html?type={HISTORY_TYPE.get(a["kind"], "")}&n={a["n"]}'
            kl = KIND_LABEL.get(a["kind"], "")
            rows.append(
                f'<li><a href="{href}"><span class="pty-el-lab">{esc(a["label"])}</span>'
                f'<span class="pty-el-k">{esc(kl)}</span>'
                f'<span class="pty-el-m">{esc(a["metric"])}</span></a></li>'
            )
        elections = (f'<section class="pty-sec"><h2>등장 선거 <span class="pty-cnt">{len(apps)}</span></h2>'
                     f'<ul class="pty-elections">{"".join(rows)}</ul></section>')

    # 소속 인물
    mem = members.get(name, [])
    members_html = ""
    if mem:
        shown = mem[:60]
        items = []
        for m in shown:
            slug = f'{m["name"]}-{m["dob"]}'
            badge = f'<span class="pty-mem-wl">{esc(m["title"])}</span>' if m.get("title") else ""
            items.append(
                f'<li><a href="/person/{quote(slug)}/">{esc(m["name"])}{badge}</a></li>'
            )
        more = f'<p class="pty-more">외 {len(mem) - len(shown)}명</p>' if len(mem) > len(shown) else ""
        members_html = (f'<section class="pty-sec"><h2>소속 인물 <span class="pty-cnt">{len(mem)}</span></h2>'
                        f'<ul class="pty-members">{"".join(items)}</ul>{more}</section>')

    desc = (f'{name}' + (f'({abbr})' if abbr else '')
            + f' 선거 기록 — {life_span}. 역대 대선·총선·지선 득표와 소속 인물. '
            + (info.get("note") or ""))
    return PAGE.format(
        nav=render_nav(menu_for_path("party/x/index.html")),
        name=esc(name), abbr_badge=abbr_badge, life=life, life_span=esc(life_span), note=note_html,
        lineage=lineage, elections=elections, runs=render_runs(name),
        members=members_html,
        regions=regions,
        desc=esc(desc[:160]), canon=purl(name), qname=quote(name),
        jsonld=party_jsonld(name, info, esc(desc[:160])),
    )



# ── parties.html 정당 색인 ─────────────────────────────────────────────────
# 정당 허브가 /party/ 145쪽을 **정적으로 하나도 링크하지 않았다.** 계보도는
# assets/lineage.js가 registry.json을 읽어 렌더 후에 그리므로, 크롤러가 렌더하기
# 전에는 허브에서 정당으로 가는 길이 없다. /history/ 66쪽이 섬이었던 것과 같은
# 부류인데, 이쪽은 섬은 아니다 — 인물 20,254곳·지역 6,775곳에서 링크가 들어온다.
# 문제는 **아무도 열거하지 않는다**는 것이고, 그래서 깊이가 3~7홉으로 흩어진다.
#
# region/index.html이 374곳을 그렇게 다룬다(정적 칩 + 접기). 그 패턴을 그대로 쓴다.
PARTY_INDEX_START = "<!-- PARTY_INDEX_START"
PARTY_INDEX_END = "<!-- PARTY_INDEX_END -->"

# 계열 표시 순서 — registry의 stream 값. '기타'가 51개로 가장 크지만 맨 뒤에 둔다.
STREAM_ORDER = ["보수", "중도보수", "중도", "중도진보", "진보", "기타"]


def party_index_block(ps: dict) -> str:
    ps = dict(ps)
    if not ps:
        return PARTY_INDEX_START + " — 정당이 없다 -->\n" + PARTY_INDEX_END
    by: dict = {}
    for name, v in ps.items():
        by.setdefault(v.get("stream") or "기타", []).append((name, v))
    out = [PARTY_INDEX_START + " — scripts/build/build_party_pages.py 자동 갱신. 손수정 X.",
           "     계보도(lineage.js)가 같은 링크를 렌더 후에 만들지만, 그건 렌더 후에만 존재한다. -->",
           '  <section class="ph-sec" aria-label="정당 목록">',
           f'    <h2>정당 목록 <span class="ph-meta">{len(ps)}개</span></h2>']
    for stream in STREAM_ORDER + [s for s in by if s not in STREAM_ORDER]:
        items = by.get(stream)
        if not items:
            continue
        # 현존은 펼치고 소멸은 접는다 — 51개짜리 '기타'가 화면을 덮지 않게.
        live = sorted((n for n, v in items if not v.get("dissolved")),
                      key=lambda n: -(ps[n].get("order") or 0))
        gone = sorted((n for n, v in items if v.get("dissolved")),
                      key=lambda n: (ps[n].get("dissolved") or ""), reverse=True)
        out.append(f'    <div class="pi-group"><h3 class="pi-stream">{esc(stream)}'
                   f'<span class="ph-meta">{len(items)}</span></h3>')
        if live:
            out.append('      <ul class="pi-list">' + "".join(_chip(n, ps[n]) for n in live) + "</ul>")
        if gone:
            out.append(f'      <details class="pi-past"><summary>사라진 정당 {len(gone)}개</summary>')
            out.append('        <ul class="pi-list">' + "".join(_chip(n, ps[n]) for n in gone) + "</ul>")
            out.append("      </details>")
        out.append("    </div>")
    out += ["  </section>", "  " + PARTY_INDEX_END]
    return "\n".join(out)


def _chip(name: str, v: dict) -> str:
    span = (v.get("founded") or "")[:4]
    if v.get("dissolved"):
        span += "~" + (v["dissolved"] or "")[:4]
    return (f'<li><a href="/party/{quote(name)}/">{esc(name)}</a>'
            + (f'<span class="pi-span">{esc(span)}</span>' if span else "") + "</li>")


def sync_parties_html(ps: dict) -> bool:
    page = ROOT / "parties.html"
    if not page.exists():
        return False
    html = page.read_text(encoding="utf-8")
    blk = party_index_block(ps)
    pat = re.compile(re.escape(PARTY_INDEX_START) + r"[\s\S]*?" + re.escape(PARTY_INDEX_END))
    if pat.search(html):
        new = pat.sub(blk, html)
    else:
        anchor = '  <section class="ph-sec">'
        if anchor not in html:
            print("  ! parties.html에 삽입 지점이 없다", file=sys.stderr)
            return False
        new = html.replace(anchor, blk + "\n\n" + anchor, 1)
    if new != html:
        page.write_text(new, encoding="utf-8")
        return True
    return False

def main():
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))["parties"]
    timeline = json.loads(TIMELINE.read_text(encoding="utf-8"))
    persons = json.loads(PERSON_INDEX.read_text(encoding="utf-8"))["persons"]

    known = set(reg.keys())
    appearances = build_appearances(timeline)
    members = build_members(persons)
    strength = build_region_strength()
    page_slugs = {d.name for d in (ROOT / "region").iterdir() if d.is_dir()} \
        if (ROOT / "region").exists() else set()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    urls = []
    for name, info in reg.items():
        d = OUT_DIR / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(render(name, info, known, appearances, members,
                      render_regions(name, strength, page_slugs)), encoding="utf-8")
        urls.append(purl(name))
    import shutil   # stale 제거 — 개명·삭제된 정당 디렉터리 잔존분.
    n_stale = 0
    for dch in OUT_DIR.iterdir():
        if dch.is_dir() and dch.name not in reg:
            shutil.rmtree(dch)
            n_stale += 1
    SITEMAP_OUT.write_text("\n".join(urls), encoding="utf-8")
    print(f"→ {OUT_DIR.relative_to(ROOT)}/ : {len(urls)} 정당 페이지 (stale 제거 {n_stale})")

    # 허브가 정당을 열거하게 한다. 계보도는 렌더 후에만 존재한다.
    if sync_parties_html(reg):
        print(f"→ parties.html 정당 색인 갱신 ({len(reg)}개)")
    # 커버리지 경고 — timeline 등장하나 registry에 없어 페이지 없는 정당
    missing = sorted(set(appearances) - known)
    if missing:
        print(f"  ⚠ registry 미등록(페이지 없음) {len(missing)}개: {', '.join(missing[:15])}{' …' if len(missing) > 15 else ''}")


if __name__ == "__main__":
    main()
