"""Search Console Search Analytics → 층별 색인·노출 시계열.

**이 스크립트가 답하는 질문은 하나다: 우리가 낸 5,027쪽 중 몇 쪽이 실제로 검색에
나타나는가.** sitemap에 있다·크롤됐다는 그 질문의 대리 지표일 뿐이고, 2026-07에
2,190쪽이 '크롤링됨 - 색인 생성되지 않음'으로 묶였을 때 저장소 안에서는 아무것도
빨갛지 않았다(docs/page-map.md gap-5).

왜 Search Analytics가 먼저인가 — 쿼터가 설계를 정한다:

    URL Inspection    속성당 2,000/일  · "색인됐나"에 직접 답함
    Search Analytics  분당 1,200       · 25,000행/요청 → 5,027쪽이 요청 한 번

  노출 ≥1이면 색인된 게 **확정**이다(색인 안 된 쪽은 결과에 못 뜬다). 그래서
  Analytics 한 번으로 색인 확정분을 전부 걷어내고, 남은 '노출 0'에만 하루 2,000건
  Inspection을 쓰면 표본이 아니라 전수로 물을 수 있다. 순서가 반대면 4,340개
  인물 페이지에 쿼터를 다 쓰고도 표본 오차만 남는다.

  ⚠️ 역은 성립하지 않는다. **노출 0은 미색인의 증거가 아니라 후보다** — 색인됐지만
  한 번도 순위에 못 든 쪽이 섞여 있다. 둘을 가르는 건 Inspection의 coverageState뿐
  이므로, 이 스크립트의 산출물은 '미색인 목록'이 아니라 `pages_seen.json`(=본 것)
  이다. 안 본 것을 미색인이라 부르지 않는다.

결손 모델(docs/absence.md):
  질의가 성공했는데 층에 행이 없으면 그 층은 진짜 노출 0 → 0으로 적는다("없다").
  질의가 실패하면 그 주를 **아예 쓰지 않는다**("못 받았다"). 실패를 0으로 적으면
  다음 주 검사가 없던 급락을 본다.

  GSC 보존은 16개월이다. 그 밖은 API로도 못 가져오므로 영구 결손이고, 0으로 채우지
  않는다. 오늘 붙였다면 2025-04 이전은 없다.

인증:
  GCP 서비스 계정 → GSC 속성에 '제한된 사용자'로 추가 → JSON 키.
    GSC_SA_JSON       키 JSON **내용** (CI: secrets.GSC_SA_JSON)
    GSC_SA_JSON_FILE  키 파일 경로 (로컬)

사용:
  GSC_SA_JSON_FILE=~/gsc-key.json python scripts/fetch/fetch_gsc.py
  python scripts/fetch/fetch_gsc.py --window 90 --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "seo"
SITE_HOST = "polis.ysw.kr"
API = "https://searchconsole.googleapis.com/webmasters/v3"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"

# 25,000이 요청당 상한(기본 1,000). 우리는 5,027쪽이라 한 번에 들어오지만, 페이지가
# 늘면 조용히 잘리는 자리라 페이징을 그대로 둔다.
ROW_LIMIT = 25000

# GSC 확정 데이터는 2~3일 지연된다. dataState=all로 당기면 미확정이 섞이고 그 주가
# 나중에 커진다 — 주간 잡에 신선도를 살 이유가 없으므로 창을 3일 뒤로 민다.
LAG_DAYS = 3


def layer_map() -> dict[str, str]:
    """sitemap 층 파일 → {경로: 층}. 층 정의의 단일 출처는 sitemap 자신이다.

    여기서 접두사 규칙을 다시 쓰면 build_sitemap.py의 sections와 조용히 어긋난다.
    """
    m: dict[str, str] = {}
    for f in sorted(ROOT.glob("sitemap-*.xml")):
        layer = f.stem.replace("sitemap-", "")
        root = ET.fromstring(f.read_text(encoding="utf-8"))
        for loc in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
            m[norm_path(loc.text or "")] = layer
    return m


def norm_path(url: str) -> str:
    """절대 URL·퍼센트 인코딩을 경로 하나로 — GSC는 인코딩된 URL을 돌려준다."""
    p = urlsplit(url).path or "/"
    return unquote(p)


def session():
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
    except ImportError:
        sys.exit("google-auth 없음 — pip install -r requirements.txt")

    raw = os.environ.get("GSC_SA_JSON")
    if not raw:
        f = os.environ.get("GSC_SA_JSON_FILE")
        if not f:
            sys.exit("GSC_SA_JSON 또는 GSC_SA_JSON_FILE 필요 "
                     "(서비스 계정 키를 GSC 속성에 '제한된 사용자'로 추가할 것)")
        raw = Path(f).expanduser().read_text(encoding="utf-8")
    try:
        cred = service_account.Credentials.from_service_account_info(
            json.loads(raw), scopes=[SCOPE])
    except (ValueError, KeyError) as e:
        # 키가 깨졌는데 traceback만 뜨면 CI 로그에서 원인이 안 읽힌다. GCP가 주는
        # JSON을 통째로 넣어야 한다 — client_email만 뽑아 넣은 사고가 흔하다.
        sys.exit(f"서비스 계정 키가 형식에 안 맞다: {e}\n"
                 "  GCP가 내려준 JSON **전체**를 그대로 넣을 것 "
                 "(gh secret set GSC_SA_JSON < key.json)")
    return AuthorizedSession(cred)


def resolve_site(sess, override: str | None) -> str:
    """도메인 속성(sc-domain:)과 URL 접두사 속성은 siteUrl 표기가 다르다.

    어느 쪽으로 등록했는지 사람이 기억할 필요가 없도록 목록에서 찾는다. 계정이 두
    속성 다 갖고 있으면 도메인 속성을 고른다 — www·http 변형까지 한 번에 세므로.
    """
    if override:
        return override
    r = sess.get(f"{API}/sites")
    r.raise_for_status()
    entries = [e["siteUrl"] for e in r.json().get("siteEntry", [])]
    for want in (f"sc-domain:{SITE_HOST}", f"https://{SITE_HOST}/"):
        if want in entries:
            return want
    hit = [s for s in entries if SITE_HOST in s]
    if not hit:
        sys.exit(f"서비스 계정이 {SITE_HOST} 속성을 못 본다 — GSC '사용자 및 권한'에 "
                 f"추가했는지 확인. 지금 보이는 속성: {entries or '없음'}")
    return hit[0]


def query(sess, site: str, body: dict) -> list[dict]:
    """searchanalytics.query — 25,000행 상한을 startRow로 넘긴다."""
    from urllib.parse import quote
    url = f"{API}/sites/{quote(site, safe='')}/searchAnalytics/query"
    rows, start = [], 0
    while True:
        r = sess.post(url, json={**body, "rowLimit": ROW_LIMIT, "startRow": start})
        if r.status_code != 200:
            sys.exit(f"GSC {r.status_code}: {r.text[:400]}")
        got = r.json().get("rows", [])
        rows += got
        if len(got) < ROW_LIMIT:
            return rows
        start += ROW_LIMIT


def page_rows(sess, site: str, start: date, end: date) -> list[dict]:
    """페이지 차원 단독.

    ⚠️ aggregationType은 반드시 byPage. 기본 auto는 Google이 고르는데, property
    집계가 섞이면 층별 페이지 수가 회차마다 다른 기준으로 세어진다.

    ⚠️ page×query로 분해해서 층 합계를 내면 안 된다 — 익명화된 희소 질의가 빠져
    합이 항상 작다. 층 합계는 이 단독 질의에서만 뽑는다.
    """
    return query(sess, site, {
        "startDate": start.isoformat(), "endDate": end.isoformat(),
        "dimensions": ["page"], "type": "web",
        "aggregationType": "byPage", "dataState": "final",
    })


def appearance_rows(sess, site: str, start: date, end: date) -> list[dict]:
    """searchAppearance 단독 — 다른 차원과 **같이 쓸 수 없다**(API 제약).

    이게 답하는 건 하나다: 인물 4,340쪽에 박은 Person·BreadcrumbList 구조화
    데이터를 Google이 실제로 채택했는가(docs/page-map.md gap-5). 마크업이 있는
    것과 리치 결과로 뜨는 것은 다른 사실이고, 지금까지 후자는 아무도 확인 안 했다.
    """
    return query(sess, site, {
        "startDate": start.isoformat(), "endDate": end.isoformat(),
        "dimensions": ["searchAppearance"], "type": "web", "dataState": "final",
    })


def summarize(rows: list[dict], layers: dict[str, str]) -> dict:
    """층별 {노출된 페이지 수, 노출, 클릭} + sitemap 밖 페이지.

    'pages'가 핵심 지표다 — 클릭·노출은 선거 주기와 시사에 흔들리지만(우리 사이트는
    특히), **노출된 페이지 수가 줄었다**는 건 색인이 되돌아갔다는 뜻에 가깝다.
    """
    tot = {l: {"pages": 0, "impressions": 0, "clicks": 0}
           for l in sorted(set(layers.values()))}
    tot["_unlisted"] = {"pages": 0, "impressions": 0, "clicks": 0}
    for r in rows:
        p = norm_path(r["keys"][0])
        # sitemap에 없는데 노출되는 페이지 = 유령(옛 URL·파라미터 변형). 세어만 둔다.
        b = tot[layers.get(p, "_unlisted")]
        b["pages"] += 1
        b["impressions"] += int(r.get("impressions", 0))
        b["clicks"] += int(r.get("clicks", 0))
    return tot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=7,
                    help="집계 창(일). 기본 7 = 주간 잡")
    ap.add_argument("--roster-window", type=int, default=90,
                    help="pages_seen 창(일). 짧으면 계절성 페이지가 미색인으로 오인된다")
    ap.add_argument("--site", help="siteUrl 강제 (sc-domain:… 또는 https://…/)")
    ap.add_argument("--dry-run", action="store_true", help="쓰지 않고 출력만")
    args = ap.parse_args()

    layers = layer_map()
    if not layers:
        sys.exit("sitemap-*.xml 없음 — build_sitemap.py 먼저")

    end = date.today() - timedelta(days=LAG_DAYS)
    start = end - timedelta(days=args.window - 1)
    r_start = end - timedelta(days=args.roster_window - 1)

    sess = session()
    site = resolve_site(sess, args.site)
    print(f"속성 {site} · 창 {start}~{end} ({args.window}일)")

    rows_week = page_rows(sess, site, start, end)
    week = summarize(rows_week, layers)
    roster = page_rows(sess, site, r_start, end)
    appear = appearance_rows(sess, site, r_start, end)

    for l, v in week.items():
        total = sum(1 for x in layers.values() if x == l) if l != "_unlisted" else 0
        share = f" / {total}" if total else ""
        print(f"  {l:10} 노출된 페이지 {v['pages']:>5}{share}"
              f"  노출 {v['impressions']:>7}  클릭 {v['clicks']:>5}")

    seen = {norm_path(r["keys"][0]): {"impressions": int(r.get("impressions", 0)),
                                      "clicks": int(r.get("clicks", 0))}
            for r in roster}
    queue = sorted(p for p in layers if p not in seen)
    print(f"\n{args.roster_window}일 내 노출된 페이지 {len(seen)} · "
          f"한 번도 안 뜬 sitemap URL {len(queue)}  ← Inspection 대기열")
    print("  ⚠️ 대기열 = 미색인 아님. coverageState로 갈라야 '미색인'이라 부를 수 있다.")
    print("\n검색 표시 형태(구조화 데이터 채택 여부):")
    for r in sorted(appear, key=lambda x: -x.get("impressions", 0)):
        print(f"  {r['keys'][0]:24} 노출 {int(r.get('impressions', 0)):>7}")
    if not appear:
        print("  (없음 — 리치 결과로 채택된 게 없다는 뜻)")

    if args.dry_run:
        print("\n--dry-run — 쓰지 않음")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    cov_p = OUT / "coverage.json"
    cov = json.loads(cov_p.read_text(encoding="utf-8")) if cov_p.exists() else {"weeks": {}}
    cov["site"] = site
    # 'ok'는 **질의가 성공했다**는 사실 자체를 적는 자리다. 값에서 유추하지 않는다 —
    # 전 층이 0인 주는 진짜 노출 0일 수도(우리 사이트는 실제로 그렇다) 수집 실패일
    # 수도 있고, 숫자만 보면 둘이 똑같이 생겼다. 실패하면 이 줄에 닿기 전에 죽으므로
    # ok가 없는 주는 존재하지 않는다 — 손으로 채워 넣은 주를 잡는 표식이기도 하다.
    cov["weeks"][end.isoformat()] = {"start": start.isoformat(), "ok": True,
                                     "rows": len(rows_week), "layers": week}
    cov_p.write_text(json.dumps(cov, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                     encoding="utf-8")

    (OUT / "pages_seen.json").write_text(json.dumps(
        {"generated": end.isoformat(), "window_days": args.roster_window,
         "site": site, "pages": dict(sorted(seen.items()))},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    (OUT / "inspect_queue.txt").write_text("\n".join(queue) + "\n", encoding="utf-8")

    (OUT / "appearance.json").write_text(json.dumps(
        {"generated": end.isoformat(), "window_days": args.roster_window,
         "types": {r["keys"][0]: {"impressions": int(r.get("impressions", 0)),
                                  "clicks": int(r.get("clicks", 0))} for r in appear}},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"\n→ {cov_p.relative_to(ROOT)} ({len(cov['weeks'])}주) · "
          f"pages_seen.json · inspect_queue.txt · appearance.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
