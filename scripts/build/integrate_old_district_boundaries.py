"""옛 총선(3·4·5대) 별표(old_district_boundaries_{n}.json)를 national_assembly_{n}.json에 통합.

1) 별표 선거구(제N 순서) ↔ 우리 '제N선거구'(번호순) order-zip → name=실제 선거구명, sigungu=[시군].
2) 제주(우리 VCCP09 미수집) — 위키 결과 템플릿에서 후보·득표 full backfill.
3) 알려진 오타 수정(경기 김포군 정담→정준 등).

재현: python scripts/build/integrate_old_district_boundaries.py [3 4 5]
"""
import json, re, sys, time
import urllib.request, urllib.parse
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"
RES = ROOT / "data/results"
UA = "vote-via-data-research/1.0 (hislab.mueller@gmail.com)"
ORD = {3: "제3대", 4: "제4대", 5: "제5대"}
CANON = {"강원특별자치도": "강원도", "전북특별자치도": "전라북도", "제주특별자치도": "제주도"}
# 우리 데이터의 알려진 당선자 오타 → 위키/사료 정답
WINNER_FIX = {(3, "경기도", "정담"): "정준"}
# 3·4대 제주 하위문서는 stub(후보·득표 없음) — 당선자만 사료/위키 확보(득표 미상)
JEJU_WINNER_ONLY = {
    (3, "북제주군 갑"): ("김석호", "무소속"), (3, "북제주군 을"): ("김두진", "무소속"),
    (3, "남제주군"): ("강경옥", "자유당"),
    (4, "제주시"): ("고담룡", "민주당"), (4, "북제주군"): ("김두진", "자유당"),
    (4, "남제주군"): ("현오봉", "무소속"),
}


def cs(s):
    return CANON.get(s, s)


def num(name):
    m = re.search(r"제(\d+)", name)
    return int(m.group(1)) if m else 9999


def link_name(s):
    m = re.search(r"\[\[([^\]]+)\]\]", s)
    if m:
        inner = m.group(1)
        return inner.split("|")[-1].strip() if "|" in inner else re.sub(r"\s*\(.*?\)\s*", "", inner).strip()
    return s.strip()


def norm_party(p):
    p = p.strip()
    p = re.sub(r"(19|20)\d\d$", "", p)  # 민주당1955 → 민주당
    return p or "무소속"


def fetch(page):
    u = ("https://ko.wikipedia.org/w/api.php?action=parse&page="
         + urllib.parse.quote(page) + "&prop=wikitext&format=json")
    req = urllib.request.Request(u, headers={"User-Agent": UA})
    return json.loads(urllib.request.urlopen(req, timeout=25).read())["parse"]["wikitext"]["*"]


def parse_results(wt):
    """민의원 결과 섹션의 선거구별 후보 리스트. {선거구명(끝 토큰): [cand...]}"""
    i = wt.find("민의원의원 선거 결과")
    if i < 0:
        i = wt.find("선거 결과")
    sec = wt[i:] if i >= 0 else wt
    out = {}
    # '=== 선거구명 ===' 단위로 분할
    for blk in re.split(r"\n===\s*", sec):
        hm = re.match(r"([^\n=]+?)\s*===", blk)
        if not hm:
            continue
        region = hm.group(1).strip()
        cands = []
        for cm in re.finditer(r"\{\{(당선 )?선거결과/정당명/막대\s*\|(.+?)\}\}", blk, re.S):
            won = bool(cm.group(1))
            params = cm.group(2)

            def fld(k):
                m = re.search(r"\|?\s*" + k + r"\s*=\s*(\[\[[^\]]+\]\]|[^|}\n]+)", params)
                return m.group(1).strip() if m else ""
            nm = link_name(fld("후보"))
            if not nm:
                continue
            votes = int(re.sub(r"[^\d]", "", fld("득표수") or "0") or 0)
            cands.append({"name": nm, "party": norm_party(fld("정당")),
                          "votes": votes, "pct": float(fld("득표율") or 0),
                          "won": won, "rank": 0})
        if cands:
            cands.sort(key=lambda c: -c["votes"])
            for r, c in enumerate(cands, 1):
                c["rank"] = r
            out[region] = cands
    return out


def integrate(n):
    bdy = json.loads((GEO / f"old_district_boundaries_{n}.json").read_text(encoding="utf-8"))
    path = RES / f"national_assembly_{n}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    races = doc["district"]
    # 오타 수정
    for r in races:
        key = (n, cs(r["sido"]), r.get("winner"))
        if key in WINNER_FIX:
            old = r["winner"]; r["winner"] = WINNER_FIX[key]
            for c in r.get("candidates", []):
                if c.get("name") == old:
                    c["name"] = r["winner"]
            print(f"  [fix] {n}대 {r['sido']} {r['name']} 당선자 {old}→{r['winner']}", file=sys.stderr)
    ours = defaultdict(list)
    for r in races:
        ours[cs(r["sido"])].append(r)
    assigned = 0
    jeju_pages = {}
    for sido, rows in bdy.items():
        o = sorted(ours.get(sido, []), key=lambda r: num(r["name"]))
        if len(o) == len(rows):  # order-zip
            for orace, brow in zip(o, rows):
                orace["sg_no"] = orace["name"]              # 원래 제N선거구 보존
                orace["name"] = brow["district"]            # 실제 선거구명
                orace["sigungu_area"] = brow["sigungu"]     # 시군 획정
                assigned += 1
        elif len(o) == 0:  # 제주 등 통째 누락 → 위키 결과로 backfill
            page = f"대한민국 {ORD[n]} 국회의원 선거 {sido}"
            if sido not in jeju_pages:
                jeju_pages[sido] = parse_results(fetch(page)); time.sleep(0.3)
            res = jeju_pages[sido]
            for brow in rows:
                # 결과 섹션 키는 선거구명 끝 토큰(제주시/북제주군 갑 등)과 일치
                cands = res.get(brow["district"]) or res.get(brow["district"].split()[-1])
                src = "wiki"
                if not cands and (n, brow["district"]) in JEJU_WINNER_ONLY:
                    wn, wp = JEJU_WINNER_ONLY[(n, brow["district"])]
                    cands = [{"name": wn, "party": wp, "votes": 0, "pct": 0, "won": True, "rank": 1}]
                    src = "wiki-winner-only"  # 득표 미상(하위문서 stub)
                w = next((c for c in (cands or []) if c["won"]), (cands or [None])[0])
                rec = {"sido": "제주도", "name": brow["district"], "sg_no": None,
                       "sigungu_area": brow["sigungu"],
                       "winner": w["name"] if w else None,
                       "winner_party": w["party"] if w else None,
                       "candidates": cands or [], "backfill": src}
                races.append(rec)
            print(f"  [backfill] {n}대 {sido} {len(rows)}석", file=sys.stderr)
        else:
            print(f"  [WARN] {n}대 {sido}: 우리 {len(o)} vs 별표 {len(rows)} 불일치 — 건너뜀", file=sys.stderr)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{n}대: region 부여 {assigned} + 제주 backfill → 총 {len(races)}석", file=sys.stderr)


if __name__ == "__main__":
    for a in (sys.argv[1:] or [3, 4, 5]):
        integrate(int(a))
