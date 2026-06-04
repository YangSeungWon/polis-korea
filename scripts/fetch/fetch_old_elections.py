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


def parse_general_infobox(wt: str) -> tuple[list[dict], dict]:
    """총선 infobox → 정당별 nation 합산 (의석·득표·득표율) + meta(투표율·총의석)."""
    # 선거 정보 박스 균형 추출
    m = re.search(r"\{\{선거 정보", wt)
    if not m:
        return [], {}
    i = m.start()
    depth = 0
    while i < len(wt):
        if wt[i:i+2] == "{{":
            depth += 1; i += 2
        elif wt[i:i+2] == "}}":
            depth -= 1; i += 2
            if depth == 0:
                break
        else:
            i += 1
    box = wt[m.start():i]
    # 정당별 필드
    parties = []
    for n in range(1, 12):
        m_party = re.search(rf"\|\s*정당{n}\s*=\s*'*\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", box)
        if not m_party:
            continue
        # 정당 alias 우선
        party = (m_party.group(2) or m_party.group(1)).strip()
        party = re.sub(r"\s*\([^)]+\)\s*$", "", party)
        # 의석 키 fallback: 선거후_의석N → 의석N (15대 등 옛 회차)
        m_seats = re.search(rf"\|\s*선거후_의석{n}\s*=\s*'*([\d,]+)\s*석?", box)
        if not m_seats:
            m_seats = re.search(rf"\|\s*의석{n}\s*=\s*'*([\d,]+)\s*석?", box)
        m_votes = re.search(rf"\|\s*득표수{n}\s*=\s*'*([\d,]+)", box)
        m_pct = re.search(rf"\|\s*득표율{n}\s*=\s*'*([\d.]+)\s*%", box)
        parties.append({
            "party": party,
            "name": "",  # 정당 합산이라 후보명 없음
            "seats": int(m_seats.group(1).replace(",", "")) if m_seats else 0,
            "proportional_seats": int(m_seats.group(1).replace(",", "")) if m_seats else 0,
            "votes": int(m_votes.group(1).replace(",", "")) if m_votes else 0,
            "pct": float(m_pct.group(1)) if m_pct else 0.0,
        })
    parties.sort(key=lambda c: -c["seats"])
    for i, c in enumerate(parties, 1):
        c["rank"] = i
    if parties:
        parties[0]["won"] = True
    # 메타
    extras = {}
    m_t = re.search(r"\|\s*투표율\s*=\s*([\d.]+)\s*%", box)
    if m_t:
        extras["turnout_pct"] = float(m_t.group(1))
    m_total = re.search(r"\|\s*선출_의석\s*=\s*'*([\d,]+)\s*석?", box)
    if m_total:
        extras["total_seats"] = int(m_total.group(1).replace(",", ""))
    return parties, extras


def build_general(eid: str, spec: dict) -> dict:
    """총선 — 정당별 nation 합산 (지역구+비례 합산 의석·득표). 13~16대 위키 infobox."""
    wt = fetch_wikitext(spec["page"])
    if not wt:
        raise RuntimeError(f"빈 wikitext: {spec['page']}")
    parties, extras = parse_general_infobox(wt)
    if not parties:
        raise RuntimeError(f"정당 0건: {spec['page']}")
    total_votes = sum(c["votes"] for c in parties)
    # 비례 schema (scope=nation, sg_typecode=7) — 정당 합산 정보 잘 맞음
    nation = {
        "sg_typecode": "7",
        "sido": "",
        "sigungu": "",
        "scope": "nation",
        "electors": 0,
        "voters": total_votes,
        "valid_votes": total_votes,
        "invalid_votes": 0,
        "abstain": 0,
        "candidates": parties,
    }
    if "turnout_pct" in extras:
        nation["turnout_pct"] = extras["turnout_pct"]
    if "total_seats" in extras:
        nation["total_seats"] = extras["total_seats"]
    return {
        "_meta": {
            "election": spec["name"],
            "election_id": eid,
            "election_date": spec["date"],
            "source": "wikipedia-ko-infobox",
            "_note": "옛 총선 — 위키백과 infobox에서 정당별 nation 합산 (지역구+비례 의석 합·득표·득표율). 지역구별 break 없음.",
            "n_rows": 1,
        },
        "races": [nation],
    }


def _extract_box(wt: str) -> str:
    m = re.search(r"\{\{선거 정보", wt)
    if not m:
        return ""
    i = m.start()
    depth = 0
    while i < len(wt):
        if wt[i:i+2] == "{{":
            depth += 1; i += 2
        elif wt[i:i+2] == "}}":
            depth -= 1; i += 2
            if depth == 0:
                break
        else:
            i += 1
    return wt[m.start():i]


def parse_local_infobox(wt: str) -> tuple[list[dict], dict]:
    """지선 infobox → 정당별 4 office (광역단체장·기초단체장·광역의원·기초의원).

    schema 2가지:
    - 2회 형식: 1dataN / 2dataN / 3dataN = '의석<br>득표<br>득표율'
    - 3·4회 형식: 의석N = '<br/>광역단체장 N석<br/>기초단체장 N석<br/>광역의원 N석<br/>기초의원 N석'
    """
    box = _extract_box(wt)
    if not box:
        return [], {}

    parties = []
    # 각 정당 N 시도 1~9 (지선엔 보통 5~7정당)
    for n in range(1, 12):
        m_party = re.search(rf"\|\s*정당{n}\s*=\s*'*\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", box)
        if not m_party:
            continue
        party = (m_party.group(2) or m_party.group(1)).strip()
        party = re.sub(r"\s*\([^)]+\)\s*$", "", party)
        row = {"party": party, "name": "", "seats": 0, "votes": 0, "pct": 0.0}

        # 2회 schema: 1dataN/2dataN/3dataN
        m_1data = re.search(rf"\|\s*1data{n}\s*=\s*([^|]+?)(?=\n\||$)", box)
        if m_1data:
            # 1data = 광역단체장 (의석·득표·득표율)
            txt = m_1data.group(1)
            seats = re.search(r"(\d+)\s*석", txt)
            votes = re.search(r"([\d,]{4,})", txt)
            pct = re.search(r"([\d.]+)\s*%", txt)
            row["seats_sido"] = int(seats.group(1)) if seats else 0
            row["votes_sido"] = int(votes.group(1).replace(",", "")) if votes else 0
            row["pct_sido"] = float(pct.group(1)) if pct else 0.0
            m_2data = re.search(rf"\|\s*2data{n}\s*=\s*([^|]+?)(?=\n\||$)", box)
            if m_2data:
                txt2 = m_2data.group(1)
                s = re.search(r"(\d+)\s*석", txt2); row["seats_sigungu"] = int(s.group(1)) if s else 0
            m_3data = re.search(rf"\|\s*3data{n}\s*=\s*([^|]+?)(?=\n\||$)", box)
            if m_3data:
                txt3 = m_3data.group(1)
                s = re.search(r"(\d+)\s*석", txt3); row["seats_sido_mem"] = int(s.group(1)) if s else 0

        # 3·4회 schema: 의석N = HTML span with 4 office breakdown
        m_seats = re.search(rf"\|\s*의석{n}\s*=\s*'*<span[^>]*>([\s\S]*?)</span>", box)
        if not m_seats:
            m_seats = re.search(rf"\|\s*의석{n}\s*=\s*'*([^|]+?)(?=\n\||$)", box)
        if m_seats:
            block = m_seats.group(1)
            for label, key in [("광역단체장", "seats_sido"), ("기초단체장", "seats_sigungu"),
                               ("광역의원", "seats_sido_mem"), ("기초의원", "seats_sigungu_mem")]:
                m_o = re.search(rf"{label}\s*(\d+)\s*석", block)
                if m_o and key not in row:
                    row[key] = int(m_o.group(1))

        # 단순 seats 키워드 (총합)
        row["seats"] = row.get("seats_sido", 0) + row.get("seats_sigungu", 0)
        parties.append(row)

    # 메타
    extras = {}
    m_t = re.search(r"\|\s*투표율\s*=\s*([\d.]+)\s*%", box)
    if m_t:
        extras["turnout_pct"] = float(m_t.group(1))
    return parties, extras


SIDOS_15 = [
    "서울특별시", "인천광역시", "경기도", "강원도", "대전광역시", "충청남도",
    "충청북도", "광주광역시", "전라남도", "전라북도", "부산광역시",
    "경상남도", "대구광역시", "경상북도", "제주도",
]


def parse_local_body_v1(wt: str) -> list[dict]:
    """1회 지선 (1995) — article body wikitable parse.

    schema 4가지 sub-section:
    - 광역단체장: 15 시도 sub-section 각각 first wikitable (순위·후보·정당·득표)
    - 기초단체장: 첫 wikitable (정당 / 당선자 수)
    - 광역의원: 첫 wikitable (정당 / 지역구 / 비례 / 합계)
    - 기초의원: 정당공천 X — 무소속 4541명 (단순 카운트)
    """
    races = []

    # 광역단체장 — 15 시도 sub-section. 각 1위 후보 추출 → sido scope race들
    sido_start = wt.find("=== 광역단체장 ===", wt.find("== 선거 결과 =="))
    sigungu_start = wt.find("=== 기초단체장 ===", sido_start)
    sido_block = wt[sido_start:sigungu_start] if sido_start > 0 and sigungu_start > sido_start else ""

    for sido in SIDOS_15:
        # subsection 위치
        idx = sido_block.find(f"===== {sido} =====")
        if idx < 0:
            continue
        # 다음 ===== 까지
        next_idx = sido_block.find("=====", idx + 15)
        sub = sido_block[idx:next_idx if next_idx > 0 else idx + 5000]
        # 첫 wikitable
        m_tab = re.search(r"\{\|[\s\S]*?\|\}", sub)
        if not m_tab:
            continue
        table = m_tab.group(0)
        # 행 단위 — '|-' split, 후보 row만 (4 셀 이상 + name·party·votes 있음)
        cands = []
        for rowtext in re.split(r"\n\|-", table):
            # 4셀 이상 (순위·기호·후보·정당·득표수·득표율·비고)
            if rowtext.count("||") < 4:
                continue
            # 첫 [[name]] · 두 번째 [[party|alias]]
            links = re.findall(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", rowtext)
            if len(links) < 2:
                continue
            name_target, name_alias = links[0]
            party_target, party_alias = links[1]
            # 득표수 — 첫 콤마 포함 큰 숫자
            m_v = re.search(r"\|\s*([\d,]{4,})\s*\|", rowtext)
            # 득표율 — N.N%
            m_p = re.search(r"([\d.]+)\s*%", rowtext)
            if not m_v or not m_p:
                continue
            name = (name_alias or name_target).strip()
            party = (party_alias or party_target).strip()
            party = re.sub(r"\s*\([^)]+\)\s*$", "", party)
            cands.append({
                "name": name,
                "party": party,
                "votes": int(m_v.group(1).replace(",", "")),
                "pct": float(m_p.group(1)),
            })
        if not cands:
            continue
        cands.sort(key=lambda c: -c["votes"])
        for i, c in enumerate(cands, 1):
            c["rank"] = i
        cands[0]["won"] = True
        total_v = sum(c["votes"] for c in cands)
        # 투표율 — '투표율 | 66.18%'
        m_t = re.search(r"투표율\s*\|\s*([\d.]+)\s*%", table)
        race = {
            "sg_typecode": "3",
            "sido": sido,
            "sigungu": "",
            "scope": "sido",
            "electors": 0,
            "voters": total_v,
            "valid_votes": total_v,
            "invalid_votes": 0,
            "abstain": 0,
            "candidates": cands,
        }
        if m_t:
            race["turnout_pct"] = float(m_t.group(1))
        races.append(race)

    # 기초단체장 — 정당별 nation 합산
    sigungu_end = wt.find("=== 광역의원 ===", sigungu_start)
    sigungu_block = wt[sigungu_start:sigungu_end] if sigungu_start > 0 and sigungu_end > sigungu_start else ""
    m_t = re.search(r"\{\|[\s\S]*?\|\}", sigungu_block)
    if m_t:
        rows = re.findall(r"\|\s*\[\[([^\]|]+)(?:\|([^\]]+))?\]\]\s*\n\|\s*(\d+)", m_t.group(0))
        cands = []
        for tg, al, n in rows:
            party = (al or tg).strip()
            party = re.sub(r"\s*\([^)]+\)\s*$", "", party)
            cands.append({"name": "", "party": party, "seats": int(n), "proportional_seats": int(n), "votes": 0, "pct": 0.0})
        cands.sort(key=lambda c: -c["seats"])
        for i, c in enumerate(cands, 1):
            c["rank"] = i
        if cands:
            cands[0]["won"] = True
            races.append({
                "sg_typecode": "4", "sido": "", "sigungu": "", "scope": "nation",
                "electors": 0, "voters": 0, "valid_votes": 0, "invalid_votes": 0, "abstain": 0,
                "candidates": cands,
            })

    # 광역의원 — 정당별 지역구·비례·합계
    member_start = wt.find("=== 광역의원 ===", sigungu_start)
    member_end = wt.find("=== 기초의원 ===", member_start)
    member_block = wt[member_start:member_end] if member_start > 0 and member_end > member_start else ""
    m_t = re.search(r"\{\|[\s\S]*?\|\}", member_block)
    if m_t:
        # 정당 / 지역구 / 비례 / 합계 행
        rows = re.findall(
            r"\|\s*\[\[([^\]|]+)(?:\|([^\]]+))?\]\]\s*\n\|\s*([\d-]+)\s*\n\|\s*([\d-]+)\s*\n\|\s*(\d+)",
            m_t.group(0),
        )
        cands = []
        for tg, al, dist, prop, total in rows:
            party = (al or tg).strip()
            party = re.sub(r"\s*\([^)]+\)\s*$", "", party)
            total_n = int(total)
            cands.append({
                "name": "", "party": party,
                "seats": total_n, "proportional_seats": total_n,
                "district_seats": int(dist) if dist.isdigit() else 0,
                "votes": 0, "pct": 0.0,
            })
        cands.sort(key=lambda c: -c["seats"])
        for i, c in enumerate(cands, 1):
            c["rank"] = i
        if cands:
            cands[0]["won"] = True
            races.append({
                "sg_typecode": "5", "sido": "", "sigungu": "", "scope": "nation",
                "electors": 0, "voters": 0, "valid_votes": 0, "invalid_votes": 0, "abstain": 0,
                "candidates": cands,
            })

    return races


def build_local(eid: str, spec: dict) -> dict:
    """지선 — office별 nation 합산 (정당별 의석).

    - 1회 (1995): article body wikitable (시도지사 15개 + 기초·광역의원 합산)
    - 2·3·4회: infobox parser
    """
    wt = fetch_wikitext(spec["page"])
    if not wt:
        raise RuntimeError(f"빈 wikitext: {spec['page']}")

    # 1회 — body parser
    if eid == "1st-local-1995":
        races = parse_local_body_v1(wt)
        if not races:
            raise RuntimeError(f"1회 race 0건: {spec['page']}")
        return {
            "_meta": {
                "election": spec["name"],
                "election_id": eid,
                "election_date": spec["date"],
                "source": "wikipedia-ko-body",
                "_note": "1회 지선 — 위키백과 article body wikitable에서 광역단체장 (15 시도 1위) + 기초단체장 (정당 합산) + 광역의원 (정당 합산). 기초의원은 정당공천 X.",
                "n_rows": len(races),
            },
            "races": races,
        }

    # 2·3·4회 — infobox parser (기존)
    parties, extras = parse_local_infobox(wt)
    if not parties:
        raise RuntimeError(f"정당 0건: {spec['page']}")

    # office별로 race 생성 (sido 광역단체장 / sigungu 기초단체장 / 광역의원 / 기초의원)
    races = []
    for office_label, seat_key, sg_tc, scope in [
        ("광역단체장", "seats_sido", "3", "nation"),
        ("기초단체장", "seats_sigungu", "4", "nation"),
        ("광역의원", "seats_sido_mem", "5", "nation"),
        ("기초의원", "seats_sigungu_mem", "6", "nation"),
    ]:
        if not any(p.get(seat_key, 0) for p in parties):
            continue
        cands = []
        for rank, p in enumerate(sorted(parties, key=lambda x: -x.get(seat_key, 0)), 1):
            seats = p.get(seat_key, 0)
            entry = {
                "name": "",
                "party": p["party"],
                "seats": seats,
                "proportional_seats": seats,
                "votes": p.get("votes_sido", 0) if seat_key == "seats_sido" else 0,
                "pct": p.get("pct_sido", 0.0) if seat_key == "seats_sido" else 0.0,
                "rank": rank,
            }
            if rank == 1 and seats > 0:
                entry["won"] = True
            cands.append(entry)
        total_votes = sum(c["votes"] for c in cands)
        races.append({
            "sg_typecode": sg_tc,
            "sido": "",
            "sigungu": "",
            "scope": scope,
            "electors": 0,
            "voters": total_votes,
            "valid_votes": total_votes,
            "invalid_votes": 0,
            "abstain": 0,
            "candidates": cands,
        })
    if extras.get("turnout_pct"):
        for r in races:
            r["turnout_pct"] = extras["turnout_pct"]
    return {
        "_meta": {
            "election": spec["name"],
            "election_id": eid,
            "election_date": spec["date"],
            "source": "wikipedia-ko-infobox",
            "_note": "옛 지선 — 위키백과 infobox에서 office별 (광역·기초·광역의원·기초의원) 정당별 nation 합산. 시도/시군구별 break 없음.",
            "n_rows": len(races),
        },
        "races": races,
    }


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
    ap.add_argument("--kind", default="auto", choices=["auto", "presidential", "general", "local"], help="auto = id로 추론")
    args = ap.parse_args()

    spec = WIKI_PAGES.get(args.id)
    if not spec:
        print(f"ERR: {args.id} mapping 없음 — WIKI_PAGES에 추가", file=sys.stderr)
        sys.exit(1)

    kind = args.kind
    if kind == "auto":
        if "-pres-" in args.id:
            kind = "presidential"
        elif "-general-" in args.id:
            kind = "general"
        elif "-local-" in args.id:
            kind = "local"
        else:
            print(f"ERR: kind 추론 실패 from {args.id}", file=sys.stderr)
            sys.exit(1)

    if kind == "presidential":
        data = build_presidential(args.id, spec)
    elif kind == "general":
        data = build_general(args.id, spec)
    elif kind == "local":
        data = build_local(args.id, spec)
    else:
        print(f"ERR: kind={kind} 미지원", file=sys.stderr); sys.exit(1)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{args.id}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    n = len(data["races"][0]["candidates"])
    label = "후보" if kind == "presidential" else "정당"
    print(f"→ {out_path.relative_to(ROOT)} ({n} {label} · nation race 1)")


if __name__ == "__main__":
    main()
