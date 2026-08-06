"""총선 회차 간 비교 — **비교 가능한 선거구만**.

22대↔21대 vertical slice다. '총선 비교 완성'이 아니다.

선거구는 회차마다 획정이 바뀐다. 이름이 같아도 유권자가 다르면 그 delta는 거짓이다.
그래서 data/district_lineage/{현재}__{직전}.json의 판정을 그대로 따른다:

  comparable == "yes"     → 득표 swing·격차·투표율 delta를 만든다
  comparable == "unknown" → 관계만 보여주고 delta는 만들지 않는다(판정 보류)
  comparable == "no"      → 관계만 보여준다(획정 변경)

**split/merged를 안다고 delta를 만들 수는 없다.** A → B + C 에서 A의 과거 득표를
B와 C에 어떻게 나눌지 근거가 없다. 관계를 아는 것과 값을 나누는 것은 다른 일이다.

그리고 비교 가능한 부분집합의 합계를 **전국 변화처럼 쓰지 않는다.** 190개 안의
정당 증감과 254개 전국 결과는 다른 숫자다 — 섞으면 없는 사실이 만들어진다.

출력: data/comparisons/general/{현재}__{직전}.json
사용: python3 scripts/build/build_general_comparison.py --current 22nd-general-2024 --previous 21st-general-2020
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
# 모든 비교 연산이 **같은 resolver**를 거친다. 승자 판정과 득표 집계가 서로 다른
# 방식을 쓰면 같은 버그가 연산마다 다르게 나타난다(실제로 그랬다).
from party_identity import identity, labels_for, unregistered  # noqa: E402

OUT = ROOT / "data/comparisons/general"
LINEAGE = ROOT / "data/district_lineage"

# lineage는 시도 약칭, results는 정식명 — 키를 맞춘다.
SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북",
    "충청남도": "충남", "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주",
}


def load_races(eid: str) -> dict:
    """선거구 key → race. 지역구(tc2·district)만."""
    fp = ROOT / "data/results" / f"{eid}.json"
    d = json.loads(fp.read_text(encoding="utf-8"))
    out = {}
    for r in d.get("races") or []:
        if r.get("sg_typecode") != "2" or r.get("scope") != "district":
            continue
        sido = SHORT.get(r.get("sido") or "", r.get("sido") or "")
        out[f"{sido} {r.get('district')}".strip()] = r
    return out


def ordinal(eid: str) -> int | None:
    """22nd-general-2024 → 22."""
    head = eid.split("-")[0]
    digits = "".join(c for c in head if c.isdigit())
    return int(digits) if digits else None


def top2(race: dict) -> tuple[dict | None, dict | None]:
    cs = sorted(race.get("candidates") or [], key=lambda c: -(c.get("votes") or 0))
    return (cs[0] if cs else None), (cs[1] if len(cs) > 1 else None)


def turnout(race: dict) -> float | None:
    el, vo = race.get("electors"), race.get("voters")
    if not el or vo is None:
        return None          # 결손은 0이 아니다
    return round(vo / el * 100, 2)


def margin(race: dict) -> float | None:
    a, b = top2(race)
    if not a or not b or a.get("pct") is None or b.get("pct") is None:
        return None
    return round(a["pct"] - b["pct"], 2)


def party_share(race: dict, date: str) -> dict:
    """정당 대표키 → 득표율. 같은 정당 복수 후보는 합산.
    무소속은 합치지 않는다 — 다른 사람이다."""
    out: dict = {}
    for c in race.get("candidates") or []:
        p, pct = c.get("party"), c.get("pct")
        if not p or pct is None or p == "무소속":
            continue
        k = identity(p, date)
        out[k] = round(out.get(k, 0) + pct, 2)
    return out


def election_date(eid: str) -> str:
    fp = ROOT / "data/elections" / f"{eid}.json"
    try:
        return json.loads(fp.read_text(encoding="utf-8")).get("date") or ""
    except Exception:
        return ""


# ── 집계 게이트 ─────────────────────────────────────────────────────────────
# `comparable == "yes"`는 **그 선거구 하나의 delta를 계산할 수 있다**는 뜻일 뿐,
# 그 부분집합을 합친 값이 전국을 대표한다는 뜻이 아니다.
#
# 비교 가능한 선거구는 경계가 안정적인 곳이고, 제외되는 곳은 재획정이 많은 도시권에
# 몰린다. 선거구 계보를 고치기 전 22↔21 실측에서 1위 정당 구성이 민주당 -5.5%p /
# 국민의힘 +6.1%p 기울었다 — **측정하려는 swing(±4%p)보다 편향이 컸다.** 계보가
# 좋아진 지금 그 편차는 0.9%p지만 세종 coverage 0%로 여전히 차단된다.
# 편차 수치는 입력이 좋아지면 변한다 — 그래서 상수로 박지 않고 매번 재는 것이다.
#
# 문구로 경고하지 않는다. 대표성이 검증되지 않으면 **집계 지표를 만들지 않는다.**
MIN_ELECTORATE = 0.90    # 선거인 coverage
MAX_PARTY_SKEW = 3.0     # 1위 정당 점유율 편차(%p) — swing 크기와 맞먹으면 무의미하다
MIN_SIDO_COVER = 0.30    # 시도별 최저 coverage — 0%인 시도가 있으면 지역 대표성이 없다
METRO = {"서울", "경기", "인천"}


def coverage_audit(units: list, cur: dict) -> dict:
    """비교 가능 subset이 전체를 대표하는가 — 숫자로 답한다."""
    yes = {u["district"] for u in units if u["comparable"] == "yes"}
    all_k = [k for k in cur]

    def electors(ks):
        return sum(cur[k].get("electors") or 0 for k in ks if k in cur)

    def winner_party(k):
        cs = sorted(cur[k].get("candidates") or [], key=lambda c: -(c.get("votes") or 0))
        return (cs[0].get("party") or "무소속") if cs else None

    el_all, el_yes = electors(all_k), electors(yes)
    by_sido: dict = {}
    for k in all_k:
        sd = k.split()[0]
        b = by_sido.setdefault(sd, {"total": 0, "compared": 0})
        b["total"] += 1
        if k in yes:
            b["compared"] += 1
    for b in by_sido.values():
        b["pct"] = round(b["compared"] / b["total"] * 100, 1)

    w_all, w_yes = Counter(), Counter()
    for k in all_k:
        p = winner_party(k)
        if p:
            w_all[p] += 1
            if k in yes:
                w_yes[p] += 1
    party_share = {}
    # set 순회는 실행마다 순서가 달라 같은 입력에서도 diff가 생긴다. 그러면 이 파일은
    # '항상 변경됨'이 되어 낡은 것과 구별되지 않는다 — 정렬해서 결정적으로 만든다.
    for p in sorted(w_all):
        if w_all[p] < 3:
            continue
        a = w_all[p] / len(all_k) * 100
        b = (w_yes[p] / len(yes) * 100) if yes else 0
        party_share[p] = {"all_pct": round(a, 1), "compared_pct": round(b, 1),
                          "skew_pp": round(b - a, 1)}
    metro_all = sum(1 for k in all_k if k.split()[0] in METRO) / len(all_k) * 100
    metro_yes = (sum(1 for k in yes if k.split()[0] in METRO) / len(yes) * 100) if yes else 0

    return {
        "districts": {"compared": len(yes), "total": len(all_k),
                      "pct": round(len(yes) / len(all_k) * 100, 1)},
        "electorate": {"compared": el_yes, "total": el_all,
                       "pct": round(el_yes / el_all * 100, 1) if el_all else 0},
        "metro_share": {"all_pct": round(metro_all, 1), "compared_pct": round(metro_yes, 1),
                        "skew_pp": round(metro_yes - metro_all, 1)},
        "by_winning_party": party_share,
        "by_sido": by_sido,
    }


def aggregation_gate(cov: dict) -> tuple[bool, list]:
    """집계 지표를 만들어도 되는가. 실패 사유를 전부 남긴다."""
    fails = []
    if cov["electorate"]["pct"] < MIN_ELECTORATE * 100:
        fails.append(f"선거인 coverage {cov['electorate']['pct']}% "
                     f"< {MIN_ELECTORATE * 100:.0f}%")
    skew = max((abs(v["skew_pp"]) for v in cov["by_winning_party"].values()), default=0)
    if skew > MAX_PARTY_SKEW:
        worst = max(cov["by_winning_party"].items(), key=lambda x: abs(x[1]["skew_pp"]))
        fails.append(f"1위 정당 구성 편차 {worst[0]} {worst[1]['skew_pp']:+}%p "
                     f"(한도 ±{MAX_PARTY_SKEW}%p) — 측정하려는 swing보다 편향이 크다")
    thin = [s for s, b in cov["by_sido"].items() if b["pct"] < MIN_SIDO_COVER * 100]
    if thin:
        fails.append(f"coverage {MIN_SIDO_COVER * 100:.0f}% 미만 시도: "
                     + ", ".join(f"{s}({cov['by_sido'][s]['pct']}%)" for s in sorted(thin)))
    return (not fails), fails


def build(cur_id: str, prev_id: str) -> dict:
    cur_n, prev_n = ordinal(cur_id), ordinal(prev_id)
    cur_date, prev_date = election_date(cur_id), election_date(prev_id)
    lin_fp = LINEAGE / f"{cur_n}__{prev_n}.json"
    if not lin_fp.exists():
        raise SystemExit(f"선거구 계보가 없다: {lin_fp.relative_to(ROOT)}\n"
                         "  먼저 scripts/normalize/build_district_lineage.py를 돌릴 것.")
    lin = json.loads(lin_fp.read_text(encoding="utf-8"))
    cur, prev = load_races(cur_id), load_races(prev_id)

    # 대표키 → 현재 회차에서 실제로 쓰인 이름. 계보 대표가 옛 이름('미래통합당')이라
    # 그대로 쓰면 화면에 없는 당이 나온다.
    # 현재 회차 이름이 우선 — 계보 대표는 '미래통합당' 같은 옛 이름이라 라벨로 못 쓴다.
    # 라벨은 **회차별로 따로** 둔다. 하나로 병합하면 나중 회차 이름이 앞 회차를 덮어써서
    # 같은 표가 두 이름으로 나온다. 실제로 그랬다: 2020년 총선에 등록한 군소 '한나라당'이
    # 1997년 한나라당(→새누리당 계보)과 같은 identity라, 강릉시 no_longer_ran이
    # 2016년 새누리당 57.16%를 '한나라당'으로 표시했다(previous_winner는 새누리당).
    # 어느 쪽 이름을 쓸지는 **그 값이 어느 회차 것이냐**로 정해진다.
    label_prev = labels_for(list(prev.values()), prev_date)
    label = labels_for(list(cur.values()), cur_date)

    # registry에 관계가 없는 정당 — 추정해서 잇지 않되 조용히 버리지도 않는다.
    unreg: dict = {}
    for races, dt in ((cur.values(), cur_date), (prev.values(), prev_date)):
        for r in races:
            for c in r.get("candidates") or []:
                n = c.get("party")
                if n and n != "무소속" and unregistered(n, dt):
                    unreg[n] = dt

    units, rel_n, outcome_n = [], Counter(), Counter()
    swing_sum: dict = defaultdict(float)
    swing_n: dict = defaultdict(int)
    turnout_d, margin_moves = [], []

    for u in lin["units"]:
        key, rel, comp = u["district"], u["relation"], u["comparable"]
        rel_n[rel] += 1
        rec = {"district": key, "sido": u["sido"], "relation": rel,
               "comparable": comp, "reason": u["reason"]}
        c = cur.get(key)
        p_key = u["previous"][0]["prev"] if u.get("previous") else None
        p = prev.get(p_key) if p_key else None

        if comp != "yes" or not c or not p:
            # 관계는 보여주되 값은 만들지 않는다. 근거가 없으면 계산하지 않는다.
            rec["previous_district"] = p_key
            units.append(rec)
            continue

        ct, pt = top2(c)[0], top2(p)[0]
        cm, pm = margin(c), margin(p)
        cto, pto = turnout(c), turnout(p)
        cs, ps = party_share(c, cur_date), party_share(p, prev_date)

        outcome = None
        if ct and pt:
            cp, pp = ct.get("party") or "무소속", pt.get("party") or "무소속"
            if cp == "무소속" and pp == "무소속":
                outcome = "independent_to_independent"
            elif identity(cp, cur_date) == identity(pp, prev_date):
                outcome = "party_hold"   # 개명 포함 — 같은 identity면 같은 당이다
            else:
                outcome = "party_flip"
            outcome_n[outcome] += 1

        # '이전에 후보가 없었다'와 '득표가 줄었다'는 다르다. 관악구갑에서 2020년
        # 미래통합당은 아예 출마하지 않았는데(무소속 김성식이 2위) 그대로 세면
        # '국민의힘 +42.9%p'가 되어 없던 지지 이동처럼 읽힌다.
        # 평균 swing에서는 양쪽 다 출마한 곳만 센다.
        d_share, entered, left = {}, [], []
        for pty in set(cs) | set(ps):
            in_cur, in_prev = pty in cs, pty in ps
            d = round(cs.get(pty, 0) - ps.get(pty, 0), 2)
            name = label.get(pty) or label_prev.get(pty) or pty
            if in_cur and in_prev:
                if d:
                    d_share[name] = d
                    swing_sum[pty] += d
                    swing_n[pty] += 1
            elif in_cur:
                entered.append({"party": name, "pct": cs[pty]})
            else:
                # 지난 회차에만 나온 정당 — 그 회차 투표용지 이름으로 적는다
                left.append({"party": label_prev.get(pty) or name,
                             "previous_pct": ps[pty]})

        # identity 값이 바뀌면 집합 순회 순서가 흔들린다 — 값은 그대로인데 diff가 난다.
        # 표시 이름으로 정렬해 출력을 고정한다.
        entered.sort(key=lambda x: x["party"])
        left.sort(key=lambda x: x["party"])
        d_share = dict(sorted(d_share.items()))

        rec.update({
            "previous_district": p_key,
            "outcome": outcome,
            "winner": {"name": ct.get("name"), "party": ct.get("party"),
                       "pct": ct.get("pct")} if ct else None,
            "previous_winner": {"name": pt.get("name"), "party": pt.get("party"),
                                "pct": pt.get("pct")} if pt else None,
            "margin": cm, "previous_margin": pm,
            "margin_delta": round(cm - pm, 2) if cm is not None and pm is not None else None,
            "turnout": cto, "previous_turnout": pto,
            "turnout_delta": round(cto - pto, 2) if cto is not None and pto is not None else None,
            "share_delta": d_share,          # 양쪽 다 출마한 정당만
            "newly_ran": entered,            # 이번에만 출마 — 증감이 아니다
            "no_longer_ran": left,           # 지난번에만 출마
        })
        units.append(rec)
        if rec["turnout_delta"] is not None:
            turnout_d.append(rec["turnout_delta"])
        if d_share:
            biggest = max(d_share.items(), key=lambda x: abs(x[1]))
            margin_moves.append({"district": key, "party": biggest[0], "delta": biggest[1]})

    n_yes = sum(1 for u in units if u["comparable"] == "yes")
    n_unknown = sum(1 for u in units if u["comparable"] == "unknown")
    n_no = sum(1 for u in units if u["comparable"] == "no")
    margin_moves.sort(key=lambda x: -abs(x["delta"]))

    cov = coverage_audit(units, cur)
    allowed, gate_fails = aggregation_gate(cov)

    # 게이트를 통과하지 못하면 **집계 지표를 만들지 않는다.**
    # 문구로 경고하고 값을 내보내면, 그 값은 결국 어딘가에서 전국 지표로 쓰인다.
    agg = {
        "party_swing_in_compared": {
            label.get(p, p): {"mean_pp": round(swing_sum[p] / swing_n[p], 2),
                              "districts": swing_n[p]}
            for p in sorted(swing_sum, key=lambda x: -abs(swing_sum[x] / swing_n[x]))
            if swing_n[p] >= 5
        },
        "turnout_in_compared": {
            "mean_delta_pp": round(sum(turnout_d) / len(turnout_d), 2) if turnout_d else None,
            "districts": len(turnout_d),
        },
        "biggest_moves": margin_moves[:12],
    } if allowed else {}

    return {
        "_meta": {
            "current": cur_id, "previous": prev_id,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": "polis 계산",
            "scope_note": ("**비교 가능한 선거구만** 계산했다. 선거구는 회차마다 획정이 "
                           "바뀌어, 이름이 같아도 유권자가 다르면 그 delta는 거짓이다."),
            "aggregation_note": (
                "**정확한 부분집합 ≠ 대표 가능한 전체.** comparable='yes'는 그 선거구 "
                "하나의 delta를 계산할 수 있다는 뜻일 뿐이다. 비교 가능한 곳은 경계가 "
                "안정적인 곳이고 제외되는 곳은 재획정이 많은 도시권에 몰리므로, "
                "부분집합 합계는 전국을 대표하지 않을 수 있다. coverage 감사를 통과할 "
                "때만 집계 지표를 만든다 — 경고 문구로 대신하지 않는다."),
            "excluded_note": ("split·merged는 관계를 알아도 delta를 만들 수 없다. "
                              "A → B + C에서 A의 과거 득표를 나눌 근거가 없다."),
            "lineage": f"data/district_lineage/{cur_n}__{prev_n}.json",
        },
        "counts": {
            "total_districts": len(units),
            "compared": n_yes,
            "undetermined": n_unknown,
            "excluded_redistricting": n_no,
            "by_relation": dict(rel_n),
            "outcome": dict(outcome_n),
        },
        # **hard gate** — 문구가 아니라 모델에서 막는다.
        "aggregation_allowed": allowed,
        "aggregation_blocked_because": gate_fails,
        "coverage": cov,
        "swing_denominator": (
            "분모 = 비교 가능한 선거구 중 **두 회차 모두 그 정당이 출마한** 곳. "
            "한쪽만 출마한 곳은 newly_ran·no_longer_ran으로 따로 담는다 — "
            "0%에서 42.9%가 된 것과 5%에서 47.9%가 된 것은 다른 사실이다. "
            "5곳 미만은 평균이 뜻을 잃어 싣지 않는다."),
        "unregistered_parties": sorted(unreg),
        "unregistered_note": (
            "정당 registry에 계보가 없는 이름들. 추정해서 잇지 않으므로 각각 독립 "
            "identity로 센다. '녹색정의당'처럼 실제로는 계보가 있는 것이 섞여 있으면 "
            "registry를 보강해야 한다 — 여기서 임의로 잇지 않는다."),
        **agg,
        "units": units,
    }


def existing_pairs() -> list:
    """이미 만들어 둔 비교 쌍 — 인자 없이 실행하면 그것들을 다시 만든다.

    이 산출물은 registry(정당 identity)와 선거구 계보를 **둘 다** 입력으로 받는데,
    어느 쪽을 고쳐도 자동으로 다시 만들어지지 않아 조용히 낡았다. 실제로 그랬다:
    선거구 계보가 좋아진 뒤에도 committed 파일은 compared 204(→226)에 멈춰 있었다.
    그래서 regen_check가 인자 없이 돌릴 수 있어야 한다.
    """
    out = []
    for fp in sorted(OUT.glob("*__*.json")):
        if fp.name.startswith("national__"):
            continue                      # 전국 집계는 build_general_national의 산출물
        cur, _, prev = fp.stem.partition("__")
        if cur and prev and "__" not in prev:
            out.append((cur, prev))
    return out


def write_one(cur_id: str, prev_id: str) -> dict:
    """생성 시각은 **내용이 바뀔 때만** 바꾼다.

    매번 새 timestamp를 쓰면 내용이 같아도 diff가 생겨서, 이 파일은 '항상 변경됨'이
    되고 결국 freshness 검사에서 빠지게 된다 — 낡아도 아무도 모르게 된다.
    """
    d = build(cur_id, prev_id)
    OUT.mkdir(parents=True, exist_ok=True)
    fp = OUT / f"{cur_id}__{prev_id}.json"
    if fp.exists():
        try:
            old = json.loads(fp.read_text(encoding="utf-8"))
            prev_at = (old.get("_meta") or {}).get("generated_at")
            probe = json.loads(json.dumps(d))
            probe["_meta"]["generated_at"] = prev_at
            if probe == old and prev_at:
                d["_meta"]["generated_at"] = prev_at
        except Exception:                                        # noqa: BLE001
            pass
    fp.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--current")
    ap.add_argument("--previous")
    args = ap.parse_args()
    if not args.current or not args.previous:
        pairs = existing_pairs()
        if not pairs:
            ap.error("--current/--previous 가 필요하다 (기존 산출물도 없다)")
        for cur, prev in pairs:
            write_one(cur, prev)
            print(f"→ {cur}__{prev}", file=sys.stderr)
        return 0
    d = write_one(args.current, args.previous)
    fp = OUT / f"{args.current}__{args.previous}.json"
    c = d["counts"]
    print(f"→ {fp.relative_to(ROOT)}", file=sys.stderr)
    print(f"   전체 {c['total_districts']} · 직접 비교 {c['compared']}"
          f" · 판정 보류 {c['undetermined']} · 획정 변경 제외 {c['excluded_redistricting']}",
          file=sys.stderr)
    print(f"   수성 {c['outcome'].get('party_hold', 0)}"
          f" · 교체 {c['outcome'].get('party_flip', 0)}", file=sys.stderr)
    cv = d["coverage"]
    print(f"   선거인 coverage {cv['electorate']['pct']}%"
          f" · 수도권 편차 {cv['metro_share']['skew_pp']:+}%p", file=sys.stderr)
    if d["aggregation_allowed"]:
        for p, v in list(d.get("party_swing_in_compared", {}).items())[:5]:
            print(f"   {p} {v['mean_pp']:+.2f}%p (비교 {v['districts']}곳)", file=sys.stderr)
    else:
        print("   ✗ 집계 지표 생성 차단 — subset이 전국을 대표하지 않는다:", file=sys.stderr)
        for f in d["aggregation_blocked_because"]:
            print(f"       · {f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
