"""정당 identity resolver — 비교 연산이 전부 같은 문을 지나는가.

정당 문자열과 비교 identity는 다른 것이다. 분리하지 않으면 같은 버그가 연산마다
다르게 나타난다. 실제로 그랬다:
  · 승자 판정은 same_party, 득표 집계는 raw name → '국민의힘 +46%p / 미래통합당 -45%p'
    (둘은 개명인데 없는 변화가 만들어졌다)
  · '민중당'은 1965년 것과 2017년 것이 다른 당인데 한 덩어리로 세어졌다

**계보에 있다고 무조건 합산하지 않는다.** 합당·분당·선거연합은 표를 귀속시킬 근거가 없다.

실행: .venv/bin/python tests/test_party_identity.py
"""
from __future__ import annotations
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/build"))
from party_identity import identity, policy, unregistered, display_name  # noqa: E402
from party_identity import canonical  # noqa: E402


def _edate(fp):
    """결과 파일에 date가 없으면 elections 메타에서 가져온다."""
    eid = fp.name[:-5].split(".")[0]
    try:
        return json.loads((ROOT / "data/elections" / f"{eid}.json")
                          .read_text(encoding="utf-8")).get("date") or ""
    except Exception:                                            # noqa: BLE001
        return ""

G20, G24 = "2020-04-15", "2024-04-10"
fails: list[str] = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    # ── 개명은 같은 identity ────────────────────────────────────────────────
    print("\n[개명] 같은 당이 이름만 바꿨다")
    RENAMES = [
        ("미래통합당", G20, "국민의힘", G24, "2020.9 개명"),
        ("민중당", G20, "진보당", G24, "2020.6 개명 · 1965년 민중당과 다른 당"),
        ("한나라당", "2010-06-02", "새누리당", "2014-06-04", "2012.2 개명"),
    ]
    for a, da, b, db, why in RENAMES:
        ck(f"{a} ≡ {b} ({why})", identity(a, da) == identity(b, db),
           f"{identity(a, da)} vs {identity(b, db)}")
        ck(f"{a}→{b} 전이 = same", policy(a, da, b, db) == "same", policy(a, da, b, db))

    # ── 한시 당명 ──────────────────────────────────────────────────────────
    # 같은 등록 정당이 한동안 다른 이름을 썼다가 되돌린 경우다. registry에서
    # predecessors ∩ successors 가 자기 자신을 가리키는 모양(왕복)으로 나타난다.
    #
    # 이 유형은 **하나로 묶어서 검사한다.** 개별로 적으면 하나만 등록됐을 때
    # 다른 하나가 조용히 다르게 동작해도 통과한다 — 실제로 녹색정의당이
    # 미등록이라 '비교 불가'였고, 그건 판단이 아니라 registry 공백이었다.
    print("\n[한시 당명] 같은 등록 정당이 이름만 잠깐 바꿨다")
    TEMP = [("녹색정의당", G24, "2024.2 녹색당과 선거연합 · 2024.4 정의당 환원"),
            ("민주노동당(2025)", "2025-06-01", "2025.5 변경 · 2025.7 정의당 환원")]
    pols = set()
    for nm, dt, why in TEMP:
        ck(f"정의당 ≡ {nm} ({why})", identity("정의당", G20) == identity(nm, dt),
           f'{identity("정의당", G20)} vs {identity(nm, dt)}')
        pols.add(policy("정의당", G20, nm, dt))
    # 두 사례가 갈리면 둘 중 하나는 registry 공백 때문에 그렇게 보이는 것이다
    ck(f"한시 당명이 서로 같은 정책을 받는다 ({pols})", len(pols) == 1, str(pols))
    # 다만 identity가 같다고 '표가 같은 선택지'는 아니다 — 선거연합이 섞여 있으면
    # registry note가 그걸 말하고 있어야 한다(policy는 아직 이를 구분하지 못한다).
    _reg = json.loads((ROOT / "data/parties/registry.json").read_text(encoding="utf-8"))["parties"]
    for nm, _dt, _why in TEMP:
        ck(f"{nm}: 한시 당명이라는 사실이 registry에 적혀 있다",
           "한시 당명" in (_reg.get(nm, {}).get("note") or ""))

    # ── 개명 사슬 ──────────────────────────────────────────────────────────
    # 등록이 끊기지 않은 한 정당이 이름만 여러 번 바꾼 경우다. 선관위 정당등록현황의
    # **자유통일당 등록연월일이 2016-03-16**(기독자유당 창당일)이라는 게 근거다.
    # 사슬은 **끝과 끝만 보면 안 된다** — 가운데 마디가 빠지면 identity가 두 덩어리로
    # 쪼개지는데, 양끝만 비교하면 그게 안 보인다. 이웃한 마디마다 확인한다.
    print("\n[개명 사슬] 등록이 이어지면 이름이 바뀌어도 한 정당이다")
    CHAIN = [("기독자유당", "2016-04-13"), ("기독자유통일당", "2020-04-15"),
             ("국민혁명당", "2022-03-09"), ("자유통일당", "2024-04-10")]
    for (a, da), (b, db) in zip(CHAIN, CHAIN[1:]):
        ck(f"{a} ≡ {b}", identity(a, da) == identity(b, db),
           f"{identity(a, da)} vs {identity(b, db)}")
    ck("사슬 전체가 한 identity",
       len({identity(n, dt) for n, dt in CHAIN}) == 1,
       str({n: identity(n, dt) for n, dt in CHAIN}))
    # 각 이름이 **그 이름을 쓰던 때의 관측**을 실제로 덮는가 — 시기 경계가 맞아야
    # 승격이 의미가 있다(1971 정의당이 어긋난 게 이 지점이었다)
    for n, dt in CHAIN:
        ck(f"{n}: 관측 시점({dt})이 registry가 아직 등록으로 인정한다",
           not unregistered(n, dt), n)

    # ── 합당·분당은 잇지 않는다 ────────────────────────────────────────────
    print("\n[합당·분당] 표를 귀속시킬 근거가 없다")
    for a, b, why in [("더불어시민당", "더불어민주당", "위성정당 합당 — 유권자 선택 구조가 달랐다"),
                      ("열린민주당", "더불어민주당", "합당")]:
        ck(f"{a} ≢ {b} ({why})", identity(a, G20) != identity(b, G24),
           f"{identity(a, G20)} == {identity(b, G24)}")
        ck(f"{a}→{b} 전이가 same이 아니다", policy(a, G20, b, G24) != "same",
           policy(a, G20, b, G24))

    # ── 매칭 실패는 최신 노드로 가지 않는다 ────────────────────────────────
    #
    # 두 번 같은 방식으로 틀렸다: 1971년 정의당(122,914표)이 2012년 정의당으로,
    # 2016년 민주당(209,872표)이 더불어민주당으로. 둘 다 '어느 구간에도 안 걸림'을
    # '최신 것'으로 바꿔서 생겼다. 사례별 검사 대신 **함수 수준 불변식**으로 건다.
    print("\n[fallback 금지] 모르면 최신 정당으로 보내지 않는다")
    from party_canon import _BASE_ERAS, _REUSED_BASES, disambiguate_party  # noqa: E402

    def next_month(ym):
        # registry에는 연도만 적힌 것도 있다("1988"). 그 경우 12월로 본다 —
        # 빈틈을 **좁게** 잡아야 없는 빈틈을 만들지 않는다.
        y = int(ym[:4])
        m = int(ym[5:7]) if len(ym) >= 7 and ym[5:7].isdigit() else 12
        return f"{y + (m == 12)}-{(m % 12) + 1:02d}"

    # ── 같은 이름의 두 구간이 겹치지 않는가 ────────────────────────────────
    # 겹치면 분기 결과가 registry의 **기재 순서**에 달린다. 순서는 데이터 모델이
    # 아니라 파일 편집의 흔적이므로, 그 위에 판정을 얹으면 안 된다.
    # 월 해상도 때문에만 겹치는 경우가 하나 있다. 감추지 말고 목록으로 고정한다 —
    # 예외가 늘면 검사가 실패해서 드러난다.
    MONTH_RESOLUTION_OVERLAPS = {
        # 박근혜 새누리당은 2017-02-13 자유한국당으로 개명했고, 조원진 등이 만든
        # 새누리당은 2017-02-21 창당이다. 실제로는 8일 차이로 안 겹친다.
        ("새누리당", "새누리당(2017)"): "2017-02",
        # 민정당+민주당 민중당은 1967-02-07 신민당으로 합쳐졌고, 신민회는
        # 1967-02-25 당명을 민중당으로 바꿨다. 18일 차이로 안 겹친다.
        ("민중당", "민중당(1967)"): "1967-02",
    }
    print("\n[시기 노드] 같은 이름의 구간이 겹치지 않는다")
    _obs_months = {(r["name"], m[:7]) for r in json.loads(
        (ROOT / "data/parties/observed.json").read_text(encoding="utf-8"))["parties"]
        for m in (r["first"], r["last"])}
    for base in sorted(_REUSED_BASES):
        nodes = sorted((n_f_d for n_f_d in _BASE_ERAS[base] if n_f_d[1]),
                       key=lambda t: t[1])
        for (n1, _f1, d1), (n2, f2, _d2) in zip(nodes, nodes[1:]):
            if f2 > d1:
                ck(f"{n1} ~ {n2}: 구간이 안 겹친다", True)
                continue
            month = MONTH_RESOLUTION_OVERLAPS.get((n1, n2))
            ck(f"{n1} ~ {n2}: 겹침이 월 해상도 탓임이 기록돼 있다",
               month is not None and month == f2,
               f"{f2} ~ {d1} 겹침 — 알려진 예외가 아니다")
            # 알려진 예외라도 **그 달에 관측이 떨어지면** 순서 의존이 실제 판정을
            # 바꾼다. 그때는 예외로 넘길 수 없다.
            ck(f"{n1} ~ {n2}: 겹치는 달({month})에 관측이 없다",
               (base, month) not in _obs_months and month not in
               {m for n, m in _obs_months if n == base},
               f"{base} 관측이 {month}에 있다")

    for base in sorted(_REUSED_BASES):
        spans = sorted(((f, d) for _n, f, d in _BASE_ERAS[base] if f), key=lambda t: t[0])
        # ① 첫 노드보다 이른 날짜
        ck(f"{base}: 첫 구간보다 이르면 원자료 이름 그대로",
           disambiguate_party(base, "1800-01-01") == base,
           f'→ {disambiguate_party(base, "1800-01-01")}')
        # ② 마지막 노드보다 늦은 날짜 — **현존 정당이면 건너뛴다**(dissolved가 없으니
        #    2999년도 그 구간 안이다. 그건 fallback이 아니라 정상 매칭이다)
        if all(d != "9999-99" for _f, d in spans):
            probe = f"{int(spans[-1][1][:4]) + 50}-01-01"
            ck(f"{base}: 마지막 구간보다 늦으면 원자료 이름 그대로",
               disambiguate_party(base, probe) == base,
               f"→ {disambiguate_party(base, probe)}")
        # ③ 구간 **사이의 빈틈** — 2016년 민주당이 바로 여기 떨어졌다.
        #    '민주당'만은 registry 노드가 아니라 _MINJOO_ERAS(연속 구간)로 가른다.
        #    1963·1967 재편처럼 노드 사이가 비어도 같은 계열로 이어지는 구간이 있어서
        #    빈틈 탐침이 성립하지 않는다 — 아래 전용 검사로 따로 본다.
        for (_f1, d1), (f2, _d2) in (zip(spans, spans[1:]) if base != "민주당" else []):
            if d1 == "9999-99" or not d1 or next_month(d1) >= f2:
                continue
            gap = next_month(d1) + "-15"
            ck(f"{base}@{gap[:7]}: 구간 사이 빈틈이면 원자료 이름 그대로",
               disambiguate_party(base, gap) == base,
               f"→ {disambiguate_party(base, gap)}")
    ck("민주당 2016: 최신 노드(더불어민주당)로 가지 않는다",
       disambiguate_party("민주당", "2016-04-13") != "더불어민주당",
       disambiguate_party("민주당", "2016-04-13"))
    ck("민주당 1948: 아래쪽으로도 새지 않는다",
       disambiguate_party("민주당", "1948-05-10") == "민주당",
       disambiguate_party("민주당", "1948-05-10"))
    # 그렇다고 분기 자체가 죽으면 안 된다 — 걸리는 구간은 여전히 걸려야 한다
    for dt, want in [("1958-05-02", "민주당(1955)"), ("1992-03-24", "민주당(1991)"),
                     ("2012-04-11", "민주통합당")]:
        ck(f"민주당@{dt} → {want}", disambiguate_party("민주당", dt) == want,
           disambiguate_party("민주당", dt))

    # ── 2016년 두 민주당이 동시에 살아 있는가 ──────────────────────────────
    # 원자료를 정규화로 덮어써서 한 정당이 사라졌던 자리다(f87861d37).
    print("\n[원자료 보존] 2016 비례에 두 실체가 함께 있다")
    _r16 = json.loads((ROOT / "data/results/20th-general-2016.json")
                      .read_text(encoding="utf-8"))
    _nat = [r for r in _r16["races"]
            if r.get("sg_typecode") == "7" and r.get("scope") == "nation"]
    _v = {c["party"]: c["votes"] for r in _nat for c in r["candidates"]}
    ck("더불어민주당 6,069,744", _v.get("더불어민주당") == 6069744, str(_v.get("더불어민주당")))
    ck("민주당 209,872", _v.get("민주당") == 209872, str(_v.get("민주당")))
    ck(f"비례 정당 21종 (NEC 원자료와 같은 수)", len(_v) == 21, str(len(_v)))
    ck("둘은 다른 identity",
       identity("민주당", "2016-04-13") != identity("더불어민주당", "2016-04-13"),
       identity("민주당", "2016-04-13"))

    # ── 한나라당 세 실체 ──────────────────────────────────────────────────
    # 개명으로 이름이 비면 다른 정당이 그 이름을 가져간다. 19대 총선 비례 투표용지에는
    # 새누리당(기호 1)과 한나라당(기호 20)이 **동시에** 있었다 — 선관위 공고로 확인된다.
    # 노드가 하나뿐이면 2012년 이후 341,814표가 박근혜 한나라당에 붙거나,
    # 구간 밖으로 떨어져 어디에도 안 붙는다.
    print("\n[이름 재사용] 이름이 비면 다른 정당이 가져간다")
    _r12 = json.loads((ROOT / "data/results/19th-general-2012.json")
                      .read_text(encoding="utf-8"))
    _n12 = [r for r in _r12["races"]
            if r.get("sg_typecode") == "7" and r.get("scope") == "nation"]
    _v12 = {c["party"]: c["votes"] for r in _n12 for c in r["candidates"]}
    ck("2012 비례에 새누리당 9,130,651", _v12.get("새누리당") == 9130651, str(_v12.get("새누리당")))
    ck("2012 비례에 한나라당 181,822", _v12.get("한나라당") == 181822, str(_v12.get("한나라당")))
    for dt, want in [("2008-04-09", "한나라당"), ("2012-04-11", "한나라당(2012)"),
                     ("2016-04-13", "한나라당(2014)"), ("2026-06-03", "한나라당(2014)")]:
        ck(f"한나라당@{dt} → {want}", disambiguate_party("한나라당", dt) == want,
           disambiguate_party("한나라당", dt))
    ck("2012 두 이름은 다른 identity",
       identity("한나라당", "2012-04-11") != identity("새누리당", "2012-04-11"),
       identity("한나라당", "2012-04-11"))
    # 조원진 새누리당은 **소멸하지 않았다**. dissolved=2022-03이 잘못 적혀 있어
    # 22대 총선 비례 57,210표가 구간 밖으로 떨어져 있었다. 선관위 정당등록현황에
    # 등록연월일 2017-04-10으로 지금도 있다.
    for dt, want in [("2016-04-13", "새누리당"), ("2017-05-09", "새누리당(2017)"),
                     ("2022-03-09", "새누리당(2017)"), ("2024-04-10", "새누리당(2017)")]:
        ck(f"새누리당@{dt} → {want}", disambiguate_party("새누리당", dt) == want,
           disambiguate_party("새누리당", dt))
    _r24 = json.loads((ROOT / "data/results/22nd-general-2024.json")
                      .read_text(encoding="utf-8"))
    _v24 = {c["party"]: c["votes"] for r in _r24["races"]
            if r.get("sg_typecode") == "7" and r.get("scope") == "nation"
            for c in r["candidates"]}
    ck("2024 비례에 새누리당 57,210", _v24.get("새누리당") == 57210, str(_v24.get("새누리당")))
    ck("2024 새누리당 ≠ 국민의미래",
       identity("새누리당", "2024-04-10") != identity("국민의미래", "2024-04-10"),
       identity("새누리당", "2024-04-10"))

    # 이승만 자유당(1951~1970)과 2020년 손상윤 자유당. 조직 연속성은 없다 —
    # 대표가 '이승만의 반공 정신을 잇는다'고 말한 것은 계보가 아니다.
    for dt, want in [("1960-03-15", "자유당"), ("2020-04-15", "자유당(2020)")]:
        ck(f"자유당@{dt} → {want}", disambiguate_party("자유당", dt) == want,
           disambiguate_party("자유당", dt))
    # 2020년 '통일민주당'은 2015-10-07 등록된 정당(→국민대통합당)이 10개월 쓴 이름이다.
    for dt, want in [("1988-04-26", "통일민주당"), ("2020-04-15", "통일민주당(2020)")]:
        ck(f"통일민주당@{dt} → {want}",
           disambiguate_party("통일민주당", dt) == want,
           disambiguate_party("통일민주당", dt))
    # '구 평화민주당을 계승한다'는 창당 명분은 계보가 아니다. 별도 등록·19년 공백.
    for dt, want in [("1988-04-26", "평화민주당"), ("2010-06-02", "평화민주당(2010)")]:
        ck(f"평화민주당@{dt} → {want}",
           disambiguate_party("평화민주당", dt) == want,
           disambiguate_party("평화민주당", dt))
    # ── identity 층에서도 같은 병합이 일어나면 안 된다 ─────────────────────
    # disambiguate_party의 fallback은 막아 뒀는데, 못 가른 이름이 마침 registry에
    # 있으면 identity()가 한 층 뒤에서 그 정당의 pid를 내줬다. 1,654,284표가
    # 그렇게 '아는 정당'에 붙어 있었다.
    print("\n[생애 밖] 그 정당이 없던 때의 표를 그 정당에 붙이지 않는다")
    from party_identity import _outside_lifetime  # noqa: E402
    _stray, _bad_date = collections.Counter(), {}
    for _fp in sorted((ROOT / "data/results").glob("*.json")):
        if ".sigungu." in _fp.name:
            continue
        try:
            _d = json.loads(_fp.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        _dt = _d.get("date") or _edate(_fp)
        for _r in _d.get("races") or []:
            if _r.get("scope") not in ("nation", "district", "sido"):
                continue
            for _c in _r.get("candidates") or []:
                _p = _c.get("party") or ""
                if not _p or _p == "무소속":
                    continue
                _cn = canonical(_p, _dt)
                if _outside_lifetime(_cn, _dt):
                    _stray[_cn] += _c.get("votes") or 0
                    _bad_date[_cn] = _dt
    ck(f"생애 밖 관측이 남아 있다 ({len(_stray)}종, {sum(_stray.values()):,}표) — "
       "0이면 검사가 죽은 것이다", bool(_stray))
    # 생애 밖 이름이 그 정당의 pid를 받으면 안 된다
    for _n in sorted(_stray):
        ck(f"{_n}: 생애 밖 표가 pid:{_n}로 가지 않는다",
           identity(_n, _bad_date[_n]) != f"pid:{_n}",
           identity(_n, _bad_date[_n]))
    # 생애 안/밖이 같은 pid를 받으면 안 된다
    for _n, _out, _in in [("민주통일당", "2012-04-11", "1973-02-27"),
                          ("대한국민당", "2024-04-10", "1950-05-30"),
                          ("공화당", "2024-04-10", "1997-12-18")]:
        ck(f"{_n}: {_out} ≠ {_in}",
           identity(_n, _out) != identity(_n, _in),
           f"{identity(_n, _out)} == {identity(_n, _in)}")

    # 민국당은 2001년이 아니라 17대 총선(2004-04)까지 살아 있었다. dissolved 오기로
    # 2004년 지역구 4,347표가 한민당계 민주국민당(1949)에 붙어 있었다.
    for dt, want in [("1950-05-30", "민주국민당"), ("2000-04-13", "민주국민당(2000)"),
                     ("2004-04-15", "민주국민당(2000)")]:
        ck(f"민주국민당@{dt} → {want}",
           disambiguate_party("민주국민당", dt) == want,
           disambiguate_party("민주국민당", dt))

    # 민중당은 넷이다. 1967-02에 하나는 신민당으로 합쳐지고(2-07) 다른 하나가
    # 그 이름을 이어받았다(2-25) — 같은 달에 주인이 바뀐다.
    for dt, want in [("1967-05-03", "민중당(1967)"), ("1967-06-08", "민중당(1967)"),
                     ("1971-05-25", "민중당(1967)"), ("1992-03-24", "민중당(1990)"),
                     ("2020-04-15", "민중당(2017)")]:
        ck(f"민중당@{dt} → {want}", disambiguate_party("민중당", dt) == want,
           disambiguate_party("민중당", dt))
    ck("1948 민중당은 아직 모른다 — 아는 정당에 붙이지 않는다",
       identity("민중당", "1948-05-10") == "pid:민중당(미상)",
       identity("민중당", "1948-05-10"))

    # 김구 한독당과, 국제녹색당(2007 등록)이 2022 개명한 한독당.
    for dt, want in [("1948-05-10", "한국독립당"), ("2026-06-03", "한국독립당(2022)")]:
        ck(f"한국독립당@{dt} → {want}",
           disambiguate_party("한국독립당", dt) == want,
           disambiguate_party("한국독립당", dt))

    for dt, want in [("1963-11-26", "자유민주당"), ("2024-04-10", "자유민주당(2021)")]:
        ck(f"자유민주당@{dt} → {want}",
           disambiguate_party("자유민주당", dt) == want,
           disambiguate_party("자유민주당", dt))
    # 흡수는 계열을 전파하지 않는다 — 자유당(2020)이 자유민주당(2021)에 흡수됐어도
    # 2020년 자유당 표를 2024년 자유민주당 표와 같은 identity로 세지 않는다.
    ck("자유당(2020) ≢ 자유민주당(2021) — 흡수는 합산 근거가 아니다",
       identity("자유당", "2020-04-15") != identity("자유민주당", "2024-04-10"),
       identity("자유당", "2020-04-15"))

    # ── '소멸했다'와 '거기까지만 안다'를 가른다 ────────────────────────────
    # 국민회는 1951년에 여당 지위를 잃었을 뿐 3·4대 총선에 계속 나왔다. 소멸 시점은
    # 모른다 — dissolved를 지우면 뒤 시대를 삼키고, 지어내면 없는 사실을 만든다.
    print("\n[미상 경계] dissolved가 소멸을 뜻하지 않는 경우")
    _bounded = {n: i for n, i in _reg.items() if i.get("dissolved_bound")}
    ck(f"dissolved_bound를 쓰는 노드가 있다 ({len(_bounded)}종)", bool(_bounded))
    _life = json.loads((ROOT / "data/parties/lifecycle.json")
                       .read_text(encoding="utf-8"))["parties"]
    for _n, _i in _bounded.items():
        ck(f"{_n}: bound 값이 어휘 안에 있다",
           _i["dissolved_bound"] == "last_known_active", _i["dissolved_bound"])
        ck(f"{_n}: dissolved가 비어 있지 않다 (경계는 있어야 한다)", bool(_i.get("dissolved")))
        ck(f"{_n}: 생애 사건이 dissolution으로 굳지 않는다",
           (_life.get(_n) or {}).get("ended_by", {}).get("type") == "unknown",
           str((_life.get(_n) or {}).get("ended_by")))
        # 경계 자체는 살아 있어야 한다 — 뒤 시대 관측을 삼키면 안 된다
        _after = f"{int(_i['dissolved'][:4]) + 20}-01-01"
        ck(f"{_n}: 확인 범위 밖({_after[:4]})은 그 정당으로 안 간다",
           identity(_n, _after) != f"pid:{_n}", identity(_n, _after))
    for dt, want in [("1950-05-30", "국민회"), ("1954-05-20", "국민회"),
                     ("1958-05-02", "국민회")]:
        ck(f"국민회@{dt} → {want}", disambiguate_party("국민회", dt) == want,
           disambiguate_party("국민회", dt))
    # 대한국민당도 같은 유형이었다 — 1951-12는 자유당 창당으로 주류가 빠진 때이지
    # 소멸이 아니다. 1958-07까지 존속했고 3대 총선 3석을 얻었다.
    for dt, want in [("1950-05-30", "대한국민당"), ("1954-05-20", "대한국민당"),
                     ("2024-04-10", "대한국민당(2021)"),
                     ("2026-06-03", "대한국민당(2021)")]:
        ck(f"대한국민당@{dt} → {want}",
           disambiguate_party("대한국민당", dt) == want,
           disambiguate_party("대한국민당", dt))
    ck("대한국민당 ≢ 자유당 — 주류 이탈은 후신이 아니다",
       identity("대한국민당", "1954-05-20") != identity("자유당", "1954-05-20"),
       identity("대한국민당", "1954-05-20"))
    # '공화당'은 세 정당이 쓴 이름이고, 그중 하나는 도중에 정식명이 바뀌었다.
    for dt, want in [("1997-12-18", "공화당"), ("2000-04-13", "공화당"),
                     ("2004-04-15", "민주공화당(1997)"),
                     ("2016-04-13", "공화당(2014)"), ("2020-04-15", "공화당(2014)"),
                     ("2024-04-10", "공화당(2024)"), ("2026-06-03", "공화당(2024)")]:
        ck(f"공화당@{dt} → {want}", disambiguate_party("공화당", dt) == want,
           disambiguate_party("공화당", dt))
    ck("2004 공화당이 박정희 민주공화당으로 가지 않는다",
       identity("공화당", "2004-04-15") != identity("민주공화당", "1967-06-08"),
       identity("공화당", "2004-04-15"))
    ck("1997·2004는 같은 정당 (등록명만 바뀌었다)",
       identity("공화당", "1997-12-18") == identity("공화당", "2004-04-15"),
       f'{identity("공화당", "1997-12-18")} vs {identity("공화당", "2004-04-15")}')
    ck("대한독립촉성국민회 ≡ 국민회 (1948-12-26 개칭)",
       identity("대한독립촉성국민회", "1948-05-10") == identity("국민회", "1950-05-30"),
       f'{identity("대한독립촉성국민회", "1948-05-10")} vs {identity("국민회", "1950-05-30")}')

    for dt, want in [("2008-04-09", "친박연대"), ("2018-06-13", "친박연대(2017)")]:
        ck(f"친박연대@{dt} → {want}",
           disambiguate_party("친박연대", dt) == want,
           disambiguate_party("친박연대", dt))
    ck("자유당 1970~2020 사이는 원자료 이름 그대로",
       disambiguate_party("자유당", "1990-01-01") == "자유당",
       disambiguate_party("자유당", "1990-01-01"))

    # 2013-04 재등록 ~ 2014-02 개명 사이에는 '한나라당'이라는 정당이 없었다.
    # 없는 것을 있는 것으로 만들지 않는다.
    ck("2013 공백기엔 원자료 이름 그대로",
       disambiguate_party("한나라당", "2013-08-01") == "한나라당",
       disambiguate_party("한나라당", "2013-08-01"))

    # ── 등록약칭 해소 층 ───────────────────────────────────────────────────
    # NEC 개표 API는 등록약칭을 준다. 그 약칭이 회차마다 다른 정당을 가리키는 일이 있어
    # (선거일, 문자열) 쌍으로만 가를 수 있다. **원자료는 건드리지 않는다** —
    # 2016년 민주당 사고가 정확히 원자료를 치환해서 났다.
    print("\n[약칭 해소] 읽는 시점에만 바꾼다")
    from party_canon import resolve_recorded_name  # noqa: E402

    _fid = json.loads((ROOT / "data/parties/name_fidelity.json").read_text(encoding="utf-8"))
    _applied = [c for c in _fid["cases"] if c["status"] == "applied"]
    _defer = [c for c in _fid["cases"] if c["status"] == "deferred"]
    ck(f"적용 대상이 있다 ({len(_applied)}건)", bool(_applied))
    # 한 회차 안에서 문자열↔정식명은 1:1이어야 한다. 한 문자열이 두 정식명으로
    # 가면 어느 쪽인지 정할 수 없고, 두 문자열이 한 정식명으로 가면 원자료에서
    # 별개였던 행이 합쳐진다 — 2016년 민주당이 정확히 뒤쪽이었다.
    _by_date = collections.defaultdict(list)
    for c in _applied:
        _by_date[c["election_date"]].append((c["stored"], c["official"]))
    for _d, _ps in sorted(_by_date.items()):
        _st = collections.Counter(s for s, _ in _ps)
        _of = collections.Counter(o for _, o in _ps)
        ck(f"{_d}: 한 문자열이 한 정식명으로만 간다",
           all(v == 1 for v in _st.values()),
           str([k for k, v in _st.items() if v > 1]))
        ck(f"{_d}: 두 문자열이 한 정식명으로 합쳐지지 않는다",
           all(v == 1 for v in _of.values()),
           str([k for k, v in _of.items() if v > 1]))
    for c in _applied:
        # 이 층이 하는 일은 **문자열 → 그 회차 정식명**까지다. 그 뒤 시기 분기가
        # 정식명을 재사용 이름으로 보고 노드를 고르는 건 다음 층의 일이다.
        ck(f'{c["election"]} {c["stored"]} → {c["official"]}',
           resolve_recorded_name(c["stored"], c["election_date"]) == c["official"],
           resolve_recorded_name(c["stored"], c["election_date"]))
        # 같은 문자열이라도 **다른 회차는 건드리지 않는다** — 그게 이 층의 요점이다
        ck(f'{c["stored"]}: 날짜가 없으면 바꾸지 않는다',
           resolve_recorded_name(c["stored"], "") == c["stored"])
        # 해소가 **그때 없던 정당**에 표를 붙이면 안 된다. 2004년 '공화당'의 정식명은
        # 민주공화당인데 registry의 민주공화당은 1963년 박정희 정당이었다 — 그대로
        # 적용하면 24,360표가 그 정당에 붙는다. 민주공화당(1997) 노드가 생기기
        # 전까지 이 건이 deferred였던 이유다. 두 층을 다 거친 결과로 확인한다.
        # **약칭과 별개 정당을 가르는 신호**: 같은 회차에 정식명이 따로 행으로
        # 있으면 그건 약칭이 아니라 두 정당이다. 2016년 민주당 사고가 바로 그
        # 구별을 못 해서 났다. 19대 '기독당'(=기독자유민주당) 옆에 한국기독당이
        # 따로 있는 것처럼, 비슷한 이름이 같이 있는 회차가 실제로 많다.
        _same_day = set()
        for _fp2 in sorted((ROOT / "data/results").glob("*.json")):
            if ".sigungu." in _fp2.name:
                continue
            try:
                _d2 = json.loads(_fp2.read_text(encoding="utf-8"))
            except Exception:                                    # noqa: BLE001
                continue
            if (_d2.get("date") or _edate(_fp2)) != c["election_date"]:
                continue
            for _r2 in _d2.get("races") or []:
                for _c2 in _r2.get("candidates") or []:
                    if _c2.get("party"):
                        _same_day.add(_c2["party"])
        ck(f'{c["election"]} {c["stored"]}: 같은 회차에 정식명이 따로 없다',
           c["official"] not in _same_day,
           f'{c["official"]}가 별도 행으로 있다 — 약칭이 아니라 다른 정당이다')
        _final = disambiguate_party(c["stored"], c["election_date"])
        _reg_all = json.loads((ROOT / "data/parties/registry.json")
                              .read_text(encoding="utf-8"))["parties"]
        ck(f'{c["election"]} {c["stored"]}: 정식명 계열로 간다',
           re.sub(r"\(\d{4}\)$", "", _final) == c["official"], _final)
        _node = _reg_all.get(_final)
        if _node:
            _f = (_node.get("founded") or "")[:7]
            _d = (_node.get("dissolved") or "9999-99")[:7]
            _ym = c["election_date"][:7]
            ck(f'{c["election"]} {_final}: 그 시점에 존재하던 정당이다',
               bool(_f) and _f <= _ym <= _d, f"{_f}~{_d} vs {_ym}")
    for c in _defer:
        ck(f'{c["election"]} {c["stored"]}: 막아 둔 건은 적용되지 않는다',
           resolve_recorded_name(c["stored"], c["election_date"]) == c["stored"],
           resolve_recorded_name(c["stored"], c["election_date"]))
        ck(f'{c["election"]} {c["stored"]}: 막은 이유가 적혀 있다', bool(c.get("blocked_by")))
    # 원자료 불변 — 해소된 이름이 results 파일에 스며들지 않았는가
    for c in _fid["cases"]:
        eid_files = sorted((ROOT / "data/results").glob("*.json"))
        raw_has_stored = raw_has_official = False
        for fp in eid_files:
            try:
                doc = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:                                    # noqa: BLE001
                continue
            if (doc.get("_meta") or {}).get("election_date") != c["election_date"]:
                continue
            names = {x.get("party") for r in doc.get("races") or []
                     for x in r.get("candidates") or []}
            raw_has_stored |= c["stored"] in names
            raw_has_official |= c["official"] in names
        ck(f'{c["election"]} 원자료에 저장 문자열이 그대로 있다 ({c["stored"]})',
           raw_has_stored)
        ck(f'{c["election"]} 원자료에 해소된 이름이 스며들지 않았다 ({c["official"]})',
           not raw_has_official)

    # ── 동음이의 ────────────────────────────────────────────────────────────
    print("\n[동음이의] 이름이 같아도 다른 당")
    ck("민중당 1965 ≠ 민중당 2017",
       identity("민중당", "1965-06-01") != identity("민중당", G20),
       f'{identity("민중당", "1965-06-01")} vs {identity("민중당", G20)}')

    # ── stable id는 화면에 안 나간다 ────────────────────────────────────────
    print("\n[라벨] 계보 대표를 화면에 쓰지 않는다")
    pid = identity("국민의힘", G24)
    ck("identity는 내부 접두사를 가진다 (화면용 아님)", pid.startswith("pid:"), pid)
    ck("display_name은 그 회차 이름", display_name(pid, {pid: "국민의힘"}) == "국민의힘")
    cmp_fp = ROOT / "data/comparisons/general/22nd-general-2024__21st-general-2020.json"
    if cmp_fp.exists():
        d = json.loads(cmp_fp.read_text(encoding="utf-8"))
        # 집계는 대표성 게이트를 통과할 때만 생성된다(test_aggregation_gate 참조).
        # identity가 새는지는 **unit-level share_delta**로 본다 — 그건 항상 있다.
        keys = sorted({k for u in d["units"] for k in (u.get("share_delta") or {})})
        ck("산출물에 pid가 새지 않았다", not any(k.startswith("pid:") for k in keys), str(keys[:3]))
        ck("산출물에 옛 이름(미래통합당)이 라벨로 없다", "미래통합당" not in keys, str(keys[:6]))
        # 개명을 못 이으면 한 선거구에서 ±40%p 같은 값이 나온다 — identity가 섰는지의 신호
        worst = max((abs(v) for u in d["units"] for v in (u.get("share_delta") or {}).values()),
                    default=0)
        ck(f"선거구 delta가 현실적 범위 (최대 {worst:.1f}%p < 60)", worst < 60, str(worst))
        ck("분모 규칙이 적혀 있다", "두 회차 모두" in d.get("swing_denominator", ""))
        ck("registry 공백이 드러난다", "unregistered_parties" in d)
        # 공백 목록은 **registry를 채우면 줄어야 한다.** 여기 이름을 하나 박아두면
        # 그 이름을 해소한 순간 검사가 거짓이 된다(녹색정의당이 그랬다).
        # 검사할 것은 특정 이름이 아니라 **목록이 registry와 어긋나지 않는가**다.
        ck("공백 목록이 여전히 드러난다 (0이 되면 그것도 의심스럽다)",
           bool(d["unregistered_parties"]))
        ck("registry에 있는 이름은 공백 목록에 없다",
           not [p for p in d["unregistered_parties"] if p in _reg],
           str([p for p in d["unregistered_parties"] if p in _reg][:3]))

    # ── 비교 코드에 raw 문자열 비교가 남아 있지 않은가 ──────────────────────
    print("\n[전수] 비교 코드가 resolver를 우회하지 않는가")
    src = (ROOT / "scripts/build/build_general_comparison.py").read_text(encoding="utf-8")
    body = "\n".join(l for l in src.split("\n") if not l.strip().startswith("#"))
    raw = re.findall(r'\.party\s*==[^=]|party\s*==\s*[\'"]|same_party\(|party_key\(', body)
    ck("raw 정당명 비교가 없다", not raw, str(raw[:3]))
    ck("identity()를 쓴다", "identity(" in body)

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
