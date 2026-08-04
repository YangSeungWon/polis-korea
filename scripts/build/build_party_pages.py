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
<title>polis · {name}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="polis · {name}">
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


def render(name, info, known, appearances, members, regions=""):
    abbr = info.get("abbr")
    abbr_badge = f' <span class="pty-abbr" data-party="{esc(name)}">{esc(abbr)}</span>' if abbr else ""
    founded = info.get("founded", "")
    dissolved = info.get("dissolved")
    life = esc(founded) + (f" ~ {esc(dissolved)}" if dissolved else " ~ 현재" if founded else "")
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

    desc = f'{name}' + (f'({abbr})' if abbr else '') + f' — {life}. ' + (info.get("note") or "")
    return PAGE.format(
        nav=render_nav(menu_for_path("party/x/index.html")),
        name=esc(name), abbr_badge=abbr_badge, life=life, note=note_html,
        lineage=lineage, elections=elections, members=members_html,
        regions=regions,
        desc=esc(desc[:160]), canon=purl(name), qname=quote(name),
        jsonld=party_jsonld(name, info, esc(desc[:160])),
    )


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
    # 커버리지 경고 — timeline 등장하나 registry에 없어 페이지 없는 정당
    missing = sorted(set(appearances) - known)
    if missing:
        print(f"  ⚠ registry 미등록(페이지 없음) {len(missing)}개: {', '.join(missing[:15])}{' …' if len(missing) > 15 else ''}")


if __name__ == "__main__":
    main()
