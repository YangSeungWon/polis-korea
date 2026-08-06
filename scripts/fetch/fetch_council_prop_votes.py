"""info.nec.go.kr VCCP09(electionCode=9) → 기초의원 비례 **시군구별 득표**를 의석 race에 보강.

당선인 API(fetch_council_prop / fetch_council_winners_live)는 의석만 준다. 득표는
개표현황(VCCP09)에만 있다 — 없으면 '기초의원 비례 시·군·구별 표심' 지도가 통째로 빈다.

## 회차를 하드코딩하지 않는다

이 스크립트는 원래 4회 한 회차만 박혀 있었고(`ELECTIONS = {4: ...}`), 그래서 5~8회는
**가져올 수 있는데 안 가져온 상태**로 남아 있었다. 화면에는 '자료 없음'으로 보였다.
가져올 수 있는 것을 없다고 말하지 않기 위해 전 회차를 대상으로 돌린다.

## 시도 코드는 회차마다 다르다

강원(4200→5200)·전북(4500→5300)처럼 특별자치도 전환으로 코드가 바뀐다. 코드표를
손으로 관리하면 조용히 한 시도가 통째로 빠진다 — 후보 코드를 **훑어서 응답이 있는
것만** 쓴다.

## 남는 결손은 '자료 없음'이 아니라 '무투표 당선'이다

개표현황에 없는 시군구를 무투표 API(tc=9)와 대조하니 거의 완전히 일치했다
(9회 58/58, 8회 61/62, 6회 64/65 — 어긋난 것은 군위군·미추홀구·마산/진해처럼
이름·시도가 바뀐 곳뿐이다). **투표를 안 했으니 개표가 없는 것**이지 자료가 빠진 게
아니다. 둘은 전혀 다른 사실이라 그렇게 표시해야 한다 — `uncontested`로 표시한다.

(광역 비례 tc=8은 무투표가 0건이다. 기초 비례만 정수가 작아 실제로 생긴다.)

사용: python scripts/fetch/fetch_council_prop_votes.py [--n 5 6 7 8 9] [--dry-run]
의존: pandas, lxml.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import urllib.request
import urllib.parse
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data" / "results"
VCCP_URL = "https://info.nec.go.kr/electioninfo/electionInfo_report.xhtml"
ELECTIONS = {
    4: ("4th-local-2006", "20060531"), 5: ("5th-local-2010", "20100602"),
    6: ("6th-local-2014", "20140604"), 7: ("7th-local-2018", "20180613"),
    8: ("8th-local-2022", "20220601"), 9: ("9th-local-2026", "20260603"),
}
OVERRIDE = {4: {"민주당": "민주당(2005)"}}

# 후보 cityCode — 회차마다 유효한 것만 응답한다. 이름은 응답에서 오는 게 아니라
# 우리 데이터의 sido와 맞춰야 하므로 (코드 → 데이터 sido 후보) 로 둔다.
CITY_CODES = {
    "1100": ["서울특별시"], "2600": ["부산광역시"], "2700": ["대구광역시"],
    "2800": ["인천광역시"], "2900": ["광주광역시"], "3000": ["대전광역시"],
    "3100": ["울산광역시"], "3600": ["세종특별자치시"], "4100": ["경기도"],
    "4200": ["강원도", "강원특별자치도"], "5200": ["강원특별자치도", "강원도"],
    "4300": ["충청북도"], "4400": ["충청남도"],
    "4500": ["전라북도", "전북특별자치도"], "5300": ["전북특별자치도", "전라북도"],
    "4600": ["전라남도"], "4700": ["경상북도"], "4800": ["경상남도"],
    "5000": ["제주도", "제주특별자치도"],
}


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def alias_map():
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


def make_canon(existing, override):
    al = alias_map()

    def cf(p):
        if p in override:
            return override[p]
        if p in existing:
            return p
        c = al.get(p)
        return c if (c and c in existing) else p
    return cf


def norm_sgg(name: str) -> str:
    """시군구명 매칭용 — 공백 제거. 통합시 일반구는 그대로(데이터도 동일 표기 가정)."""
    return re.sub(r"\s+", "", name or "")


def num(v):
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def fetch_sido(election_name: str, city_code: str) -> dict:
    """{norm 시군구명: {electors,voters,valid,invalid,parties:{party:(votes,pct)}}}."""
    data = urllib.parse.urlencode({
        "electionId": "0000000000", "requestURI": "/electioninfo/0000000000/vc/vccp09.jsp",
        "topMenuId": "VC", "secondMenuId": "VCCP09", "menuId": "VCCP09", "statementId": "VCCP09_#9",
        "oldElectionType": "1", "electionType": "4", "electionName": election_name, "electionCode": "9",
        "cityCode": city_code, "townCode": "-1", "sggCityCode": "-1"}).encode()
    req = urllib.request.Request(VCCP_URL, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    tables = pd.read_html(StringIO(html))
    t = None
    for x in tables:
        if x.shape[1] >= 9 and "선거구명" in [str(c[0]) if isinstance(c, tuple) else str(c) for c in x.columns]:
            t = x; break
    if t is None or len(t) < 3:
        return {}
    cols = list(t.columns)
    # 컬럼 위치: 0 선거구명, 1 구시군명, 2 선거인수, 3 투표수, 4..n-2 정당+계, n-2 무효, n-1 기권
    party_cols = cols[4:-2]
    out = {}
    i = 0
    while i + 2 < len(t):
        names = t.iloc[i]      # 정당명 행
        vals = t.iloc[i + 1]   # 득표수 행
        pcts = t.iloc[i + 2]   # 득표율 행
        sgg = names[cols[0]]
        if not isinstance(sgg, str) or not sgg.strip():
            i += 1; continue
        parties = {}
        valid = 0
        for c in party_cols:
            pname = names[c]
            if not isinstance(pname, str):
                continue
            if pname == "계":
                valid = num(vals[c]); continue
            parties[pname] = (num(vals[c]), float(pcts[c]) if pd.notna(pcts[c]) else None)
        if parties:
            out[norm_sgg(sgg)] = {
                "electors": num(vals[cols[2]]), "voters": num(vals[cols[3]]),
                "valid": valid, "invalid": num(vals[cols[-2]]), "abstain": num(vals[cols[-1]]),
                "parties": parties,
            }
        i += 3
    return out


UNCON_API = ("https://apis.data.go.kr/9760000/WtvtelpcInfoInqireService/"
             "getWtvtelpcsccnInfoInqire")
# 무투표 대조용 정규화. **양쪽 다 거쳐야 한다** — API만 정규화하고 우리 데이터를
# 그대로 두면 '강원특별자치도' 행이 '강원도' 키와 안 맞아 통째로 놓친다(9회 49곳이 그랬다).
_SIDO_EQ = {"강원특별자치도": "강원도", "전북특별자치도": "전라북도",
            "제주특별자치도": "제주도"}
# 시군구 개명·이관·통합 — 무투표 명부는 그 시점 이름이고 우리 행은 현행 이름일 수 있다.
_SGG_ALIAS = {
    "미추홀구": "남구",          # 인천 2018-07 개칭
    "군위군": "군위군",          # 경북→대구(2023) — 시도만 다르므로 아래에서 시도 무시
}
# 시도가 바뀐 시군구는 시도를 빼고 이름만으로 맞춘다(동명이 없을 때만 안전).
_SIDO_FREE = {"군위군", "마산시", "진해시"}


def _api_key() -> str:
    import os
    key = os.environ.get("NEC_API_KEY")
    if key:
        return key
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("NEC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"\'')
    return ""


def uncon_keys(sido: str, sgg: str) -> set:
    """(시도, 시군구) → 대조용 키 집합. **API 행과 내부 행이 같은 함수를 거친다.**
    한쪽만 정규화하면 '강원특별자치도' 행이 '강원도' 키와 안 맞아 통째로 놓친다."""
    sd = _SIDO_EQ.get(sido, sido)
    out = {(sd, sgg), (sd, _SGG_ALIAS.get(sgg, sgg))}
    if sgg in _SIDO_FREE:
        out.add(("*", sgg))              # 시도가 바뀐 곳은 이름만으로 (동명 없을 때만)
    return out


def is_uncontested(row: dict, uncon: set) -> bool:
    return bool(uncon_keys(row.get("sido") or "", row.get("sigungu") or "") & uncon)


def fetch_uncontested(sg_id: str) -> set:
    """무투표 당선된 (시도, 시군구). **응답이 {"response": {...}}로 한 겹 더 싸여 있다** —
    그걸 놓치면 body가 None이라 API가 죽은 줄 알게 된다(실제로 그랬다)."""
    import time
    key = _api_key()
    if not key:
        print("  ! NEC_API_KEY 없음 — 무투표 대조 건너뜀"); return set()
    out, page = set(), 1
    while page < 30:
        q = urllib.parse.urlencode({"serviceKey": key, "pageNo": page, "numOfRows": 20,
                                    "sgId": sg_id, "sgTypecode": "9", "resultType": "json"},
                                   safe="%")
        d = None
        for _ in range(6):
            try:
                d = json.loads(urllib.request.urlopen(f"{UNCON_API}?{q}", timeout=90).read())
                break
            except Exception:                                    # noqa: BLE001
                time.sleep(6)
        if d is None:
            # **부분 실패를 완료로 취급하지 않는다.** 조용히 끊으면 못 받은 페이지의
            # 시군구가 '무투표 아님'으로 남아 원인 미상이 된다 — 8회가 61→12로 줄었다.
            raise RuntimeError(f"무투표 API 응답 실패 (sgId={sg_id}, page={page}) — "
                               "부분 결과로 표시를 바꾸지 않는다")
        d = d.get("response") or {}
        code = (d.get("header") or {}).get("resultCode")
        if code == "INFO-03":
            break                       # 해당 선거에 무투표 없음 — 정상
        if code != "INFO-00":
            raise RuntimeError(f"무투표 API 오류 {code} (sgId={sg_id}, page={page})")
        it = ((d.get("body") or {}).get("items") or {}).get("item") or []
        if isinstance(it, dict):
            it = [it]
        for i in it:
            out |= uncon_keys(i.get("sdName") or "", i.get("sggName") or "")
        if len(it) < 20:
            break
        page += 1
    return out


def target_path(fid: str) -> Path:
    """tc9 행이 실제로 들어 있는 파일. 5~8회는 .sigungu 청크, 9회는 본 파일이다."""
    chunk = RESULTS / f"{fid}.sigungu.json"
    if chunk.exists():
        d = json.loads(chunk.read_text())
        if any(r.get("sg_typecode") == "9" for r in d.get("races", [])):
            return chunk
    return RESULTS / f"{fid}.json"


def backfill(n, dry):
    fid, sg_id = ELECTIONS[n]
    path = target_path(fid)
    if not path.exists():
        print(f"  ! {fid}: 결과 파일 없음"); return
    data = json.loads(path.read_text())
    rows = [r for r in data.get("races", []) if r.get("sg_typecode") == "9"
            and r.get("scope") == "proportional_sigungu"]
    if not rows:
        print(f"  ! {fid}: tc9 행 없음 ({path.name})"); return
    existing = {c.get("party") for r in data.get("races", []) for c in (r.get("candidates") or []) if c.get("party")}
    canon = make_canon(existing, OVERRIDE.get(n, {}))
    sidos = {r.get("sido", "") for r in rows}

    # 시도별 개표 수집 — 응답이 있는 코드만 채택(회차마다 코드가 다르다).
    #
    # **한 파일 안에 시도 표기가 섞여 있다.** 8회 결과에 '강원도'와 '강원특별자치도'가
    # 같이 들어 있어, 코드를 첫 이름 하나에만 저장했더니 나머지 17곳이 통째로 결손이
    # 됐다. 그 코드가 대응하는 **모든 표기**에 같은 응답을 건다.
    by_sido: dict = {}
    for cc, cands in CITY_CODES.items():
        hits = [s for s in cands if s in sidos and s not in by_sido]
        if not hits:
            continue
        try:
            got = fetch_sido(sg_id, cc)
        except Exception as e:                                   # noqa: BLE001
            print(f"  ! {'·'.join(hits)}({cc}) 개표 실패: {e}"); got = {}
        for h in hits:
            if got:
                by_sido[h] = got

    before = sum(1 for r in rows
                 if any(c.get("party") and (c.get("votes") or 0) > 0 for c in (r.get("candidates") or [])))
    matched = unmatched = 0
    for r in rows:
        sido = r.get("sido", "")
        sgg = norm_sgg(r.get("sigungu", ""))
        votes = by_sido.get(sido, {}).get(sgg)
        if not votes:
            unmatched += 1
            continue
        matched += 1
        cand_by_party = {c["party"]: c for c in r.get("candidates", [])}
        for praw, (v, pct) in votes["parties"].items():
            party = canon(praw)
            c = cand_by_party.get(party)
            if c:
                c["votes"] = v; c["pct"] = pct
            else:
                r.setdefault("candidates", []).append(
                    {"name": party, "party": party, "votes": v, "pct": pct, "seats": 0, "won": False})
        r["electors"] = votes["electors"]; r["voters"] = votes["voters"]
        r["valid_votes"] = votes["valid"]; r["invalid_votes"] = votes["invalid"]
        r["abstain"] = votes["abstain"]
        r.pop("votes_pending", None)
        r["candidates"].sort(key=lambda c: -(c.get("votes") or 0))
        for i, c in enumerate(r["candidates"]):
            c["rank"] = i + 1

    # 남은 결손이 무투표 당선인지 확인해 **사실을 붙인다**. '자료 없음'과 다르다.
    uncon = fetch_uncontested(sg_id)
    marked = 0
    for r in rows:
        if any(c.get("party") and (c.get("votes") or 0) > 0 for c in (r.get("candidates") or [])):
            continue
        if is_uncontested(r, uncon):
            r["uncontested"] = True
            r.pop("votes_pending", None)
            r.pop("unknown_reason", None)
            r.pop("checked_sources", None)
            for c in r.get("candidates") or []:
                if c.get("seats"):
                    c["uncontested"] = True
            marked += 1
        else:
            # 원인을 못 찾은 것도 **찾아본 흔적을 남긴다** — 다음에 같은 조사를 반복하지
            # 않게. 결손을 조용히 두는 것과 '어디를 봤는데 없더라'는 다르다.
            r["unknown_reason"] = "개표현황·무투표 명부 어디에도 없음"
            r["checked_sources"] = [
                f"info.nec.go.kr VCCP09 electionCode=9 (sgId={sg_id})",
                f"data.go.kr WtvtelpcInfoInqireService sgTypecode=9 (sgId={sg_id})",
            ]
            r["last_verified"] = _today()

    after = sum(1 for r in rows
                if any(c.get("party") and (c.get("votes") or 0) > 0 for c in (r.get("candidates") or [])))
    left = len(rows) - after - marked
    print(f"  {fid} ({path.name}) 기초비례 {len(rows)}곳: "
          f"득표 {before} → {after} · 무투표 {marked} · 원인 미상 {left}"
          f"{' [dry]' if dry else ''}")
    if not dry and (matched or marked):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, nargs="*", default=sorted(ELECTIONS))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    for n in args.n:
        if n not in ELECTIONS:
            print(f"  ! {n}회는 대상이 아니다"); continue
        backfill(n, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
