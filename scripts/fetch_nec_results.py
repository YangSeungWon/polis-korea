"""NEC OpenAPI 투·개표 정보 → data/results/{election_id}.json.

검증된 endpoint:
  https://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2/getXmntckSttusInfoInqire

응답 스키마 (XML):
  sgId·sgTypecode·sdName·sggName·wiwName·sunsu·tusu·yutusu·mutusu·gigwonsu·
  jd01..50 (정당명)·hbj01..50 (후보명)·dugsu01..50 (득표수)·crOrder

wiwName="합계" row = 시도 전체 결과 (광역단체장·교육감 race 본체)
wiwName="구·시·군명" row = 시군구별 세부 (광역단체장 race의 지역별 / 기초단체장 race)

호출 시점: 개표 시작 후 (6/3 23시 ~ 6/4 새벽). 잠정 → 확정.

사용:
  python3 scripts/fetch_nec_results.py --election 9th-local-2026 --dry-run
  python3 scripts/fetch_nec_results.py --election 9th-local-2026
  python3 scripts/fetch_nec_results.py --election 8th-local-2022  # 옛 선거 재수집
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ELECTIONS_DIR = ROOT / "data/elections"
RESULTS_DIR = ROOT / "data/results"

API_BASE = "https://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2"
ENDPOINT_XMNTCK = "/getXmntckSttusInfoInqire"  # 개표 결과 (메인)
ENDPOINT_VOTE = "/getVoteSttusInfoInqire"      # 투표 결과 (투표율 등)

# 광역시도 17개 (전남광주 통합 전 매핑 — NEC API는 이전 명칭 사용 가능성)
ALL_SIDOS = [
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
    "충청북도", "충청남도", "전북특별자치도", "전라남도", "경상북도", "경상남도",
    "제주특별자치도",
]


def load_election_meta(election_id: str) -> dict:
    p = ELECTIONS_DIR / f"{election_id}.json"
    if not p.exists():
        print(f"ERR: 메타 없음 — {p}", file=sys.stderr)
        sys.exit(1)
    return json.loads(p.read_text(encoding="utf-8"))


def _load_api_key() -> str:
    k = os.environ.get("NEC_API_KEY")
    if k:
        return k
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith("NEC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def fetch_xmntck(sg_id: str, sg_typecode: str, sd_name: str, api_key: str,
                 num_rows: int = 300) -> list[dict]:
    """한 (sg_id, sg_typecode, sd_name)의 개표 결과. 시도 합계 + 시군구별 row."""
    params = {
        "serviceKey": api_key, "sgId": sg_id, "sgTypecode": sg_typecode,
        "sdName": sd_name, "numOfRows": num_rows, "pageNo": 1,
    }
    url = f"{API_BASE}{ENDPOINT_XMNTCK}?{urllib.parse.urlencode(params, safe='%')}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            raw = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return [{"_error": str(e), "_sd_name": sd_name}]
    try:
        root = ET.fromstring(raw)
        result_code = root.findtext(".//resultCode", "")
        if result_code == "INFO-03":  # 데이터 없음 (개표 전 또는 sg 조합 무)
            return []
        items = []
        for item in root.findall(".//item"):
            d = {child.tag: child.text for child in item}
            items.append(d)
        return items
    except Exception as e:
        return [{"_error": f"XML parse: {e}", "_raw_head": raw[:300]}]


def parse_row_candidates(row: dict) -> list[dict]:
    """jd01..50, hbj01..50, dugsu01..50을 candidates list로 정규화."""
    cs = []
    total = sum(int(row.get(f"dugsu{i:02d}") or 0) for i in range(1, 51))
    for i in range(1, 51):
        nm = row.get(f"hbj{i:02d}") or ""
        if not nm or nm == "None":
            continue
        pty = row.get(f"jd{i:02d}") or ""
        votes = int(row.get(f"dugsu{i:02d}") or 0)
        pct = round(100 * votes / total, 2) if total > 0 else 0.0
        cs.append({"name": nm, "party": pty, "votes": votes, "pct": pct})
    cs.sort(key=lambda c: -c["votes"])
    for rank, c in enumerate(cs, 1):
        c["rank"] = rank
    if cs:
        cs[0]["won"] = True
    return cs


def normalize_race(meta: dict, sg_typecode: str, sd: str, sgg: str,
                   row: dict) -> dict:
    """한 row → 표준 race record.

    sd_name='합계' 호출 응답 — sgg='대한민국' wiw='합계' = nation race.
    sd_name='합계' 호출 응답 — sgg=시도명 wiw='합계' = 시도별 합계 (sd_name=시도 호출과 동일).
    sd_name=시도 호출 응답 — wiw='합계' = 시도 합계 (광역단체장 race 본체).
    sd_name=시도 호출 응답 — wiw=시군구명 = 시군구별 (기초단체장 race 본체 / 광역단체장 세부).
    """
    # 통합 시도 매핑 (전남광주 등)
    merges = {alias: m["canonical"]
              for m in meta.get("sido_merge", [])
              for alias in m.get("merge_from", [])}
    sd = merges.get(sd, sd)
    # nation row 식별 — '합계' 호출의 nation row.
    # 대선: sgg='대한민국' wiw='합계' / 비례: sgg='비례대표' wiw='합계'
    is_nation = (sgg in ("대한민국", "비례대표")) or (sd == "" and not sgg)
    if is_nation:
        scope = "nation"
        sido_out = ""
        sigungu_out = ""
    elif not sgg or sgg == "합계":
        scope = "sido"
        sido_out = sd
        sigungu_out = ""
    else:
        scope = "sigungu"
        sido_out = sd
        sigungu_out = sgg
    return {
        "sg_typecode": sg_typecode,
        "sido": sido_out,
        "sigungu": sigungu_out,
        "scope": scope,
        "electors": int(row.get("sunsu") or 0),
        "voters": int(row.get("tusu") or 0),
        "valid_votes": int(row.get("yutusu") or 0),
        "invalid_votes": int(row.get("mutusu") or 0),
        "abstain": int(row.get("gigwonsu") or 0),
        "candidates": parse_row_candidates(row),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--election", required=True, help="data/elections/{id}.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="첫 시도만 1회 호출 (전체 안 받음, 검증용)")
    ap.add_argument("--delay", type=float, default=0.3,
                    help="요청 간 지연 (NEC 부담 완화)")
    args = ap.parse_args()

    meta = load_election_meta(args.election)
    sg_id = meta.get("nec", {}).get("sg_id", "")
    if not sg_id:
        print(f"ERR: 메타에 nec.sg_id 없음", file=sys.stderr)
        sys.exit(1)
    api_key = _load_api_key()
    if not api_key:
        print("ERR: NEC_API_KEY 미설정 (.env)", file=sys.stderr)
        sys.exit(1)

    print(f"=== {meta['name']} (sg_id={sg_id}) 개표 결과 fetch ===", file=sys.stderr)
    offices = meta.get("offices", [])
    # 1=대통령, 2=국회의원, 3=광역단체장, 4=기초단체장, 7=비례대표, 11=교육감.
    # 5(광역의원)·6(기초의원)는 sd 단위 호출만으로는 race 식별 어려움 → 별도 처리 (TODO)
    target_offices = [o for o in offices
                      if o.get("sg_typecode") in ("1", "2", "3", "4", "7", "11")]
    print(f"  대상 office: {[o['level'] for o in target_offices]}", file=sys.stderr)
    print(f"  대상 시도: {len(ALL_SIDOS)}개", file=sys.stderr)

    all_races: list[dict] = []
    n_call = n_row = 0
    # nation scope race가 의미 있는 office (대선·총선 비례).
    # sd_name='합계' 호출 → sgg='대한민국' wiw='합계' row 1개 = 전국 race.
    # 시도별 호출 합산은 재외·관외 누락 → nation race가 정답.
    NATION_OFFICES = {"1", "7"}
    for office in target_offices:
        tc = office["sg_typecode"]
        if tc in NATION_OFFICES and not args.dry_run:
            nation_rows = fetch_xmntck(sg_id, tc, "합계", api_key)
            n_call += 1
            for row in nation_rows:
                # sgg='대한민국' wiw='합계' = 대선 nation race.
                # sgg='비례대표' wiw='합계' = 총선 비례 nation race.
                # 그 외 row(시도별)는 중복 → skip.
                if row.get("sggName") in ("대한민국", "비례대표"):
                    race = normalize_race(meta, tc, "", row.get("sggName", ""), row)
                    all_races.append(race)
                    n_row += 1
            print(f"  ✓ {office['level']} 전국 합계 nation race",
                  file=sys.stderr)
            time.sleep(args.delay)
        sidos = [ALL_SIDOS[0]] if args.dry_run else ALL_SIDOS
        for sd in sidos:
            rows = fetch_xmntck(sg_id, tc, sd, api_key)
            n_call += 1
            if rows and "_error" in rows[0]:
                print(f"  ✗ {office['level']} {sd}: {rows[0]['_error']}", file=sys.stderr)
                continue
            n_row += len(rows)
            for row in rows:
                race = normalize_race(meta, tc, sd, row.get("wiwName", ""), row)
                all_races.append(race)
            print(f"  ✓ {office['level']} {sd}: {len(rows)} rows",
                  file=sys.stderr)
            time.sleep(args.delay)

    # 옛 선거(선거일 < 오늘 - 7일)는 확정 결과. 신선거는 잠정 가능 → False.
    from datetime import date, timedelta
    try:
        ed = date.fromisoformat(meta["date"])
        is_final = ed < date.today() - timedelta(days=7)
    except Exception:
        is_final = False
    out = {
        "_meta": {
            "election": meta["name"],
            "election_id": meta["id"],
            "election_date": meta["date"],
            "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "is_final": is_final,
            "n_calls": n_call,
            "n_rows": n_row,
        },
        "races": all_races,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{args.election}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out_path.relative_to(ROOT)} ({len(all_races)} race rows, "
          f"{n_call} calls)", file=sys.stderr)


if __name__ == "__main__":
    main()
