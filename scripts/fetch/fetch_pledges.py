"""NEC 선거공약 API(ElecPrmsInfoInqireService) → data/pledges/{election_id}.json.

당선인의 선거공약서 공약(분야·제목·내용)을 회차별로 수집한다.

제약 (실측 확인):
  · 공약서 제출 대상은 sg_typecode 1(대통령)·3(시도지사)·4(구시군의장)·11(교육감)뿐.
    총선·지방의원·비례는 아예 없다.
  · **낙선자 공약은 시한부다.** 문서는 "종료된 선거는 당선인 공약만"이라고 하지만
    실제로는 선거 후 한동안 남아 있다가 사라진다. 2026-08-04 기준 실측:
        9회 지선(2026-06, 2개월 전)  → 낙선자 공약 살아 있음
        21대 대선(2025-06, 14개월 전) → 없음
        8회·7회 지선(2022·2018)       → 없음
    소멸 시점은 2개월~14개월 사이 어딘가다. 한 번 사라지면 복구 수단이 없으므로
    **선거가 끝나면 되도록 빨리** --all-candidates로 훑어 둬야 한다(0단계).
  · 2017년(19대 대선)이 하한선. 2014년 6회 지선·2007년 17대 대선은 INFO-03.

조인 키: cnddtId = 명부 API의 huboid. 명부에서 huboid를 받아 공약 API에 넣는 2단 구조.
  · 당선인 명부  WinnerInfoInqireService2      — 사후 백필용(3단계)
  · 등록 후보 명부 PofelcddInfoInqireService    — 선거 기간 캡처용(0단계·낙선자 포함)

함정: 공약 본문 필드는 문서상 prmsCont{i}이나 실제 응답은 prmmCont{i}다. 둘 다 읽는다.

사용:
  # 3단계 — 끝난 선거 당선인 백필
  python3 scripts/fetch/fetch_pledges.py
  python3 scripts/fetch/fetch_pledges.py --election 9th-local-2026

  # 0단계 — 선거 기간 중 전 후보 캡처 (이때만 낙선자 공약을 잡을 수 있다)
  python3 scripts/fetch/fetch_pledges.py --active --all-candidates

이어받기: 기존 파일의 인물은 건너뛰고 새로 등록된 후보만 받는다. 0단계로 잡아 둔
낙선자는 이후 당선인 백필이 돌아도 지워지지 않는다(_meta.scope도 all_candidates 유지).
"""
from __future__ import annotations
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ELECTIONS_DIR = ROOT / "data/elections"
OUT_DIR = ROOT / "data/pledges"

BASE = "https://apis.data.go.kr/9760000"
WINNER = f"{BASE}/WinnerInfoInqireService2/getWinnerInfoInqire"
# 전 후보 등록 명부 — 당선인 명부와 달리 낙선자까지 huboid로 열거된다.
# 낙선자 공약은 선거가 끝나면 사라지므로 '선거 기간 중' 캡처(0단계)는 이걸 써야 한다.
CANDIDATE = f"{BASE}/PofelcddInfoInqireService/getPofelcddRegistSttusInfoInqire"
PLEDGE = f"{BASE}/ElecPrmsInfoInqireService/getCnddtElecPrmsInfoInqire"

# 선거공약서 제출 대상 직.
PLEDGE_TYPECODES = ("1", "3", "4", "11")
# API 보유 하한 — 이전 회차는 전부 INFO-03이라 호출 낭비를 막는다.
MIN_SG_ID = "20170101"
# 응답이 담는 공약 슬롯 수 (prmsOrd1..10).
MAX_SLOTS = 10

# NEC 서버가 특정 레코드에서 재현성 있게 500x를 낸다 — 클라이언트로는 회피 불가
# (XML·JSON·numOfRows 무관하게 502). 실패로 계속 잡지 말고 알려진 결손으로 넘긴다.
# 해소되면 이 목록에서 지우면 자동으로 다시 받는다.
KNOWN_UPSTREAM_ERROR = {
    "100162500": "9회 대구 교육감 강은희 — NEC API 502 (2026-08-04 확인)",
    "100153751": "9회 경남 교육감 오인태 — NEC API 502 (2026-08-04 확인)",
}


def _load_api_key() -> str:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("NEC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    import os
    return os.environ.get("NEC_API_KEY", "")


def _get(url: str) -> ET.Element:
    """NEC API는 간헐적으로 502/504를 낸다 — 재시도 없이 두면 그 직이 통째로 빠진다."""
    last = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return ET.fromstring(r.read().decode("utf-8", errors="replace"))
        except Exception as e:
            last = e
            time.sleep(min(2 ** attempt, 20))
    raise last


def fetch_winners(key: str, sg_id: str, tc: str) -> list[dict]:
    """당선인 명부 전체 — cnddtId(huboid) 확보용. 페이지네이션 자동."""
    out, page = [], 1
    while page <= 20:
        url = (f"{WINNER}?serviceKey={key}&sgId={sg_id}&sgTypecode={tc}"
               f"&pageNo={page}&numOfRows=100&resultType=xml")
        root = _get(url)
        if root.findtext(".//resultCode") != "INFO-00":
            break
        items = root.findall(".//item")
        if not items:
            break
        for it in items:
            g = lambda t: (it.findtext(t) or "").strip()
            out.append({"cnddt_id": g("huboid"), "name": g("name"), "party": g("jdName"),
                        "sido": g("sdName"), "sigungu": g("wiwName"), "sgg_name": g("sggName")})
        total = int(root.findtext(".//totalCount") or 0)
        if page * 100 >= total:
            break
        page += 1
    return out


def fetch_candidates(key: str, sg_id: str, tc: str) -> list[dict]:
    """등록 후보 전체(낙선자 포함) — 0단계 캡처용. 페이지네이션 자동."""
    out, page = [], 1
    while page <= 60:
        url = (f"{CANDIDATE}?serviceKey={key}&sgId={sg_id}&sgTypecode={tc}"
               f"&pageNo={page}&numOfRows=100&resultType=xml")
        root = _get(url)
        if root.findtext(".//resultCode") != "INFO-00":
            break
        items = root.findall(".//item")
        if not items:
            break
        for it in items:
            g = lambda t: (it.findtext(t) or "").strip()
            out.append({"cnddt_id": g("huboid"), "name": g("name"), "party": g("jdName"),
                        "sido": g("sdName"), "sigungu": g("wiwName"), "sgg_name": g("sggName")})
        total = int(root.findtext(".//totalCount") or 0)
        if page * 100 >= total:
            break
        page += 1
    return out


def fetch_pledges(key: str, sg_id: str, tc: str, cnddt_id: str) -> tuple[list[dict], str]:
    """한 사람의 공약 리스트. (pledges, resultCode)."""
    url = (f"{PLEDGE}?serviceKey={key}&sgId={sg_id}&sgTypecode={tc}"
           f"&cnddtId={cnddt_id}&pageNo=1&numOfRows={MAX_SLOTS}&resultType=xml")
    root = _get(url)
    code = root.findtext(".//resultCode") or "?"
    it = root.find(".//item")
    if code != "INFO-00" or it is None:
        return [], code
    g = lambda t: (it.findtext(t) or "").strip()
    out = []
    for i in range(1, MAX_SLOTS + 1):
        title = g(f"prmsTitle{i}")
        # 문서는 prmsCont{i}, 실제 응답은 prmmCont{i} — 둘 다 시도.
        content = g(f"prmmCont{i}") or g(f"prmsCont{i}")
        realm = g(f"prmsRealmName{i}")
        if not (title or content):
            continue
        out.append({"order": int(g(f"prmsOrd{i}") or i), "realm": realm,
                    "title": title, "content": content})
    declared = int(g("prmsCnt") or 0)
    if declared > MAX_SLOTS:
        print(f"    ! prmsCnt={declared} > 슬롯 {MAX_SLOTS} — 잘림 가능", file=sys.stderr)
    return out, code


def targets(only: str | None, active_only: bool) -> list[dict]:
    """공약 회수 대상 (선거 메타, 직 목록)."""
    active = set()
    if active_only:
        idx = json.loads((ELECTIONS_DIR / "index.json").read_text(encoding="utf-8"))
        active = set(idx.get("active") or [])
    out = []
    for p in sorted(ELECTIONS_DIR.glob("*.json")):
        if p.name == "index.json":
            continue
        meta = json.loads(p.read_text(encoding="utf-8"))
        if only and meta.get("id") != only:
            continue
        if active_only and meta.get("id") not in active:
            continue
        sg_id = (meta.get("nec") or {}).get("sg_id", "")
        if not sg_id or sg_id < MIN_SG_ID:
            continue
        tcs = [o["sg_typecode"] for o in meta.get("offices", [])
               if o.get("sg_typecode") in PLEDGE_TYPECODES]
        if tcs:
            out.append({"meta": meta, "sg_id": sg_id, "typecodes": tcs})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--election", help="특정 회차만 (data/elections/{id}.json)")
    ap.add_argument("--dry-run", action="store_true", help="대상 회차·인원만 출력")
    ap.add_argument("--all-candidates", action="store_true",
                    help="당선인이 아니라 등록 후보 전체 (0단계 — 선거 기간 중에만 유효)")
    ap.add_argument("--active", action="store_true",
                    help="elections/index.json의 active 회차만 (0단계 자동화용)")
    ap.add_argument("--delay", type=float, default=0.25, help="요청 간 지연")
    args = ap.parse_args()

    key = _load_api_key()
    if not key:
        print("ERR: NEC_API_KEY 미설정 (.env)", file=sys.stderr)
        sys.exit(1)

    tg = targets(args.election, args.active)
    if not tg:
        if args.active:
            # 진행 중인 선거가 없는 평시 — 정상 상태다. 매일 도는 잡을 실패시키지 않는다.
            print("active 회차 없음 — 할 일 없음", file=sys.stderr)
            return
        print("대상 회차 없음 — --election 오타이거나 2017년 이전", file=sys.stderr)
        sys.exit(1)
    print(f"=== 공약 회수 대상 {len(tg)}개 회차 ===", file=sys.stderr)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    grand_people = grand_pledges = 0
    failures: list[str] = []
    known: list[str] = []
    for t in tg:
        meta, sg_id = t["meta"], t["sg_id"]
        fp = OUT_DIR / f"{meta['id']}.json"
        # 이어받기 — 이미 회수한 사람은 건너뛴다. NEC가 502를 내도 진행분이 남는다.
        people, n_pledge, empty, prev_scope, n_roster = [], 0, 0, None, 0
        if fp.exists() and not args.dry_run:
            prev = json.loads(fp.read_text(encoding="utf-8"))
            people = prev.get("people", [])
            prev_scope = (prev.get("_meta") or {}).get("roster_scope")
            n_pledge = sum(len(p.get("pledges") or []) for p in people)
            empty = int((prev.get("_meta") or {}).get("n_without_pledges") or 0)
        done = {p["cnddt_id"] for p in people}
        roster = "등록 후보" if args.all_candidates else "당선인"
        for tc in t["typecodes"]:
            ws = (fetch_candidates(key, sg_id, tc) if args.all_candidates
                  else fetch_winners(key, sg_id, tc))
            if not ws:
                print(f"  {meta['id']} tc{tc}: {roster} 명부 없음 — skip", file=sys.stderr)
                continue
            if args.dry_run:
                print(f"  {meta['id']} tc{tc}: {roster} {len(ws)}명 [dry]", file=sys.stderr)
                continue
            n_roster += len(ws)
            got = skipped = 0
            for w in ws:
                if w["cnddt_id"] in done:
                    skipped += 1
                    continue
                if w["cnddt_id"] in KNOWN_UPSTREAM_ERROR:
                    known.append(f"{w['name']}: {KNOWN_UPSTREAM_ERROR[w['cnddt_id']]}")
                    continue
                try:
                    pl, code = fetch_pledges(key, sg_id, tc, w["cnddt_id"])
                except Exception as e:
                    # 재시도를 다 쓴 실패 — 조용히 넘기지 않고 기록해 끝에 보고한다.
                    failures.append(f"{meta['id']}/tc{tc}/{w['name']}({w['cnddt_id']}): {e}")
                    continue
                if pl:
                    people.append({**w, "sg_typecode": tc, "pledges": pl})
                    n_pledge += len(pl)
                    got += 1
                else:
                    empty += 1
                done.add(w["cnddt_id"])
                time.sleep(args.delay)
            msg = f"  {meta['id']} tc{tc}: 당선인 {len(ws)} → 공약 보유 {got}"
            print(msg + (f" (이어받기 skip {skipped})" if skipped else ""), file=sys.stderr)
        if args.dry_run or not people:
            continue
        out = {
            "_meta": {
                "election": meta["name"], "election_id": meta["id"],
                "election_date": meta["date"], "sg_id": sg_id,
                "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "source": "nec-openapi-ElecPrmsInfoInqireService",
                # 어느 명부로 훑었는지. 한 번이라도 전 후보로 받았으면 유지한다 — 나중에
                # 당선인 백필이 돌아도 이미 잡아 둔 낙선자 공약의 가치를 지우지 않기 위해.
                # '전 후보를 훑었다'와 '전 후보 공약을 가졌다'는 다르다 — 선거가 끝난 뒤
                # 훑으면 낙선자는 INFO-03이라 n_roster와 n_people 격차로 드러난다.
                "roster_scope": ("all_candidates"
                                 if (args.all_candidates or prev_scope == "all_candidates")
                                 else "winners_only"),
                "n_roster": n_roster,
                "_note": "종료된 선거는 당선인 공약만 제공된다 — 낙선자 공약은 선거 기간 중에만 회수 가능",
                "n_people": len(people), "n_pledges": n_pledge,
                "n_without_pledges": empty,
            },
            "people": people,
        }
        fp.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  → {fp.relative_to(ROOT)} ({len(people)}명 · 공약 {n_pledge}건)", file=sys.stderr)
        grand_people += len(people)
        grand_pledges += n_pledge

    if args.dry_run:
        return
    print(f"\n완료: {grand_people}명 · 공약 {grand_pledges}건", file=sys.stderr)
    if known:
        print(f"\n⚠ 알려진 NEC 서버 결함으로 미회수 {len(known)}건:", file=sys.stderr)
        for k in known:
            print(f"    {k}", file=sys.stderr)
    if failures:
        print(f"\n✗ 회수 실패 {len(failures)}건 — 재실행하면 이어받는다:", file=sys.stderr)
        for f in failures[:10]:
            print(f"    {f}", file=sys.stderr)
        if len(failures) > 10:
            print(f"    … 외 {len(failures) - 10}건", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
