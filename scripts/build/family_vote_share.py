"""회차별 **정치계열 득표 비중** — 분류 안 된 표를 지우지 않는다.

## 규칙

`mixed`(계열이 갈리는 합당체)와 `unknown`(계보를 모르는 당)의 표를 어느 계열에도
배분하지 않고, 빼고 나머지를 100%로 재정규화하지도 않는다. 그렇게 하면 오래된 선거로
갈수록 커버리지가 떨어지는데 그래프는 여전히 확신에 찬 모양이 된다.

    conservative 41 · democratic 33 · progressive 4 · regional 6 · mixed 7 · unknown 9

세 비중을 따로 보존한다. '보수 48%'라고 말할 수 있는 정도와, 계보는 알지만 단일
계열로 못 나누는 표는 다른 것이다.

    known_single_family_share   단일 계열로 확정된 표
    mixed_family_share          계보는 아는데 계열이 갈리는 표(3당합당 후신 등)
    unknown_family_share        계보를 모르는 표
    classification_coverage     = known_single (분류 가능한 비중)

## 모드

    strict      조직 계보만. 1980 강제해산에서 끊긴다.
    historical  + 확인된 historical_bridge. 장기 흐름을 볼 때.

**분류되지 않은 표 ≠ 없는 표.**

사용: python scripts/build/family_vote_share.py
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/build"))
from party_canon import disambiguate_party  # noqa: E402

RESULTS = ROOT / "data/results"
AXES = ROOT / "data/parties/political_axes.json"
OUT = ROOT / "data/parties/family_vote_share.json"

FAMILIES = ("conservative", "democratic", "progressive", "regional", "other")


def _families(mode: str) -> dict:
    ax = json.loads(AXES.read_text(encoding="utf-8"))
    key = "lineage_family" if mode == "strict" else "lineage_family_historical"
    return {n: v["family"] for n, v in ax[key].items()}


def _dominant() -> dict:
    """mixed 정당의 **주계열** — 근거가 있는 것만. 계보 사실을 덮어쓰지 않는다."""
    ax = json.loads(AXES.read_text(encoding="utf-8"))
    return {n: v for n, v in (ax.get("dominant_family") or {}).items()
            if v.get("value") and v["value"] != "unknown"}


def _date(path: Path, doc: dict) -> str:
    meta = doc.get("_meta") or {}
    # 파일마다 키가 다르다 — election_date / date 둘 다 쓰인다
    for k in ("election_date", "date"):
        if meta.get(k):
            return meta[k]
    hit = re.search(r'"date":\s*"(\d{4}-\d{2}-\d{2})"', path.read_text(encoding="utf-8"))
    return hit.group(1) if hit else ""


def _walk_candidates(o, out: list) -> None:
    if isinstance(o, dict):
        if isinstance(o.get("candidates"), list):
            out.extend(c for c in o["candidates"] if isinstance(c, dict))
        for v in o.values():
            _walk_candidates(v, out)
    elif isinstance(o, list):
        for v in o:
            _walk_candidates(v, out)


def tally(cands: list, date: str, fam: dict, dominant: dict | None = None) -> dict:
    """정당별 득표 → 계열별 합. 무소속은 계열을 추정하지 않는다."""
    acc: dict = collections.Counter()
    for c in cands:
        v = c.get("votes")
        p = c.get("party")
        if not v or not isinstance(v, (int, float)):
            continue
        if not p or p == "무소속":
            # 무소속을 정당 계보로 추정하지 않는다. 후보 단위 근거가 있을 때만
            # 따로 넣어야 하고, 지금은 없다.
            acc["independent"] += v
            continue
        canon = disambiguate_party(p, date)
        f = fam.get(canon, "unknown")
        if f in FAMILIES:
            acc[f] += v
        elif f == "mixed":
            # 주계열이 근거와 함께 확인된 mixed는 따로 센다 — 해석 레이어에서만 쓴다.
            # 여기서 단일 계열로 재분류하지 않는다. mixed는 mixed다.
            acc["mixed_with_dominant" if (dominant or {}).get(canon) else "mixed"] += v
        else:
            acc["unknown"] += v
    return dict(acc)


def summarize(acc: dict, dominant: dict | None = None) -> dict:
    """coverage를 하나로 뭉개지 않는다.

    `mixed`를 `unknown`과 같이 세면 진단이 뒤집힌다. **둘은 품질상 정반대다** —
    unknown은 계보를 모르는 것이고, mixed는 계보를 알아서 복수 계열인 것이다.
    국민의힘은 3당합당 후신이라 mixed인데, 그걸 '분류 실패'로 세면 "22대 계보가
    19%밖에 안 풀린다"는 잘못된 진단이 나온다.

        lineage_resolved       단일 + 복수 — 계보 자체를 설명할 수 있는 표
        single_family          하나의 계열로만 귀속되는 표
        dominant_projection    단일 + mixed 중 dominant가 검증된 표 (해석 레이어용)
    """
    total = sum(acc.values())
    if not total:
        return {}
    single = sum(acc.get(f, 0) for f in FAMILIES)
    mixed = acc.get("mixed", 0)
    dom_ok = acc.get("mixed_with_dominant", 0)
    pct = lambda v: round(v / total * 100, 2)      # noqa: E731
    return {
        "total_votes": total,
        "share": {k: pct(v) for k, v in sorted(acc.items())},
        "single_family_coverage": pct(single),
        "lineage_resolved_coverage": pct(single + mixed + dom_ok),
        "dominant_projection_coverage": pct(single + dom_ok),
        "mixed_share": pct(mixed + dom_ok),
        "unknown_share": pct(acc.get("unknown", 0)),
        "independent_share": pct(acc.get("independent", 0)),
    }


def main() -> int:
    fam_s, fam_h = _families("strict"), _families("historical")
    dom = _dominant()
    rows = []
    # 어느 정당이 미분류 표를 좌우하는가 — 다음 계보 보강 우선순위가 여기서 나온다.
    unknown_by_party: dict = collections.Counter()
    for f in sorted(RESULTS.glob("*.json")):
        if ".sigungu" in f.name or f.name.startswith(("local_", "national_assembly_",
                                                      "presidential_")):
            continue          # 같은 선거의 다른 표현 — 이중 집계 방지
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception:                                       # noqa: BLE001
            continue
        cands: list = []
        _walk_candidates(doc, cands)
        if not cands:
            continue
        date = _date(f, doc)
        if not date:
            continue
        for c in cands:
            v, p_ = c.get("votes"), c.get("party")
            if (isinstance(v, (int, float)) and v and p_ and p_ != "무소속"
                    and fam_s.get(disambiguate_party(p_, date), "unknown") == "unknown"):
                unknown_by_party[disambiguate_party(p_, date)] += v
        s = summarize(tally(cands, date, fam_s, dom), dom)
        h = summarize(tally(cands, date, fam_h, dom), dom)
        if not s:
            continue
        rows.append({"election": f.stem, "date": date,
                     "label": ((doc.get("_meta") or {}).get("label")
                               or (doc.get("_meta") or {}).get("election") or f.stem),
                     "strict": s, "historical": h})
    rows.sort(key=lambda r: r["date"])
    doc = {
        "_note": ("회차별 정치계열 득표 비중. mixed·unknown 표를 어느 계열에도 배분하지 "
                  "않고 재정규화하지도 않는다 — **분류되지 않은 표 ≠ 없는 표**. "
                  "무소속은 정당 계보로 추정하지 않고 따로 센다."),
        "_modes": {"strict": "조직 계보만", "historical": "+ 확인된 historical_bridge"},
        "elections": rows,
        # 계보를 하나 뚫을 때 몇 표가 분류되는가. 숫자가 큰 것부터 확인하면 된다.
        "unknown_priority": [{"party": k, "votes": v}
                             for k, v in unknown_by_party.most_common(20)],
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"→ {OUT.name}: 선거 {len(rows)}회\n")
    print(f"  {'선거':26} {'계보설명':>7} {'단일':>6} {'혼합':>6} {'미확인':>7} {'무소속':>7}")
    for r in rows:
        s = r["strict"]
        print(f"  {r['label'][:24]:26} {s['lineage_resolved_coverage']:6.1f}% "
              f"{s['single_family_coverage']:5.1f}% {s['mixed_share']:5.1f}% "
              f"{s['unknown_share']:6.1f}% {s['independent_share']:6.1f}%")
    print("\n[보강 우선순위] 미분류 표가 많은 정당 — 하나 뚫을 때 얻는 게 큰 순서")
    for k, v in unknown_by_party.most_common(12):
        print(f"  {v:12,}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
