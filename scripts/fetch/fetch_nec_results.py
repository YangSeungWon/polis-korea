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
  python3 scripts/fetch/fetch_nec_results.py --election 9th-local-2026 --dry-run
  python3 scripts/fetch/fetch_nec_results.py --election 9th-local-2026
  python3 scripts/fetch/fetch_nec_results.py --election 8th-local-2022  # 옛 선거 재수집
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

ROOT = Path(__file__).resolve().parents[2]
ELECTIONS_DIR = ROOT / "data/elections"
RESULTS_DIR = ROOT / "data/results"

API_BASE = "https://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2"
ENDPOINT_XMNTCK = "/getXmntckSttusInfoInqire"  # 개표 결과 (메인)
ENDPOINT_VOTE = "/getVoteSttusInfoInqire"      # 투표 결과 (투표율 등)

# NEC API가 받는 시도명은 sg_id 시점 기준. 옛 회차는 옛 명칭 써야 인식.
# 변경 이력:
#   2006-07-01: 제주도 → 제주특별자치도
#   2012-07-01: 세종특별자치시 신설 (없음 → 17개)
#   2023-06-11: 강원도 → 강원특별자치도
#   2024-01-18: 전라북도 → 전북특별자치도
#   2026-06-03: 광주광역시+전라남도 → 전남광주특별시 (메타 sido_merge로 처리)
# 통합 시도명을 쓰는 직 — 광역단체장(3)·교육감(11)·광역의원 비례(8).
# tc8은 통합 시도의회의 비례라 선거 자체가 하나다(광주·전남 어느 쪽으로 물어도 선거인수·
# 정당 득표가 완전히 같은 행이 온다). 지역구(tc5)·기초 단위(4·6·9)는 옛 시도별로 나뉘어
# 치러지므로 분리 유지.
SIDO_MERGE_TYPECODES = {"3", "8", "11"}


def sidos_for_sg_id(sg_id: str) -> list[str]:
    yyyymmdd = int(sg_id) if sg_id.isdigit() else 99999999
    base = ["서울특별시", "부산광역시", "대구광역시", "인천광역시",
            "광주광역시", "대전광역시", "울산광역시", "경기도",
            "충청북도", "충청남도", "전라남도", "경상북도", "경상남도"]
    # 세종특별자치시 신설은 2012-07-01이지만 NEC API는 19대 총선(2012-04)에도
    # 세종 데이터 보유 — 2012년 이후 항상 query. INFO-03 응답하면 자연 skip.
    if yyyymmdd >= 20120101:
        base.append("세종특별자치시")
    # NEC OpenAPI 시도명 일관성 없음 — 회차마다 옛/새 명칭 중 하나만 응답.
    # (16대 대선: 제주특별자치도만 OK, 17대 총선: 제주도만 OK 등)
    # 한 명칭만 fix할 수 없어 fetch wrapper가 두 명칭 순차 시도, INFO-00 받은 것 채택.
    base.append("강원특별자치도" if yyyymmdd >= 20230611 else "강원도")
    base.append("전북특별자치도" if yyyymmdd >= 20240118 else "전라북도")
    base.append("제주특별자치도")
    return base


# 시도명 fallback alias — 어떤 회차에 어떤 명칭이 응답될지 모름.
# fetch_xmntck_with_fallback가 두 명칭 순차 시도, INFO-00 받은 것 사용.
SIDO_NAME_ALIASES = {
    "제주특별자치도": ["제주특별자치도", "제주도"],
    "제주도":         ["제주도", "제주특별자치도"],
    "강원특별자치도": ["강원특별자치도", "강원도"],
    "강원도":         ["강원도", "강원특별자치도"],
    "전북특별자치도": ["전북특별자치도", "전라북도"],
    "전라북도":       ["전라북도", "전북특별자치도"],
}


# 호환용 default (legacy 호출 — main()는 sidos_for_sg_id 사용)
ALL_SIDOS = sidos_for_sg_id("99999999")


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


def _fetch_page(sg_id: str, sg_typecode: str, sd_name: str, api_key: str,
                page: int, num_rows: int = 100) -> tuple[int, list[dict]]:
    """한 page 호출. (totalCount, items) 반환."""
    # resultType=xml 필수 — 이 API의 기본 응답이 XML→JSON으로 바뀌어, 없으면 JSON이
    # 와서 ET.fromstring이 ParseError. 호출부가 예외를 삼켜 '0 rows'로 조용히 실패한다.
    params = {
        "serviceKey": api_key, "sgId": sg_id, "sgTypecode": sg_typecode,
        "sdName": sd_name, "numOfRows": num_rows, "pageNo": page,
        "resultType": "xml",
    }
    url = f"{API_BASE}{ENDPOINT_XMNTCK}?{urllib.parse.urlencode(params, safe='%')}"
    # NEC API는 간헐적으로 504/502를 낸다. 재시도 없이 두면 그 시도(sdName) 전체가
    # 통째로 빠진 채 파일이 써져, 실행할 때마다 race 수가 달라진다.
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                raw = r.read().decode("utf-8", errors="replace")
            break
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    else:
        raise last
    root = ET.fromstring(raw)
    total = int(root.findtext(".//totalCount", "0") or "0")
    result_code = root.findtext(".//resultCode", "")
    if result_code == "INFO-03":
        return 0, []
    items = [{c.tag: c.text for c in item} for item in root.findall(".//item")]
    return total, items


def fetch_xmntck(sg_id: str, sg_typecode: str, sd_name: str, api_key: str,
                 num_rows: int = 100) -> list[dict]:
    """한 (sg_id, sg_typecode, sd_name)의 개표 결과 — 페이지네이션 자동.

    NEC API max 100 row/page → totalCount 보고 추가 page 호출.
    옛 시도명·새 시도명 fallback: SIDO_NAME_ALIASES에 따라 두 명칭 순차 시도.
    """
    aliases = SIDO_NAME_ALIASES.get(sd_name, [sd_name])
    total, items, used_name = 0, [], sd_name
    last_err = None
    for alias in aliases:
        try:
            t, it = _fetch_page(sg_id, sg_typecode, alias, api_key, 1, num_rows)
        except Exception as e:
            last_err = e   # 통신·파싱 실패는 '데이터 없음'과 다르다 — 삼키지 않고 보고
            continue
        if t > 0 or it:
            total, items, used_name = t, it, alias
            break
    if not items:
        # 모든 alias가 예외로 죽었으면 빈 결과가 아니라 장애 — 호출부가 race를 건너뛰고
        # 빈 파일을 쓰지 않도록 _error를 올린다.
        return [{"_error": f"{type(last_err).__name__}: {last_err}"}] if last_err else []
    # 추가 page (page 2, 3, ...)
    page = 2
    while len(items) < total and page <= 20:  # 안전 cap
        try:
            _, more = _fetch_page(sg_id, sg_typecode, used_name, api_key, page, num_rows)
            if not more:
                break
            items.extend(more)
            page += 1
            time.sleep(0.15)
        except Exception:
            break
    return items


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


def normalize_race(meta: dict, sg_typecode: str, sd: str, sgg: str, wiw: str,
                   row: dict) -> dict:
    """한 row → 표준 race record.

    NEC API 응답 row 의미 (sg_typecode별):

    | tc | sgg | wiw | scope | sigungu | district |
    |----|-----|-----|-------|---------|----------|
    | 1 (대선) | '대한민국' (sd_name='합계') | '합계' | nation | '' | - |
    | 1 (대선) | '대한민국' (sd_name=시도) | '합계' | sido | '' | - |
    | 1 (대선) | '대한민국' (sd_name=시도) | 시군구명 | sigungu | wiw | - |
    | 2 (총선) | 지역구명 | '합계' | district | '' | sgg |
    | 2 (총선) | 지역구명 | 시군구명 | district_sigungu | wiw | sgg |
    | 3 (광역) | 시도명 | '합계' | sido | '' | - |
    | 3 (광역) | 시도명 | 시군구명 | sigungu | wiw | - |
    | 4 (기초) | 시군구명 | '합계' | sigungu | sgg | - |
    | 4 (기초) | 시군구명 | 시군구명 (=sgg) | sigungu_part | wiw | - |
    | 7 (비례) | '비례대표' | '합계' | nation | '' | - |
    | 7 (비례) | '비례대표' (sd_name=시도) | 시군구명 | sigungu | wiw | - |
    | 11 (교육감) | 시도명 | '합계' | sido | '' | - |
    | 11 (교육감) | 시도명 | 시군구명 | sigungu | wiw | - |
    """
    # 통합 시도 매핑 (전남광주 등) — 시도 단위로 1명을 뽑는 직(광역단체장·교육감)에만
    # 적용한다. 기초단체장·광역의원·기초의원·비례는 통합 뒤에도 옛 시도별로 나뉘어
    # 치러지므로 '광주광역시'/'전라남도'를 그대로 유지해야 한다(당선인 명부·hex 레이아웃
    # 모두 분리 표기 기준). 전 직에 일괄 적용하면 명부와 시도명이 어긋나 매칭이 깨진다.
    if sg_typecode in SIDO_MERGE_TYPECODES:
        merges = {alias: m["canonical"]
                  for m in meta.get("sido_merge", [])
                  for alias in m.get("merge_from", [])}
        sd = merges.get(sd, sd)

    out = {
        "sg_typecode": sg_typecode,
        "sido": sd,
        "sigungu": "",
        "scope": "sido",
        "electors": int(row.get("sunsu") or 0),
        "voters": int(row.get("tusu") or 0),
        "valid_votes": int(row.get("yutusu") or 0),
        "invalid_votes": int(row.get("mutusu") or 0),
        "abstain": int(row.get("gigwonsu") or 0),
        "candidates": parse_row_candidates(row),
    }

    # nation row: sd_name='합계' 호출의 sgg='대한민국'(대선) / '비례대표'(비례)
    if sgg in ("대한민국", "비례대표") and wiw == "합계" and (not sd or sd == "합계"):
        out["sido"] = ""
        out["scope"] = "nation"
        return out

    # 총선 국회의원 (tc=2): sgg가 지역구명
    if sg_typecode == "2":
        out["district"] = sgg
        if wiw == "합계":
            out["scope"] = "district"
        else:
            out["scope"] = "district_sigungu"
            out["sigungu"] = wiw
        return out

    # 기초단체장 (tc=4): sgg가 시군구명
    if sg_typecode == "4":
        out["sigungu"] = sgg
        out["scope"] = "sigungu" if wiw == "합계" else "sigungu_part"
        return out

    # 광역의원 (tc=5) · 기초의원 (tc=6): sgg가 선거구명
    # wiw='합계' → district 합계, wiw=시군구명 → district_sigungu sub-row
    if sg_typecode in ("5", "6"):
        out["district"] = sgg
        if wiw == "합계":
            out["scope"] = "district"
        else:
            out["scope"] = "district_sigungu"
            out["sigungu"] = wiw
        return out

    # 광역의원 비례 (tc=8): sgg=시도명. wiw='합계' → 시도 비례 race,
    # wiw=시군구 → 그 시도 비례의 시군구별 분해.
    if sg_typecode == "8":
        if wiw == "합계":
            out["scope"] = "proportional_sido"
        else:
            out["scope"] = "proportional_sido_sigungu"
            out["sigungu"] = wiw
        return out

    # 기초의원 비례 (tc=9): sgg=시군구명. wiw='합계' → 그 시군구 비례 race,
    # wiw=일반구 → 분해(창원시의창구 등). 일반구가 없는 시군구는 sgg와 같은 이름의
    # 행이 합계와 값까지 똑같이 한 번 더 오므로 호출부에서 걸러진다.
    if sg_typecode == "9":
        out["sigungu"] = sgg
        if wiw == "합계":
            out["scope"] = "proportional_sigungu"
        else:
            out["scope"] = "proportional_sigungu_part"
            out["sigungu_part"] = wiw
        return out

    # 그 외 (tc=1,3,7,11): sgg가 시도명·대한민국·비례대표·sd_name 결정
    # wiw='합계' → 시도 race / wiw=시군구 → 시군구 race
    if wiw == "합계":
        out["scope"] = "sido"
    else:
        out["scope"] = "sigungu"
        out["sigungu"] = wiw
    return out


def inject_uncontested(election_id: str, races: list[dict]) -> int:
    """무투표 당선 race를 새 schema에 추가. 추가 건수 반환.

    NEC 개표 API는 투표 진행 지역만 응답 → 단독 후보 등록으로 자동 당선된
    지역구는 누락. data/raw/nec_uncontested/{n}.json에서 inject.
    파일 schema: [{sido, name, winner, winner_party}, ...]
    """
    # election_id에서 회차 n 추출 ('22nd-general-2024' → 22)
    parts = election_id.split("-")
    if len(parts) < 3 or parts[1] not in ("general", "local", "pres"):
        return 0
    ordinal = parts[0]  # '22nd', '21st', ...
    try:
        n = int(''.join(c for c in ordinal if c.isdigit()))
    except ValueError:
        return 0
    # 총선만 무투표 캐시 보유 (지선은 별도, 대선은 없음)
    if parts[1] != "general":
        return 0
    p = ROOT / f"data/raw/nec_uncontested/{n}.json"
    if not p.exists():
        return 0
    try:
        uc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return 0
    existing = {(r.get("sido", ""), r.get("district", "")) for r in races
                if r.get("scope") == "district"}
    added = 0
    for entry in uc:
        key = (entry.get("sido", ""), entry.get("name", ""))
        if not key[1] or key in existing:
            continue
        races.append({
            "sg_typecode": "2",
            "sido": entry["sido"],
            "sigungu": "",
            "district": entry["name"],
            "scope": "district",
            "electors": 0,
            "voters": 0,
            "valid_votes": 0,
            "invalid_votes": 0,
            "abstain": 0,
            "candidates": [{
                "name": entry["winner"],
                "party": entry.get("winner_party", ""),
                "votes": 0,
                "pct": 100.0,
                "rank": 1,
                "won": True,
                "uncontested": True,
            }],
            "_source": "nec_uncontested",
        })
        added += 1
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--election", required=True, help="data/elections/{id}.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="첫 시도만 1회 호출 (전체 안 받음, 검증용)")
    ap.add_argument("--delay", type=float, default=0.3,
                    help="요청 간 지연 (NEC 부담 완화)")
    ap.add_argument("--force", action="store_true",
                    help="race 급감(기존의 50% 미만)에도 덮어쓰기")
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
    # 8·9(광역/기초 비례)도 개표 API가 제공한다 — 정당별 득표·투표율까지 온다.
    # (예전엔 제외돼 있어 비례만 라이브 산출물을 이관해 써야 했다.) 의석 배분은
    # 개표 API에 없으므로 당선인 명부 오버레이가 이어서 채운다.
    target_offices = [o for o in offices
                      if o.get("sg_typecode") in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "11")]
    sidos_at_sg = sidos_for_sg_id(sg_id)
    print(f"  대상 office: {[o['level'] for o in target_offices]}", file=sys.stderr)
    print(f"  대상 시도: {len(sidos_at_sg)}개 ({sg_id} 시점)", file=sys.stderr)

    all_races: list[dict] = []
    failures: list[str] = []
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
                    race = normalize_race(meta, tc, "", row.get("sggName", ""),
                                          row.get("wiwName", ""), row)
                    all_races.append(race)
                    n_row += 1
            print(f"  ✓ {office['level']} 전국 합계 nation race",
                  file=sys.stderr)
            time.sleep(args.delay)
        sidos = [sidos_at_sg[0]] if args.dry_run else sidos_at_sg
        for sd in sidos:
            rows = fetch_xmntck(sg_id, tc, sd, api_key)
            n_call += 1
            if rows and "_error" in rows[0]:
                print(f"  ✗ {office['level']} {sd}: {rows[0]['_error']}", file=sys.stderr)
                failures.append(f"{office['level']}/{sd}")
                continue
            n_row += len(rows)
            for row in rows:
                sgg, wiw = row.get("sggName", ""), row.get("wiwName", "")
                # tc9에서 일반구가 없는 시군구는 '합계' 행과 값까지 동일한 자기 이름 행이
                # 한 번 더 온다(부산 중구 → (중구,합계)·(중구,중구)). 분해가 아니라 중복.
                if tc == "9" and wiw == sgg:
                    continue
                race = normalize_race(meta, tc, sd, sgg, wiw, row)
                all_races.append(race)
            print(f"  ✓ {office['level']} {sd}: {len(rows)} rows",
                  file=sys.stderr)
            time.sleep(args.delay)

    # 한 시도라도 통신 실패면 결과가 조용히 불완전해진다 — 부분 결과로 덮어쓰지 않는다.
    if failures and not args.force:
        print(f"\n✗ 중단: {len(failures)}개 호출 실패 — {', '.join(failures[:5])}"
              f"{' 외' if len(failures) > 5 else ''}\n"
              f"  부분 결과로 덮어쓰지 않음. 재실행하거나 --force.", file=sys.stderr)
        sys.exit(1)

    # 통합 시도(예: 전남광주특별시)는 구 시도 두 이름 모두로 호출되어 같은 race가 두 번
    # 수집된다. 내용까지 완전히 같은 row만 제거 — 일반구 부분집계(sigungu_part)처럼
    # 키는 같지만 내용이 다른 정상 row는 건드리지 않는다.
    seen: set[str] = set()
    deduped = []
    for r in all_races:
        sig = json.dumps(r, sort_keys=True, ensure_ascii=False)
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append(r)
    if len(deduped) != len(all_races):
        print(f"  ✓ 통합 시도 중복 제거: {len(all_races) - len(deduped)}건", file=sys.stderr)
        all_races = deduped

    # 옛 선거(선거일 < 오늘 - 7일)는 확정 결과. 신선거는 잠정 가능 → False.
    from datetime import date, timedelta
    try:
        ed = date.fromisoformat(meta["date"])
        is_final = ed < date.today() - timedelta(days=7)
    except Exception:
        is_final = False
    # 무투표 당선 backfill — NEC 개표 API는 투표 있는 지역만 반환.
    # 무투표 당선 지역은 data/raw/nec_uncontested/{n}.json에서 inject (총선만).
    uc_added = inject_uncontested(args.election, all_races)
    if uc_added:
        n_row += uc_added
        print(f"  ✓ 무투표 당선 backfill: {uc_added}건", file=sys.stderr)

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
    # 회귀 방어: 이 스크립트는 파일을 전면 교체한다. API 장애·응답 포맷 변경으로 race가
    # 0건이거나 기존의 절반 미만이면 덮어쓰지 않는다. --force로만 통과.
    if out_path.exists() and not args.force:
        try:
            prev = len(json.loads(out_path.read_text(encoding="utf-8")).get("races", []))
        except Exception:
            prev = 0
        if prev and len(all_races) < prev * 0.5:
            print(f"\n✗ 중단: race {prev} → {len(all_races)} (50% 미만). 기존 파일 유지.\n"
                  f"  API 장애/포맷 변경 의심. 의도한 축소면 --force.", file=sys.stderr)
            sys.exit(1)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out_path.relative_to(ROOT)} ({len(all_races)} race rows, "
          f"{n_call} calls)", file=sys.stderr)


if __name__ == "__main__":
    main()
