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
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
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


def build_members(persons: list) -> dict:
    """party → [{name, dob, wins, losses}] (페이지 보유 인물만, 당선많은순)."""
    out = {}
    for p in persons:
        if not (p.get("assembly_id") and p.get("dob")):
            continue
        for party in set(canon_party(x) for x in p.get("parties", [])):
            out.setdefault(party, []).append({
                "name": p["name"], "dob": p["dob"],
                "wins": p.get("wins", 0), "losses": p.get("losses", 0),
            })
    for party in out:
        out[party].sort(key=lambda m: (-m["wins"], -m["losses"], m["name"]))
    return out


PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<base href="/">
<title>polis · {name}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="polis · {name}">
<meta property="og:description" content="{desc}">
<link rel="canonical" href="{canon}">
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
    <!-- NAV_START — scripts/build/sync_nav_html.py 자동 갱신. -->
    <span data-nav-urgent></span>
    <a href="/polls.html" class="hdr-link">여론조사</a>
    <a href="/byelection/" class="hdr-link">재·보궐</a>
    <a href="/tracker.html" class="hdr-link">지지율 추이</a>
    <a href="/history.html" class="hdr-link">역대 결과</a>
    <a href="/timeline.html" class="hdr-link">타임라인</a>
    <a href="/parties.html" class="hdr-link">정당사</a>
    <a href="/search.html" class="hdr-link">검색</a>
    <!-- NAV_END -->
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
  <footer class="foot">
    <p class="fine">정당 메타·계보: <code>data/parties/registry.json</code> · 회차 등장: 역대 결과 · 소속 인물: 의원 ID 매핑(당선·낙선 포함은 <a href="/search.html?q={qname}">검색</a>).</p>
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
    if (el.classList.contains('pty-bar')) el.style.background = c;
    else if (el.classList.contains('pty-rel')) {{ el.style.color = c; el.style.borderColor = c; }}
    else el.style.setProperty('--pty-c', c);
  }});
}})();
</script>
</body>
</html>
"""


def render(name, info, known, appearances, members):
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
            items.append(
                f'<li><a href="/person/{quote(slug)}/">{esc(m["name"])}'
                f'<span class="pty-mem-wl">{m["wins"]}승</span></a></li>'
            )
        more = f'<p class="pty-more">외 {len(mem) - len(shown)}명</p>' if len(mem) > len(shown) else ""
        members_html = (f'<section class="pty-sec"><h2>소속 인물 <span class="pty-cnt">{len(mem)}</span></h2>'
                        f'<ul class="pty-members">{"".join(items)}</ul>{more}</section>')

    desc = f'{name}' + (f'({abbr})' if abbr else '') + f' — {life}. ' + (info.get("note") or "")
    return PAGE.format(
        name=esc(name), abbr_badge=abbr_badge, life=life, note=note_html,
        lineage=lineage, elections=elections, members=members_html,
        desc=esc(desc[:160]), canon=purl(name), qname=quote(name),
    )


def main():
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))["parties"]
    timeline = json.loads(TIMELINE.read_text(encoding="utf-8"))
    persons = json.loads(PERSON_INDEX.read_text(encoding="utf-8"))["persons"]

    known = set(reg.keys())
    appearances = build_appearances(timeline)
    members = build_members(persons)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    urls = []
    for name, info in reg.items():
        d = OUT_DIR / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(render(name, info, known, appearances, members), encoding="utf-8")
        urls.append(purl(name))
    SITEMAP_OUT.write_text("\n".join(urls), encoding="utf-8")
    print(f"→ {OUT_DIR.relative_to(ROOT)}/ : {len(urls)} 정당 페이지")
    # 커버리지 경고 — timeline 등장하나 registry에 없어 페이지 없는 정당
    missing = sorted(set(appearances) - known)
    if missing:
        print(f"  ⚠ registry 미등록(페이지 없음) {len(missing)}개: {', '.join(missing[:15])}{' …' if len(missing) > 15 else ''}")


if __name__ == "__main__":
    main()
