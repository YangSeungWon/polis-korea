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
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/build"))
from party_identity import identity, policy, unregistered, display_name  # noqa: E402

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
    for c in _applied:
        ck(f'{c["election"]} {c["stored"]} → {c["official"]}',
           disambiguate_party(c["stored"], c["election_date"]) == c["official"],
           disambiguate_party(c["stored"], c["election_date"]))
        # 같은 문자열이라도 **다른 회차는 건드리지 않는다** — 그게 이 층의 요점이다
        ck(f'{c["stored"]}: 날짜가 없으면 바꾸지 않는다',
           resolve_recorded_name(c["stored"], "") == c["stored"])
        # 해소가 **그때 없던 정당**에 표를 붙이면 안 된다. 2004년 '공화당'의 정식명은
        # 민주공화당이지만 registry의 민주공화당은 1963년 박정희 정당이다 — 그대로
        # 적용하면 24,360표가 그 정당에 붙는다. 그래서 그 건은 deferred다.
        _node = json.loads((ROOT / "data/parties/registry.json")
                           .read_text(encoding="utf-8"))["parties"].get(c["official"])
        if _node:
            _f = (_node.get("founded") or "")[:7]
            _d = (_node.get("dissolved") or "9999-99")[:7]
            _ym = c["election_date"][:7]
            ck(f'{c["election"]} {c["official"]}: 그 시점에 존재하던 정당이다',
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
