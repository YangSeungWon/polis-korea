#!/usr/bin/env python3
"""대선 전국 여론조사 PDF의 '권역별 후보지지도' cross-tab → 시도별 행 추출.

대선 NESDC 등록조사는 대부분 전국 단위라 aggregated에 시도 행이 거의 없다(19대=충북뿐).
하지만 전국 조사의 통계표 PDF엔 후보지지도가 권역(서울/경기·인천/충청/호남/대구·경북/
부산·울산·경남/강원·제주)별로 cross-tab돼 있다. 그 권역 행을 뽑아 시도로 확장(권역 값을
구성 시도에 동일 배분)해, 지역 지도를 권역 해상도로 채운다. best-effort(표준 NESDC 통계표 형식).

형식(예 3782 page 5):
  3. 제19대 대통령 후보지지도
   ... 문재인 안철수 홍준표 심상정 유승민 없음 기타 없음/기타  (열=후보)
   서 울   526 405 42.1 19.4 18.1 11.0 5.9 1.4 2.1 3.5            (행=권역; 정수=사례수·소수=%)
규칙: 권역 행 = 시도 키워드로 시작 + 충분한 숫자. 후보 pct = 소수 토큰 중 앞 N개(헤더 후보 순).

출력: data/raw/parsed/pres_region_<id>.json = { ntt_id: [{sido, candidates:[{name,party,pct}]}] }
build_polls_pres.py가 읽어 per-sido 행 emit.
"""
from __future__ import annotations
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cid_decode import build_cid_table  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW_PDF = ROOT / "data/raw/pdf"
PARSED = ROOT / "data/raw/parsed"

# 권역 라벨 토큰 → 시도 canonical (권역 값을 구성 시도 전부에 동일 배분)
TOK_SIDO = {
    "서울": ["서울특별시"], "인천": ["인천광역시"], "경기": ["경기도"],
    "수도권": ["서울특별시", "인천광역시", "경기도"],
    "충청": ["충청북도", "충청남도", "대전광역시", "세종특별자치시"],
    "충북": ["충청북도"], "충남": ["충청남도"], "대전": ["대전광역시"], "세종": ["세종특별자치시"],
    "호남": ["광주광역시", "전라남도", "전북특별자치도"],
    "광주": ["광주광역시"], "전라": ["전라남도", "전북특별자치도"],
    "전남": ["전라남도"], "전북": ["전북특별자치도"],
    "대구": ["대구광역시"], "경북": ["경상북도"], "tk": ["대구광역시", "경상북도"],
    "부산": ["부산광역시"], "울산": ["울산광역시"], "경남": ["경상남도"],
    "강원": ["강원특별자치도"], "제주": ["제주특별자치도"],
    "영남": ["대구광역시", "경상북도", "부산광역시", "울산광역시", "경상남도"],
}
# 권역 라벨로 인정할 토큰(이걸로 시작해야 권역 행). 다른 cross-tab 행(직업·연령) 배제.
REGION_HEAD = set(TOK_SIDO)
PAGE_CAP = 22   # 후보지지도 cross-tab는 통계표 앞쪽 — 미스 PDF 전량 스캔 방지(속도)

_CID_RE = re.compile(r"\(cid:(\d+)\)")
_CID_TABLE = None


def decode(s: str) -> str:
    global _CID_TABLE
    if "(cid:" not in s:
        return s
    if _CID_TABLE is None:
        _CID_TABLE = build_cid_table()
    return _CID_RE.sub(lambda m: _CID_TABLE.get(int(m.group(1)), ""), s)


def region_sidos(label: str) -> list[str]:
    """권역 라벨 → 시도 리스트. 인식 토큰들의 합집합(순서·중복 제거)."""
    lab = label.replace(" ", "")
    out = OrderedDict()
    # 긴 토큰 우선(충청 before 충) 위해 길이 내림차순
    rest = lab
    for tok in sorted(TOK_SIDO, key=len, reverse=True):
        if tok in rest:
            for s in TOK_SIDO[tok]:
                out[s] = 1
            rest = rest.replace(tok, " ")
    return list(out)


def find_crosstab_page(doc, cand_names: list[str]):
    """후보 이름들이 한 줄(열 헤더)에 모이고 권역 행이 있는 페이지."""
    need = [c for c in cand_names if c][:5]
    for pg in doc.pages[:PAGE_CAP]:
        t = decode(pg.extract_text() or "")
        lines = t.split("\n")
        # 헤더: 후보 ≥2명이 같은 줄
        hdr_idx = next((i for i, ln in enumerate(lines[:12])
                        if sum(c in ln for c in need) >= max(2, len(need) - 1)), None)
        if hdr_idx is None:
            continue
        # 권역 행 존재?
        if any(any(ln.replace(" ", "").startswith(tok) for tok in REGION_HEAD)
               and len(re.findall(r"\d+\.\d", ln)) >= 2 for ln in lines):
            return lines, hdr_idx
    return None, None


def candidate_order(header_line: str, cand_names: list[str]) -> list[str]:
    """헤더 줄에서 후보 등장 위치순으로 컬럼 순서 결정."""
    pos = [(header_line.find(c), c) for c in cand_names if c and c in header_line]
    return [c for _, c in sorted(pos)]


def parse_pdf(pdf_path: Path, cands: list[dict]):
    names = [c.get("name") for c in cands if c.get("name")]
    party = {c.get("name"): c.get("party", "") for c in cands}
    try:
        with pdfplumber.open(pdf_path) as doc:
            lines, hdr_idx = find_crosstab_page(doc, names)
    except Exception:
        return None
    if not lines:
        return None
    order = candidate_order(lines[hdr_idx], names)
    if len(order) < 2:
        return None
    N = len(order)
    by_sido: dict[str, dict] = {}
    for ln in lines:
        lab_raw = ln.replace(" ", "")
        if not any(lab_raw.startswith(tok) for tok in REGION_HEAD):
            continue
        floats = re.findall(r"\d+\.\d+", ln)
        if len(floats) < N:
            continue
        # 라벨 = 첫 숫자 전까지
        m = re.match(r"^([^\d]+)", ln)
        label = (m.group(1) if m else "").strip()
        sidos = region_sidos(label)
        if not sidos:
            continue
        pcts = [float(x) for x in floats[:N]]
        cand_rows = [{"name": order[i], "party": party.get(order[i], ""), "pct": pcts[i]}
                     for i in range(N)]
        for sido in sidos:
            by_sido[sido] = {"sido": sido, "candidates": cand_rows}  # 마지막 권역 우선(중복 시도 없음)
    return list(by_sido.values()) or None


def main():
    if len(sys.argv) < 2:
        print("usage: extract_pres_region.py <election_id>  (예: 19th-pres-2017)", file=sys.stderr)
        sys.exit(2)
    eid = sys.argv[1]
    short = eid.split("-")[0].replace("th", "").replace("st", "").replace("nd", "").replace("rd", "")
    csv_path = ROOT / f"data/raw/nesdc_{short}pres_polls.csv"
    import csv
    meta = {}
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            meta[row["ntt_id"]] = row
    # ntt → parsed 후보지지 candidates — meta(이 회차)에 있는 ntt 파일만 로드(전량 스캔 회피)
    parsed_cand = {}
    meta_ids = set(meta)
    for p in PARSED.glob("*.json"):
        if p.name.split("_")[0] not in meta_ids:
            continue
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        ntt = str(d.get("ntt_id") or p.name.split("_")[0])
        for q in d.get("questions", []):
            if q.get("election_office") == "후보지지" and (q.get("candidates") or []):
                if ntt not in parsed_cand or len(q["candidates"]) > len(parsed_cand[ntt][1]):
                    parsed_cand[ntt] = (p, q["candidates"])

    # 캐시: PDF 파일명 → rows(list) 또는 None. PDF는 파일명당 불변이라 안전. run 간 재사용.
    cache_path = PARSED / ".pres_region_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    out = {}
    nat = ok = 0
    todo = [(ntt, m) for ntt, m in meta.items()
            if not ((m.get("region") or m.get("survey_region") or "").strip()
                    and not (m.get("region") or m.get("survey_region") or "").startswith("전국"))
            and ntt in parsed_cand]
    print(f"전국 조사 후보지지 parsed {len(todo)}건 — PDF 권역 스캔 시작...", flush=True)
    for i, (ntt, m) in enumerate(todo):
        nat += 1
        pdf_name = parsed_cand[ntt][0].name[:-5]  # .json 떼면 PDF stem
        if pdf_name in cache:
            rows = cache[pdf_name]
        else:
            pdfs = list(RAW_PDF.glob(pdf_name + ".*"))
            rows = parse_pdf(pdfs[0], parsed_cand[ntt][1]) if pdfs else None
            cache[pdf_name] = rows
        if rows:
            out[ntt] = rows
            ok += 1
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(todo)} 처리, 추출 {ok}건", flush=True)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False))
    cache_path.write_text(json.dumps(cache, ensure_ascii=False))
    dst = PARSED / f"pres_region_{short}pres.json"
    dst.write_text(json.dumps(out, ensure_ascii=False))
    print(f"{eid}: 전국조사 {nat}건 중 권역 cross-tab 추출 {ok}건 → {dst.name}")
    # 커버리지 요약
    sidos = {s for rows in out.values() for r in rows for s in [r["sido"]]}
    print(f"  채워진 시도: {len(sidos)} — {sorted(sidos)}")


if __name__ == "__main__":
    main()
