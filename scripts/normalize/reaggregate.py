"""읍면동 실측 득표를 **다른 회차의 선거구 경계**로 다시 더한다.

획정이 바뀌면 선거구는 비교할 수 없다 — 지금까지 그렇게 보류해 왔다. 그런데 NEC
투표구별 개표(VCCP08)에는 선거구·투표구·후보별 득표가 한 표에 같이 있다. 과거 표를
**그 표가 나온 동 그대로** 현재 선거구에 다시 담으면 추정 없이 비교가 선다.

## 하지 않는 것

면적비·인구비 배분을 하지 않는다. 한 건도. 어느 동 표인지 모르는 표(관외사전·
국외부재자·거소선상)는 **나누지 않고 제외하고, 제외했다는 사실과 규모를 남긴다**.
그래서 재집계 결과는 전체 결과가 아니라 `동 귀속표 기준` 결과다.

## 분모를 맞춘다 — 이게 가장 큰 함정

2020을 2024 경계로 재집계한 값(동 귀속표)을 2024 **공식 전체** 득표율과 빼면
획정 문제를 고치고 분모 불일치라는 새 오류를 만든다. 제외한 10%가 양쪽에서 다르게
빠지기 때문이다. swing은 **양 회차 모두 동 귀속표 기준**끼리만 계산한다.
공식 전체는 참조값으로 따로 들고 있는다.

## 방법(method)과 주장할 수 있는 것(capability)은 다르다

**재집계된 수준값은 틀릴 수 있어도 같은 분모의 변화량은 유효할 수 있다.**
하남시갑이 그 증거다. 동 귀속표만 보면 승자가 뒤집히는데(관외사전이 민주 +7.4%p 편향),
그 편향이 두 회차 사이에 거의 안 움직여서(0.24%p) 차이를 빼면 상쇄된다.

그래서 `reaggregated`를 하나의 신뢰 상태로 쓰지 않는다. 방법은 어떻게 구했는지고,
capability는 그것으로 **무엇을 주장할 수 있는지**다. 셋을 따로 판정한다.

    level    이 값을 '그 지역의 득표율'이라고 말할 수 있는가
             → 제외표를 빼도 공식 결과가 재현될 때만. 하남시갑은 false.
    delta    '이만큼 변했다'고 말할 수 있는가
             → 제외표 편향이 회차 사이에 안정적일 때. 하남시갑은 true.
    winner   '누가 이겼다'를 이 값으로 말할 수 있는가
             → 동 귀속표 승자와 공식 승자가 같을 때만.

셋은 서로를 끌어내리지 않는다. level이 false여도 delta는 true일 수 있다.

## 품질을 커버리지로만 판단하지 않는다

현 회차에는 두 값이 다 있다 — 동 귀속표 기준과 공식 전체. 둘의 차이가 곧
"귀속 불가 표를 뺐을 때 결과가 얼마나 흔들리는가"의 실측치다. 관외사전이 정치적으로
치우친 지역이면 커버리지가 높아도 차이가 크게 난다. 그래서 커버리지와 별개로
이 재현 오차를 품질 판정에 쓴다.

    validated     재현 오차 ≤ 1.0%p  그리고 커버리지 ≥ 85%
    limited       재현 오차 ≤ 3.0%p  그리고 커버리지 ≥ 70%
    insufficient  그 밖 — 수치를 내지 않는다

사용: python scripts/normalize/reaggregate.py 22 21 --sgg 4100:4131
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/build"))
import party_identity as PI  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts/normalize"))
import dong_geometry  # noqa: E402
from dong_geometry import ukey  # noqa: E402

RAW = ROOT / "data/raw/nec"
OUT = ROOT / "data/reaggregated"
ELECTION_DATE = {21: "2020-04-15", 22: "2024-04-10", 20: "2016-04-13"}

# 선거구 이름은 시도 안에서만 유일하다. '남구'는 부산·대구·인천·광주·울산에 다 있고
# '동구'·'중구'·'서구'도 마찬가지다. 시도를 빼고 키를 잡으면 전국 실행에서 다른
# 선거구의 표가 한 덩어리로 합쳐진다 — 254곳이 244곳으로 줄어드는 걸로 드러났다.
# **문자열 동일성 ≠ 의미 동일성**은 정당만의 함정이 아니다.
SIDO_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
    "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
    "강원도": "강원", "강원특별자치도": "강원", "충청북도": "충북",
    "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북",
    "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
    "제주특별자치도": "제주",
}


def dkey(sido: str, district: str) -> str:
    """선거구 키 — 시도를 반드시 붙인다. 계보 파일과 같은 표기('부산 남구')."""
    return f"{SIDO_SHORT.get(sido, sido)} {district}"

GOOD_ERR, OK_ERR = 1.0, 3.0
GOOD_COV, OK_COV = 0.85, 0.70
MAX_BIAS_SHIFT = 2.0    # 제외표 편향이 회차 사이에 이만큼 넘게 흔들리면 delta도 못 믿는다


# ── 후보 문자열 분해 ───────────────────────────────────────────────────────
def split_candidate(s: str) -> tuple[str, str]:
    """'더불어민주당최종윤' → ('더불어민주당', '최종윤'). registry 이름으로만 자른다."""
    names = sorted(_party_names(), key=len, reverse=True)
    for p in names:
        if s.startswith(p):
            return p, s[len(p):]
    if s.startswith("무소속"):
        return "무소속", s[3:]
    return "", s


_PN: set[str] | None = None


def _party_names() -> set[str]:
    """정당 이름 사전. registry + **실제 결과에 나온 이름**.

    registry에만 기대면 등록되지 않은 원외정당(국가혁명배당금당 등 293종)이 전부
    잘리지 않아 빈 키 하나로 뭉친다. 21대 서울 영등포구을에서 그런 표가 4.03%였고,
    그게 다른 미등록 정당들과 합쳐져 있었다. 이름을 못 가르는 것과 여러 당을 한
    덩어리로 세는 것은 다른 문제이고, 후자가 더 나쁘다.
    """
    global _PN
    if _PN is None:
        reg = json.loads((ROOT / "data/parties/registry.json").read_text(encoding="utf-8"))
        out: set[str] = set()
        for name, p in reg["parties"].items():
            out.add(name)
            if p.get("abbr"):
                out.add(p["abbr"])
            for a in p.get("aliases") or []:
                out.add(a)
        for f in sorted((ROOT / "data/results").glob("national_assembly_*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except Exception:                                   # noqa: BLE001
                continue
            for r in d.get("district") or []:
                for c in (r.get("candidates") or []) if isinstance(r, dict) else []:
                    if c.get("party"):
                        out.add(c["party"])
        _PN = {x for x in out if x}
    return _PN


# ── 집계 ──────────────────────────────────────────────────────────────────
def _load(n: int, tag: str) -> list[dict]:
    f = RAW / f"emd_votes_{n}{tag}.json"
    if not f.exists():
        raise FileNotFoundError(f"{f} — 먼저 fetch_emd_votes.py {n} 로 받아라")
    return json.loads(f.read_text(encoding="utf-8"))


def dong_map(blocks: list[dict]) -> dict[str, str]:
    """동 → 선거구. 한 동이 두 선거구에 걸치면 담지 않는다(가로지르는 동)."""
    seen: dict[str, set[str]] = {}
    for b in blocks:
        for r in b["rows"]:
            if r["dong"]:
                seen.setdefault(ukey(b["sgg_code"], r["dong"]), set()).add(
                    dkey(b["sido"], r["district"]))
    return {d: next(iter(v)) for d, v in seen.items() if len(v) == 1}


def crossing(blocks: list[dict]) -> list[str]:
    seen: dict[str, set[str]] = {}
    for b in blocks:
        for r in b["rows"]:
            if r["dong"]:
                seen.setdefault(ukey(b["sgg_code"], r["dong"]), set()).add(
                    dkey(b["sido"], r["district"]))
    return sorted(d for d, v in seen.items() if len(v) > 1)


def by_party(rows: list[dict], date: str) -> dict[str, int]:
    """후보 득표 → 정당 identity별 합. 정당 비교는 전부 resolver를 거친다."""
    out: dict[str, int] = {}
    for r in rows:
        for cand, v in r["per_candidate"].items():
            p, _ = split_candidate(cand)
            key = PI.identity(p, date) if p and p != "무소속" else "무소속"
            out[key] = out.get(key, 0) + v
    return out


def attributable(blocks: list[dict], dmap: dict[str, str] | None = None):
    """동에 귀속되는 행만 선거구별로 모은다. dmap을 주면 그 경계로 다시 담는다."""
    per: dict[str, list[dict]] = {}
    excluded: dict[str, int] = {}
    unmapped: dict[str, int] = {}
    for b in blocks:
        for r in b["rows"]:
            if r["kind"] == "subtotal":
                continue
            if r["kind"] != "precinct" and r["unit"] != "관내사전투표":
                excluded[r["kind"]] = excluded.get(r["kind"], 0) + r["valid"]
                continue
            if not r["dong"]:                      # 합동투표구 — 동을 특정 못 한다
                unmapped["joint_precinct"] = unmapped.get("joint_precinct", 0) + r["valid"]
                continue
            tgt = (dmap.get(ukey(b["sgg_code"], r["dong"])) if dmap is not None
                   else dkey(b["sido"], r["district"]))
            if tgt is None:
                unmapped["no_lineage"] = unmapped.get("no_lineage", 0) + r["valid"]
                continue
            per.setdefault(tgt, []).append(r)
    return per, excluded, unmapped


def official(blocks: list[dict]) -> dict[str, dict]:
    """각 선거구 '계' 행 — 공식 전체 결과. 참조값으로만 쓴다.

    '계'는 (구시군 × 선거구)마다 하나다. 선거구가 여러 시군구에 걸치면
    (동구군위군을 = 대구 동구 일부 + 군위군) 여러 개가 나오므로 **더한다**.
    덮어쓰면 분모가 일부만 남아 커버리지가 100%를 넘는다 — 실제로 614%가 나왔다.
    """
    out: dict[str, dict] = {}
    for b in blocks:
        for r in b["rows"]:
            if r["kind"] != "subtotal" or r["unit"] != "계":
                continue
            cur = out.get(dkey(b["sido"], r["district"]))
            if cur is None:
                out[dkey(b["sido"], r["district"])] = dict(r, per_candidate=dict(r["per_candidate"]))
                continue
            for k in ("electors", "votes", "valid", "invalid"):
                cur[k] += r[k]
            for k, v in r["per_candidate"].items():
                cur["per_candidate"][k] = cur["per_candidate"].get(k, 0) + v
    return out


def _partial_districts(rnd: int, off: dict) -> set[str]:
    """회수한 구시군만으로는 선거구 전체가 안 되는 곳. 공식 결과 파일과 대사한다.

    fixture는 구시군 단위로 받는데 선거구는 시군구를 넘나든다. 한 조각만 받고도
    합계가 그럴듯해 보이면 '정확한 부분집합'을 전체로 착각하게 된다.
    """
    f = ROOT / f"data/results/national_assembly_{rnd}.json"
    if not f.exists():
        return set()
    d = json.loads(f.read_text(encoding="utf-8"))
    want: dict[str, int] = {}
    for r in d.get("district") or []:
        if not isinstance(r, dict):
            continue
        # 여기서도 시도를 붙인다 — '남구'만으로 맞추면 다른 시도 것과 대사하게 된다
        nm = dkey(r.get("sido") or "", r.get("name") or r.get("district") or "")
        v = sum(c.get("votes") or 0 for c in (r.get("candidates") or []))
        if nm.strip() and v:
            want[nm] = v
    bad = set()
    for k, row in off.items():
        w = want.get(k)
        if w and abs(sum(row["per_candidate"].values()) - w) > 0.01 * w:
            bad.add(k)
    return bad


def _excluded_lean_by_district(blocks: list[dict], date: str) -> dict[str, dict]:
    """**선거구마다** 제외표가 공식 전체보다 어느 정당 쪽으로 몇 %p 치우쳤나.

    전국 하나로 뭉치면 안 된다. 관외사전·국외부재자의 정치적 치우침은 지역마다 다르다.
    전국 평균을 모든 선거구에 갖다 대면 실제로는 안정적인 곳을 불안정으로 보거나
    그 반대가 된다 — 대조군 검증에서 서울 영등포구을이 동 구성은 양 회차 완전히
    같은데도 direct와 5.2%p 어긋나는 걸로 드러났다.

    그 회차 자신의 선거구에서만 잰다. 재집계 대상 회차의 경계로 옮겨 재면 분모가 어긋난다.
    """
    att, _, _ = attributable(blocks)
    off = official(blocks)
    out: dict[str, dict] = {}
    for d, orow in off.items():
        o = by_party([orow], date)
        a = by_party(att.get(d, []), date)
        osh = shares(o)
        ex = shares({k: v for k in set(o) | set(a) if (v := o.get(k, 0) - a.get(k, 0)) > 0})
        out[d] = {k: ex.get(k, 0) - osh[k] for k in osh}
    return out


def _prev_lean_for(cur_d: str, contrib: dict, lean_by: dict) -> dict:
    """현 선거구에 표를 보낸 **과거 선거구들**의 편향을 기여 규모로 가중평균한다.

    획정이 바뀌었으면 여러 과거 선거구에서 표가 온다. 하나만 쓰거나 전국 평균을 쓰면
    비교 대상이 어긋난다.
    """
    src = contrib.get(cur_d) or {}
    tot = sum(src.values()) or 1.0
    out: dict = {}
    for pd_, w in src.items():
        for k, v in (lean_by.get(pd_) or {}).items():
            out[k] = out.get(k, 0.0) + v * w / tot
    return out


def shares(pv: dict[str, int]) -> dict[str, float]:
    t = sum(pv.values())
    return {k: v / t * 100 for k, v in pv.items()} if t else {}


# ── 동 계보 ───────────────────────────────────────────────────────────────
def load_lineage() -> dict:
    f = ROOT / "data/geography/dong_lineage.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def _short(keys) -> dict:
    """{시군구코드:동 → 선거구}에서 이름만 뽑아 본다. 계보 파일이 이름 기반이라
    폴리곤이 없을 때의 보조 경로에서만 쓴다 — 충돌 가능성이 있으므로 우선순위는 낮다."""
    out: dict = {}
    for k, v in keys.items():
        out.setdefault(k.split(":", 1)[-1], v)
    return out


def resolve_dong(dong: str, sgg: str, lin: dict, target: set[str]) -> str | None:
    """과거 동 이름 → 현 회차 동 이름. 없으면 None(추정하지 않는다)."""
    if dong in target:
        return dong
    for e in lin.get(sgg, []):
        if e["from"] == dong:
            to = e["to"]
            return to[0] if len(to) == 1 and to[0] in target else (
                to[0] if all(t in target for t in to) and e.get("same_district") else None)
    return None


# ── 본체 ──────────────────────────────────────────────────────────────────
def run(cur: int, prev: int, tag: str = "") -> dict:
    fixture = tag[1:] if tag.startswith("_") else tag
    cb, pb = _load(cur, tag), _load(prev, tag)
    cdate, pdate = ELECTION_DATE[cur], ELECTION_DATE[prev]
    dmap = dong_map(cb)
    cross = crossing(cb)
    lin = load_lineage()
    tgt_dongs = dmap

    # 과거 동 → 현 선거구. **지오메트리가 먼저다.** 이름 일치는 근거가 못 된다:
    # 부천은 2019년에 36개 동을 10개 광역동으로 합쳤다가 2024년에 되돌려서,
    # 2020년 '중동'과 2024년 '중동'이 이름은 같은데 크기가 다르다.
    sgg = pb[0]["sgg_name"] if pb else ""
    geo, crossing_map = dong_geometry.resolve(cur, prev, fixture, cb, pb, dmap)
    prev_dongs = {ukey(b["sgg_code"], r["dong"])
                  for b in pb for r in b["rows"] if r["dong"]}
    crossing_prev = sorted(crossing_map)

    short = _short(dmap)          # 이름 → 선거구 (계보 보조 경로 전용)
    pmap: dict[str, str] = {}
    unresolved: list[str] = []
    for d in sorted(prev_dongs):
        if d in geo:                      # 폴리곤이 한 선거구 안에 온전히 들어간다
            pmap[d] = geo[d]
        elif d in crossing_map:           # 선거구를 가로지른다 — 동 단위로 못 나눈다
            unresolved.append(d)
        elif (t := resolve_dong(d.split(":", 1)[-1], sgg, lin, short)):
            pmap[d] = short[t]            # 폴리곤이 없을 때만 계보 이름으로 (근거 기록됨)
        else:
            unresolved.append(d)

    # 과거 회차 제외표 편향은 **그 회차 자신의 선거구 단위**로 잰다. 새 경계로 재집계한
    # 값에서 옛 공식 전체를 빼면 분모가 어긋난다 — 재집계가 고치려던 그 오류다.
    lean_by = _excluded_lean_by_district(pb, pdate)
    # 현 선거구 ← 과거 선거구별 기여 규모(유효표). 편향 비교의 짝을 맞추는 데 쓴다.
    contrib: dict[str, dict] = {}
    for b in pb:
        for r in b["rows"]:
            if r["kind"] != "precinct" or not r["dong"]:
                continue
            tgt = pmap.get(ukey(b["sgg_code"], r["dong"]))
            if not tgt:
                continue
            src = dkey(b["sido"], r["district"])
            c = contrib.setdefault(tgt, {})
            c[src] = c.get(src, 0) + r["valid"]

    cur_att, cur_exc, cur_unm = attributable(cb)
    prv_att, prv_exc, prv_unm = attributable(pb, pmap)
    cur_off = official(cb)
    partial = _partial_districts(cur, cur_off)

    # 가로지르는 동의 표는 어느 선거구 것인지 모른다. 그 동이 **닿는** 선거구에만
    # '잃은 표'로 달아 둔다 — 면적비로 나누지 않는다. 안 닿는 선거구는 멀쩡하다.
    lost_by: dict[str, int] = {}
    for b in pb:
        for r in b["rows"]:
            for t_ in crossing_map.get(ukey(b["sgg_code"], r["dong"] or ""), []):
                if r["kind"] == "precinct":
                    lost_by[t_] = lost_by.get(t_, 0) + r["valid"]

    districts = {}
    for d in sorted(cur_att):
        ca = by_party(cur_att[d], cdate)
        pa = by_party(prv_att.get(d, []), pdate)
        off = cur_off.get(d)
        off_p = by_party([off], cdate) if off else {}
        cs, ps, os_ = shares(ca), shares(pa), shares(off_p)
        # 재현 오차 — 현 회차에서 동 귀속표가 공식 전체를 얼마나 되살리나
        err = max((abs(cs.get(k, 0) - os_.get(k, 0)) for k in set(cs) | set(os_)),
                  default=0.0)
        att_v, off_v = sum(ca.values()), sum(off_p.values())
        cov = att_v / off_v if off_v else 0.0
        # 제외한 표만 따로 — 이 표가 정치적으로 치우쳤는지 직접 잰다.
        # 오차 크기만으로는 부족하다: 하남시갑은 오차 1.24%p인데 승자가 뒤집힌다.
        exc_p = {k: off_p.get(k, 0) - ca.get(k, 0) for k in set(off_p) | set(ca)}
        exc_s = shares({k: v for k, v in exc_p.items() if v > 0})
        w_att = max(cs, key=cs.get, default=None)
        w_off = max(os_, key=os_.get, default=None)
        agree = w_att == w_off
        qual = ("validated" if err <= GOOD_ERR and cov >= GOOD_COV and agree else
                "limited" if err <= OK_ERR and cov >= OK_COV else "insufficient")
        # 제외표 편향이 회차 사이에 얼마나 흔들리나. swing은 양쪽에서 같은 종류의 표를
        # 빼므로, 편향이 **안정적이면 상쇄되고** 흔들리면 그만큼 swing에 섞인다.
        # 하남 실측: 민주 +7.63%p(2020) → +7.39%p(2024). 안정적이라 swing이 선다.
        prev_lean = _prev_lean_for(d, contrib, lean_by)
        stab = {k: round(abs((exc_s.get(k, 0) - os_.get(k, 0)) - prev_lean[k]), 2)
                for k in set(os_) & set(prev_lean) if os_[k] > 3}

        # 가로지르는 동이 있으면 그 표를 어디에 담을지 알 수 없다. 면적비로 쪼개지
        # 않으므로 재집계 자체가 성립하지 않는다 — 계보는 잇되 수치는 내지 않는다.
        lost = lost_by.get(d, 0)
        blocked = (d in partial) or lost > 0.02 * (sum(pa.values()) + lost)
        if blocked:
            qual = "insufficient"

        # '지난번엔 아예 안 나왔다'와 '표가 줄었다'는 다르다. 대구 동구군위군을에서
        # 2020년 민주당은 나왔고 2024년엔 안 나왔는데, 그대로 빼면 '민주당 -24.8%p'가
        # 되어 없던 이탈처럼 읽힌다. 양쪽 다 나온 정당만 swing으로 센다.
        # 측정과 일반화를 나눈다. 하남시갑의 동 귀속표 49.35/50.65는 **틀린 값이 아니다** —
        # '동 귀속 가능한 표에서 잰 값'으로는 정확하다. 틀리는 건 그걸 전체 공식 득표
        # 수준이라고 말하는 것이다. `level=false`라고 쓰면 측정 자체가 무효로 읽힌다.
        #
        #     measurement            부분집합에서 실제로 쟀는가
        #     inference_to_full      그 값을 전체 결과로 일반화해도 되는가
        #     comparison.delta       같은 분모끼리의 변화량을 말할 수 있는가
        #
        # 부분집합에서 정확한 값 ≠ 전체 수준값으로 쓸 수 있는 값.
        measured = bool(att_v) and not blocked
        infer_level = bool(agree and err <= GOOD_ERR and cov >= GOOD_COV)
        infer_reason = (None if infer_level else
                        "excluded_votes_change_winner" if not agree else
                        "attributable_does_not_reproduce_official"
                        if err > GOOD_ERR else "coverage_too_low")

        # 경쟁 구도가 달라졌는지 — 한쪽 회차에만 있는 유효 규모 후보/정당.
        # 하남시갑 2020년 무소속 이현재 15.67%가 그 예다. 이걸 '제외표 편향 문제'라고
        # 부르면 관외사전 표본 탓으로 오해된다. 실제로는 **정당 득표 delta의 해석이
        # 깨진 것**이다 — 보수표가 무소속으로 갈렸으니 국민의힘 변화량은 뜻이 다르다.
        MAJOR = 5.0
        only_one = {k for k in set(cs) | set(ps)
                    if abs(cs.get(k, 0) - ps.get(k, 0)) >= MAJOR
                    and (k not in cs or k not in ps)}
        struct_changed = bool(only_one)

        def _delta_reason(party: str) -> str | None:
            if party not in ps:
                return "party_entry"
            if party not in cs:
                return "party_exit"
            if stab.get(party, 0.0) <= MAX_BIAS_SHIFT:
                return None
            # 편향이 흔들리는 이유가 둘로 갈린다 — 섞으면 안 된다
            return ("candidacy_configuration_changed" if struct_changed
                    else "excluded_vote_bias_shift")

        both = sorted(k for k in set(cs) & set(ps) if k != "무소속")
        delta_by = {k: {"allowed": _delta_reason(k) is None,
                        "bias_shift_pp": round(stab.get(k, 0.0), 2),
                        "reason": _delta_reason(k)} for k in both}
        delta_ok = any(v["allowed"] for v in delta_by.values())

        cap = {
            "measurement": {
                "attributable_level": {
                    "valid": measured,
                    "note": "동 귀속 가능한 표에서 잰 값 — 그 범위에서는 정확하다",
                    "reason": None if measured else "reaggregation_blocked"},
                "attributable_winner": {"valid": measured},
            },
            "inference_to_full_result": {
                "level": {"allowed": infer_level and measured,
                          "reason": None if (infer_level and measured)
                          else ("reaggregation_blocked" if not measured
                                else infer_reason)},
                "winner": {"allowed": bool(agree) and measured,
                           "reason": None if (agree and measured)
                           else ("reaggregation_blocked" if not measured
                                 else "excluded_votes_change_winner")},
            },
            "comparison": {
                "delta": {"allowed": bool(pa) and delta_ok and measured,
                          "by_party": delta_by,
                          "reason": (None if (pa and delta_ok and measured) else
                                     "reaggregation_blocked" if not measured else
                                     "no_previous_data" if not pa else
                                     "no_common_party" if not delta_by else
                                     "candidacy_configuration_changed"
                                     if struct_changed else
                                     "excluded_vote_bias_shift")},
            },
        }

        swing = unstable = None
        entered = {k: round(cs[k], 2) for k in cs if k not in ps and k != "무소속"}
        left = {k: round(ps[k], 2) for k in ps if k not in cs and k != "무소속"}
        if pa and qual != "insufficient" and cap["comparison"]["delta"]["allowed"]:
            # **양쪽 모두 동 귀속표 기준**. 공식 전체와 섞지 않는다.
            # 편향이 안정적인 정당만 낸다. 흔들리는 정당의 변화량은 제외표 이동이
            # 섞여 있어 그대로 쓰면 없던 변화를 만든다.
            ok_p = {k for k, v in delta_by.items() if v["allowed"]}
            swing = {k: round(cs[k] - ps[k], 2)
                     for k in sorted(set(cs) & set(ps))
                     if k != "무소속" and k in ok_p}
            unstable = {k: round(cs[k] - ps[k], 2)
                        for k in sorted(set(cs) & set(ps))
                        if k != "무소속" and k not in ok_p}
        districts[d] = {
            "method": ("context_only" if blocked else
                       "reaggregated" if pa else "direct"),
            "reaggregation_quality": qual,
            "attributable": (None if blocked else
                             {"votes": att_v,
                              "share": {k: round(v, 2) for k, v in cs.items()}}),
            "official_reference": {"votes": off_v,
                                   "share": {k: round(v, 2) for k, v in os_.items()}},
            # 차단됐으면 수치를 아예 담지 않는다. 남겨 두고 '주의' 문구를 붙이면
            # 그 문구가 떨어져 나간 자리에서 그대로 인용된다.
            "prev_reaggregated": (None if blocked or not pa else
                                  {"votes": sum(pa.values()),
                                   "share": {k: round(v, 2) for k, v in ps.items()}}),
            "capability": cap,
            "swing_attributable_basis": swing,
            # 편향이 흔들려 변화량을 주장할 수 없는 정당 — 버리지 않고 드러낸다
            "swing_bias_unstable": unstable or None,
            # 증감이 아니다 — 한쪽 회차에만 출마한 정당은 따로 담는다
            "newly_ran": entered if swing is not None else None,
            "no_longer_ran": left if swing is not None else None,
            "provenance": {
                "source": "info.nec.go.kr VCCP08 투표구별 개표",
                "basis_boundary": f"{cur}대 선거구",
                "denominator": "동 귀속표 기준 (양 회차 동일)",
                "coverage": round(cov, 4),
                "excluded_categories": cur_exc,
                "unmapped": cur_unm,
                "prev_excluded_categories": prv_exc,
                "prev_unmapped": prv_unm,
                "dong_lineage_applied": [f"{k}→{v}" for k, v in sorted(pmap.items())
                                         if k not in tgt_dongs],
                "unresolved_dongs": sorted(set(unresolved)),
                "crossing_prev_dongs": sorted(n for n, ds in crossing_map.items()
                                              if d in ds),
                # '우리 알고리즘이 못 푼다'가 아니라 '읍면동 해상도에 정보가 없다'다.
                # 투표구 경계 자료가 생기면 다음 단계로 풀린다. 없으면 배분하지 않는다.
                "resolution_required": ("precinct" if any(d in ds for ds
                                                          in crossing_map.values())
                                        else None),
                "votes_unplaceable": lost,
                "partial_fetch": d in partial,
                "crossing_dongs": cross,
                "party_identity": "scripts/build/party_identity.py",
                "allocation_by_area_or_population": 0,
                "current_election_validation_error_pp": round(err, 2),
            },
            # 현 회차로 잰 검증값. 재집계 수치를 화면에 쓸 때 **반드시 같이** 나간다.
            "validation": {
                "winner_attributable": w_att,
                "winner_official": w_off,
                "winner_agrees": agree,
                "excluded_share": {k: round(v, 2) for k, v in exc_s.items()},
                "excluded_lean_pp": {k: round(exc_s.get(k, 0) - os_.get(k, 0), 2)
                                     for k in os_},
                "excluded_lean_prev_pp": {k: round(v, 2) for k, v in prev_lean.items()},
                "bias_stability_pp": stab,
            },
        }
    return {"current": cur, "previous": prev, "sgg": sgg, "districts": districts}


def main() -> None:
    a = sys.argv[1:]
    cur, prev = int(a[0]), int(a[1])
    tag = ("_" + a[a.index("--name") + 1] if "--name" in a else
           "_" + "-".join(s.replace(":", "") for s in a[a.index("--sgg") + 1].split(","))
           if "--sgg" in a else "")
    res = run(cur, prev, tag)
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{cur}__{prev}{tag}.json"
    f.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for d, v in res["districts"].items():
        p = v["provenance"]
        print(f"\n[{d}] {v['method']} / {v['reaggregation_quality']}")
        print(f"  커버리지 {p['coverage']*100:.1f}% · 재현오차 {p['current_election_validation_error_pp']}%p")
        if v["attributable"] is None:
            why = ("선거구 일부만 회수됨(구시군 누락)" if p["partial_fetch"]
                   else "선거구를 가로지르는 동: " + ", ".join(p["crossing_prev_dongs"]))
            print(f"  ✗ 재집계 차단 — {why}")
            continue
        print(f"  {cur} 동귀속 {v['attributable']['share']}")
        print(f"  {cur} 공식전체 {v['official_reference']['share']}")
        if v["prev_reaggregated"]:
            print(f"  {prev} 재집계 {v['prev_reaggregated']['share']}")
            print(f"  swing {v['swing_attributable_basis']}")
    print(f"\n→ {f}")


if __name__ == "__main__":
    main()
