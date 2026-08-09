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
    """fetch(...).json()의 **모양 있는 fallback**이 본문 null을 거르는가.

    catch는 fetch 거부만 잡는다. 본문이 `null`이면 r.json()은 null로 정상
    resolve해 `r.ok ? r.json() : {폴백}`을 그대로 통과하고, 소비하는 쪽에서
    'Cannot read properties of null'로 터진다.

    이 종류가 세 번 났다: climate.js가 먼저 겪고 주석까지 남겼는데 같은 묶음의
    core.js엔 안 들어와 있었고, UI 감사에서 두 번은 플레이키로 넘어갔다.
    한쪽만 배우지 않도록 전수로 건다.
    """
    print("\n[본문 null] 모양 있는 fallback이 본문 null을 거르는가")
    import re as _r
    risky = []
    for p in sorted((ROOT / "assets").rglob("*.js")):
        lines = p.read_text(encoding="utf-8", errors="replace").split("\n")
        for i, ln in enumerate(lines, 1):
            if ".json()" not in ln:
                continue
            # fallback이 배열/객체 리터럴이면 **모양을 기대**하는 코드다
            fb = (_r.findall(r"json\(\)\s*:\s*(\[\]|\{[^}]*\})", ln)
                  + _r.findall(r"catch\(\(\)\s*=>\s*\(?(\[\]|\{[^}]*\})", ln))
            if not fb:
                continue
            # **같은 체인만** 본다. 앞뒤 몇 줄을 통째로 보면 이웃 호출의 가드가
            # 이 줄을 덮어 준다 — 실제로 lens-switcher에서 가드 하나를 지워도
            # 옆 줄 것 때문에 통과했다.
            chain = [ln]
            for nxt in lines[i:i + 4]:
                if nxt.strip().startswith("."):
                    chain.append(nxt)
                    continue
                # 체인의 마지막이 콜백을 열었으면 그 **본문 첫 줄**까지가 같은
                # 체인이다 — 가드가 거기 있는 게 정상이다(`.then((list) => {`
                # 다음 줄의 `if (!Array.isArray(list))`). 안 보면 오탐이 난다.
                if chain[-1].rstrip().endswith("{"):
                    chain.append(nxt)
                    if not nxt.rstrip().endswith("{"):
                        break
                    continue
                break
            ctx = "\n".join(chain)
            if ("typeof" in ctx and "object" in ctx) or "Array.isArray" in ctx:
                continue
            risky.append(f"{p.relative_to(ROOT)}:{i}")
    ck(f"모양 가드가 없는 곳이 없다 ({len(risky)}곳)", not risky, str(risky[:6]))


def main() -> int:
    check_missing_not_zero()
    check_identity()
    check_stale_workarounds()
    check_comparison_surfaced()
    check_json_shape_guards()
    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
