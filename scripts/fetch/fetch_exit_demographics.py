#!/usr/bin/env python3
"""한국어 위키백과 대선 문서의 '방송3사 심층 출구조사' 성×연령 표 → JSON.

위키백과 회차 문서 본문에 KBS·MBC·SBS 공동(KEP) 심층 출구조사가 wikitable로 정리돼 있다:
  헤더 = 인구 그룹 | 이재명 | 김문수 | 이준석
  섹션(! colspan="4" |...) = 이념 / 2022년 대선 투표 / 성별 / 연령 / 연령과 성별 / ...
  행 = |라벨  + 후보별 |style=...background-color..| 수치(승자 '''볼드''').
이 도구는 성별·연령·연령과성별(성×연령 그리드) 섹션을 뽑아, 폴/투표율 추출기와 동일한
형태로 출력(레이어 통합 viz용).

출력: data/exit_polls/demographics_<id>.json
  { "_meta":{...},
    "성별": {남성:[{name,party,pct}], 여성:[...]},
    "연령": {"18-29":[...], "30":[...], ...},
    "성연령": {"남성":{"18-29":[...],...}, "여성":{...}} }

사용: python3 scripts/fetch/fetch_exit_demographics.py 21st-pres-2025
"""
from __future__ import annotations
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXIT_DIR = ROOT / "data" / "exit_polls"
# 회차 → 위키 소스. lang(ko/en)·문서·후보(컬럼 순서·정당)·header(표 탐지용 헤더 토큰).
#   21대=한국위키 '심층 출구조사', 20대=영문위키 'Age by gender'(한국위키엔 없음, 나무위키와 교차검증 일치).
ELECTIONS = {
    "21st-pres-2025": {
        "lang": "ko", "page": "대한민국 제21대 대통령 선거",
        "cands": [("이재명", "더불어민주당"), ("김문수", "국민의힘"), ("이준석", "개혁신당")],
        "header": ["이재명", "김문수", "이준석"],
    },
    "20th-pres-2022": {
        "lang": "en", "page": "2022 South Korean presidential election",
        "cands": [("이재명", "더불어민주당"), ("윤석열", "국민의힘")],   # 표 컬럼 순서: Lee, Yoon
        "header": ["Lee", "Yoon"],
    },
}

AGE_MAP = {  # 위키 라벨(한/영) → 폴 정렬 띠. en-dash·하이픈·공백 정규화 후 매칭.
    "18~29세": "18-29", "18-29세": "18-29", "20대": "18-29", "18-29 years old": "18-29",
    "30~39세": "30", "30-39세": "30", "30대": "30", "30-39 years old": "30",
    "40~49세": "40", "40대": "40", "40-49 years old": "40",
    "50~59세": "50", "50대": "50", "50-59 years old": "50",
    "60~69세": "60", "60대": "60", "60-69 years old": "60",
    "70세 이상": "70+", "70대 이상": "70+", "70대+": "70+",
    "70 and older": "70+", "70 or older": "70+", "70+ years old": "70+",
}


def wikitext(page: str, lang: str = "ko") -> str:
    api = f"https://{lang}.wikipedia.org/w/api.php"
    params = {"action": "parse", "page": page, "prop": "wikitext",
              "format": "json", "formatversion": "2"}
    req = urllib.request.Request(api + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": "polis/1.0 (election data)"})
    return json.load(urllib.request.urlopen(req, timeout=40))["parse"]["wikitext"]


def find_table(wt: str, header) -> str | None:
    """헤더 토큰이 모이고 성연령(연령과 성별/Age by gender) 행이 있는 wikitable."""
    for m in re.finditer(r"\{\|[^\n]*wikitable.*?\n\|\}", wt, re.S):
        tbl = m.group(0)
        if sum(n in tbl[:600] for n in header) >= len(header) - 1 \
                and ("연령" in tbl or "Age by gender" in tbl):
            return tbl
    return None


def cell_nums(chunk: str, n: int):
    """행 chunk에서 후보 n명 수치 추출(배경색 셀, 승자 볼드 무관)."""
    vals = re.findall(r"background-color:[^|]*\|\s*'*([\d.]+)'*", chunk)
    return [float(v) for v in vals[:n]] if len(vals) >= n else None


def _gender(label: str):
    """라벨에서 성별 — 한(남/여) 영(men/women/Male/Female). 없으면 None."""
    if re.search(r"(남성|남자)\b|\bmen\b|\bMale\b", label):
        return "남성"
    if re.search(r"(여성|여자)\b|\bwomen\b|\bFemale\b", label):
        return "여성"
    return None


def _age(label: str):
    """라벨 → 폴 띠. 성별 접미 제거 + en-dash/공백 정규화."""
    s = re.sub(r"\s*(남성|남자|여성|여자|men|women)\s*$", "", label).strip()
    s2 = s.replace("–", "-").replace("—", "-")        # en/em-dash → hyphen
    return AGE_MAP.get(s) or AGE_MAP.get(s2) or AGE_MAP.get(s2.replace(" ", "")) \
        or AGE_MAP.get(s.replace(" ", ""))


def parse(tbl: str, cands):
    names = [c[0] for c in cands]
    party = dict(cands)
    N = len(cands)

    def row(pcts):
        return [{"name": names[i], "party": party[names[i]], "pct": pcts[i]} for i in range(N)]

    out = {"성별": {}, "연령": {}, "성연령": {"남성": {}, "여성": {}}}
    section = None
    for chunk in tbl.split("\n|-"):
        sm = re.search(r'!\s*colspan="\d+"\s*\|\s*([^\n|]+)', chunk)
        if sm:
            section = sm.group(1).strip()
        lm = re.search(r"^\|\s*([^|\n!][^\n|]*?)\s*$", chunk, re.M)
        if not lm:
            continue
        label = lm.group(1).strip()
        pcts = cell_nums(chunk, N)
        if not pcts:
            continue
        is_grid = bool(section) and (("연령" in section and "성별" in section) or "Age by gender" in section)
        is_age = bool(section) and section in ("연령", "연령별", "Age") and not is_grid
        is_sex = bool(section) and section in ("성별", "Gender")
        g, a = _gender(label), _age(label)
        # 성×연령 그리드 ("18~29세 남성" / "18–29 years old men")
        if is_grid and g and a:
            out["성연령"][g][a] = row(pcts)
        # 연령 (전체)
        elif is_age and a and not g:
            out["연령"][a] = row(pcts)
        # 성별 단독 (남/여, 연령 없음)
        elif is_sex and g and not a:
            out["성별"][g] = row(pcts)
    return out


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ELECTIONS:
        print(f"usage: fetch_exit_demographics.py <election_id>\n  등록: {list(ELECTIONS)}", file=sys.stderr)
        sys.exit(2)
    eid = sys.argv[1]
    cfg = ELECTIONS[eid]
    lang = cfg.get("lang", "ko")
    wt = wikitext(cfg["page"], lang)
    tbl = find_table(wt, cfg.get("header") or [c[0] for c in cfg["cands"]])
    if not tbl:
        print("성연령 출구조사 표를 못 찾음", file=sys.stderr)
        sys.exit(1)
    out = parse(tbl, cfg["cands"])
    result = {"_meta": {"election": eid,
                        "source": f"{lang}.wikipedia 방송3사(KEP) 출구조사" + (" — 나무위키 교차검증" if lang == "en" else " 심층"),
                        "page": cfg["page"],
                        "note": "선거당일 출구조사 추정(실제 득표 아님). 연령 띠: 18-29/30/40/50/60/70+"}}
    result.update(out)
    EXIT_DIR.mkdir(parents=True, exist_ok=True)
    dst = EXIT_DIR / f"demographics_{eid.split('-')[0].replace('st','').replace('th','').replace('nd','').replace('rd','')}pres.json"
    dst.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    g = out["성연령"]["남성"]
    print(f"{eid} → {dst.name}")
    print(f"  성별: {list(out['성별'])} | 연령: {list(out['연령'])} | 성연령 남:{list(g)} 여:{list(out['성연령']['여성'])}")
    if g.get("18-29"):
        print("  검증 18-29 남성:", {c['name']: c['pct'] for c in g['18-29']})
        print("  검증 18-29 여성:", {c['name']: c['pct'] for c in out['성연령']['여성'].get('18-29', [])})


if __name__ == "__main__":
    main()
