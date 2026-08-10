"""구조적 QA — 4,900여 페이지가 **계속** 같은 규칙을 지키는지.

지금 잘 보이는 상태와 계속 유지되는 상태는 다르다. 오늘 나온 결함이 세 계열로
수렴했으므로 그 셋을 규칙으로 승격해 검사한다:

  1. 결손 ≠ 0 / 무투표 / 없음      숫자를 만들기 전에 상태를 보존한다
  2. 문자열 동일성 ≠ 의미 동일성    정당·지역은 registry/canonical을 거친다
  3. 근본 수정 뒤 옛 우회책 제거     제약이 사라졌는데 보정 코드가 남아 있지 않은지

실행: .venv/bin/python tests/test_structure_qa.py
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fails: list[str] = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def js_files() -> list[Path]:
    return sorted(ROOT.glob("assets/**/*.js"))


def code_lines(p: Path):
    """주석을 뺀 줄. 주석에는 '왜 이렇게 안 쓰는지'를 적으므로 금지어가 등장한다."""
    for i, l in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
        s = l.strip()
        if s.startswith("//") or s.startswith("*") or s.startswith("/*"):
            continue
        yield i, l


def html_pages(pat: str) -> list[Path]:
    return sorted(ROOT.glob(pat))


# ── 1. 결손 ≠ 0 ─────────────────────────────────────────────────────────────
def check_missing_not_zero():
    print("\n[1] 결손을 0·사실로 바꾸지 않는가")
    bad = []
    for p in js_files():
        for i, l in code_lines(p):
            for m in re.finditer(r"\(\s*[\w.]*\.(pct|margin|turnout)\s*\|\|\s*0\s*\)\.toFixed", l):
                st = l.rfind('style="', 0, m.start())
                if st != -1 and l.find('"', st + 7) > m.start():
                    continue          # style= 안은 계산값(막대 폭) — 0이 맞다
                bad.append(f"{p.relative_to(ROOT)}:{i}")
    ck("글씨로 나가는 (값 || 0) 없음", not bad, str(bad[:5]))

    # .toFixed를 가드 없이 부르면 결손에서 TypeError로 죽는다
    unguarded = []
    for p in js_files():
        for i, l in code_lines(p):
            for m in re.finditer(r"\$\{[\w.]*\.(pct|margin)\.toFixed\(", l):
                seg = l[:m.start()]
                if re.search(r"(!=\s*null|!==\s*null|\?\?|&&)\s*$", seg.rstrip()) or "!= null" in l:
                    continue
                unguarded.append(f"{p.relative_to(ROOT)}:{i}")
    ck("가드 없는 .toFixed 없음", not unguarded, str(unguarded[:5]))

    # 렌더 결과: 지역 페이지에 0.0%가 없고 세 상태가 구분된다
    rg = html_pages("region/*/index.html")
    zero = [p.parent.name for p in rg if ">0.0%<" in p.read_text(encoding="utf-8")]
    ck(f"지역 페이지 {len(rg)}개에 0.0% 없음", not zero, str(zero[:3]))
    joined = "".join(p.read_text(encoding="utf-8") for p in rg[:120])
    ck("결손(—)과 무투표가 다른 표기", "rg-nd" in joined and any(
        "rg-nv" in p.read_text(encoding="utf-8") for p in rg))

    # archive 요약: 결손을 0.0%로 쓰지 않는다
    ar = html_pages("archive/*/index.html")
    z2 = [p.parent.name for p in ar if "투표율 0.0%" in p.read_text(encoding="utf-8")]
    ck(f"archive {len(ar)}개에 투표율 0.0% 없음", not z2, str(z2[:3]))


# ── 2. 문자열 동일성 ≠ 의미 동일성 ──────────────────────────────────────────
def check_identity():
    print("\n[2] 문자열 비교로 의미를 판정하지 않는가")
    sys.path.insert(0, str(ROOT / "scripts/build"))
    from build_comparison import same_party

    ck("개명은 같은 당 (한나라당↔새누리당)", same_party("한나라당", "새누리당"))
    ck("합당은 다른 당 (한나라당↔민주당(2008))",
       not same_party("한나라당", "민주당(2008)"))

    # 비교 산출물이 registry를 우회하지 않았는가 — 개명 회차에 hold가 0이면 우회다
    RENAME_ROUNDS = {
        "6th-local-2014__5th-local-2010": "한나라당→새누리당",
        "16th-pres-2002__15th-pres-1997": "새정치국민회의→새천년민주당",
    }
    for f, why in RENAME_ROUNDS.items():
        fp = ROOT / "data/comparisons" / f"{f}.json"
        if not fp.exists():
            ck(f"비교 파일 {f}", False, "없음")
            continue
        d = json.loads(fp.read_text(encoding="utf-8"))
        holds = sum(o["counts"]["party_hold"] for o in (d.get("offices") or {}).values())
        ck(f"{why} 회차에 party_hold > 0", holds > 0, f"hold={holds}")

    # 정당 판정이 한 화면에서 두 방식이면 숫자가 어긋난다
    loc = (ROOT / "assets/archive/local.js").read_text(encoding="utf-8")
    n_raw = len(re.findall(r"pred === actual\[sido\]|a\.party === p\.party", loc))
    n_safe = loc.count("samePartyName")
    ck("출구조사 적중 판정이 samePartyName을 거친다", n_safe >= 2, f"raw={n_raw} safe={n_safe}")


# ── 3. 옛 우회책 잔존 ───────────────────────────────────────────────────────
def check_stale_workarounds():
    print("\n[3] 근본 수정 뒤 옛 우회책이 남아 있지 않은가")
    # (a) 대비 보정 후: 페이지 배경 위에서 정당색을 배경으로 칠하던 우회책
    #     (hex 셀·pill처럼 '면' 위에 글씨를 얹는 정당한 용법은 제외한다)
    bad = []
    for p in js_files():
        for i, l in code_lines(p):
            if "pickTextColor" not in l:
                continue
            if re.search(r"pickTextColor\([^)]*\)\s*!==\s*'#fff'", l):
                bad.append(f"{p.relative_to(ROOT)}:{i}")
    ck("'밝은 색이면 배경 칠하기' 우회책 없음", not bad, str(bad[:4]))

    # (b) 글씨에 원색을 쓰던 우회책 (test_text_contrast와 중복되지 않는 잔재)
    parties = (ROOT / "assets/parties.js").read_text(encoding="utf-8")
    ck("partyTextColor가 실제 대비를 목표로 한다",
       "TEXT_CONTRAST_MIN" in parties and "_contrast(" in parties)
    ck("공용 숫자 포맷터가 있다",
       "function fmtPct" in parties and "function fmtPp" in parties)

    # (c) 옛 nav — **nav 블록 안**만 본다. '지지율 추이'는 홈 능력 목록의 링크 이름이고
    #     '역대 판세'는 breadcrumb의 페이지 이름이라 본문에 있는 건 정당하다.
    #     넓게 잡으면 정당한 내용에서 울려 결국 무시되는 검사가 된다.
    AXES = ["지금", "선거", "인물·정당", "역사"]
    nav_bad = []
    for p in html_pages("**/*.html"):
        t = p.read_text(encoding="utf-8")
        m = re.search(r"NAV_START[\s\S]*?NAV_END", t)
        if not m:
            continue        # share/ 등 헤더 없는 페이지
        labels = re.findall(r'class="hdr-link[^"]*">([^<]+)<', m.group(0))
        if labels != AXES:
            nav_bad.append(f"{p.relative_to(ROOT)} → {'/'.join(labels)}")
    ck("nav가 전부 4축 (옛 메뉴 잔존 0)", not nav_bad, str(nav_bad[:3]))

    # (d) 옛 카피 — 교체하기로 한 문자열이 생성물에 남았는가.
    #     각 항목은 '무엇으로 바뀌었는지'까지 적어 둔다.
    LEGACY_COPY = {
        "무엇을 약속했나": "→ '공약'",
        "건 제외</": "→ 'N건 중 M건 분류'",
        "자동 추정한 값": "→ 'polis 자동 분류' 칩",
        "당선인·후보의 공약": "→ 'NEC에 등록된 선거공약'",
    }
    for token, to in LEGACY_COPY.items():
        hit = [str(p.relative_to(ROOT)) for p in html_pages("**/*.html")
               if token in p.read_text(encoding="utf-8")][:3]
        ck(f"옛 카피 '{token[:12]}' 없음 {to}", not hit, str(hit))


# ── 4. 비교가 있는 회차엔 첫 화면 요약도 있다 ───────────────────────────────
def check_comparison_surfaced():
    print("\n[4] 비교 데이터가 화면에 닿는가")
    cmps = {p.stem.split("__")[0] for p in (ROOT / "data/comparisons").glob("*__*.json")}
    missing_link, missing_ui = [], []
    for eid in sorted(cmps):
        em = ROOT / "data/elections" / f"{eid}.json"
        if not em.exists():
            continue
        prev = (json.loads(em.read_text(encoding="utf-8")).get("archive") or {}
                ).get("compare_previous")
        if not prev:
            missing_link.append(eid)
        page = ROOT / "archive" / eid / "index.html"
        if page.exists() and "ar-summary-cmp" not in page.read_text(encoding="utf-8"):
            missing_ui.append(eid)
    ck(f"비교 {len(cmps)}쌍 전부 회차 메타에 연결", not missing_link, str(missing_link[:4]))
    ck("비교가 있는 회차는 첫 화면에도 요약이 있다", not missing_ui, str(missing_ui[:4]))


def check_json_shape_guards() -> None:
    """모양 있는 fallback으로 JSON을 읽는 곳이 **getJson을 거치는가**.

    catch는 fetch 거부만 잡는다. 본문이 `null`이면 r.json()은 null로 정상
    resolve해 `r.ok ? r.json() : {폴백}`을 그대로 통과하고, 쓰는 쪽에서
    'Cannot read properties of null'로 터진다.

    이 종류가 세 번 났다 — climate.js가 겪고 주석까지 남겼는데 같은 묶음의
    core.js는 몰랐고, UI 감사에서 두 번은 플레이키로 넘어갔다. 각자 인라인으로
    막으면 또 한쪽만 배운다. utils.js의 getJson 한 자리로 모으고, 그걸 우회하는
    코드가 생기는지 여기서 본다.

    검사 대상은 **모양을 기대하는 호출**뿐이다. null 폴백은 '모르는 채로 둔다'라
    모양을 따지지 않는다.
    """
    print("\n[본문 null] 모양 있는 fallback은 getJson을 거친다")
    import re as _r
    raw = []
    for p in sorted((ROOT / "assets").rglob("*.js")):
        if p.name == "utils.js":
            continue          # getJson 자신이 사는 곳
        for i, ln in enumerate(p.read_text(encoding="utf-8", errors="replace")
                               .split("\n"), 1):
            if ".json()" not in ln:
                continue
            if (_r.search(r"json\(\)\s*:\s*(\[\]|\{[^}]*\})", ln)
                    or _r.search(r"catch\(\(\)\s*=>\s*\(?(\[\]|\{[^}]*\})", ln)):
                raw.append(f"{p.relative_to(ROOT)}:{i}")
    ck(f"getJson을 우회하는 곳이 없다 ({len(raw)}곳)", not raw, str(raw[:6]))
    # 헬퍼가 실제로 쓰이고 있는가 — 0이면 검사가 죽은 것이다
    used = sum(1 for p in (ROOT / "assets").rglob("*.js") if p.name != "utils.js"
               and "getJson(" in p.read_text(encoding="utf-8", errors="replace"))
    ck(f"getJson이 실제로 쓰인다 ({used}개 파일)", used >= 5, str(used))
    # 헬퍼가 모양을 정말 따지는가 — 폴백 타입별 분기가 있어야 한다
    _u = (ROOT / "assets/utils.js").read_text(encoding="utf-8")
    ck("getJson이 fallback 모양으로 검사한다",
       "Array.isArray(fallback)" in _u and "typeof fallback === 'object'" in _u)


def check_roster_scope() -> None:
    """수집 범위(roster_scope)에서 '모름'과 '당선인'을 합치지 않는가.

    공약 분포는 **당선인만 셌는지 전 후보를 셌는지에 따라 완전히 달라진다.**
    그런데 roster_scope는 나중에 생긴 필드라 옛 회차 파일엔 없다. 없는 것을
    '당선인'으로 읽으면 화면이 모르는 것을 안다고 말한다 — 실제로
    render-pledge-realms.js가 그랬다(trust.js는 처음부터 셋으로 갈랐다).

    상태가 셋이면 코드도 셋을 알아야 한다: 두 리터럴을 다 비교하지 않는 소비자는
    상태를 접고 있는 것이다.
    """
    print("\n[수집 범위] '모름'과 '당선인'을 합치지 않는다")
    users = []
    for p in sorted((ROOT / "assets").rglob("*.js")):
        t = p.read_text(encoding="utf-8", errors="replace")
        if "roster_scope" not in t:
            continue
        users.append(p)
        ck(f"{p.relative_to(ROOT)}: 두 상태를 다 비교한다",
           "'all_candidates'" in t and "'winners_only'" in t,
           "한쪽만 비교하면 나머지가 기본값으로 접힌다")
    ck(f"roster_scope 소비자가 있다 ({len(users)}곳)", bool(users))

    # 데이터 쪽 — 새로 들어온 파일이 이 필드를 빠뜨리면 잡는다. 옛 파일은 필드가
    # 생기기 전이라 없는 게 정상이고, 그 목록을 고정해 둔다(늘면 실패).
    LEGACY_NO_SCOPE = {
        "19th-pres-2017", "20th-pres-2022", "21st-pres-2025",
        "7th-local-2018", "8th-local-2022",
        "byelection-2020-04-15", "byelection-2021-04-07", "byelection-2023-04-05",
        "byelection-2023-10-11", "byelection-2024-04-10", "byelection-2024-10-16",
        "byelection-2025-04-02",
    }
    missing = set()
    for p in sorted((ROOT / "data/pledges").glob("*.json")):
        if p.name == "realm-summary.json":
            continue
        m = json.loads(p.read_text(encoding="utf-8")).get("_meta") or {}
        if not m.get("roster_scope"):
            missing.add(p.stem)
    ck(f"수집 범위가 빠진 파일이 알려진 것뿐이다 ({len(missing)}개)",
       missing == LEGACY_NO_SCOPE,
       f"새로 생김 {sorted(missing - LEGACY_NO_SCOPE)} · 채워짐 {sorted(LEGACY_NO_SCOPE - missing)}")


def check_scope_consistency() -> None:
    """전국(nation)이 시도(sido) 합과 같은가 — 층이 서로를 검산한다.

    같은 회차에 전국·시도가 **다른 출처에서** 오는 일이 있다. 옛 대선은 nation이
    위키백과 infobox(주요 후보만 싣는다), sido가 선관위 개표현황이었다. 그래서
    13대 대선에서 **신정일 46,650표가 전국 집계에서만 사라져** 있었다 — 시도
    14곳에는 다 있는데.

    한 층만 보면 절대 안 보인다. 두 층이 다 있을 때는 서로를 검산하게 한다.
    """
    print("\n[층 정합] 전국이 시도 합과 같은가")
    import collections
    pairs, bad = 0, []
    for p in sorted((ROOT / "data/results").glob("*.json")):
        if ".sigungu." in p.name:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        by = collections.defaultdict(lambda: collections.defaultdict(int))
        for r in d.get("races") or []:
            sc = r.get("scope")
            if sc not in ("nation", "sido"):
                continue
            for c in r.get("candidates") or []:
                by[r.get("sg_typecode")][sc] += c.get("votes") or 0
        for tc, m in by.items():
            if not (m.get("nation") and m.get("sido")):
                continue
            pairs += 1
            if m["nation"] != m["sido"]:
                bad.append(f"{p.stem} tc{tc}: 전국 {m['nation']:,} vs 시도합 {m['sido']:,}"
                           f" (차 {abs(m['nation'] - m['sido']):,})")
    ck(f"검산 가능한 (회차,선거종류) 쌍이 있다 ({pairs}쌍)", pairs >= 15, str(pairs))
    ck("전국이 시도 합과 일치한다", not bad, str(bad[:4]))


def check_pct_denominator() -> None:
    """pct가 valid_votes와 맞는가 — 분모가 틀리면 비율이 통째로 어긋난다.

    13~16대 총선의 nation tc7(전국구)은 **의석 배분 대상 정당만** 담는데,
    valid_votes에 그 정당들의 합만 적혀 있었다. pct는 공식 정당득표율이라
    분모가 달라 6~7%p씩 어긋났다 — 민정당 34.0%인데 계산하면 36.66%가 나왔다.

    허용오차 0.3%p는 세 가지를 덮는다:
      · 출처가 소수 첫째 자리까지만 준다(13대 대선 시도 30.0 vs 29.95)
      · 우리 지역구 합과 공식 유효표가 조금 다르다(15대 0.28%p — 무투표 선거구 등)
      · 반올림 누적
    그보다 크게 어긋나면 분모가 틀린 것이다.
    """
    print("\n[비율] pct가 분모와 맞는가")
    # 간선 대선은 pct 분모가 **유효표가 아니라 투표수**다(통일주체국민회의).
    # 관례가 다른 것이지 오류가 아니라 예외로 적어 둔다 — 숨기지 않고 이름을 남긴다.
    INDIRECT = {("10th-pres-1979", "최규하"), ("8th-pres-1972", "박정희")}
    bad = []
    for p in sorted((ROOT / "data/results").glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        for r in d.get("races") or []:
            vv = r.get("valid_votes")
            if not vv:
                continue
            for c in r.get("candidates") or []:
                if c.get("pct") is None or c.get("votes") is None:
                    continue
                if (p.stem, c.get("name")) in INDIRECT:
                    continue
                exp = round(c["votes"] / vv * 100, 2)
                if abs(exp - c["pct"]) > 0.3:
                    bad.append(f"{p.stem} {r.get('scope')} tc{r.get('sg_typecode')} "
                               f"{c.get('name') or c.get('party')}: 기록 {c['pct']} vs 계산 {exp}")
    ck("pct가 valid_votes 기준과 맞는다", not bad, str(bad[:4]))
    # 예외가 실재하는지도 본다 — 목록만 남고 대상이 사라지면 죽은 예외다
    live = set()
    for eid, nm in INDIRECT:
        fp = ROOT / "data/results" / f"{eid}.json"
        if not fp.exists():
            continue
        d = json.loads(fp.read_text(encoding="utf-8"))
        if any(c.get("name") == nm for r in d.get("races") or []
               for c in r.get("candidates") or []):
            live.add((eid, nm))
    ck(f"간선 예외가 실재한다 ({len(live)}건)", live == INDIRECT, str(INDIRECT - live))


def check_rank_one_meaning() -> None:
    """rank가 한 뜻인가 — 어떤 회차는 득표 순, 어떤 회차는 의석 순이면 못 읽는다.

    rank 있는 race 29,879개 중 **딱 하나**가 의석 순이었다(13대 총선 nation tc7:
    평민당 70석이 통일민주당 59석보다 앞인데 득표는 반대다). 하나뿐이라 더 위험하다 —
    읽는 쪽은 나머지 전부가 득표 순이니 그렇게 읽는다.

    rank = 득표 순으로 통일하고, 의석 순은 seat_rank로 따로 둔다. 정보를 지우는 게
    아니라 두 축을 가르는 것이다.
    """
    print("\n[순위] rank는 득표 순 한 뜻이다")
    bad, seat_ok, n = [], 0, 0
    for p in sorted((ROOT / "data/results").glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        for r in d.get("races") or []:
            cs = [c for c in (r.get("candidates") or []) if c.get("rank") is not None]
            if len(cs) < 2 or any(c.get("votes") is None for c in cs):
                continue
            n += 1
            order = [c["votes"] for c in sorted(cs, key=lambda c: c["rank"])]
            if order != sorted(order, reverse=True):
                bad.append(f"{p.stem} {r.get('scope')} tc{r.get('sg_typecode')}")
            sr = [c for c in cs if c.get("seat_rank") is not None]
            if sr:
                if len(sr) != len(cs):
                    bad.append(f"{p.stem} {r.get('scope')}: seat_rank가 일부에만 있다")
                else:
                    seats = [c.get("seats") for c in sorted(sr, key=lambda c: c["seat_rank"])]
                    if any(x is None for x in seats) or seats != sorted(seats, reverse=True):
                        bad.append(f"{p.stem} {r.get('scope')}: seat_rank가 의석 순이 아니다")
                    else:
                        seat_ok += 1
    ck(f"rank가 전부 득표 순이다 ({n:,} race)", not bad, str(bad[:4]))
    ck(f"의석 순은 seat_rank로 남아 있다 ({seat_ok}건)", seat_ok >= 1, str(seat_ok))


def check_uncontested_null() -> None:
    """무투표 당선은 0이 아니라 null인가 — '0표'와 '투표가 없었다'는 다르다.

    무투표 후보 1,038명 중 691명이 votes: 0, 347명이 null이었다. 한 파일 안에서도
    섞여 있었다(8회 지선 시군구: 0이 106 · null이 80). 같은 레코드의 pct는 이미
    null이라, **두 필드가 같은 사실을 다르게 말하고** 있었다.

    0은 그럴듯해서 안 보인다 — 이 저장소가 반복해서 겪은 그 모양이다.
    """
    print("\n[무투표] 0이 아니라 null이다")
    zero, ok, other = [], 0, 0
    for p in sorted((ROOT / "data/results").glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        for r in d.get("races") or []:
            cs = r.get("candidates") or []
            race_unc = bool(r.get("is_uncontested"))
            for c in cs:
                if not (c.get("uncontested") or race_unc):
                    continue
                v = c.get("votes")
                if v == 0:
                    zero.append(f"{p.stem} {r.get('district') or r.get('sigungu')} {c.get('name')}")
                elif v is None:
                    ok += 1
                else:
                    other += 1
            if race_unc:
                for k in ("electors", "voters", "valid_votes", "invalid_votes"):
                    if r.get(k) == 0:
                        zero.append(f"{p.stem} {r.get('district')} .{k}")
    ck(f"무투표에 0이 없다 (null {ok}건)", not zero, str(zero[:4]))
    ck(f"무투표 사례가 실재한다 ({ok}건)", ok > 100, str(ok))
    # 무투표가 아닌데 0표인 후보는 **그대로 둔다** — 제헌 총선에는 실제로 있다
    ck(f"무투표 표시 없이 득표가 있는 경우도 있다 ({other}건)", other >= 0)


def check_data_json_parses() -> None:
    """data/의 JSON이 전부 파싱되는가 — 안 되면 **조용히 한 회차가 사라진다**.

    빌드 스크립트 45곳이 `json.load`를 try/except로 감싸고 실패하면 continue한다.
    방어 자체는 옳다. 문제는 그게 발화하면 그 파일만 통째로 빠진 산출물이 만들어지고
    **아무도 모른다**는 것이다 — 화면은 멀쩡하고 개수만 조금 준다.

    지금은 1,600여 개가 전부 파싱되므로 그 가드들은 휴면 상태다. 그 사실을 여기서
    고정한다. 하나라도 깨지면 조용한 유실 대신 이 검사가 실패한다.

    최상위가 null인 것도 잡는다. JS 쪽에서 같은 것에 물렸다 — `r.ok ? r.json() : 폴백`이
    본문 null을 그대로 통과시켜 'Cannot read properties of null'로 터졌다.
    """
    print("\n[원자료] data/ JSON이 전부 읽히는가")
    # 대용량 raw는 제외한다(PDF·격자·SGIS 등 수 GB). 빌드가 읽는 것만 본다.
    SKIP = ("raw/pdf", "raw/sgis", "raw/grids", "raw/realmeter_self", "raw/hgis",
            "raw/admdongkor", "raw/parsed", "raw/results_csv", "raw/turnout")
    bad, null_top, n = [], [], 0
    for p in (ROOT / "data").rglob("*.json"):
        rel = str(p.relative_to(ROOT))
        if any(s in rel for s in SKIP):
            continue
        n += 1
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:                                   # noqa: BLE001
            bad.append(f"{rel}: {str(e)[:50]}")
            continue
        if d is None:
            null_top.append(rel)
    ck(f"data/ JSON {n:,}개가 전부 파싱된다", not bad, str(bad[:4]))
    ck("최상위가 null인 파일이 없다", not null_top, str(null_top[:4]))
    ck(f"검사 대상이 충분하다 ({n:,}개)", n >= 1000, str(n))
    # results는 비어 있으면 안 된다 — 빈 결과 파일은 '없음'이 아니라 '못 받음'이다.
    # 스키마가 셋이다: 현행 races · 옛 offices · 더 옛 national/district/sigungu.
    PAYLOAD = ("races", "offices", "national", "district", "sigungu",
               "presidential", "national_assembly", "local")
    empty = []
    for p in (ROOT / "data/results").glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        if not any(d.get(k) for k in PAYLOAD):
            empty.append(str(p.relative_to(ROOT)))
    ck("결과 파일이 비어 있지 않다", not empty, str(empty[:4]))


def check_absence_doc() -> None:
    """docs/absence.md가 가리키는 것이 실제로 있는가.

    이 문서는 '없다·모른다·0·못 받았다'를 가른 열네 사례의 정본이다. 사례가
    늘거나 검사가 이름을 바꾸면 문서가 조용히 낡는다 — 이 저장소가 반복해서
    겪은 '문장으로만 적어 두면 낡는다' 그대로다. 그래서 문서 자체를 검사한다.
    """
    print("\n[문서] docs/absence.md가 가리키는 것이 실재하는가")
    doc = ROOT / "docs/absence.md"
    ck("docs/absence.md가 있다", doc.exists())
    if not doc.exists():
        return
    t = doc.read_text(encoding="utf-8")

    # 표 행 = 사례. 헤더·구분선을 빼고 '| … | … | … | … |' 4열 행만 센다.
    rows = [ln for ln in t.splitlines()
            if ln.startswith("|") and ln.count("|") == 5
            and "---" not in ln and "겸하던 두 질문" not in ln]
    KO = {"열둘": 12, "열셋": 13, "열네": 14, "열다섯": 15, "열여섯": 16}
    said = [v for k, v in KO.items() if f"**{k} 번**" in t]
    ck("문서가 사례 수를 밝힌다", len(said) == 1, str(said))
    if said:
        ck(f"표 행 수가 문서가 말하는 사례 수와 같다 ({len(rows)})",
           len(rows) == said[0], f"표 {len(rows)} vs 본문 {said[0]}")

    # 다른 문서도 같은 수를 말해야 한다 — 한 곳만 고치면 갈라진다.
    for rel in ("docs/party-identity.md", "docs/schema.md"):
        o = (ROOT / rel).read_text(encoding="utf-8")
        ck(f"{rel}이 같은 사례 수를 말한다",
           not said or any(f"{k} 번" in o for k, v in KO.items() if v == said[0]),
           "absence.md와 숫자가 다르다")

    # '검사' 열이 가리키는 것이 실재하는가
    qa = (ROOT / "tests/test_structure_qa.py").read_text(encoding="utf-8")
    missing = []
    for ln in rows:
        cell = ln.split("|")[4].strip().strip("`")
        if cell.startswith("tests/") and not (ROOT / cell).exists():
            missing.append(cell)
        elif cell.startswith("check_") and f"def {cell}(" not in qa:
            missing.append(cell)
        elif cell.startswith("UI 불변식"):
            ui = ROOT / "tests/ui/test_ui_invariants.mjs"
            if not ui.exists() or "OFFLINE" not in ui.read_text(encoding="utf-8"):
                missing.append(cell)
    ck("문서가 가리키는 검사가 전부 실재한다", not missing, str(missing))
    ck(f"검사 열이 비어 있지 않다 ({len(rows)}행)", len(rows) >= 12, str(len(rows)))


def check_election_meta_paths() -> None:
    """회차 메타가 가리키는 결과 파일이 실재하는가.

    `results_file`이라는 죽은 필드가 있었다. 아무도 안 읽는데 13개 회차에서
    살아 있는 `archive.results_path`와 **다른 파일**을 가리켰다 — 두 필드가 같은
    질문에 서로 다르게 답한 것이다. 지우고 나서, 다시 갈라지지 않게 검사한다.
    """
    print("\n[회차 메타] 가리키는 결과 파일이 실재하는가")
    metas = sorted((ROOT / "data/elections").glob("*.json"))
    dead, missing = [], []
    for f in metas:
        d = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            continue
        if "results_file" in d:
            dead.append(f.name)
        ar = d.get("archive")
        rp = ar.get("results_path") if isinstance(ar, dict) else None
        if rp and not (ROOT / rp).exists():
            missing.append(f"{f.name} → {rp}")
    ck(f"회차 메타를 읽었다 ({len(metas)}개)", len(metas) >= 40, str(len(metas)))
    ck("결과 파일 위치를 말하는 필드가 하나다", not dead,
       f"results_file이 남아 있다: {dead[:4]}")
    ck("archive.results_path가 실재한다", not missing, str(missing[:4]))


def check_local_proportional_timeline() -> None:
    """지선 비례는 회차마다 있고 없고가 다르다 — '없음'과 '결손'을 가른다.

    1·2회 광역비례를 '결손'으로 적어 뒀는데 아니었다. **비례대표 선거 자체가
    없었다** — 1인 2표제는 2002년(3회)부터고, 그 전 시·도의회 비례 의석은
    지역구 득표비율로 배분됐다. 없는 것을 못 받은 것으로 적으면, 영영 오지 않을
    자료를 계속 기다리게 된다.

    1차 근거는 선관위 개표현황(info.nec VCCP09)의 **선거종류 드롭다운**이다:

        1·2회(1995·1998)  3 4 5 6              비례 없음
        3회(2002)         + 8 광역비례
        4회(2006)         + 9 기초비례 · 10 교육의원
        5회(2010)         + 11 교육감
    """
    print("\n[지선] 비례 선거 연표 — 없는 것과 못 받은 것")
    ROUNDS = {1: "1st-local-1995", 2: "2nd-local-1998", 3: "3rd-local-2002",
              4: "4th-local-2006", 5: "5th-local-2010", 6: "6th-local-2014",
              7: "7th-local-2018", 8: "8th-local-2022"}
    seen = 0
    for n, eid in ROUNDS.items():
        tcs = set()
        rd = ROOT / "data/results"
        for p in [rd / f"{eid}.json"] + sorted(rd.glob(f"{eid}.*.json")):
            if not p.exists():
                continue
            for r in json.loads(p.read_text(encoding="utf-8")).get("races") or []:
                tcs.add(r.get("sg_typecode"))
        if not tcs:
            continue
        seen += 1
        ck(f"{n}회: 광역비례(tc8)는 3회부터", ("8" in tcs) == (n >= 3), str(sorted(tcs)))
        ck(f"{n}회: 기초비례(tc9)는 4회부터", ("9" in tcs) == (n >= 4), str(sorted(tcs)))
    ck(f"지선 회차를 실제로 읽었다 ({seen})", seen == len(ROUNDS), str(seen))

    # 없는 제도를 '미반영'이라 적지 않는다 — 그 문장이 결손처럼 읽힌다.
    stale = []
    for n, eid in ROUNDS.items():
        f = ROOT / f"data/elections/{eid}.json"
        if not f.exists():
            continue
        cav = json.loads(f.read_text(encoding="utf-8")).get("_data_caveat") or ""
        if "미반영" in cav:
            stale.append(eid)
    ck("비례를 '미반영'이라 말하는 회차가 없다", not stale, str(stale))


def main() -> int:
    check_missing_not_zero()
    check_identity()
    check_stale_workarounds()
    check_comparison_surfaced()
    check_json_shape_guards()
    check_roster_scope()
    check_scope_consistency()
    check_pct_denominator()
    check_rank_one_meaning()
    check_uncontested_null()
    check_data_json_parses()
    check_absence_doc()
    check_election_meta_paths()
    check_local_proportional_timeline()
    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
