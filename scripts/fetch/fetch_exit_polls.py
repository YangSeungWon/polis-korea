"""위키백과 한국어판에서 출구조사 데이터 fetch → data/exit_polls/{id}.json sources에 추가.

위키 회차별 페이지에 출구조사 섹션은 template invocation으로 분리됨:
  {{제8회 전국동시지방선거 광역자치단체장 출구조사}}
  {{대한민국 제21대 대통령 선거 출구조사}}      (KEP 3사)
  {{대한민국 제21대 대통령 선거 출구조사 2}}    (JTBC)
template page wikitext에 wikitable로 시도·정당·후보·예측 득표율 정리.
지선 광역단체장이든 대선 권역별이든 동일한 rowspan="3" chunk 패턴.

지원 회차는 data/elections/{id}.json 의 wiki_exit_polls 블록에 정의:
  {
    "wiki_exit_polls": {
      "kind": "local" | "pres",
      "templates": [{"page": "틀:...", "key": "kep_3sa", "name": "..."}, ...]
    }
  }
새 회차는 메타에 추가하면 동작.

사용:
  python3 scripts/fetch/fetch_exit_polls.py --id 8th-local-2022
  python3 scripts/fetch/fetch_exit_polls.py --id 21st-pres-2025
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXIT_DIR = ROOT / "data" / "exit_polls"
WIKI_API = "https://ko.wikipedia.org/w/api.php"

# 위키 출구조사 source 매핑은 data/elections/{id}.json 의 wiki_exit_polls 블록.
# kind=local: template page에 시도별 광역단체장 wikitable
# kind=pres:  대선 권역별 (전국 + 17 시도)
ELECTIONS_DIR = ROOT / "data" / "elections"


def load_election_spec(election_id: str) -> dict | None:
    p = ELECTIONS_DIR / f"{election_id}.json"
    if not p.exists():
        return None
    meta = json.loads(p.read_text(encoding="utf-8"))
    wep = meta.get("wiki_exit_polls") or {}
    if not wep.get("templates"):
        return None
    return {"kind": wep.get("kind") or "local", "sources": wep["templates"]}



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
        # 광역단체장 (-시장/-도지사 suffix)
        "서울특별시장": "서울특별시", "부산광역시장": "부산광역시", "대구광역시장": "대구광역시",
        "인천광역시장": "인천광역시", "광주광역시장": "광주광역시", "대전광역시장": "대전광역시",
        "울산광역시장": "울산광역시", "세종특별자치시장": "세종특별자치시",
        "경기도지사": "경기도", "강원특별자치도지사": "강원특별자치도", "강원도지사": "강원특별자치도",
        "충청북도지사": "충청북도", "충청남도지사": "충청남도",
        "전북특별자치도지사": "전북특별자치도", "전라북도지사": "전북특별자치도", "전라남도지사": "전라남도",
        "경상북도지사": "경상북도", "경상남도지사": "경상남도",
        "제주특별자치도지사": "제주특별자치도",
        # 대선 권역 (시도 풀네임 또는 축약형)
        "전국": "전국",
        "서울": "서울특별시", "서울특별시": "서울특별시",
        "부산": "부산광역시", "부산광역시": "부산광역시",
        "대구": "대구광역시", "대구광역시": "대구광역시",
        "인천": "인천광역시", "인천광역시": "인천광역시",
        "광주": "광주광역시", "광주광역시": "광주광역시",
        "대전": "대전광역시", "대전광역시": "대전광역시",
        "울산": "울산광역시", "울산광역시": "울산광역시",
        "세종": "세종특별자치시", "세종특별자치시": "세종특별자치시",
        "경기": "경기도", "경기도": "경기도",
        "강원": "강원특별자치도", "강원특별자치도": "강원특별자치도", "강원도": "강원특별자치도",
        "충북": "충청북도", "충청북도": "충청북도",
        "충남": "충청남도", "충청남도": "충청남도",
        "전북": "전북특별자치도", "전북특별자치도": "전북특별자치도", "전라북도": "전북특별자치도",
        "전남": "전라남도", "전라남도": "전라남도",
        "경북": "경상북도", "경상북도": "경상북도",
        "경남": "경상남도", "경상남도": "경상남도",
        "제주": "제주특별자치도", "제주특별자치도": "제주특별자치도",
    }
    for chunk in chunks:
        # 시도 이름 — chunk 시작이 평문 한글이면 평문, 아니면 첫 [[link]]
        head = chunk[:200]
        m_plain = re.match(r"\s*([가-힣]+)\s*(?:\n|\||$)", head)
        m_link = re.search(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", head)
        if m_plain and (not m_link or m_plain.end() <= m_link.start()):
            sido_raw = m_plain.group(1).strip()
        elif m_link:
            sido_raw = m_link.group(1).strip()
        else:
            continue
        sido = sido_norm.get(sido_raw)
        if not sido:
            continue
        # 정당명 — ![[정당명]] 또는 ![[link|표시명]] (표시명 우선)
        party_matches = re.findall(r"!\s*\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", chunk)
        parties = [(alias.strip() if alias else target.strip()) for target, alias in party_matches]
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




def parse_wikitable_general_seats(wikitext: str) -> dict:
    """총선 출구조사 — 의석 예측 wikitable → {방송사_key: {name, seats}}.

    template 구조:
      ! 방송사  ! [[정당1]]<br/>[[위성1]]  ! [[정당2]]<br/>[[위성2]]  ...
      |-
      ! KBS  | 178~196 | 87~105 | ...
      |- ...

    위성정당이 본정당과 같은 헤더 cell에 묶여있으면 위성을 메모로 보존.
    """
    out: dict[str, dict] = {}
    # 첫 wikitable 추출
    m = re.search(r"\{\|[\s\S]*?\|\}", wikitext)
    if not m:
        return out
    table = m.group(0)
    rows = re.split(r"\n\|-+\n", table)
    if len(rows) < 3:
        return out
    # rows[0] = {|... 테이블 opener / |+ caption. 실제 헤더 행은 rows[1].
    header = rows[1]
    data_rows = rows[2:]
    # 정당 헤더 cell들 — '!' 뒤 [[정당]] (또는 alias) [<br/>...] 여러 줄 OK.
    # 셀 단위: line starts with ! then content. '! 방송사'는 첫 cell, 나머지가 정당.
    header_lines = [ln for ln in header.splitlines() if ln.strip().startswith("!")]
    if len(header_lines) < 3:
        # 한 줄에 '!!' 구분으로 묶여있을 수도
        joined = " ".join(header_lines)
        cells = re.split(r"!\s*", joined)
        cells = [c.strip() for c in cells if c.strip()]
    else:
        cells = [ln.lstrip("!").strip() for ln in header_lines]
    if not cells:
        return out
    party_cells = cells[1:]  # 첫 cell = 방송사 라벨

    def extract_parties(cell: str) -> tuple[str, str]:
        """cell → (main_party, satellite_or_alias). [[A|B]] → B, [[A]] → A."""
        links = re.findall(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", cell)
        if not links:
            return "", ""
        names = [alias.strip() if alias else target.strip() for target, alias in links]
        main = names[0]
        extra = names[1] if len(names) > 1 else ""
        return main, extra

    parties = [extract_parties(c) for c in party_cells]

    # 데이터 행
    for row in data_rows:
        m_bc = re.match(r"\s*!\s*([^\n|]+)", row)
        if not m_bc:
            continue
        bc = m_bc.group(1).strip()
        # 셀: | 값 패턴
        cells_data = re.findall(r"^\|\s*([^\n|]+)", row, flags=re.M)
        # 첫 데이터 row의 cell 수가 party 수와 안 맞으면 skip
        if len(cells_data) < len(parties):
            continue
        seats: dict[str, dict] = {}
        for (main, extra), raw in zip(parties, cells_data[:len(parties)]):
            if not main:
                continue
            raw = raw.strip()
            mn, mx = parse_seat_range(raw)
            if mn is None:
                continue
            entry: dict = {"min": mn, "max": mx}
            if extra and extra != main:
                entry["satellite"] = extra
            seats[main] = entry
        if seats:
            key, name = BROADCAST_TO_KEY(bc)
            out[key] = {"name": name, "seats": seats}
    return out


def parse_seat_range(text: str) -> tuple:
    """'178~196' / '0' / '178 ~ 196' → (min, max). 못 파싱 시 (None, None)."""
    text = text.strip().replace("~", "~").replace("〜", "~")
    m = re.match(r"^\s*(\d+)\s*~\s*(\d+)\s*$", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"^\s*(\d+)\s*$", text)
    if m:
        n = int(m.group(1))
        return n, n
    return None, None


BROADCASTER_MAP = {
    "KBS": ("kbs", "KBS 출구조사"),
    "MBC": ("mbc", "MBC 출구조사"),
    "SBS": ("sbs", "SBS 출구조사"),
    "JTBC": ("jtbc", "JTBC 출구조사"),
    "채널A": ("channel_a", "채널A 출구조사"),
    "MBN": ("mbn", "MBN 출구조사"),
    "방송 3사": ("kep_3sa", "KBS·MBC·SBS 공동 출구조사"),
    "방송3사": ("kep_3sa", "KBS·MBC·SBS 공동 출구조사"),
}


def BROADCAST_TO_KEY(text: str) -> tuple[str, str]:
    """방송사 라벨 → (source key, 표시명)."""
    cleaned = re.sub(r"\s+", "", text)
    for label, kv in BROADCASTER_MAP.items():
        if label.replace(" ", "") in cleaned:
            return kv
    return ("other", text)


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


def upsert_source(data: dict, key: str, block: dict):
    """sources 배열에서 key 매칭 source 갱신, 없으면 추가. released_at·quote_after 보존."""
    idx = next((i for i, s in enumerate(data["sources"]) if s.get("key") == key), -1)
    if idx >= 0:
        existing = data["sources"][idx]
        for k, v in block.items():
            if k in ("released_at", "quote_after") and existing.get(k):
                continue
            existing[k] = v
    else:
        data["sources"].append(block)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="election id, e.g. 8th-local-2022")
    ap.add_argument("--source-key", default="kep_3sa", help="광역단체장 모드 source key")
    args = ap.parse_args()
    spec = load_election_spec(args.id)
    if not spec:
        print(f"ERR: {args.id} wiki_exit_polls 매핑 없음 — data/elections/{args.id}.json에 추가", file=sys.stderr)
        sys.exit(1)
    EXIT_DIR.mkdir(parents=True, exist_ok=True)
    data = load_existing(args.id)

    kind = spec["kind"]
    office = {"local": "광역단체장", "pres": "대통령", "general": "국회의원"}.get(kind, "")
    any_updated = False
    for src in spec["sources"]:
        wt = fetch_wikitext(src["page"])
        if not wt:
            print(f"  ! {src['page']}: wikitext 비어있음 (스킵)", file=sys.stderr)
            continue
        if kind == "general":
            # 한 페이지에 여러 방송사 row가 있어 → 여러 source 동시 생성
            parsed = parse_wikitable_general_seats(wt)
            if not parsed:
                print(f"  ! {src['page']}: 0건 (스킵)", file=sys.stderr)
                continue
            for skey, block in parsed.items():
                print(f"  {skey}: {len(block['seats'])} 정당 의석 예측 ← {src['page']}", file=sys.stderr)
                upsert_source(data, skey, {
                    "key": skey,
                    "name": block["name"],
                    "released_at": "",
                    "quote_after": "",
                    "office": office,
                    "seats": block["seats"],
                })
                any_updated = True
            continue
        parsed = parse_wikitable_kep(wt)
        if not parsed:
            print(f"  ! {src['page']}: 0건 (스킵)", file=sys.stderr)
            continue
        print(f"  {src['key']}: {len(parsed)} 권역 ← {src['page']}", file=sys.stderr)
        upsert_source(data, src["key"], {
            "key": src["key"],
            "name": src["name"],
            "released_at": "",
            "quote_after": "",
            "office": office,
            "results": parsed,
        })
        any_updated = True
    if not any_updated:
        print("결과 0 — page name·구조 확인", file=sys.stderr)
        sys.exit(2)
    out_path = EXIT_DIR / f"{args.id}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {out_path.name}")


if __name__ == "__main__":
    main()
