"""NEC 선거공약 API(ElecPrmsInfoInqireService) → data/pledges/{election_id}.json.

당선인의 선거공약서 공약(분야·제목·내용)을 회차별로 수집한다.

제약 (실측 확인):
  · 공약서 제출 대상은 sg_typecode 1(대통령)·3(시도지사)·4(구시군의장)·11(교육감)뿐.
    총선·지방의원·비례는 아예 없다.
  · **종료된 선거는 당선인 공약만** 제공된다. 낙선자 공약은 선거 기간에만 받을 수 있고
    끝나면 영구히 사라진다(20대 대선 이재명 → INFO-03 확인). 후보 간 공약 비교가
    필요하면 선거 기간 중에 별도로 회수해 둬야 한다.
  · 2017년(19대 대선)이 하한선. 2014년 6회 지선·2007년 17대 대선은 INFO-03.

조인 키: cnddtId = WinnerInfoInqireService2의 huboid. 당선인 명부에서 huboid를 받아
        공약 API에 넣는 2단 구조다.

함정: 공약 본문 필드는 문서상 prmsCont{i}이나 실제 응답은 prmmCont{i}다. 둘 다 읽는다.

사용:
  python3 scripts/fetch/fetch_pledges.py                      # 대상 회차 전체
  python3 scripts/fetch/fetch_pledges.py --election 9th-local-2026
  python3 scripts/fetch/fetch_pledges.py --dry-run            # 회차·인원만 출력
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


def targets(only: str | None) -> list[dict]:
    """공약 회수 대상 (선거 메타, 직 목록)."""
    out = []
    for p in sorted(ELECTIONS_DIR.glob("*.json")):
        meta = json.loads(p.read_text(encoding="utf-8"))
        if only and meta.get("id") != only:
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
    ap.add_argument("--dry-run", action="store_true", help="대상 회차·당선인 수만 출력")
    ap.add_argument("--delay", type=float, default=0.25, help="요청 간 지연")
    args = ap.parse_args()

    key = _load_api_key()
    if not key:
        print("ERR: NEC_API_KEY 미설정 (.env)", file=sys.stderr)
        sys.exit(1)

    tg = targets(args.election)
    if not tg:
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
        people, n_pledge, empty = [], 0, 0
        if fp.exists() and not args.dry_run:
            prev = json.loads(fp.read_text(encoding="utf-8"))
            people = prev.get("people", [])
            n_pledge = sum(len(p.get("pledges") or []) for p in people)
            empty = int((prev.get("_meta") or {}).get("n_without_pledges") or 0)
        done = {p["cnddt_id"] for p in people}
        for tc in t["typecodes"]:
            ws = fetch_winners(key, sg_id, tc)
            if not ws:
                print(f"  {meta['id']} tc{tc}: 당선인 명부 없음 — skip", file=sys.stderr)
                continue
            if args.dry_run:
                print(f"  {meta['id']} tc{tc}: 당선인 {len(ws)}명 [dry]", file=sys.stderr)
                continue
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
                "scope": "winners_only",
                "_note": "종료된 선거는 당선인 공약만 제공된다 — 낙선자 공약은 API에 없음",
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
