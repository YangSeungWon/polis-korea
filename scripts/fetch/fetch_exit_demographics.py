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
WIKI_API = "https://ko.wikipedia.org/w/api.php"

# 회차 → (위키 문서, 후보 순서·정당). 표 헤더 후보 순서와 일치해야 함.
ELECTIONS = {
    "21st-pres-2025": {
        "page": "대한민국 제21대 대통령 선거",
        "cands": [("이재명", "더불어민주당"), ("김문수", "국민의힘"), ("이준석", "개혁신당")],
    },
}

AGE_MAP = {  # 위키 라벨 → 폴 정렬 띠
    "18~29세": "18-29", "18-29세": "18-29", "20대": "18-29",
    "30~39세": "30", "30-39세": "30", "30대": "30",
    "40~49세": "40", "40대": "40", "50~59세": "50", "50대": "50",
    "60~69세": "60", "60대": "60", "70세 이상": "70+", "70대 이상": "70+", "70대+": "70+",
}


def wikitext(page: str) -> str:
    params = {"action": "parse", "page": page, "prop": "wikitext",
              "format": "json", "formatversion": "2"}
    req = urllib.request.Request(WIKI_API + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": "polis/1.0 (election data)"})
    return json.load(urllib.request.urlopen(req, timeout=40))["parse"]["wikitext"]


def find_table(wt: str, cands) -> str | None:
    """후보 3명이 헤더에 모인 심층 출구조사 wikitable 본문."""
    names = [c[0] for c in cands]
    for m in re.finditer(r"\{\|[^\n]*wikitable.*?\n\|\}", wt, re.S):
        tbl = m.group(0)
        head = tbl[:400]
        if sum(n in head for n in names) >= len(names) - 1 and "연령" in tbl:
            return tbl
    return None


def cell_nums(chunk: str, n: int):
    """행 chunk에서 후보 n명 수치 추출(배경색 셀, 승자 볼드 무관)."""
    vals = re.findall(r"background-color:[^|]*\|\s*'*([\d.]+)'*", chunk)
    return [float(v) for v in vals[:n]] if len(vals) >= n else None


def parse(tbl: str, cands):
    names = [c[0] for c in cands]
    party = dict(cands)
    N = len(cands)

    def row(pcts):
        return [{"name": names[i], "party": party[names[i]], "pct": pcts[i]} for i in range(N)]

    out = {"성별": {}, "연령": {}, "성연령": {"남성": {}, "여성": {}}}
    section = None
    for chunk in tbl.split("\n|-"):
        # 섹션 헤더
        sm = re.search(r'!\s*colspan="\d+"\s*\|\s*([^\n|]+)', chunk)
        if sm:
            section = sm.group(1).strip()
        # 라벨 = 첫 데이터 셀(style 없는 |텍스트)
        lm = re.search(r"^\|\s*([^|\n!][^\n|]*?)\s*$", chunk, re.M)
        if not lm:
            continue
        label = lm.group(1).strip()
        pcts = cell_nums(chunk, N)
        if not pcts:
            continue
        # 성별 (남성/여성 단독)
        if section in ("성별",) and re.fullmatch(r"(남성|남자|여성|여자)", label):
            out["성별"]["남성" if label[0] == "남" else "여성"] = row(pcts)
            continue
        # 연령 (전체)
        if section in ("연령", "연령별"):
            age = AGE_MAP.get(label) or AGE_MAP.get(label.replace(" ", ""))
            if age:
                out["연령"][age] = row(pcts)
            continue
        # 연령과 성별 (성×연령 그리드): "18~29세 남성"
        if section and ("연령" in section and "성별" in section):
            gm = re.search(r"(남성|남자|여성|여자)", label)
            agelab = re.sub(r"\s*(남성|남자|여성|여자)\s*$", "", label).strip()
            age = AGE_MAP.get(agelab) or AGE_MAP.get(agelab.replace(" ", ""))
            if gm and age:
                g = "남성" if gm.group(1)[0] == "남" else "여성"
                out["성연령"][g][age] = row(pcts)
            continue
    return out


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ELECTIONS:
        print(f"usage: fetch_exit_demographics.py <election_id>\n  등록: {list(ELECTIONS)}", file=sys.stderr)
        sys.exit(2)
    eid = sys.argv[1]
    cfg = ELECTIONS[eid]
    wt = wikitext(cfg["page"])
    tbl = find_table(wt, cfg["cands"])
    if not tbl:
        print("심층 출구조사 표를 못 찾음", file=sys.stderr)
        sys.exit(1)
    out = parse(tbl, cfg["cands"])
    result = {"_meta": {"election": eid, "source": "ko.wikipedia 방송3사(KEP) 심층 출구조사",
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
