"""위키백과 한국어판 → 옛 선거 회차 (NEC OpenAPI 미가용) 결과 fetch.

NEC OpenAPI는 2010-07-28 이후만. 13·14·15대 대선(1987·1992·1997) 등 옛 회차
데이터는 위키백과 article infobox에 후보 1~N · 정당 · 득표수 · 득표율
구조화돼있음. fetch + parse + 표준 schema 출력.

지원:
  - 대선 (presidential): infobox 후보 N · 정당 · 득표수 · 득표율 → nation race
  - 총선/지선: infobox 정당별 의석/득표가 다른 schema (TODO)

사용:
  python3 scripts/fetch/fetch_old_elections.py --id 13th-pres-1987
  python3 scripts/fetch/fetch_old_elections.py --id 15th-pres-1997 --kind presidential
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "data" / "results"
ELECTIONS_DIR = ROOT / "data" / "elections"
WIKI_API = "https://ko.wikipedia.org/w/api.php"

# 옛 회차 ID → 위키 page name + meta
WIKI_PAGES = {
    "13th-pres-1987": {"page": "대한민국 제13대 대통령 선거", "name": "제13대 대통령선거", "date": "1987-12-16"},
    "14th-pres-1992": {"page": "대한민국 제14대 대통령 선거", "name": "제14대 대통령선거", "date": "1992-12-18"},
    "15th-pres-1997": {"page": "대한민국 제15대 대통령 선거", "name": "제15대 대통령선거", "date": "1997-12-18"},
    "13th-general-1988": {"page": "대한민국 제13대 국회의원 선거", "name": "제13대 국회의원선거", "date": "1988-04-26"},
    "14th-general-1992": {"page": "대한민국 제14대 국회의원 선거", "name": "제14대 국회의원선거", "date": "1992-03-24"},
    "15th-general-1996": {"page": "대한민국 제15대 국회의원 선거", "name": "제15대 국회의원선거", "date": "1996-04-11"},
    "16th-general-2000": {"page": "대한민국 제16대 국회의원 선거", "name": "제16대 국회의원선거", "date": "2000-04-13"},
    "1st-local-1995":   {"page": "제1회 전국동시지방선거", "name": "제1회 전국동시지방선거", "date": "1995-06-27"},
    "2nd-local-1998":   {"page": "제2회 전국동시지방선거", "name": "제2회 전국동시지방선거", "date": "1998-06-04"},
    "3rd-local-2002":   {"page": "제3회 전국동시지방선거", "name": "제3회 전국동시지방선거", "date": "2002-06-13"},
    "4th-local-2006":   {"page": "제4회 전국동시지방선거", "name": "제4회 전국동시지방선거", "date": "2006-05-31"},
}


def fetch_wikitext(page: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            qs = urllib.parse.urlencode({
                "action": "parse", "format": "json", "page": page,
                "prop": "wikitext", "redirects": 1,
            })
            req = urllib.request.Request(
                f"{WIKI_API}?{qs}",
                headers={"User-Agent": "polis-korea-archive/1.0 (https://polis.ysw.kr)"},
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            wt = d.get("parse", {}).get("wikitext", {})
            return wt.get("*", "") if isinstance(wt, dict) else ""
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(2 ** attempt * 3)  # 3, 6, 12 sec
                continue
            raise
    return ""


def parse_pres_infobox(wt: str) -> list[dict]:
    """대선 infobox → candidates list (전국 합계)."""
    out = []
    for n in range(1, 12):
        m_name = re.search(rf"\|\s*후보{n}\s*=\s*'*\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", wt)
        m_party = re.search(rf"\|\s*정당{n}\s*=\s*'*\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", wt)
        m_votes = re.search(rf"\|\s*득표수{n}\s*=\s*'*([\d,]+)", wt)
        m_pct = re.search(rf"\|\s*득표율{n}\s*=\s*'*([\d.]+)\s*%", wt)
        if not m_name or not m_pct:
            continue
        # 정당명 disambig suffix 정리
        party_raw = m_party.group(1).strip() if m_party else ""
        party = re.sub(r"\s*\([^)]+\)\s*$", "", party_raw)
        out.append({
            "name": m_name.group(1).strip(),
            "party": party,
            "votes": int(m_votes.group(1).replace(",", "")) if m_votes else 0,
            "pct": float(m_pct.group(1)),
        })
    # 정렬·rank·won
    out.sort(key=lambda c: -c["votes"])
    for i, c in enumerate(out, 1):
        c["rank"] = i
    if out:
        out[0]["won"] = True
    return out


def parse_investiture_year_voters(wt: str) -> dict:
    """투표율·선거인수 추출 (infobox에 있으면)."""
    out = {}
    m_t = re.search(r"\|\s*투표율\s*=\s*([\d.]+)\s*%", wt)
    if m_t:
        out["turnout_pct"] = float(m_t.group(1))
    m_e = re.search(r"\|\s*선거인수\s*=\s*([\d,]+)", wt)
    if m_e:
        out["electors"] = int(m_e.group(1).replace(",", ""))
    return out


def build_presidential(eid: str, spec: dict) -> dict:
    wt = fetch_wikitext(spec["page"])
    if not wt:
        raise RuntimeError(f"빈 wikitext: {spec['page']}")
    cands = parse_pres_infobox(wt)
    if not cands:
        raise RuntimeError(f"후보 0건: {spec['page']}")
    extras = parse_investiture_year_voters(wt)
    total_votes = sum(c["votes"] for c in cands)
    nation = {
        "sg_typecode": "1",
        "sido": "",
        "sigungu": "",
        "scope": "nation",
        "electors": extras.get("electors", 0),
        "voters": total_votes,
        "valid_votes": total_votes,
        "invalid_votes": 0,
        "abstain": 0,
        "candidates": cands,
    }
    if "turnout_pct" in extras:
        nation["turnout_pct"] = extras["turnout_pct"]
    return {
        "_meta": {
            "election": spec["name"],
            "election_id": eid,
            "election_date": spec["date"],
            "source": "wikipedia-ko-infobox",
            "_note": "옛 회차 — NEC OpenAPI 미가용으로 위키백과 infobox에서 nation 합계만 채움. 시도/시군구 별 break 없음.",
            "n_rows": 1,
        },
        "races": [nation],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="election id, e.g. 15th-pres-1997")
    ap.add_argument("--kind", default="presidential", choices=["presidential"], help="현재 대선만 지원")
    args = ap.parse_args()

    spec = WIKI_PAGES.get(args.id)
    if not spec:
        print(f"ERR: {args.id} mapping 없음 — WIKI_PAGES에 추가", file=sys.stderr)
        sys.exit(1)

    if args.kind != "presidential":
        print(f"ERR: kind={args.kind} 현재 미지원", file=sys.stderr)
        sys.exit(1)

    data = build_presidential(args.id, spec)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{args.id}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    n = len(data["races"][0]["candidates"])
    print(f"→ {out_path.relative_to(ROOT)} ({n} 후보 · nation race 1)")


if __name__ == "__main__":
    main()
