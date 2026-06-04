"""NEC 실시간 개표 포털(info.nec.go.kr) → data/results/{election_id}.json.

fetch_nec_results.py(data.go.kr OpenAPI·인증키 필요·배치)와 **같은 schema**를 내지만,
소스가 NEC 개표방송 포털의 비공식 JSON 엔드포인트라 **인증키 불필요**하고 개표 진행 중
실시간 값을 준다. 선거 당일/개표 중 archive 페이지에 잠정 결과를 띄우는 용도.
(레퍼런스 메모: nec-live-count)

엔드포인트:
  1. 세션 쿠키: GET /m/main/showDocument.xhtml?electionId=..&secondMenuId=VCCP09&topMenuId=VC
  2. 개표 statement: POST /m/electioninfo/electionInfo_report.json
       data: electionId, statementId=VCCP09_#<code>, electionCode=<code>,
             cityCode=0(전체)|시도코드, sggCityCode=-1, townCode=-1
       → jsonResult.body[] (지역별 row, 대문자 필드)
  3. 시도/시군구 코드: GET /m/bizcommon/selectbox/<cityEndpoint>?electionId=..&electionCode=..

row 필드: SDNAME/SGGNAME/WIWNAME 지역, HUBO0x 후보명, JD0x 정당, DUGSU0x 득표수,
  DUGYUL0x 득표율, SUNSU 선거인수, TUHAMSU 투표수, TOTALDUGSU 유효(득표합계),
  MUTUSU 무효, GIGWON 기권, GAEPYOYUL 개표율, HUBOSU/MAXHUBOSU 후보수.

scope 매핑 (sg_typecode):
  3 광역단체장·11 교육감 → cityCode=0 한 번에 시도 합계 rows (scope=sido)
  4 기초단체장 → 시도 코드별 loop, 시군구 합계 rows (scope=sigungu)
  통합 시도(전남광주통합특별시)는 '소계' row가 결합 race, 광주/전남 sub-row는 drop.

사용:
  python3 scripts/fetch/fetch_nec_live.py --election 9th-local-2026 --dry-run
  python3 scripts/fetch/fetch_nec_live.py --election 9th-local-2026
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
ELECTIONS_DIR = ROOT / "data/elections"
RESULTS_DIR = ROOT / "data/results"

BASE = "https://info.nec.go.kr"
REPORT = "/m/electioninfo/electionInfo_report.json"
SELECTBOX = "/m/bizcommon/selectbox/"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

# sg_typecode → statementId 접미 (포털 JS 매핑; 투표상황 미입력판은 _0)
STATEMENT_SUFFIX = {"10": "10_0"}  # 5/6은 _0 suffix 시 0 row 회신, 기본 tc 그대로 사용
# cityEndpoint by sg_typecode (포털 OptionSearch 인자에서)
CITY_ENDPOINT = {
    "3": "selectbox_cityCodeDIBySgJson.json", "11": "selectbox_cityCodeDIBySgJson.json",
    "8": "selectbox_cityCodeDIBySgJson.json", "4": "selectbox_cityCodeBySgJson.json",
    "9": "selectbox_cityCodeBySgJson.json", "2": "selectbox_cityCodeBySgJson.json",
}


def load_election_meta(election_id: str) -> dict:
    p = ELECTIONS_DIR / f"{election_id}.json"
    if not p.exists():
        print(f"ERR: 메타 없음 — {p}", file=sys.stderr)
        sys.exit(1)
    return json.loads(p.read_text(encoding="utf-8"))


def to_int(s) -> int:
    if s is None:
        return 0
    try:
        return int(str(s).replace(",", "").strip() or 0)
    except ValueError:
        return 0


def to_float(s) -> float:
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def make_session(election_id: str, menu: str) -> requests.Session:
    """showDocument 1회 방문해 세션 쿠키 확보 (없으면 SY00200003 '잘못된 접근경로')."""
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    doc = f"{BASE}/m/main/showDocument.xhtml?electionId={election_id}&secondMenuId={menu}&topMenuId=VC"
    s.get(doc, timeout=20)
    s.headers.update({"Referer": doc, "X-Requested-With": "XMLHttpRequest"})
    return s


def fetch_report(s: requests.Session, election_id: str, menu: str, statement_id: str,
                 election_code: str, city_code: str = "0") -> list[dict]:
    data = {
        "electionId": election_id, "secondMenuId": menu, "topMenuId": "VC",
        "statementId": statement_id, "electionCode": election_code,
        "cityCode": city_code, "sggCityCode": "-1", "townCode": "-1",
    }
    r = s.post(BASE + REPORT, data=data, timeout=20)
    j = r.json().get("jsonResult", {})
    if j.get("header", {}).get("result") != "ok":
        raise RuntimeError(j.get("header", {}).get("errorMessage", "unknown"))
    return j.get("body") or []


def fetch_city_list(s: requests.Session, election_id: str, election_code: str) -> list[dict]:
    endpoint = CITY_ENDPOINT.get(election_code, "selectbox_cityCodeBySgJson.json")
    r = s.get(BASE + SELECTBOX + endpoint,
              params={"electionId": election_id, "electionCode": election_code}, timeout=20)
    return r.json().get("jsonResult", {}).get("body") or []


def parse_candidates(row: dict) -> list[dict]:
    n = to_int(row.get("MAXHUBOSU") or row.get("HUBOSU"))
    cs = []
    for i in range(1, max(n, 0) + 1):
        nm = row.get(f"HUBO{i:02d}")
        if not nm or nm == "None":
            continue
        cs.append({
            "name": nm,
            "party": row.get(f"JD{i:02d}") or "",
            "votes": to_int(row.get(f"DUGSU{i:02d}")),
            "pct": to_float(row.get(f"DUGYUL{i:02d}")),
        })
    cs.sort(key=lambda c: -c["votes"])
    for rank, c in enumerate(cs, 1):
        c["rank"] = rank
    if cs:
        cs[0]["won"] = True
    return cs


def base_race(row: dict, sg_typecode: str, canon) -> dict:
    return {
        "sg_typecode": sg_typecode,
        "sido": canon(row.get("SDNAME", "")),
        "sigungu": "",
        "scope": "sido",
        "electors": to_int(row.get("SUNSU")),
        "voters": to_int(row.get("TUHAMSU") or row.get("TUSU")),
        "valid_votes": to_int(row.get("TOTALDUGSU")),
        "invalid_votes": to_int(row.get("MUTUSU")),
        "abstain": to_int(row.get("GIGWON")),
        "count_pct": to_float(row.get("GAEPYOYUL")),
        "candidates": parse_candidates(row),
    }


def build(election_id_meta: str) -> dict:
    meta = load_election_meta(election_id_meta)
    sg_id = meta.get("nec", {}).get("sg_id", "")
    if not sg_id:
        print("ERR: 메타에 nec.sg_id 없음", file=sys.stderr)
        sys.exit(1)
    election_id = f"00{sg_id}"  # NEC 포털 electionId (예: 20260603 → 0020260603)
    menu = meta.get("nec", {}).get("live_menu", "VCCP09")
    # 통합 시도 alias → canonical. **광역단체장(tc=3)에만 적용**.
    # 행정 통합은 광역장 1명만 선출 통합이고, 기초장·의원·교육감은 옛 시도 단위로
    # 자치구·시군이 그대로 존속 → tc=4/5/6/11은 raw sido(광주광역시·전라남도) 유지해야
    # hex(옛 시도 분리)와 자연 매칭. 통합 적용을 분기 안 하면 dashboard에서 매번
    # split 로직 패치하는 hack 반복.
    merges = {}
    for m in meta.get("sido_merge", []):
        for a in m.get("merge_from", []):
            merges[a] = m["canonical"]
        if m.get("nec_sgg"):
            merges[m["nec_sgg"]] = m["canonical"]
    # 광역단체장(3)·교육감(11): 통합 시도 1명 선출 → canonical merge.
    # 기초장(4)·광역의원(5)·기초의원(6): 자치구·시군 그대로 → raw sido 유지.
    MERGED_TC = {"3", "11"}
    def canon_for(tc):
        def fn(sd):
            return merges.get(sd, sd) if tc in MERGED_TC else sd
        return fn

    s = make_session(election_id, menu)
    races: list[dict] = []
    n_call = 0
    LIVE_TC = {"2", "3", "4", "5", "6", "11", "8", "9"}  # 의원(5/6)은 시도0 호출 한 번에 선거구별 row 회신
    # 2 = 국회의원 (재보궐 district scope) — 시도 loop, SGGNAME=선거구, WIWNAME=소계 row
    offices = [o for o in meta.get("offices", []) if o.get("sg_typecode") in LIVE_TC]
    print(f"=== {meta['name']} 실시간 개표 (electionId={election_id}) ===", file=sys.stderr)

    for o in offices:
        tc = o["sg_typecode"]
        stmt = f"VCCP09_#{STATEMENT_SUFFIX.get(tc, tc)}".replace("VCCP09", menu)
        scope = o.get("scope", "sido")
        if scope == "sido":
            # cityCode=0 한 번에 시도 합계
            rows = fetch_report(s, election_id, menu, stmt, tc, "0"); n_call += 1
            kept = 0
            for row in rows:
                sd, sgg, wiw = row.get("SDNAME", ""), row.get("SGGNAME", ""), row.get("WIWNAME", "")
                if wiw != "합계":
                    continue
                # 통합 시도: '소계'(결합 race)만 채택, 광주/전남 sub-breakdown(SD≠SGG)은 drop
                if sd != sgg and sd != "소계":
                    continue
                r = base_race(row, tc, canon_for(tc))
                r["sido"] = canon_for(tc)(sgg if sd == "소계" else sd)
                r["scope"] = "sido"
                races.append(r); kept += 1
            print(f"  ✓ {o['level']} (sido): {kept} races", file=sys.stderr)
            time.sleep(0.3)
        elif scope == "sigungu":
            # 시도 코드별 loop → 시군구 합계
            cities = fetch_city_list(s, election_id, tc); n_call += 1
            kept = 0
            for c in cities:
                code = str(c.get("CODE"))
                rows = fetch_report(s, election_id, menu, stmt, tc, code); n_call += 1
                for row in rows:
                    # 시군구 race 총계는 WIWNAME='소계' (시도 level은 '합계'와 달리).
                    # WIW=구명 sub-row는 drop.
                    if row.get("WIWNAME") != "소계":
                        continue
                    r = base_race(row, tc, canon_for(tc))
                    r["sigungu"] = row.get("SGGNAME", "")
                    r["scope"] = "sigungu"
                    races.append(r); kept += 1
                time.sleep(0.2)
            print(f"  ✓ {o['level']} (sigungu): {kept} races ({len(cities)} 시도)", file=sys.stderr)
        elif scope == "district":
            # 광역의원(5)·기초의원(6): cityCode=0 한 호출 = 전 선거구 row (WIW=시군구).
            #   → 시도별 loop 없이 한 번에 끝남, 모든 row가 race.
            # 재보궐 국회의원(2): 시도 코드별 loop, WIWNAME=소계 row만 채택.
            if tc in ("5", "6"):
                rows = fetch_report(s, election_id, menu, stmt, tc, "0"); n_call += 1
                kept = 0
                for row in rows:
                    sgg = row.get("SGGNAME", "")
                    if not sgg or sgg in ("합계", "소계"):
                        continue
                    r = base_race(row, tc, canon_for(tc))
                    r["sido"] = canon_for(tc)(row.get("SDNAME", ""))
                    r["district"] = sgg
                    r["sigungu"] = row.get("WIWNAME", "")  # 선거구가 걸린 시군구
                    r["scope"] = "district"
                    races.append(r); kept += 1
                print(f"  ✓ {o['level']} (district, 한 호출): {kept} races", file=sys.stderr)
            else:
                cities = fetch_city_list(s, election_id, tc); n_call += 1
                kept = 0
                for c in cities:
                    code = str(c.get("CODE"))
                    rows = fetch_report(s, election_id, menu, stmt, tc, code); n_call += 1
                    for row in rows:
                        if row.get("WIWNAME") != "소계":
                            continue
                        r = base_race(row, tc, canon_for(tc))
                        r["sido"] = canon_for(tc)(row.get("SDNAME", ""))
                        r["district"] = row.get("SGGNAME", "")
                        r["sigungu"] = ""
                        r["scope"] = "district"
                        races.append(r); kept += 1
                    time.sleep(0.2)
                print(f"  ✓ {o['level']} (district): {kept} races ({len(cities)} 시도)", file=sys.stderr)

    return {
        "_meta": {
            "election": meta["name"],
            "election_id": meta["id"],
            "election_date": meta["date"],
            "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "is_final": False,            # 라이브/잠정
            "source": "nec-live-portal",  # info.nec.go.kr (개표방송)
            "n_calls": n_call,
            "n_rows": len(races),
        },
        "races": races,
    }


def main():
    ap = argparse.ArgumentParser(description="NEC 실시간 개표 → results JSON")
    ap.add_argument("--election", required=True, help="data/elections/{id}.json")
    ap.add_argument("--dry-run", action="store_true", help="저장 안 하고 요약만")
    args = ap.parse_args()

    out = build(args.election)
    if args.dry_run:
        import collections
        sc = collections.Counter((r["scope"], r["sg_typecode"]) for r in out["races"])
        print(f"[dry-run] races {len(out['races'])} {dict(sc)} (저장 안 함)", file=sys.stderr)
        return
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{args.election}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    st = out["_meta"]
    print(f"\n→ {out_path.relative_to(ROOT)} ({st['n_rows']} races, {st['n_calls']} calls, "
          f"is_final={st['is_final']})", file=sys.stderr)


if __name__ == "__main__":
    main()
