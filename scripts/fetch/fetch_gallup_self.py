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
PARTY_OUT = ROOT / "data/polls/aggregated_gallup.json"   # 갤럽 정당지지(트래커 소스)
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


# 정당지지 산문 파싱용 — 당명(정식명, partyColor 캐노니컬).
_P_NAMES = (r"더불어민주당|국민의힘|조국혁신당|개혁신당|진보당|정의당|기본소득당|사회민주당|"
            r"기본소득당|새로운미래|이외 ?정당/?단체")
_PARTY_BODY = re.compile(r"지지하는 정당은[^)]*\)\s*(.+?무당.{0,4}층\s*\d+%)")
_PARTY_BODY2 = re.compile(r"정당\s*지지도[:\]]\s*(.+?무당.{0,4}층\s*\d+%)")


def parse_leaders(body: str):
    rows = []
    for g in re.finditer(r"([가-힣·]+(?:\s+[가-힣]+)??)\s*\(?(\d+)\s*%\)?", body):
        pct = int(g.group(2))
        for nm in re.split(r"[·,]", g.group(1)):
            nm = re.sub(r"\s.*$", "", nm.strip())
            if 2 <= len(nm) <= 4 and nm not in _STOP:
                rows.append((nm, pct))
    return rows


def parse_party(txt: str):
    """'…더불어민주당 41%, 국민의힘 29%, 조국·개혁·진보 각각 2%, 무당층 21%' → {정당:pct}."""
    m = _PARTY_BODY.search(txt) or _PARTY_BODY2.search(txt)
    if not m:
        return {}
    body = m.group(1)
    out = {}
    for g in re.finditer(r"((?:(?:" + _P_NAMES + r")[,\s]*)+)(?:각각\s*)?(\d{1,2}(?:\.\d)?)%", body):
        pct = float(g.group(2))
        for nm in re.findall(_P_NAMES, g.group(1)):
            out[nm.replace(" ", "")] = pct
    mu = re.search(r"무당.{0,4}층\s*(\d{1,2})%", body)
    if mu:
        out["없음"] = float(mu.group(1))   # 무당층 → 트래커 NON_PARTY '없음'
    # 합≈100 검증(오파싱 배제)
    s = sum(out.values())
    return out if 90 <= s <= 112 and "더불어민주당" in out and "국민의힘" in out else {}


def parse(htmltext: str, seqno: int):
    """리포트 HTML → {period_end, ho, leaders:[(name,pct)], party:{정당:pct}} 또는 None."""
    txt = _html.unescape(re.sub(r"<[^>]+>", " ", htmltext))
    txt = re.sub(r"\s+", " ", txt)
    lm = _LEAD.search(txt)
    leaders = parse_leaders(lm.group(1)) if lm else []
    party = parse_party(txt)
    if not leaders and not party:
        return None
    dm = _DATE.search(txt)
    period_end = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(4)):02d}" if dm else None
    nho = _NHO.search(txt)
    return {"period_end": period_end, "ho": (int(nho.group(1)) if nho else None),
            "leaders": leaders, "party": party}


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

    def stale(e):   # None(옛 캐시) 또는 party 키 없는 dict → 재fetch(정당지지 1회 백필)
        return e is None or (isinstance(e, dict) and "party" not in e)

    scanned = 0
    for seq in range(args.frm, args.to - 1, -1):
        if scanned >= args.max:
            break
        key = str(seq)
        if key in idx and not stale(idx[key]):
            continue
        scanned += 1
        h = fetch(seq)
        time.sleep(args.sleep)
        res = parse(h, seq) if h else None
        # sentinel: 빈 결과도 party 키 든 dict로 저장 → 다음 run에서 재fetch 안 함(None은 fetch 실패만)
        idx[key] = res if res else ({"period_end": None, "ho": None, "leaders": [], "party": {}} if h else None)
        if res:
            p = res.get("party") or {}
            ld = res.get("leaders") or []
            print(f"  seq {seq} 제{res.get('ho')}호 {res.get('period_end')}: "
                  f"장래{len(ld)} · 정당{'민주%s/국힘%s' % (p.get('더불어민주당','-'), p.get('국민의힘','-')) if p else '-'}", flush=True)
        if scanned % 25 == 0:
            idx_path.write_text(json.dumps(idx, ensure_ascii=False))
            print(f"  …{scanned} 스캔", flush=True)
    idx_path.write_text(json.dumps(idx, ensure_ascii=False))

    # ① 장래지도자(자유응답) → gallup_leaders.json
    lrecs = []
    for seq, v in idx.items():
        if not v or not v.get("period_end"):
            continue
        for nm, pct in (v.get("leaders") or v.get("rows") or []):
            if nm not in _STOP:
                lrecs.append({"date": v["period_end"], "ho": v.get("ho"), "candidate": nm,
                              "party": NAME_PARTY.get(nm, ""), "pct": pct, "seqNo": int(seq)})
    lrecs.sort(key=lambda r: (r["date"], -r["pct"]))
    OUT.write_text(json.dumps({"_meta": {"source": "gallup.co.kr 데일리 오피니언 '장래 정치 지도자 선호도'(자유응답)",
                   "kind": "gallup_leaders_open", "agency": "한국갤럽조사연구소",
                   "note": "자유응답 — NESDC 다자대결과 척도 다름. 별도 시리즈."},
                   "records": lrecs}, ensure_ascii=False, separators=(",", ":")))
    lm = sorted(set(r["date"] for r in lrecs))
    print(f"→ {OUT.name}: {len(lrecs)}건, {len(lm)}개월")

    # ② 정당지지 → aggregated_gallup.json (트래커 정당지지 소스 — 갤럽은 NESDC VT012에 안 들어옴)
    polls = []
    for seq, v in idx.items():
        if not v or not v.get("period_end") or not v.get("party"):
            continue
        cands = [{"party": k, "pct": val} for k, val in v["party"].items()]
        polls.append({"ntt_id": f"gallup-{v.get('ho') or seq}", "agency": "한국갤럽조사연구소",
                      "period_end": v["period_end"], "sido": "", "metric_type": "정당지지",
                      "office_level": "", "candidates": cands,
                      "source_url": URL.format(n=seq).split('&')[0]})
    polls.sort(key=lambda p: p["period_end"])
    PARTY_OUT.write_text(json.dumps({"_meta": {"source": "gallup.co.kr 데일리 오피니언 정당지지도(HTML 산문)",
                   "note": "갤럽 정당지지 — NESDC VT012 미포함분 보완. 트래커 정당지지 소스."},
                   "polls": polls}, ensure_ascii=False, separators=(",", ":")))
    pm = sorted(set(p["period_end"] for p in polls))
    print(f"→ {PARTY_OUT.name}: {len(polls)}건 정당지지, {pm[0] if pm else '?'}~{pm[-1] if pm else '?'}")


if __name__ == "__main__":
    main()
