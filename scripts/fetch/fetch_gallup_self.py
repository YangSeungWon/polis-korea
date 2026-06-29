#!/usr/bin/env python3
"""한국갤럽 '장래 정치 지도자 선호도'(월간 자유응답 차기주자) — gallup.co.kr 자체발표 수집.

배경: 갤럽 장래 지도자 선호도는 **자체조사(자유응답)**라 선거 사이엔 NESDC 미등록 →
gallup.co.kr 데일리 오피니언에만 있다(realmeter 국정평가와 같은 non-NESDC 패턴). NESDC 경유론
선거 국면만 잡혀 2018·19·20·23·24 공백. 이 도구가 그 월간 연속 시계열을 복원한다.

방식: reportContent.asp?seqNo=N (EUC-KR HTML)을 seqNo 역순 순회(페이지네이션 POST 우회).
본문의 '장래 정치 지도자 선호도: 이름 N%, ...' 텍스트 파싱. 증분(index.json 캐시).

⚠️ 자유응답(open-ended) — NESDC 다자대결(강제선택)과 척도 다름. 별도 시리즈로만 쓸 것.

출력: data/polls/gallup_leaders.json = {_meta, records:[{date, n, candidate, party, pct, seqNo}]}
사용: python scripts/fetch/fetch_gallup_self.py [--from SEQ] [--to SEQ] [--max N]
"""
from __future__ import annotations
import argparse
import html as _html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/polls/gallup_leaders.json"
CACHE = ROOT / "data/raw/gallup_self"
URL = "https://www.gallup.co.kr/gallupdb/reportContent.asp?seqNo={n}&bType=8"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

# 자유응답 차기주자 인물 → 정당(색). 시점에 따라 소속 변동 — 가장 알려진/현재로 근사.
NAME_PARTY = {
    "이재명": "더불어민주당", "이낙연": "더불어민주당", "김부겸": "더불어민주당", "정세균": "더불어민주당",
    "김경수": "더불어민주당", "박원순": "더불어민주당", "안희정": "더불어민주당", "추미애": "더불어민주당",
    "김동연": "더불어민주당", "김민석": "더불어민주당", "강훈식": "더불어민주당", "송영길": "더불어민주당",
    "정청래": "더불어민주당", "박찬대": "더불어민주당", "우상호": "더불어민주당", "전재수": "더불어민주당",
    "오거돈": "더불어민주당", "양승조": "더불어민주당", "임종석": "더불어민주당", "박용진": "더불어민주당",
    "윤석열": "국민의힘", "홍준표": "국민의힘", "황교안": "국민의힘", "오세훈": "국민의힘",
    "한동훈": "국민의힘", "원희룡": "국민의힘", "나경원": "국민의힘", "김문수": "국민의힘",
    "안철수": "국민의힘", "유승민": "국민의힘", "장동혁": "국민의힘", "추경호": "국민의힘",
    "이진숙": "국민의힘", "박형준": "국민의힘", "유정복": "국민의힘", "박완수": "국민의힘",
    "이준석": "개혁신당", "심상정": "정의당", "조국": "조국혁신당", "반기문": "무소속", "한덕수": "무소속",
}
# 인물 아님 — 파싱 잡음 차단
_STOP = {"의견", "유보", "이상", "각각", "이외", "인물", "포함", "기타", "순", "약", "전국", "지지층",
         "미만", "여명", "내외", "안팎", "이하", "정도", "명", "이며", "비롯", "다만", "그외", "기록"}

_DATE = re.compile(r"조사기간\s*[:：]?\s*(20\d\d)년\s*(\d+)월\s*(\d+)\s*[~∼-]\s*(\d+)\s*일")
_NHO = re.compile(r"데일리\s*오피니언\s*제\s*(\d+)\s*호")
_LEAD = re.compile(r"장래\s*정치\s*지도자\s*선호도\s*[:：\]]\s*(.+?)(?:의견\s*유보|선다형|자유응답|※|\n)")


def fetch(seqno: int) -> str | None:
    req = urllib.request.Request(URL.format(n=seqno), headers={"User-Agent": UA})
    try:
        raw = urllib.request.urlopen(req, timeout=30).read()
    except Exception:
        return None
    return raw.decode("euc-kr", errors="ignore")


def parse(htmltext: str, seqno: int):
    """리포트 HTML → (period_end, 호, [(name, pct)]) 또는 None."""
    txt = _html.unescape(re.sub(r"<[^>]+>", " ", htmltext))
    txt = txt.replace("·", "·").replace("·", "·")
    txt = re.sub(r"\s+", " ", txt)
    m = _LEAD.search(txt)
    if not m:
        return None
    body = m.group(1)
    rows = []
    for g in re.finditer(r"([가-힣·]+(?:\s+[가-힣]+)??)\s*\(?(\d+)\s*%\)?", body):
        names = re.split(r"[·,]", g.group(1))
        pct = int(g.group(2))
        for nm in names:
            nm = re.sub(r"\s.*$", "", nm.strip())   # '오세훈 서울시장' → '오세훈'
            if 2 <= len(nm) <= 4 and nm not in _STOP:
                rows.append((nm, pct))
    if not rows:
        return None
    dm = _DATE.search(txt)
    if dm:
        y, mo, _, d2 = dm.groups()
        period_end = f"{y}-{int(mo):02d}-{int(d2):02d}"
    else:
        period_end = None
    nho = _NHO.search(txt)
    return period_end, (int(nho.group(1)) if nho else None), rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", type=int, default=1645)
    ap.add_argument("--to", dest="to", type=int, default=1400)
    ap.add_argument("--max", type=int, default=300)
    ap.add_argument("--sleep", type=float, default=0.4)
    args = ap.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    idx_path = CACHE / "index.json"
    idx = json.loads(idx_path.read_text()) if idx_path.exists() else {}

    found, scanned = 0, 0
    for seq in range(args.frm, args.to - 1, -1):
        if scanned >= args.max:
            break
        key = str(seq)
        if key in idx:
            if idx[key]:
                found += 1
            continue
        scanned += 1
        h = fetch(seq)
        time.sleep(args.sleep)
        res = parse(h, seq) if h else None
        if res:
            period_end, nho, rows = res
            idx[key] = {"period_end": period_end, "ho": nho, "rows": rows}
            found += 1
            print(f"  seq {seq} 제{nho}호 {period_end}: {len(rows)}명 ({rows[0][0]} {rows[0][1]}%…)", flush=True)
        else:
            idx[key] = None
        if scanned % 25 == 0:
            idx_path.write_text(json.dumps(idx, ensure_ascii=False))
            print(f"  …{scanned} 스캔, {found} 장래지도자", flush=True)
    idx_path.write_text(json.dumps(idx, ensure_ascii=False))

    # index → records 빌드(날짜 있는 것만)
    records = []
    for seq, v in idx.items():
        if not v or not v.get("period_end"):
            continue
        for nm, pct in v["rows"]:
            if nm in _STOP:           # 캐시 재빌드 시에도 잡음 재차단
                continue
            records.append({"date": v["period_end"], "ho": v.get("ho"), "candidate": nm,
                            "party": NAME_PARTY.get(nm, ""), "pct": pct, "seqNo": int(seq)})
    records.sort(key=lambda r: (r["date"], -r["pct"]))
    out = {"_meta": {"source": "gallup.co.kr 데일리 오피니언 '장래 정치 지도자 선호도'(자유응답)",
                     "kind": "gallup_leaders_open", "agency": "한국갤럽조사연구소",
                     "note": "자유응답(open-ended) — NESDC 다자대결과 척도 다름. 별도 시리즈."},
           "records": records}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    months = sorted(set(r["date"] for r in records))
    print(f"→ {OUT.name}: {len(records)}건, {len(months)}개월 ({months[0] if months else '?'}~{months[-1] if months else '?'})")


if __name__ == "__main__":
    main()
