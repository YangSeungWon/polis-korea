"""JS로만 그리던 목록의 **정적 시드** — 연표·재보궐.

두 쪽의 본문이 크롤러에게 이렇게 보였다:

    chronology.html   293자 · "데이터 불러오는 중…"
    byelection.html   362자 · "데이터 불러오는 중…"

둘 다 sitemap에 있고 2026-06에 크롤됐고 색인되지 않았다. 본문에 '불러오는 중'이
적혀 있으면 색인을 안 하는 게 합리적인 판단이다. 렌더하면 2,719자·1,864자가 되지만
그건 다른 질문이다 — archive·history·polls에 한 것과 같은 일을 여기에도 한다.

시드는 JS가 덮어쓴다(그 자리의 목록을 새로 그린다). 사람이 보는 화면은 그대로고,
JS 없이도 사실이 HTML에 남는다.

정본은 화면과 같은 파일이다 — 연표는 data/timeline.json + history_events.json,
재보궐은 그 회차 결과. 다른 데서 뽑으면 글과 화면이 갈린다.

사용: python3 scripts/build/sync_page_seeds.py
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def esc(x) -> str:
    return (str(x if x is not None else "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def load(rel: str, default=None):
    p = ROOT / rel
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                            # noqa: BLE001
        return default


def write_block(page: Path, name: str, body: str, note: str) -> bool:
    start, end = f"<!-- {name}_START", f"<!-- {name}_END -->"
    pat = re.compile(re.escape(start) + r"[\s\S]*?" + re.escape(end))
    if not page.is_file():
        return False
    html = page.read_text(encoding="utf-8")
    if not pat.search(html):
        print(f"  ! {page.name}에 {name} 마커 없음 — 스킵", file=sys.stderr)
        return False
    block = f"{start} — scripts/build/sync_page_seeds.py 자동 갱신. 손수정 X.\n         {note} -->\n{body}    {end}"
    new = pat.sub(lambda _: block, html, count=1)
    if new != html:
        page.write_text(new, encoding="utf-8")
    return True


# ── 연표 ───────────────────────────────────────────────────────────────────
ARCH = {"presidential": "pres", "national_assembly": "general", "local": "local"}


def chrono_body() -> str:
    rounds = (load("data/timeline.json", {}) or {}).get("rounds") or []
    # history_events.json은 {republics, governments, events} 묶음이다 —
    # 리스트인 줄 알고 곧장 돌다가 문자열 키를 만나 죽었다.
    ev = load("data/history_events.json", {}) or {}
    events = (ev.get("events") or []) if isinstance(ev, dict) else (ev or [])
    rows = []
    for r in rounds:
        if r.get("upcoming") or not r.get("date"):
            continue
        n, kind, yr = r.get("n"), r.get("kind"), r["date"][:4]
        slug = f"{n}{'st' if n % 10 == 1 and n % 100 != 11 else 'nd' if n % 10 == 2 and n % 100 != 12 else 'rd' if n % 10 == 3 and n % 100 != 13 else 'th'}-{ARCH.get(kind, '')}-{yr}" \
            if isinstance(n, int) and kind in ARCH else ""
        href = f"/archive/{slug}/" if slug and (ROOT / "archive" / slug / "index.html").exists() else ""
        who = " · ".join(x for x in (r.get("winner"), r.get("winner_party")) if x)
        label = esc(r.get("label") or "")
        inner = f'<a href="{href}">{label}</a>' if href else label
        rows.append((r["date"], f'<li><span class="cx-d">{esc(r["date"])}</span> {inner}'
                                + (f' <span class="cx-w">{esc(who)}</span>' if who else "") + "</li>"))
    for e in events:
        if not e.get("date"):
            continue
        rows.append((e["date"], f'<li><span class="cx-d">{esc(e["date"])}</span> '
                                f'{esc(e.get("title") or "")}'
                                + (f' <span class="cx-t">{esc(e["tag"])}</span>' if e.get("tag") else "")
                                + "</li>"))
    rows.sort(key=lambda x: x[0], reverse=True)
    if not rows:
        return ""
    return ('    <ol class="cx-seed">\n      ' + "\n      ".join(h for _, h in rows) + "\n    </ol>\n")


# ── 재보궐 ─────────────────────────────────────────────────────────────────
def byelection_body() -> str:
    res = load("data/results/9th-byelection-2026.json", {}) or {}
    races = [r for r in (res.get("races") or []) if r.get("scope") == "district"]
    if not races:
        return ""
    rows = []
    for r in sorted(races, key=lambda x: (x.get("sido") or "", x.get("district") or "")):
        cs = sorted(r.get("candidates") or [], key=lambda c: -(c.get("votes") or 0))
        top = cs[0] if cs else None
        who = (f'{esc(top.get("name") or "")} <b>{esc(top.get("party") or "")}</b>'
               f'{f" {top['pct']:.1f}%" if top.get("pct") is not None else ""}') if top else "—"
        rows.append(f'<li><span class="bx-r">{esc(r.get("sido") or "")} '
                    f'{esc(r.get("district") or "")}</span> {who}</li>')
    date_s = esc((res.get("_meta") or {}).get("election_date") or "")
    return (f'    <p class="bx-seed-lede">{date_s} 국회의원 재·보궐선거 '
            f'{len(rows)}개 선거구 당선인.</p>\n'
            '    <ul class="bx-seed">\n      ' + "\n      ".join(rows) + "\n    </ul>\n")


# ── 타임라인 재생 ──────────────────────────────────────────────────────────
def timelapse_body() -> str:
    """재생의 정적 시드 — 지금 프레임 3장 + 회차 53건.

    timeline.html의 정적 본문이 375자였다. 세 종류 선거의 흐름을 보여주는 페이지인데
    크롤러에겐 빈 껍데기였다. 재생은 JS가 하지만, **무엇을 재생하는지**는 HTML에
    남는다 — 지금 상태 3장과 회차 목록.
    """
    d = load("data/election_timelapse.json", {}) or {}
    lanes = d.get("lanes") or []
    if not lanes:
        return ""
    figs, lists = [], []
    for L in lanes:
        frames = L.get("frames") or []
        if not frames:
            continue
        last = next((f for f in reversed(frames) if f.get("img")), None)
        if last:
            wh = f' width="{last["w"]}" height="{last["h"]}"' if last.get("w") else ""
            figs.append(
                f'<figure class="tl-seed-fig"><img src="{esc(last["img"])}"{wh} loading="lazy" '
                f'decoding="async" alt="{esc(L["name"])} {esc(last["name"])} — {esc(L["means"])}">'
                f'<figcaption>{esc(L["name"])} · {esc(last["name"])} '
                f'{esc(last["date"])} — {esc(L["means"])}</figcaption></figure>')
        items = "".join(
            f'<li><a href="/archive/{esc(f["slug"])}/">{esc(f["name"])}</a> '
            f'<span>{esc(f["date"])}</span>'
            + (f' <span class="tl-seed-note">{esc(f["note"])}</span>' if f.get("note") else "")
            + "</li>" for f in reversed(frames))
        lists.append(f'<details class="tl-seed-more"><summary>{esc(L["name"])} '
                     f'{len(frames)}회차</summary><ul>{items}</ul></details>')
    if not figs:
        return ""
    return ('    <div class="tl-seed">\n      <div class="tl-seed-figs">'
            + "".join(figs) + "</div>\n      " + "".join(lists) + "\n    </div>\n")


def main() -> int:
    n = 0
    if write_block(ROOT / "chronology.html", "CHRONO_SEED", chrono_body(),
                   "chronology.js가 로드되면 같은 자리를 연표로 갈아끼운다. JS 없이도 "
                   "선거·사건이 HTML에 남게 하는 것이 목적."):
        n += 1
    if write_block(ROOT / "timeline.html", "TL_PLAY", timelapse_body(),
                   "timelapse.js가 로드되면 같은 자리 아래에서 재생한다. JS 없이도 "
                   "지금 세 자리와 53회차가 HTML에 남게 하는 것이 목적."):
        n += 1
    if write_block(ROOT / "byelection.html", "BOE_SEED", byelection_body(),
                   "byelection.js가 로드되면 지도·상세로 갈아끼운다. JS 없이도 "
                   "선거구별 당선인이 HTML에 남게 하는 것이 목적."):
        n += 1
    print(f"→ 정적 시드 {n}쪽")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
