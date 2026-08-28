"""홈 상단 3칸의 **정적 시드** — index.html의 STATUS_STATIC 마커 사이를 갱신.

크롤러가 보던 홈 첫 화면은 이랬다:

    대통령 · 대선 — —
    국회 · 총선 — —
    지방정부 · 지선 — —

사실이 하나도 없었다. 값은 assets/status.js가 렌더 후에 채운다. 사람은 보지만
검색엔진도 공유 카드도 못 본다 — 인물 4,300쪽에서 겪은 것과 같은 구조다.

**status.js가 이 시드를 덮어쓴다.** 카드 헤딩은 `card.querySelector('.card-heading')
|| 새로 만들기`라 이미 있으면 재사용하고, 값·설명도 innerHTML로 갈아끼운다. 그래서
정적으로 심어 둬도 화면이 두 번 그려지지 않는다.

⚠️ **'잔여 임기'는 안 적는다.** 그건 오늘 기준이라 매일 변한다 — 정적 HTML이나
이미지에 박으면 하루 만에 거짓이 된다. 대신 안 변하는 사실(임기 종료 연월)을 적고,
움직이는 값은 status.js가 화면에서만 보여준다.

정본은 화면과 같은 data/timeline.json이다. 다른 파일에서 뽑으면 글과 화면이 갈린다.

사용: python3 scripts/build/sync_home_status.py
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "timeline.json"
PAGE = ROOT / "index.html"
START = "<!-- STATUS_STATIC_START"
END = "<!-- STATUS_STATIC_END -->"
PAT = re.compile(re.escape(START) + r"[\s\S]*?" + re.escape(END))

# 임기(년). 카드 설명에 '언제까지'를 적기 위한 것 — 잔여가 아니라 종료 연월이다.
TERM = {"presidential": 5, "national_assembly": 4, "local": 4}
ARCH = {"presidential": "pres", "national_assembly": "general", "local": "local"}


def esc(x) -> str:
    return (str(x if x is not None else "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def latest(rounds: list, kind: str) -> dict | None:
    xs = [r for r in rounds if r.get("kind") == kind and not r.get("upcoming")
          and r.get("date")]
    return max(xs, key=lambda r: r["date"]) if xs else None


def term_end(date_s: str, years: int) -> str:
    y, m = int(date_s[:4]) + years, date_s[5:7]
    return f"{y}-{m}"


def archive_slug(r: dict) -> str:
    n, kind, yr = r.get("n"), r.get("kind"), r["date"][:4]
    suf = {1: "st", 2: "nd", 3: "rd"}.get(n if n and n % 100 not in (11, 12, 13) else 0,
                                          "th") if isinstance(n, int) else "th"
    if isinstance(n, int) and n % 10 in (1, 2, 3) and n % 100 not in (11, 12, 13):
        suf = {1: "st", 2: "nd", 3: "rd"}[n % 10]
    else:
        suf = "th"
    return f"{n}{suf}-{ARCH[kind]}-{yr}"


# ⚠️ id는 assets/status.js가 찾는 것과 **글자 그대로** 같아야 한다. 처음에
# status-{slot}-v로 지었다가 status.js가 null.innerHTML로 죽었다 — 화면의 세 칸이
# 정적 시드에서 멈춘 채였고, 콘솔을 안 봤으면 '잘 되네'로 지나갈 뻔했다.
SLOT_IDS = {
    "president": ("status-pres-name", "status-pres-meta"),
    "assembly":  ("status-asm-top",   "status-asm-meta"),
    "local":     ("status-local-name", "status-local-meta"),
}


def card(slot: str, label: str, r: dict, value: str, meta: str) -> str:
    slug = archive_slug(r)
    href = f"/archive/{slug}/" if (ROOT / "archive" / slug / "index.html").exists() \
        else f"history.html?type={r['kind']}"
    vid, mid = SLOT_IDS[slot]
    return (f'      <a class="status-card" data-slot="{slot}" href="{href}">\n'
            f'        <div class="status-label">{esc(label)}</div>'
            f'<div class="card-heading"><span class="card-heading-n">{esc(r["label"])}</span>'
            f'<span class="card-heading-date">{esc(r["date"])}</span></div>\n'
            f'        <div class="status-value" id="{vid}">{value}</div>\n'
            f'        <div class="status-meta" id="{mid}">{esc(meta)}</div>\n'
            f'      </a>\n')


def build() -> str:
    rounds = json.loads(SRC.read_text(encoding="utf-8"))["rounds"]
    out = []

    p = latest(rounds, "presidential")
    if p:
        cs = sorted((p.get("presCandidates") or []), key=lambda c: -(c.get("pct") or 0))[:3]
        who = f'{esc(p.get("winner") or "")} <b>{esc(p.get("winner_party") or "")}</b>'
        bits = " · ".join(f'{esc(c["name"])} {c["pct"]:.1f}%' for c in cs if c.get("pct") is not None)
        out.append(card("president", "대통령 · 대선", p, f'{who}<br>{bits}',
                        f'임기 {TERM["presidential"]}년 · {term_end(p["date"], 5)}까지'))

    a = latest(rounds, "national_assembly")
    if a:
        seats = (a.get("partySeats") or [])[:5]
        tot = sum(s for _, s in (a.get("partySeats") or []))
        v = " · ".join(f'{esc(n)} <b>{s}</b>석' for n, s in seats)
        out.append(card("assembly", "국회 · 총선", a, v,
                        f'{tot}석 · 임기 4년 · {term_end(a["date"], 4)}까지'))

    lo = latest(rounds, "local")
    if lo:
        import collections
        sw = lo.get("sidoWinners") or {}
        c = collections.Counter((v.get("party") if isinstance(v, dict) else v)
                                for v in sw.values())
        v = "광역단체장 " + " · ".join(f'{esc(n)} <b>{k}</b>곳' for n, k in c.most_common(4))
        out.append(card("local", "지방정부 · 지선", lo, v,
                        f'{len(sw)}개 시·도 · 임기 4년 · {term_end(lo["date"], 4)}까지'))
    return "".join(out)


def main() -> int:
    if not SRC.is_file() or not PAGE.is_file():
        print("ERR: timeline.json 또는 index.html이 없다", file=sys.stderr)
        return 1
    html = PAGE.read_text(encoding="utf-8")
    if not PAT.search(html):
        print("ERR: index.html에 STATUS_STATIC 마커가 없다", file=sys.stderr)
        return 1
    body = build()
    if not body:
        print("ERR: timeline.json에서 최근 회차를 못 찾았다", file=sys.stderr)
        return 1
    block = (f"{START} — scripts/build/sync_home_status.py 자동 갱신. 손수정 X.\n"
             "         assets/status.js가 로드되면 같은 자리를 더 풍부하게 갈아끼운다.\n"
             "         JS 없이도(그리고 크롤러가 렌더하기 전에도) 세 자리의 사실이\n"
             "         HTML에 남게 하는 것이 목적. 잔여 임기는 안 적는다 — 매일 변한다. -->\n"
             f"{body}      {END}")
    new = PAT.sub(lambda _: block, html, count=1)
    if new != html:
        PAGE.write_text(new, encoding="utf-8")
    print(f"→ index.html 상단 3칸 정적 시드 {body.count('status-card')}칸")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
