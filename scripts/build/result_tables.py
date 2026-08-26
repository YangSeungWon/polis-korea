"""선거 결과 → 정적 HTML 표. archive와 history가 같이 쓴다.

두 생성기가 같은 표를 낸다. archive는 회차 단위로, history는 (회차 × 직위) 단위로 —
축이 하나 다를 뿐 읽는 데이터도 만드는 표도 같다. 각자 만들면 한쪽만 고쳐지고
어긋난다(이 저장소에서 뷰 표가 그렇게 네 벌이 됐다).

⚠️ 큰 회차는 시군구 결과가 **별도 청크**에 있다(_meta.chunked → {eid}.sigungu.json).
본 파일만 읽으면 21대 대선 races가 18개(전국+시도)뿐이라 표가 통째로 빈다.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "data" / "results"

TC_LABEL = {"1": "대통령", "2": "국회의원", "3": "광역단체장", "4": "기초단체장",
            "5": "광역의원", "6": "기초의원", "7": "비례대표", "11": "교육감"}


def _esc(x) -> str:
    return (str(x if x is not None else "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _pct(v) -> str:
    return f"{v:.1f}%" if isinstance(v, (int, float)) else "—"


def load_races(eid: str) -> list:
    """본 파일 + 시군구 청크를 합쳐 돌려준다."""
    rp = RESULTS_DIR / f"{eid}.json"
    if not rp.is_file():
        return []
    try:
        doc = json.loads(rp.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    races = list(doc.get("races") or [])
    if (doc.get("_meta") or {}).get("chunked"):
        cp = RESULTS_DIR / f"{eid}.sigungu.json"
        if cp.is_file():
            try:
                races += (json.loads(cp.read_text(encoding="utf-8")) or {}).get("races") or []
            except Exception:
                pass
    return races


def turnout_of(r: dict) -> str:
    el, vo = r.get("electors"), r.get("voters")
    return _pct(round(vo / el * 100, 1)) if el and vo else "—"


def winner_rows(races: list, tc: str, scope: str, *, place_cols, link) -> list[list[str]]:
    """(tc, scope) race들 → 표 행. link(kind, place, name)이 링크 HTML을 준다."""
    rows = []
    for r in races:
        if r.get("sg_typecode") != tc or r.get("scope") != scope:
            continue
        cs = sorted(r.get("candidates") or [], key=lambda c: -(c.get("votes") or 0))
        if not cs:
            continue
        c = next((x for x in cs if x.get("won")), cs[0])
        place = r.get("sigungu") or r.get("district") or r.get("sido") or ""
        cols = [_esc(r.get(k) or "") for k in place_cols]
        rows.append(cols + [link("person", place, c.get("name")),
                            link("party", "", c.get("party")),
                            _pct(c.get("pct")), turnout_of(r)])
    return rows


def table_html(sec_id: str, cap: str, head: list[str], rows: list[list[str]]) -> str:
    """표 한 장. 행이 없으면 빈 문자열 — 빈 표를 만들지 않는다."""
    if not rows:
        return ""
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return (f'\n  <section class="ar-section" id="{sec_id}">\n'
            f'    <h2 class="ar-section-title">{cap}</h2>\n'
            f'    <div class="pp-scroll">'
            f'<table class="pp-static"><caption>{cap} — {len(rows)}곳</caption>'
            f'<thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>\n'
            f'  </section>\n')
