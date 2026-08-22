"""URL Inspection — '노출 0'을 미색인과 '색인됐지만 안 뜬 것'으로 가른다.

fetch_gsc.py가 남긴 inspect_queue.txt는 **후보 목록**이다. 노출 0은 미색인의 증거가
아니라 둘 중 하나다: 진짜 색인이 안 됐거나, 색인은 됐는데 한 번도 순위에 못 들었거나.
그 둘은 대응이 완전히 다르다(전자는 우리 문제, 후자는 경쟁 문제). 가르는 건
coverageState 하나뿐이고, 그걸 묻는 API가 여기다.

쿼터가 이 스크립트의 전부다:

    속성당 2,000/일 · 600/분

  4,870쪽이면 사흘이다. 그래서 **재개 가능**해야 한다 — 결과를 inspection.json에
  누적하고, 이미 물어본 URL은 건너뛴다. 중간에 죽어도 다음 실행이 이어서 간다.
  하루 상한을 넘기면 429가 오는데, 그때는 멈추고 지금까지 것을 저장한다(버리지 않는다).

층 표본:
  person이 4,198로 86%라 순서대로 물으면 사흘 내내 person만 본다. 작은 층(main·polls·
  history·archive·party·region 합쳐 672)을 먼저 전부 채우고 person을 표본으로 섞는다.
  '어느 층이 막혔나'가 질문이므로, 층 하나를 완주하는 것보다 모든 층에 답이 있는 게 낫다.

결손(docs/absence.md):
  물어본 URL만 적는다. 안 물어본 URL은 inspection.json에 없다 — '모른다'와 '미색인'을
  같은 자리에 적지 않는다. verdict/coverageState가 비면 그 값도 그대로 비워 둔다.

사용:
  GSC_SA_JSON_FILE=~/key.json python scripts/fetch/fetch_gsc_inspect.py --limit 1200
  python scripts/fetch/fetch_gsc_inspect.py --report        # 물어본 것만 집계
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "seo"
STORE = OUT / "inspection.json"
QUEUE = OUT / "inspect_queue.txt"
ENDPOINT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
SITE = "https://polis.ysw.kr"

# 600/분 = 0.1초에 하나. 여유를 둬서 0.15 — 어차피 하루 상한(2,000)이 먼저 걸린다.
PACE = 0.15
DAILY = 2000
TODAY = date.today().isoformat()

# 작은 층부터 전부 채우고 person은 표본. person 86%가 나머지 전부를 가린다.
SMALL = ("main", "polls", "history", "archive", "party", "region")


def layer_map() -> dict[str, str]:
    m = {}
    for f in sorted(ROOT.glob("sitemap-*.xml")):
        layer = f.stem.replace("sitemap-", "")
        root = ET.fromstring(f.read_text(encoding="utf-8"))
        for loc in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
            m[unquote(urlsplit(loc.text or "").path or "/")] = layer
    return m


def load() -> dict:
    return json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {}


def save(store: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(store, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                     encoding="utf-8")


def pick(queue: list[str], store: dict, layers: dict[str, str], limit: int) -> list[str]:
    """작은 층 먼저 전부, 남는 자리에 person을 고르게 뿌린다."""
    todo = [p for p in queue if p not in store]
    small = [p for p in todo if layers.get(p) in SMALL]
    person = [p for p in todo if layers.get(p) == "person"]
    out = small[:limit]
    room = limit - len(out)
    if room > 0 and person:
        # 앞에서부터 자르면 가나다순 앞쪽만 본다 — 고르게 뽑아야 층 대표성이 생긴다.
        step = max(1, len(person) // room)
        out += person[::step][:room]
    return out


def refresh_targets(store: dict, layers: dict[str, str], n: int) -> list[str]:
    """가장 오래전에 물어본 것부터, 층을 고르게 섞어 n쪽.

    한 층만 다시 물으면 '이 층이 움직였다'는 알아도 '다른 층은 안 움직였다'는 못
    말한다. 움직임 없음도 결과이므로 층마다 표본이 있어야 한다.
    """
    by: dict[str, list[str]] = {}
    for p in sorted(store, key=lambda x: store[x].get("asked") or ""):
        by.setdefault(layers.get(p, "?"), []).append(p)
    out, i = [], 0
    while len(out) < n and any(by.values()):
        for layer in sorted(by):
            if by[layer] and len(out) < n:
                out.append(by[layer].pop(0))
        i += 1
        if i > n:
            break
    return out


def inspect(sess, site: str, path: str) -> dict | None:
    url = SITE + quote(path)
    for attempt in range(4):
        r = sess.post(ENDPOINT, json={"inspectionUrl": url, "siteUrl": site,
                                      "languageCode": "ko"})
        if r.status_code == 200:
            x = r.json().get("inspectionResult", {}).get("indexStatusResult", {})
            return {k: x.get(k) for k in
                    ("verdict", "coverageState", "robotsTxtState", "indexingState",
                     "pageFetchState", "lastCrawlTime", "googleCanonical", "userCanonical")}
        if r.status_code == 429:
            return None          # 쿼터 — 멈춘다. 지금까지 것은 호출자가 저장한다.
        if r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        print(f"  ! {path} HTTP {r.status_code} {r.text[:160]}", file=sys.stderr)
        return {"error": r.status_code}
    return {"error": "5xx"}


def report(store: dict, layers: dict[str, str]) -> None:
    """물어본 것만 집계한다 — 안 물어본 URL은 분모에도 안 들어간다."""
    by = {}
    for p, v in store.items():
        by.setdefault(layers.get(p, "?"), Counter())[v.get("coverageState") or "(응답없음)"] += 1
    print(f"\n물어본 {len(store)}쪽 · 층별 coverageState")
    for layer in sorted(by):
        c = by[layer]
        print(f"\n  {layer}  ({sum(c.values())}쪽)")
        for state, n in c.most_common():
            print(f"    {n:>5}  {state}")
    # coverageState는 languageCode를 따라 번역돼 온다(우리는 ko). 문자열로 세면
    # locale이 바뀌는 순간 조용히 0이 된다 — verdict는 PASS/NEUTRAL/FAIL로 고정이다.
    v = Counter(x.get("verdict") or "(없음)" for x in store.values())
    print(f"\n  verdict — " + " · ".join(f"{k} {n}" for k, n in v.most_common()))
    print(f"  물어본 것 중 색인됨(PASS): {v.get('PASS', 0)} / {len(store)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=DAILY,
                    help=f"이번 실행에서 물어볼 수. 속성당 하루 {DAILY}")
    ap.add_argument("--refresh", type=int, default=0, metavar="N",
                    help="이미 물어본 것 중 N쪽을 다시 묻는다(움직였는지 확인). "
                         "--limit과 별도 예산이며 같은 하루 쿼터를 쓴다")
    ap.add_argument("--report", action="store_true", help="묻지 않고 저장된 것만 집계")
    ap.add_argument("--site", help="siteUrl 강제")
    args = ap.parse_args()

    layers = layer_map()
    store = load()
    moved: list = []

    if args.report:
        report(store, layers)
        return 0

    if not QUEUE.exists():
        sys.exit("inspect_queue.txt 없음 — fetch_gsc.py 먼저")
    queue = [p for p in QUEUE.read_text(encoding="utf-8").splitlines() if p.strip()]

    # 인증·속성 해석은 fetch_gsc.py 것을 그대로 쓴다(두 벌 두면 어긋난다).
    spec = importlib.util.spec_from_file_location(
        "gsc", ROOT / "scripts/fetch/fetch_gsc.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    sess = g.session()
    site = g.resolve_site(sess, args.site)

    targets = pick(queue, store, layers, args.limit)
    # 재조회는 **이전 답을 지우지 않고** 옆에 적는다 — 움직임은 두 시점이 다 있어야
    # 보인다. 덮어쓰면 '어제 뭐였더라'가 사라지고 다음 측정이 또 기준선이 된다.
    again = refresh_targets(store, layers, args.refresh) if args.refresh else []
    print(f"속성 {site} · 대기열 {len(queue)} · 이미 물어본 {len(store)} · "
          f"이번에 신규 {len(targets)} + 재조회 {len(again)}")

    done = quota = 0
    try:
        for i, p in enumerate(again + targets, 1):
            res = inspect(sess, site, p)
            if res is None:
                quota = 1
                print(f"\n429 — 하루 쿼터({DAILY}) 소진. {done}쪽 저장하고 멈춘다.")
                break
            if p in store:
                prev = {k: v for k, v in store[p].items() if k != "prev"}
                if prev.get("coverageState") != res.get("coverageState"):
                    moved.append((p, prev.get("coverageState"), res.get("coverageState")))
                res["prev"] = {"asked": store[p].get("asked"),
                               "coverageState": prev.get("coverageState")}
            res["asked"] = TODAY
            store[p] = res
            done += 1
            if i % 100 == 0:
                print(f"  {i}/{len(again) + len(targets)} …")
                save(store)          # 중간 저장 — 죽어도 여기까지는 남는다
            time.sleep(PACE)
    except KeyboardInterrupt:
        print("\n중단 — 지금까지 것을 저장한다.")
    finally:
        save(store)

    print(f"\n→ {STORE.relative_to(ROOT)} · 이번에 {done}쪽 · 누적 {len(store)}쪽 "
          f"· 남은 대기열 {len([p for p in queue if p not in store])}")
    if again:
        print(f"\n재조회 {len(again)}쪽 중 상태가 바뀐 것: {len(moved)}")
        for p, a, b in moved[:15]:
            print(f"  {p}\n    {a}  →  {b}")
    report(store, layers)
    return 2 if quota else 0


if __name__ == "__main__":
    raise SystemExit(main())
