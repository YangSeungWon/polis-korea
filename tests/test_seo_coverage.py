"""색인 회귀 — 층별 '노출된 페이지 수'가 되돌아갔는가.

sitemap 완전성(test_sitemap.py)은 **우리가 낸 것**을 검사한다. 이 검사는 **Google이
받은 것**을 검사한다. 둘은 다른 사실이고, 2026-07에 2,190쪽이 '크롤링됨 - 색인 생성
되지 않음'이 됐을 때 앞의 검사는 전부 초록이었다.

무엇을 보는가:
  층별 **노출된 페이지 수**. 클릭·노출 총량이 아니다 — 우리 사이트는 선거 주기와
  시사에 크게 흔들려서(지방선거 주간 vs 비수기) 총량 하락은 색인과 무관한 이유로
  늘 발생한다. 반면 '몇 쪽이 결과에 나타났나'는 그보다 훨씬 둔하고, 그게 줄면
  색인이 실제로 되돌아간 쪽에 가깝다.

기준을 절대값으로 두지 않는 이유:
  person 4,340쪽은 원래 노출률이 낮다(얇음 48%). '층별 80% 이상' 같은 선을 그으면
  person은 영구히 빨갛고 나머지는 영구히 초록이라 아무 신호도 못 준다. 그래서
  **직전 4주 중앙값 대비 상대 하락**만 본다.

수집 전에는 통과시킨다:
  data/seo/coverage.json이 없으면 아직 워크플로를 안 붙인 것이다. 여기서 실패시키면
  GSC 비밀이 준비되기 전까지 checks가 통째로 빨갛고, 그러면 아무도 안 본다.
  대신 '수집 전'이라고 크게 적는다.

실행: .venv/bin/python tests/test_seo_coverage.py
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEO = ROOT / "data" / "seo"

# 직전 4주 중앙값 대비 이만큼 넘게 줄면 실패. 20%는 '한 층이 통째로 빠지는' 사고를
# 잡되 주간 잡음(±10% 안팎)에는 안 울리는 선이다. 오탐이 나면 여기를 올리지 말고
# 왜 흔들리는지부터 볼 것 — 흔들림 자체가 신호일 수 있다.
DROP = 0.20
BASE_WEEKS = 4          # 비교 기준으로 삼는 직전 주 수
STALE_DAYS = 14         # 마지막 수집이 이보다 오래되면 잡이 죽은 것

fails = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def sitemap_layers() -> dict[str, int]:
    """sitemap-{층}.xml → URL 수. 층 정의의 단일 출처."""
    out = {}
    for f in sorted(ROOT.glob("sitemap-*.xml")):
        root = ET.fromstring(f.read_text(encoding="utf-8"))
        n = len(list(root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")))
        out[f.stem.replace("sitemap-", "")] = n
    return out


def check_freshness(weeks: dict) -> None:
    last = max(weeks)
    age = (date.today() - date.fromisoformat(last)).days
    ck(f"마지막 수집이 최근이다 ({last}, {age}일 전)", age <= STALE_DAYS,
       f"{STALE_DAYS}일 넘게 안 들어왔다 — 워크플로가 죽었거나 키가 만료됐다")


def check_layers_covered(weeks: dict, sm: dict[str, int]) -> None:
    """새 층이 생겼는데 수집에 안 잡히는 자리.

    build_sitemap.py의 sections에 층을 추가하면 sitemap-{층}.xml이 생기고 이 검사가
    바로 그 층을 요구한다. 수집기는 sitemap을 읽어 층을 만들므로 보통 자동으로
    따라오지만, 층을 추가한 주에 잡이 아직 안 돌았으면 여기서 보인다.
    """
    latest = weeks[max(weeks)]["layers"]
    missing = [l for l in sm if l not in latest]
    ck(f"sitemap 층 {len(sm)}개가 전부 수집에 있다", not missing,
       f"수집에 없는 층: {missing}")


def check_regression(weeks: dict) -> None:
    """층별 노출 페이지 수의 상대 하락."""
    ordered = [weeks[k] for k in sorted(weeks)]
    if len(ordered) < BASE_WEEKS + 1:
        print(f"  · 주 {len(ordered)}개 — 기준선({BASE_WEEKS + 1}주)이 아직 없어 "
              f"회귀 검사 보류")
        return
    cur, base = ordered[-1]["layers"], ordered[-BASE_WEEKS - 1:-1]
    for layer in sorted(cur):
        if layer.startswith("_"):
            continue
        hist = [w["layers"][layer]["pages"] for w in base if layer in w["layers"]]
        if len(hist) < BASE_WEEKS:
            continue
        med = statistics.median(hist)
        now = cur[layer]["pages"]
        # 중앙값이 0이면 비율을 못 낸다 — 원래 안 뜨던 층이므로 회귀도 아니다.
        if med == 0:
            continue
        drop = (med - now) / med
        ck(f"{layer:8} 노출 페이지 {now} (기준 {med:.0f})", drop <= DROP,
           f"{drop:.0%} 하락 — 색인이 되돌아갔는지 GSC에서 확인할 것")


def check_absence_model(weeks: dict) -> None:
    """'0'이 어디서 왔는지가 적혀 있는가(docs/absence.md).

    처음엔 '전 층이 동시에 0인 주'를 수집 실패의 흔적으로 봤다. 틀렸다 — 2026-08
    실제 수집에서 polis는 **모든 층이 진짜 0**이었다(주간 노출 0). 값만 보면
    '없다'와 '못 받았다'가 똑같이 생겼고, 그래서 값에서 유추하면 안 된다.

    그래서 수집기가 성공한 주에만 ok=True를 적는다. 실패하면 그 줄에 닿기 전에
    죽으므로 ok 없는 주는 원래 존재할 수 없다 — 있다면 사람이 손으로 채운 것이고,
    그건 지어낸 값이다.
    """
    bad = [k for k, w in weeks.items() if not w.get("ok")]
    ck("모든 주가 '질의 성공' 표식을 갖는다", not bad,
       f"{bad[:3]} — 수집기가 안 쓴 주다. 손으로 채웠다면 지울 것")


def check_queue(sm: dict[str, int]) -> None:
    """대기열 + 본 것 = sitemap 전체인가.

    inspect_queue.txt는 'Inspection으로 물어볼 후보'지 미색인 목록이 아니다. 다만
    수가 sitemap 총량을 넘거나 본 것과 겹치면 산출이 깨진 것이다.
    """
    q_p, s_p = SEO / "inspect_queue.txt", SEO / "pages_seen.json"
    if not (q_p.exists() and s_p.exists()):
        return
    queue = [l for l in q_p.read_text(encoding="utf-8").splitlines() if l.strip()]
    seen = json.loads(s_p.read_text(encoding="utf-8"))["pages"]
    paths = _sitemap_paths()
    # 산출물은 **만들어질 당시의 sitemap**을 기준으로 한다. 그 뒤 sitemap이 줄면
    # (person 4,340쪽을 뺀 2026-08-26처럼) 대기열에 지금 sitemap 밖 URL이 남는다.
    # 그건 깨진 게 아니라 낡은 것이다 — 다음 수집이 갱신한다. 그래서 '합이 같은가'가
    # 아니라 '지금 sitemap이 산출물에 다 들어 있는가'를 본다.
    covered = (set(queue) | set(seen)) & paths
    missing = paths - covered
    # 수집 **뒤에** 생긴 페이지는 빠져 있는 게 맞다. 2026 재보궐 archive를 새로
    # 만들자 이 검사가 CI에서 빨개졌는데, 깨진 게 아니라 아직 안 물어본 것이었다.
    # 위 주석이 'sitemap이 줄면'만 다뤘고 '늘면'을 안 다뤘다.
    # ⚠️ 파일 mtime을 쓰면 안 된다 — CI는 새로 체크아웃해서 전부 오늘이 되고,
    # 그러면 이 검사가 영영 안 걸린다. sitemap 매니페스트의 d(그 내용이 처음
    # 나타난 날)는 커밋된 값이라 체크아웃에 안 흔들린다.
    gen = json.loads(s_p.read_text(encoding="utf-8")).get("generated") or ""
    man = {}
    mp = ROOT / "data/sitemap_lastmod.json"
    if mp.is_file():
        man = json.loads(mp.read_text(encoding="utf-8")).get("pages") or {}
    def born_of(u: str) -> str:
        rel = u.strip("/")
        for k in (f"{rel}/index.html", rel):
            if k in man:
                return man[k].get("d") or ""
        return ""
    fresh = {m for m in missing if gen and born_of(m) > gen}
    stale_missing = missing - fresh
    if fresh:
        print(f"  · 수집({gen[:10]}) 뒤에 생긴 {len(fresh)}쪽은 셈에서 뺀다 "
              f"— {sorted(fresh)[:2]}")
    ck(f"지금 sitemap {len(paths)}쪽이 전부 산출물에 있다", not stale_missing,
       f"{len(stale_missing)}쪽 빠짐 — {sorted(stale_missing)[:3]}")
    ck("대기열과 본 것이 겹치지 않는다", not (set(queue) & set(seen)))


def _sitemap_paths() -> set[str]:
    from urllib.parse import unquote, urlsplit
    out = set()
    for f in sorted(ROOT.glob("sitemap-*.xml")):
        root = ET.fromstring(f.read_text(encoding="utf-8"))
        for loc in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
            out.add(unquote(urlsplit(loc.text or "").path or "/"))
    return out


def check_workflow_add() -> None:
    """수집 잡이 data/seo/를 커밋 범위에 넣는가.

    이 저장소에서 세 번 재발한 사고다 — 생성기는 돌았는데 git add 범위에 없어서
    매번 만들고 매번 버렸다(sitemap 층 파일이 마지막 자리였다). 새로 쌓는 데이터는
    같은 함정의 다음 후보라 처음부터 검사로 박아둔다.
    """
    f = ROOT / ".github/workflows/seo-coverage.yml"
    ck("seo-coverage.yml이 있다", f.exists())
    if not f.exists():
        return
    t = f.read_text(encoding="utf-8")
    adds = " ".join(re.findall(r"git add ([^\n]*)", t))
    ck("seo-coverage.yml이 data/seo를 add한다", "data/seo" in adds,
       "생성만 하고 커밋 안 하면 매주 만들고 매주 버린다")


def main() -> int:
    sm = sitemap_layers()
    cov_p = SEO / "coverage.json"

    print("[구조] 수집 잡")
    check_workflow_add()

    if not cov_p.exists():
        print("\n[수집 전] data/seo/coverage.json 없음 — GSC 수집을 아직 안 붙였다.")
        print("  서비스 계정을 GSC 속성에 추가하고 secrets.GSC_SA_JSON을 넣으면")
        print("  seo-coverage.yml이 주간으로 채운다. 그전까지 색인율은 '모른다'.")
        print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
        return 1 if fails else 0

    weeks = json.loads(cov_p.read_text(encoding="utf-8"))["weeks"]
    print(f"\n[신선도] 수집 {len(weeks)}주")
    check_freshness(weeks)
    check_absence_model(weeks)

    print("\n[층] sitemap 층이 전부 수집되는가")
    check_layers_covered(weeks, sm)

    print("\n[회귀] 층별 노출 페이지 수")
    check_regression(weeks)

    print("\n[대기열] Inspection 후보 산출")
    check_queue(sm)

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
