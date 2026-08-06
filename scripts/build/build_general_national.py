"""총선 전국 집계 — **선거구 매칭 없이** 계산한다.

전국 정당 변화를 보려고 비교 가능한 선거구 부분집합을 합치면 안 된다. 그 부분집합은
경계가 안정적인 곳에 쏠려 있어 편향이 측정 대상보다 클 수 있다(선거구 계보를 고치기
전 22↔21 실측에서 1위 정당 구성이 ±6%p 기울었다 — 계보가 좋아진 지금은 0.9%p로
내려갔지만, 부분집합이 대표성을 보장하지 않는다는 사실 자체는 그대로다).
그런데 **전국 전체를 각 회차마다 독립적으로 합치면** 그 문제가 아예 생기지 않는다 — 공간 분할이 달라졌을 뿐 모집단은 같기 때문이다.

그래서 총선 비교는 네 층으로 나뉜다:
  ① 전국 집계        여기 — 선거구 lineage 불필요
  ② 비례 정당득표    여기 — ballot 그대로
  ③ 같은 선거구 변화  build_general_comparison.py (comparable=yes만)
  ④ 획정 변화        data/district_lineage · data/geography

## 비례를 지역구와 같은 방식으로 다루지 않는다

21대 미래한국당·더불어시민당, 22대 국민의미래·더불어민주연합은 위성정당이다.
이걸 본당과 `same_party`로 합치면 유권자가 실제로 마주한 투표용지를 왜곡한다.
그래서 비례는 **ballot_party 그대로**가 1차 데이터다. 계열 합산이 필요하면
별도의 명시적 정책이 있어야 하고, 여기서 자동으로 하지 않는다.

## 출마 범위를 함께 낸다

전국 득표율은 모든 지역구에 후보를 낸 정당에는 정당 지지의 좋은 지표지만,
60곳에만 낸 정당에는 아니다. candidacy coverage 없이 두 숫자를 나란히 놓으면
'진보당이 국민의힘보다 지지가 낮다'가 아니라 '출마를 덜 했다'를 잘못 읽게 된다.

사용: python3 scripts/build/build_general_national.py --elections 22nd-general-2024 21st-general-2020
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/comparisons/general"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from party_identity import identity, labels_for  # noqa: E402


def election_date(eid: str) -> str:
    fp = ROOT / "data/elections" / f"{eid}.json"
    try:
        return json.loads(fp.read_text(encoding="utf-8")).get("date") or ""
    except Exception:
        return ""


def load(eid: str) -> tuple[list, list]:
    """(지역구 race, 비례 전국 race)"""
    d = json.loads((ROOT / "data/results" / f"{eid}.json").read_text(encoding="utf-8"))
    races = d.get("races") or []
    dist = [r for r in races if r.get("sg_typecode") == "2" and r.get("scope") == "district"]
    prop = [r for r in races if r.get("sg_typecode") == "7" and r.get("scope") == "nation"]
    return dist, prop


def national_district(dist: list, date: str) -> dict:
    """전국 지역구 합산. **선거구를 짝지을 필요가 없다** — 전부 더하면 된다."""
    votes: dict = defaultdict(int)
    ran: dict = defaultdict(int)
    label = labels_for(dist, date)
    valid = 0
    for r in dist:
        seen = set()
        for c in r.get("candidates") or []:
            v = c.get("votes")
            if v is None:
                continue
            valid += v
            p = c.get("party")
            if not p or p == "무소속":
                votes["무소속"] += v
                continue
            pid = identity(p, date)
            votes[pid] += v
            if pid not in seen:
                ran[pid] += 1
                seen.add(pid)
    n_dist = len(dist)
    out = {}
    for pid, v in sorted(votes.items(), key=lambda x: -x[1]):
        name = "무소속" if pid == "무소속" else label.get(pid, pid)
        out[name] = {
            "votes": v,
            "pct": round(v / valid * 100, 2) if valid else None,
            # 출마 범위 — 없으면 '지지가 낮다'와 '출마를 덜 했다'를 못 가른다
            "ran_in": ran.get(pid, n_dist if pid == "무소속" else 0),
            "of_districts": n_dist,
        }
    return {"districts": n_dist, "valid_votes": valid, "by_party": out}


def proportional(prop: list) -> dict:
    """비례 정당득표 — **투표용지에 있던 이름 그대로**.
    위성정당·연합명부를 본당과 합치지 않는다. 그건 별도 정책이 필요한 분석이다."""
    if not prop:
        return {"available": False}
    r = prop[0]
    cs = sorted((r.get("candidates") or []), key=lambda c: -(c.get("votes") or 0))
    return {
        "available": True,
        "valid_votes": r.get("valid_votes"),
        "ballot_parties": [
            {"ballot_party": c.get("party") or c.get("name"),
             "votes": c.get("votes"), "pct": c.get("pct"),
             "seats": c.get("seats")}
            for c in cs if (c.get("votes") or 0) > 0
        ],
        "note": ("투표용지에 있던 정당명 그대로다. 위성정당(21대 미래한국당·더불어시민당, "
                 "22대 국민의미래·더불어민주연합)을 본당과 합치지 않는다 — 유권자가 실제로 "
                 "마주한 선택지를 왜곡하게 된다. 계열 합산이 필요하면 명시적 정책을 "
                 "따로 두어야 한다."),
    }


def build(eids: list) -> dict:
    per = {}
    for eid in eids:
        dist, prop = load(eid)
        date = election_date(eid)
        per[eid] = {
            "date": date,
            "national_district_vote": national_district(dist, date),
            "proportional": proportional(prop),
        }
    return {
        "_meta": {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": "polis 계산",
            "method": ("각 회차의 **전체 지역구 결과를 독립적으로 전국 합산**한다. "
                       "선거구 간 1:1 매칭을 요구하지 않는다 — 공간 분할이 달라져도 "
                       "전체 모집단은 같기 때문이다."),
            "why_not_subset": ("비교 가능한 선거구만 합치면 그 부분집합이 전국을 대표한다는 "
                               "보장이 없다. 편향은 계보 품질에 따라 변한다 — 22↔21은 "
                               "예전 계보에서 1위 정당 구성이 ±6%p 기울었고 지금은 0.9%p다. "
                               "그래도 세종 coverage 0%로 집계는 여전히 차단된다. "
                               "전국 변화는 여기서, 같은 선거구의 변화는 "
                               "build_general_comparison.py에서 — 두 질문은 다르다."),
            "candidacy_note": ("전국 득표율은 모든 지역구에 후보를 낸 정당에는 좋은 지표지만 "
                               "일부에만 낸 정당에는 아니다. ran_in을 함께 읽어야 한다."),
        },
        "elections": per,
    }


def existing_sets() -> list:
    """이미 만들어 둔 조합 — 인자 없이 실행하면 그것들을 다시 만든다(regen_check용)."""
    out = []
    for fp in sorted(OUT.glob("national__*.json")):
        els = fp.stem[len("national__"):].split("__")
        if all(els):
            out.append(els)
    return out


def write_one(els: list) -> dict:
    """생성 시각은 **내용이 바뀔 때만** 바꾼다 — 매번 바뀌면 낡은 것과 구별되지 않는다."""
    d = build(els)
    OUT.mkdir(parents=True, exist_ok=True)
    fp = OUT / ("national__" + "__".join(els) + ".json")
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
    ap.add_argument("--elections", nargs="+")
    args = ap.parse_args()
    if not args.elections:
        sets = existing_sets()
        if not sets:
            ap.error("--elections 가 필요하다 (기존 산출물도 없다)")
        for els in sets:
            write_one(els)
            print("→ national__" + "__".join(els), file=sys.stderr)
        return 0
    d = write_one(args.elections)
    fp = OUT / ("national__" + "__".join(args.elections) + ".json")
    print(f"→ {fp.relative_to(ROOT)}", file=sys.stderr)
    for eid, e in d["elections"].items():
        nd = e["national_district_vote"]
        print(f"\n  {eid} · 지역구 {nd['districts']} · 유효표 {nd['valid_votes']:,}",
              file=sys.stderr)
        for name, v in list(nd["by_party"].items())[:5]:
            print(f"    {name:16} {v['pct']:5.2f}%  출마 {v['ran_in']:3}/{v['of_districts']}",
                  file=sys.stderr)
        pr = e["proportional"]
        if pr.get("available"):
            top = pr["ballot_parties"][:3]
            print(f"    비례: " + " · ".join(f"{b['ballot_party']} {b['pct']}%" for b in top),
                  file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
