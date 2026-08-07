"""지선 광역의회 비례(sgTypecode=8) 시도별 **득표** + 당선인 API 의석. 3~8회.

fetch_metro_prop_old(의석만, votes_pending)를 대체 — 시도별 개표(정당 득표수·득표율·
선거인수·투표수·무효·기권)를 받고, 의석은 NEC 당선인 API로 받아 합쳐 완전한
proportional_sido race를 만든다.

## 왜 5~8회가 비어 있었나

3·4회만 이 스크립트를 돌렸고, 5~8회는 당선인 API로 **의석만** 받아 놨었다. 그래서
2010·2014·2018·2022 광역비례는 정당이 3~6종(의석 얻은 당)뿐이고 득표가 전부 0이었다.
실제로는 9~13종이 나왔고 회차당 2천만 표가 넘는다. '데이터가 그렇다'가 아니라
'안 받아 왔다'였다.

## 출처가 둘인 이유

VCCP09(info.nec.go.kr)가 주 경로인데 **세종·제주에는 아무것도 주지 않는다**(특별자치라
페이지 구조가 다르다). 그 자리를 '개표 미상'으로 두면 득표가 있는데 없다고 적는
것이 되므로, 개표 API(VoteXmntckInfoInqireService2, sgTypecode=8)로 메운다. 이
API는 cityCode를 무시하고 전 시도를 페이지로 주므로 회차당 한 번 받아 캐시한다.
득표율은 안 주므로 유효표로 나눠 채운다(유도지 추정이 아니다).

사용: NEC_API_KEY는 .env. python scripts/fetch/fetch_metro_prop_votes.py [--n 5] [--dry-run]
의존: pandas, lxml.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from collections import defaultdict
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data" / "results"
WINNER_API = "https://apis.data.go.kr/9760000/WinnerInfoInqireService2/getWinnerInfoInqire"
VCCP_URL = "https://info.nec.go.kr/electioninfo/electionInfo_report.xhtml"
VOTE_API = "https://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2/getXmntckSttusInfoInqire"

ELECTIONS = {3: ("3rd-local-2002", "20020613"), 4: ("4th-local-2006", "20060531"),
             5: ("5th-local-2010", "20100602"), 6: ("6th-local-2014", "20140604"),
             7: ("7th-local-2018", "20180613"), 8: ("8th-local-2022", "20220601")}
# OVERRIDE는 **원자료에 다른 이름을 적는** 일이라 최소로 쓴다. 2016년 민주당 사고가
# 정확히 그렇게 났다. 5~8회는 넣지 않는다 — 그 회차의 '민주당'은 읽는 시점에
# party_canon이 시기별로 가른다(2010-06은 통합민주당). 여기서 미리 정하지 않는다.
OVERRIDE = {4: {"민주당": "민주당(2005)"}}

# 시도 핵심명 → NEC cityCode. by_sido(당선인 API sdName)를 핵심명으로 정규화해 매칭.
CITYCODE = {
    "서울": "1100", "부산": "2600", "대구": "2700", "인천": "2800", "광주": "2900",
    "대전": "3000", "울산": "3100", "경기": "4100", "강원": "4200",
    "충청북": "4300", "충청남": "4400", "전라북": "4500", "전라남": "4600",
    "경상북": "4700", "경상남": "4800", "제주": "5000",
}
NON_PARTY_LEAF = {"구시군명", "선거인수", "투표수", "계", "무효투표수", "무효 투표수", "기권자수"}


def sido_core(name: str) -> str:
    for suf in ("특별자치도", "특별자치시", "특별시", "광역시", "도"):
        if name.endswith(suf):
            return name[: -len(suf)]
    return name


def load_key() -> str:
    key = os.environ.get("NEC_API_KEY")
    if not key and (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("NEC_API_KEY"):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        sys.exit("NEC_API_KEY 없음")
    return key


def alias_map() -> dict:
    reg = json.loads((ROOT / "data/parties/registry.json").read_text()).get("parties", {})
    m = {}
    for name, info in reg.items():
        if name.startswith("_") or not isinstance(info, dict):
            continue
        if info.get("abbr"):
            m[info["abbr"]] = name
        for a in info.get("aliases", []):
            m[a] = name
    return m


def make_canon(existing: set, override: dict):
    al = alias_map()

    def cf(p):
        if p in override:
            return override[p]
        if p in existing:
            return p
        c = al.get(p)
        return c if (c and c in existing) else p
    return cf


def fetch_seats(key: str, sg_id: str) -> dict:
    """sgTypecode=8 당선인 → {sido_core: {party: seats}}."""
    out = defaultdict(lambda: defaultdict(int))
    page = 1
    while True:
        url = f"{WINNER_API}?serviceKey={key}&sgId={sg_id}&sgTypecode=8&pageNo={page}&numOfRows=100&resultType=xml"
        root = ET.fromstring(urllib.request.urlopen(url, timeout=40).read())
        if root.findtext("header/resultCode") != "INFO-00":
            break
        items = root.findall("body/items/item")
        if not items:
            break
        for it in items:
            sido = sido_core((it.findtext("sdName") or "").strip())
            party = (it.findtext("jdName") or "").strip()
            if sido and party:
                out[sido][party] += 1
        if page * 100 >= int(root.findtext("body/totalCount") or 0):
            break
        page += 1
    return out


def fetch_votes(election_name: str, city_code: str) -> dict | None:
    """VCCP09 시도 개표 → {electors, voters, invalid, abstain, valid, parties:{p:(votes,pct)}}."""
    data = urllib.parse.urlencode({
        "electionId": "0000000000", "requestURI": "/electioninfo/0000000000/vc/vccp09.jsp",
        "topMenuId": "VC", "secondMenuId": "VCCP09", "menuId": "VCCP09", "statementId": "VCCP09_#8",
        "oldElectionType": "1", "electionType": "4", "electionName": election_name, "electionCode": "8",
        "cityCode": city_code, "townCode": "-1", "sggCityCode": "-1"}).encode()
    req = urllib.request.Request(VCCP_URL, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
    tables = pd.read_html(StringIO(html))
    leaf = lambda c: (c[-1] if isinstance(c, tuple) else c)
    t = None
    for x in tables:
        leaves = [leaf(c) for c in x.columns]
        if "선거인수" in leaves and any(l not in NON_PARTY_LEAF for l in leaves):
            t = x; break
    if t is None or len(t) < 2:
        return None
    cols = list(t.columns)
    col_by_leaf = {leaf(c): c for c in cols}
    r0, r1 = t.iloc[0], t.iloc[1]  # 합계(득표수), 득표율

    def num(v):
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return 0
    parties = {}
    for c in cols:
        lf = leaf(c)
        if lf in NON_PARTY_LEAF:
            continue
        parties[lf] = (num(r0[c]), float(r1[c]) if pd.notna(r1[c]) else None)
    g = lambda name: num(r0[col_by_leaf[name]]) if name in col_by_leaf else 0
    invalid = g("무효투표수") or g("무효 투표수")
    return {
        "electors": g("선거인수"), "voters": g("투표수"),
        "valid": g("계"), "invalid": invalid, "abstain": g("기권자수"),
        "parties": parties,
    }


_API_CACHE: dict = {}


def fetch_votes_api(key: str, sg_id: str) -> dict:
    """개표 API(sgTypecode=8) → {sido_core: fetch_votes와 같은 모양}.

    VCCP09는 세종·제주에 아무것도 주지 않는다(특별자치라 페이지 구조가 다르다).
    그 자리를 '개표 미상, 의석만'으로 두면 **득표가 있는데 없다고 적는** 것이 된다.
    이 API는 cityCode를 무시하고 전 시도를 페이지로 주므로 한 번 받아 캐시한다.
    """
    if sg_id in _API_CACHE:
        return _API_CACHE[sg_id]
    out, page = {}, 1
    while True:
        url = (f"{VOTE_API}?serviceKey={key}&sgId={sg_id}&sgTypecode=8"
               f"&pageNo={page}&numOfRows=100&resultType=xml")
        root = ET.fromstring(urllib.request.urlopen(url, timeout=60).read())
        if root.findtext("header/resultCode") != "INFO-00":
            break
        items = root.findall("body/items/item")
        if not items:
            break
        for it in items:
            # 시도 합계 행만 — 시군구 행까지 더하면 두 번 세어진다
            if (it.findtext("sdName") or "").strip() != "합계":
                continue
            if (it.findtext("wiwName") or "").strip() not in ("합계", "", None):
                continue
            core = sido_core((it.findtext("sggName") or "").strip())
            if not core:
                continue
            def n(tag):
                try:
                    return int((it.findtext(tag) or "0").strip() or 0)
                except ValueError:
                    return 0
            parties = {}
            for i in range(1, 51):
                nm = (it.findtext(f"jd{i:02d}") or "").strip()
                if not nm:
                    continue
                v = n(f"dugsu{i:02d}")
                parties[nm] = (v, None)
            if parties:
                out[core] = {"electors": n("sunsu"), "voters": n("tusu"),
                             "valid": n("yutusu"), "invalid": n("mutusu"),
                             "abstain": n("gigwonsu"), "parties": parties}
        total = int(root.findtext("body/totalCount") or 0)
        if page * 100 >= total:
            break
        page += 1
    _API_CACHE[sg_id] = out
    return out


def build_race(sido_full, votes, seats_map, canon):
    cands = []
    for party_raw, (v, pct) in votes["parties"].items():
        party = canon(party_raw)
        # 개표 API는 득표율을 안 준다. 유효표로 나눈 값은 유도지 추정이 아니므로
        # 여기서 채운다 — 한 회차 안에서 어떤 시도는 pct가 있고 어떤 시도는 없으면
        # 읽는 쪽이 '없는 것'과 '0'을 구별하지 못한다.
        if pct is None and v is not None and votes.get("valid"):
            pct = round(v / votes["valid"] * 100, 2)
        cands.append({"name": party, "party": party, "votes": v, "pct": pct,
                      "seats": seats_map.get(party_raw, seats_map.get(party, 0))})
    cands.sort(key=lambda c: -(c["votes"] or 0))
    for i, c in enumerate(cands):
        c["rank"] = i + 1
        c["won"] = c["seats"] > 0
    return {
        "sg_typecode": "8", "sido": sido_full, "sigungu": "", "scope": "proportional_sido",
        "electors": votes["electors"], "voters": votes["voters"],
        "valid_votes": votes["valid"], "invalid_votes": votes["invalid"], "abstain": votes["abstain"],
        "seats_total": sum(seats_map.values()), "candidates": cands,
    }


def backfill(n, key, dry):
    fid, sg_id = ELECTIONS[n]
    path = RESULTS / f"{fid}.json"
    data = json.loads(path.read_text())
    existing = {c.get("party") for r in data.get("races", []) if r.get("sg_typecode") != "8"
                for c in (r.get("candidates") or []) if c.get("party")}
    canon = make_canon(existing, OVERRIDE.get(n, {}))
    seats = fetch_seats(key, sg_id)
    # 당선인 API에 등장한 시도 = 비례 있는 시도. 각 시도 sdName(full) 보존을 위해 다시 조회 필요 →
    # 여기선 by sido_core로 cityCode 찾고, sido full명은 데이터의 광역장 race에서 가져온다.
    full_by_core = {}
    for r in data.get("races", []):
        if r.get("sg_typecode") == "3" and r.get("sido"):
            full_by_core[sido_core(r["sido"])] = r["sido"]
    races = [r for r in data.get("races", []) if r.get("sg_typecode") != "8"]
    new, tot_v, tot_s = [], 0, 0
    for core, seats_map in seats.items():
        full = full_by_core.get(core, core)
        cc = CITYCODE.get(core)
        votes = fetch_votes(sg_id, cc) if cc else None
        if not votes:
            # 세종·제주는 VCCP09가 비어 있다 — 개표 API로 메운다(득표율은 안 준다).
            votes = fetch_votes_api(key, sg_id).get(core)
            if votes:
                print(f"  · {core}: VCCP09 없음 → 개표 API")
        if not votes:
            # 제주 등 VCCP09 무투표/구조차이 — 의석만(votes_pending).
            cands = [{"name": canon(p), "party": canon(p), "votes": None, "pct": None,
                      "seats": s, "won": True, "rank": i + 1}
                     for i, (p, s) in enumerate(sorted(seats_map.items(), key=lambda x: -x[1]))]
            race = {"sg_typecode": "8", "sido": full, "sigungu": "", "scope": "proportional_sido",
                    "votes_pending": True, "seats_total": sum(seats_map.values()), "candidates": cands}
            print(f"  · {core}: 개표 미상 → 의석만({race['seats_total']}석)")
        else:
            race = build_race(full, votes, seats_map, canon)
            tot_v += sum(v for v, _ in votes["parties"].values())
        new.append(race)
        tot_s += race["seats_total"]
    races.extend(new)
    data["races"] = races
    nat = defaultdict(int)
    for r in new:
        for c in r["candidates"]:
            nat[c["party"]] += c["votes"] or 0
    summ = " · ".join(f"{p} {v:,}" for p, v in sorted(nat.items(), key=lambda x: -x[1])[:5])
    print(f"  {fid}: {len(new)}시도 · {tot_s}석 · 총득표 {tot_v:,} — {summ}{' [dry]' if dry else ''}")
    if not dry:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        # 5~8회는 의석만 있는 tc8이 .sigungu 쪽에 들어가 있다(청크 뒤에 덧붙여진 탓).
        # 득표를 본 파일에 넣었으니 그 자리는 비운다 — 안 그러면 같은 회차 광역비례가
        # 두 벌이 되고, 하나는 득표 0이라 합계가 조용히 틀린다.
        sub = path.with_suffix(".sigungu.json")
        if sub.exists():
            sd = json.loads(sub.read_text())
            keep = [r for r in sd.get("races", []) if r.get("sg_typecode") != "8"]
            if len(keep) != len(sd.get("races", [])):
                dropped = len(sd["races"]) - len(keep)
                sd["races"] = keep
                sub.write_text(json.dumps(sd, ensure_ascii=False, indent=2) + "\n")
                print(f"    .sigungu에서 의석만 tc8 {dropped}행 제거")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    key = load_key()
    for n in ([args.n] if args.n else list(ELECTIONS)):
        backfill(n, key, args.dry_run)


if __name__ == "__main__":
    main()
