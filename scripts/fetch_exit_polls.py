"""위키백과 한국어판에서 출구조사 데이터 fetch → data/exit_polls/{id}.json sources에 추가.

위키 회차별 페이지에 출구조사 섹션은 template invocation으로 분리됨:
  {{제8회 전국동시지방선거 광역자치단체장 출구조사}}
  {{제21대 대선 출구조사}}
template page wikitext에 wikitable로 시도·정당·후보·예측 득표율 정리.

지원 회차:
  - 8회 지선 (2022): 광역자치단체장
  - 21대 대선 (2025): 대통령
  - 22대 총선 (2024): 국회의원
  - 그 외는 page name 매핑 추가하면 동작.

사용:
  python3 scripts/fetch_exit_polls.py --id 8th-local-2022
  python3 scripts/fetch_exit_polls.py --id 9th-local-2026
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXIT_DIR = ROOT / "data" / "exit_polls"
WIKI_API = "https://ko.wikipedia.org/w/api.php"

# 회차 → 위키 template page name (KEP 3사 출구조사 — KBS·MBC·SBS 공동).
TEMPLATE_PAGE = {
    "8th-local-2022": [
        "틀:제8회 전국동시지방선거 광역자치단체장 출구조사",
    ],
    "9th-local-2026": [
        "틀:제9회 전국동시지방선거 광역자치단체장 출구조사",
    ],
    "21st-pres-2025": [
        "틀:제21대 대통령 선거 출구조사",
    ],
    "22nd-general-2024": [
        "틀:제22대 국회의원 선거 출구조사",
    ],
}


def fetch_wikitext(page: str) -> str:
    qs = urllib.parse.urlencode({
        "action": "parse", "format": "json", "page": page, "prop": "wikitext",
    })
    url = f"{WIKI_API}?{qs}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "polis-korea-archive/1.0 (https://polis.ysw.kr; archive@polis.ysw.kr)"
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    return d.get("parse", {}).get("wikitext", {}).get("*", "")


def strip_wiki_link(s: str) -> str:
    """[[A|B]] → B, [[A]] → A."""
    s = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", s)
    s = re.sub(r"\[\[([^\]]+)\]\]", r"\1", s)
    return s.strip()


def parse_wikitable_kep(wikitext: str) -> dict:
    """광역단체장 출구조사 template wikitext → {시도: [{name, party, pct}, ...]}.

    template 구조 (3-row pattern):
      | rowspan=3 | [[시도명]] (시·도지사 page)
      | 정당색 칸 | 정당명 | 정당색 칸 | 정당명
      |-
      | 후보명 | 후보명
      |-
      | {{막대|...}} pct% | {{막대|...}} pct%
    """
    out: dict[str, list[dict]] = {}
    # rowspan="3" 패턴으로 split — 각 시도 그룹
    chunks = re.split(r'\|\s*rowspan="?3"?\s*\|', wikitext)[1:]
    sido_norm = {
        "서울특별시장": "서울특별시", "부산광역시장": "부산광역시", "대구광역시장": "대구광역시",
        "인천광역시장": "인천광역시", "광주광역시장": "광주광역시", "대전광역시장": "대전광역시",
        "울산광역시장": "울산광역시", "세종특별자치시장": "세종특별자치시",
        "경기도지사": "경기도", "강원특별자치도지사": "강원특별자치도", "강원도지사": "강원특별자치도",
        "충청북도지사": "충청북도", "충청남도지사": "충청남도",
        "전북특별자치도지사": "전북특별자치도", "전라북도지사": "전북특별자치도", "전라남도지사": "전라남도",
        "경상북도지사": "경상북도", "경상남도지사": "경상남도",
        "제주특별자치도지사": "제주특별자치도",
    }
    for chunk in chunks:
        # 시도 이름 — 첫 [[...]]
        m_sido = re.search(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", chunk)
        if not m_sido:
            continue
        sido_raw = m_sido.group(1).strip()
        sido = sido_norm.get(sido_raw)
        if not sido:
            continue
        # 정당명 — ! [[정당명]] 패턴 (2개)
        parties = re.findall(r"!\s*\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", chunk)
        # 후보명 — colspan="2" | [[후보]] 패턴 (정당 색 칸 다음에)
        names = re.findall(r'colspan="?2"?\s*\|\s*\[\[([^\]|]+)(?:\|[^\]]*)?\]\]', chunk)
        # pct — {{막대|...}} 다음 숫자%
        pcts = re.findall(r"\{\{막대\|[^}]+\}\}\s*([\d.]+)\s*%", chunk)
        if not parties or not names or not pcts:
            continue
        rows = []
        for p, n, pct in zip(parties, names, pcts):
            # 위키 disambig suffix 제거 — "송영길 (정치인)" → "송영길"
            name_clean = re.sub(r"\s*\([^)]+\)\s*$", "", n).strip()
            rows.append({"name": name_clean, "party": p, "pct": float(pct)})
        if rows:
            out[sido] = rows
    return out


def load_existing(election_id: str) -> dict:
    p = EXIT_DIR / f"{election_id}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {
        "id": election_id,
        "election_name": "",
        "election_date": "",
        "sources": [],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="election id, e.g. 8th-local-2022")
    ap.add_argument("--source-key", default="kep_3sa", help="source key (kep_3sa·jtbc 등)")
    args = ap.parse_args()
    pages = TEMPLATE_PAGE.get(args.id)
    if not pages:
        print(f"ERR: {args.id} template page mapping 없음 — TEMPLATE_PAGE에 추가", file=sys.stderr)
        sys.exit(1)
    EXIT_DIR.mkdir(parents=True, exist_ok=True)
    data = load_existing(args.id)
    combined: dict = {}
    for page in pages:
        wt = fetch_wikitext(page)
        if not wt:
            print(f"  ! {page}: wikitext 비어있음", file=sys.stderr)
            continue
        parsed = parse_wikitable_kep(wt)
        print(f"  {page}: {len(parsed)} 시도", file=sys.stderr)
        combined.update(parsed)
    if not combined:
        print("결과 0 — page name·구조 확인", file=sys.stderr)
        sys.exit(2)
    # sources 중 key 매칭 source 갱신, 없으면 추가
    src_idx = next((i for i, s in enumerate(data["sources"]) if s.get("key") == args.source_key), -1)
    src_block = {
        "key": args.source_key,
        "name": "KBS·MBC·SBS 공동 출구조사" if args.source_key == "kep_3sa" else args.source_key,
        "released_at": "",
        "quote_after": "",
        "office": "광역단체장",
        "results": combined,
    }
    if src_idx >= 0:
        # released_at/quote_after 기존 값 유지, results만 갱신
        existing = data["sources"][src_idx]
        existing["results"] = combined
        existing["office"] = "광역단체장"
    else:
        data["sources"].append(src_block)
    out_path = EXIT_DIR / f"{args.id}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {out_path.name}: {len(combined)} 시도 source={args.source_key}")


if __name__ == "__main__":
    main()
