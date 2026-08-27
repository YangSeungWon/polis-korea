"""여론조사 1위 vs 실제 1위 — 계산의 단일 출처.

**이 계산은 지금까지 JS에만 있었다**(result-overlay.accuracyForOffice ·
adapter.localSidoWinner · utils.summarizeLatest · render-pres · render-gen).
그래서 페이지 제목이 '조사 적중률'인데 본문에는 그 숫자가 한 글자도 없다 —
JS가 돌아야 나온다. 정적 본문을 만들려면 빌드 때 같은 숫자가 필요한데, 파이썬으로
그냥 다시 구현하면 두 벌이 되고 **반드시 어긋난다**(시험 포팅이 14/16을 냈다,
런타임은 13/15였다).

그래서 계산을 여기로 옮기고 런타임은 읽기만 하게 한다. 이 파일이 정본이다.

⚠️ **감쇠 기준 시각.** JS summarizeLatest는 Date.now()로 지수감쇠를 건다. 가중평균은
지수의 공통인자 exp(-now/τ)가 약분되어 **시각에 불변**이라 값은 같다. 다만 폴이
아주 오래되면 exp(-days/7)이 배정밀도에서 0으로 내려앉는다 — daysOld > 약 5,215일
(14.3년)이면 전부 0이 되어 20대 총선(2016) 페이지가 2030년경 조용히 빈다.
여기서는 **선거일**을 기준으로 삼는다. 값은 같고 언더플로가 없다.

⚠️ **정당 동일성.** JS samePartyName은 **색으로** 비교한다(partyColor). 색은 정체의
대리물이고 정본은 data/parties/registry.json이다. 여기서는 registry로 비교한다 —
약칭이 겹치는 이름('민주당'은 시점별 별개 정당, registry._collisions 참조)은
**선거일 시점에 존재한 당**으로 가른다. registry가 그렇게 하라고 적어 뒀다.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# ── 시도 이름 정규화 — assets/utils.js canonSido와 같은 표 ──────────────────
_CANON = {"강원도": "강원특별자치도", "전라북도": "전북특별자치도", "제주도": "제주특별자치도"}


def canon_sido(s: str | None) -> str:
    return _CANON.get(s or "", s or "")


# assets/parties.js SIDO_HEX_LAYOUT의 키 — 적중률이 **어느 지역을 도는지**를 정한다.
# 실제 결과에 있는 시도를 도는 것과 다르다(전남광주 통합 회차에서 1곳 차이가 났다).
SIDO_17 = [
    "인천광역시", "서울특별시", "경기도", "강원특별자치도",
    "충청남도", "세종특별자치시", "충청북도", "경상북도",
    "전북특별자치도", "대전광역시", "대구광역시", "울산광역시",
    "전라남도", "광주광역시", "경상남도", "부산광역시",
    "제주특별자치도",
]
# 전남광주 통합(2026-06-03 신설) — 이후 지선 광역단체장은 광주·전남이 한 선거다.
HONAM_MERGE_DATE = "2026-06-03"
SIDO_MERGE = {"광주광역시": "전남광주특별시", "전라남도": "전남광주특별시"}


def sido_list(date_s: str, office: str) -> list[str]:
    """그 회차에 돌 시도 목록. 통합 이후 광역단체장은 전남광주를 한 칸으로 센다."""
    if date_s >= HONAM_MERGE_DATE and office in ("광역단체장", "교육감"):
        return [s for s in SIDO_17 if s not in SIDO_MERGE] + ["전남광주특별시"]
    return list(SIDO_17)


# ── 정당 동일성 ────────────────────────────────────────────────────────────
class Parties:
    def __init__(self) -> None:
        d = json.loads((ROOT / "data/parties/registry.json").read_text(encoding="utf-8"))
        self.p: dict = d["parties"]
        self.collide: set[str] = set(d.get("_collisions") or {})
        self.by_abbr: dict[str, list[str]] = {}
        for name, v in self.p.items():
            ab = v.get("abbr")
            if ab:
                self.by_abbr.setdefault(ab, []).append(name)

    def _alive(self, name: str, date_s: str) -> bool:
        v = self.p.get(name) or {}
        f, x = v.get("founded") or "", v.get("dissolved") or ""
        return (not f or f <= date_s[:len(f)]) and (not x or x > date_s[:len(x)])

    def canon(self, party: str | None, date_s: str) -> str | None:
        """정당명 → 정식명. 모르면 이름 그대로(비교는 문자열 일치로 떨어진다)."""
        if not party:
            return None
        party = party.strip()
        if party in self.p:
            return party
        cands = self.by_abbr.get(party) or []
        if len(cands) > 1 or party in self.collide:
            # 동음이의 — 선거일에 존재한 당으로 가른다. registry가 '회차 맥락으로
            # 구분'하라고 적어 둔 자리다. 못 가르면 이름 그대로 둔다(합치지 않는다).
            alive = [c for c in cands if self._alive(c, date_s)]
            return alive[0] if len(alive) == 1 else party
        return cands[0] if cands else party

    def same(self, a: str | None, b: str | None, date_s: str) -> bool:
        if not a or not b:
            return False
        return self.canon(a, date_s) == self.canon(b, date_s)


# ── 폴 집계 — assets/utils.js summarizeLatest 포팅 ──────────────────────────
def summarize_latest(sel: list[dict], ref_ms: float, decay_days: float = 7.0) -> dict | None:
    """시간감쇠 가중 평균으로 1위를 뽑는다. JS와 같은 식, 기준 시각만 선거일."""
    agg: dict[str, dict] = {}
    latest_name: dict[str, str] = {}
    for p in sorted(sel, key=lambda x: (x.get("period_end") or ""), reverse=True):
        if not p.get("candidates"):
            continue
        end = p.get("period_end") or p.get("period_start")
        ts = _ms(end)
        days = max(0.0, (ref_ms - (ts if ts is not None else ref_ms)) / 86_400_000)
        w = math.exp(-days / decay_days) * (p.get("sample_size") or 500)
        for c in p["candidates"]:
            pct = c.get("pct")
            if pct is None or pct < 0 or pct > 100:
                continue
            key = c.get("party") or c.get("name")
            a = agg.setdefault(key, {"party": c.get("party"), "sum": 0.0, "w": 0.0})
            a["sum"] += pct * w
            a["w"] += w
            latest_name.setdefault(key, c.get("name") or "")
    rows = [{"party": v["party"], "name": latest_name.get(k, ""), "pct": v["sum"] / v["w"]}
            for k, v in agg.items() if v["w"]]
    rows = [r for r in rows if math.isfinite(r["pct"])]
    if not rows:
        return None
    rows.sort(key=lambda r: -r["pct"])
    top, sec = rows[0], (rows[1] if len(rows) > 1 else {"name": "", "pct": 0.0})
    errs = [float(m.group(1)) for m in
            (re.search(r"±\s*(\d+\.?\d*)", p.get("sample_error") or "") for p in sel) if m]
    return {
        "party": top["party"], "name": top["name"], "pct": round(top["pct"], 1),
        "second_name": sec.get("name", ""), "second_pct": round(sec.get("pct", 0.0), 1),
        "sample_error": (sum(errs) / len(errs)) if errs else None,
        "n_polls": len(sel),
    }


def latest_poll(sel: list[dict]) -> dict | None:
    """가장 나중에 끝난 조사 하나 — 대선·총선은 집계가 아니라 이걸 쓴다
    (adapter.cellsFromPolls·districtResultFromPolls). 인용 의무의 대상이기도 하다."""
    ok = [p for p in sel if p.get("candidates")]
    return max(ok, key=lambda p: (p.get("period_end") or "")) if ok else None


def _ms(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:19]).timestamp() * 1000
    except Exception:
        return None


# 인용 의무(공직선거법·NESDC) — 조사를 인용하면 함께 표시해야 하는 것.
# data/polls/README.md '법적 의무' 참조. 표에 낼 때 빠뜨리면 안 되므로 여기서 묶는다.
CITE_FIELDS = ("agency", "requester", "method", "sample_size",
               "response_rate", "sample_error", "period_start", "period_end",
               "source_url", "ntt_id")


def cite(p: dict | None) -> dict | None:
    return {k: p.get(k) for k in CITE_FIELDS} if p else None


# ── 기관별 ─────────────────────────────────────────────────────────────────
# ⚠️ **순위표가 아니다.** 기관마다 조사하는 지역이 다르고, 박빙 지역을 많이 조사한
# 기관은 1위를 더 자주 놓친다. 오차(1위 후보 득표율 − 실제)가 그나마 비교 가능한
# 숫자지만 그것도 지역·시점에 좌우된다. 그래서 **조사 수 순으로** 내보낸다 —
# 적중률 순으로 정렬하면 표 자체가 '이 기관이 낫다'는 주장이 된다.
#
# 시점을 맞춘다. 6개월 전 조사와 사흘 전 조사를 같은 자로 재면 시점이 곧 실력으로
# 둔갑한다. 선거일 기준 WINDOW_DAYS 안의 조사만 본다.
WINDOW_DAYS = 30
MIN_POLLS = 3


def agency_rows(polls: list, actual: dict, date_s: str, P: "Parties") -> dict:
    """기관 → {n, hit, err}. actual은 (시도, 시군구, 직위) → 득표순 후보 목록."""
    from collections import defaultdict
    from datetime import date as _d, timedelta
    cut = (_d.fromisoformat(date_s) - timedelta(days=WINDOW_DAYS)).isoformat()
    stat: dict = defaultdict(lambda: {"n": 0, "hit": 0, "err": []})
    for p in polls:
        if (p.get("period_end") or "") < cut:
            continue
        key = (canon_sido(p.get("sido")), p.get("sigungu") or "", p.get("office_level"))
        a = actual.get(key)
        if not a or not p.get("candidates"):
            continue
        cs = sorted([c for c in p["candidates"] if c.get("pct") is not None],
                    key=lambda c: -c["pct"])
        if not cs:
            continue
        s = stat[p.get("agency") or "(미상)"]
        s["n"] += 1
        if P.same(cs[0].get("party"), a[0].get("party"), date_s):
            s["hit"] += 1
        # 오차 — 조사 1위 후보의 득표율과 **같은 정당** 실제 득표율의 차.
        same = next((c for c in a if P.same(c.get("party"), cs[0].get("party"), date_s)), None)
        if same and same.get("pct") is not None:
            s["err"].append(abs(cs[0]["pct"] - same["pct"]))
    rows, other_n, other_ag = [], 0, 0
    for ag, s in sorted(stat.items(), key=lambda x: (-x[1]["n"], x[0])):
        if s["n"] < MIN_POLLS:
            other_n += s["n"]
            other_ag += 1
            continue
        rows.append({"agency": ag, "n": s["n"], "hit": s["hit"],
                     "err": round(sum(s["err"]) / len(s["err"]), 1) if s["err"] else None})
    return {"window_days": WINDOW_DAYS, "min_polls": MIN_POLLS, "rows": rows,
            "other": {"agencies": other_ag, "polls": other_n}}


# 전국 후보별 표가 볼 창 — 선거일 이전 며칠 치 조사를 평균낼 것인가.
# 7일은 표본이 얇고(19대 7건) 30일은 판세가 움직인 뒤라 예측이라 하기 어렵다.
NATIONAL_WINDOW = 14


def mean_by_name(sel: list) -> dict:
    """후보 이름 → {pct: 단순평균, n: 조사 수}.

    여기선 시간감쇠를 걸지 않는다. '막판 2주 조사들의 평균'이라고 말할 것이고,
    가중을 걸면 그 문장이 거짓이 된다 — 글이 계산을 설명해야 한다.
    """
    from collections import defaultdict
    acc: dict = defaultdict(list)
    for p in sel:
        for c in p.get("candidates") or []:
            if c.get("name") and c.get("pct") is not None:
                acc[c["name"]].append(c["pct"])
    return {k: {"pct": sum(v) / len(v), "n": len(v)} for k, v in acc.items()}
