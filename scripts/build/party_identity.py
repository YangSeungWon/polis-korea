"""정당 identity resolver — 비교 연산이 **전부 여기를 거친다**.

정당 문자열과 비교 identity는 다른 것이다. 이걸 분리하지 않으면 같은 버그가
연산마다 다르게 나타난다. 실제로 그랬다:
  · 승자 판정은 same_party를 쓰고 득표 집계는 raw name을 써서
    '국민의힘 +46%p / 미래통합당 -45%p'라는 없는 변화가 만들어졌다(둘은 개명이다)
  · '민중당'은 1965년 것과 2017년 것이 다른 당인데 한 덩어리로 세어졌다

세 가지를 분리한다:
  identity_id   시간에 걸쳐 유지되는 **비교용** 키. 화면에 내보내지 않는다.
                (계보 대표는 '미래통합당'·'한나라당' 같은 옛 이름이 되므로 라벨로 부적합)
  display_name  그 회차에서 실제로 쓴 이름. 화면에는 이것만.
  policy        관계 유형에 따른 비교 정책

## 비교 정책

  rename    → direct       같은 당이 이름만 바꿨다. 직접 비교한다.
  merge     → no           여러 당이 합쳤다. 이전 각 당의 표를 후신에 귀속시킬 근거가 없다.
  split     → no           갈라졌다. 같은 이유로 나눌 수 없다.
  alliance  → conditional  선거연합·연합 당명. 명시적 정책이 있을 때만.
  new/dissolve/미상 → no

**계보에 있다고 무조건 합산하지 않는다.** 더불어시민당·열린민주당은 더불어민주당으로
합당했지만(merge), 2020년 그 표를 2024년 더불어민주당 표와 직접 비교하면 안 된다 —
위성정당이었고 유권자의 선택 구조가 달랐다.

## registry 공백

registry에 없는 정당은 **그 자체로 독립 identity**다. 추정해서 잇지 않는다.
`unregistered()`로 드러내되 조용히 버리지도 않는다 — 21·22대에만 46종이 미등록이고
대부분 원외 소수정당이지만 '녹색정의당'처럼 의미 있는 것도 섞여 있다.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data/parties/registry.json"

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from party_canon import disambiguate_party  # noqa: E402

# 관계 유형 → 비교 정책. 여기 없으면 "no"다(모르면 비교하지 않는다).
POLICY = {
    "rename": "direct",
    "merge": "no",
    "split": "no",
    "alliance": "conditional",
    "new": "no",
    "dissolve": "no",
}

_REG: dict | None = None
_CHAIN: dict | None = None


def _registry() -> dict:
    global _REG
    if _REG is None:
        try:
            _REG = json.loads(REGISTRY.read_text(encoding="utf-8"))["parties"]
        except Exception:
            _REG = {}
    return _REG


def _chains() -> dict:
    """정당명 → identity_id. **개명(rename)으로만** 잇는다."""
    global _CHAIN
    if _CHAIN is not None:
        return _CHAIN
    reg = _registry()
    parent: dict = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # predecessors는 **관계가 섞인 목록**이다. 개명 전신과 나중에 합당해 들어온 당이
    # 같이 들어 있다. 국민의힘의 predecessors는 [국민의당(2020), 미래통합당]인데
    # 미래통합당만 개명 전신이고 국민의당(2020)은 2022년에 흡수된 별개 정당이다.
    # 목록을 통째로 union하면 2020년 국민의당 표가 국민의힘 계보로 빨려 들어간다.
    #
    # 개명은 **끊김 없이 이어진다** — 전신이 해산한 달에 후신이 생긴다. 이 시점
    # 일치를 union 조건으로 쓴다. 등록된 날짜가 없으면 잇지 않는다(추정 금지).
    def continuous(pred: str, succ: dict) -> bool:
        d, f = (reg.get(pred) or {}).get("dissolved"), succ.get("founded")
        return bool(d and f and d[:7] == f[:7])

    for name, info in reg.items():
        find(name)
        if info.get("relation") != "rename":
            continue
        preds = [p for p in (info.get("predecessors") or []) if p in reg]
        # 전신이 하나뿐이면 그게 개명 전신이다. 여럿이면 시점이 맞물린 것만.
        for pr in preds if len(preds) == 1 else [p for p in preds if continuous(p, info)]:
            a, b = find(pr), find(name)
            if a != b:
                parent[b] = a
    # id는 사슬에서 사전순 최소 — 결정적이되 **표시용이 아니다**
    groups: dict = {}
    for n in parent:
        groups.setdefault(find(n), []).append(n)
    _CHAIN = {}
    for root, members in groups.items():
        pid = "pid:" + min(members)
        for m in members:
            _CHAIN[m] = pid
    return _CHAIN


def canonical(name: str, date: str = "") -> str:
    """동음이의를 날짜로 가른 정식명. '민중당' 2020 → '민중당(2017)'."""
    return disambiguate_party(name, date or "") if name else ""


def _outside_lifetime(c: str, date: str) -> bool:
    """canonical 이름이 registry에 있지만 **그 정당이 없던 때의 관측**인가.

    disambiguate_party는 시기 노드를 못 찾으면 원자료 이름을 그대로 돌려준다.
    그 이름이 마침 registry에 있으면 여기서 조용히 그 정당의 pid를 받아 간다 —
    fallback을 막아 놓고 한 층 뒤에서 같은 병합이 일어나는 것이다. 실제로:
      · 2020년 종로 '한나라당' 0.08%가 pid:새누리당에 붙어 2016년 새누리당
        39.73%와 짝지어졌다(direct -39.72%p짜리 가짜 pair)
      · 2012년 목포 '민주통일당' 524표가 1973년 양일동 민주통일당에 붙는다
    """
    node = _registry().get(c)
    if not node or not date:
        return False
    ym = date[:7]
    f = (node.get("founded") or "")[:7]
    d = (node.get("dissolved") or "")[:7]
    # 연도만 적힌 경계는 **넓게** 읽는다("1988" → 1988-01~1988-12). 좁게 읽으면
    # 1988-04 관측이 구간 밖으로 잘못 튄다(전에 이 버그로 오탐 6건이 났다).
    if f and len(f) == 4:
        f += "-01"
    if d and len(d) == 4:
        d += "-12"
    return bool(f) and (ym < f or (bool(d) and ym > d))


def identity(name: str, date: str = "") -> str:
    """비교용 stable id. **화면에 내보내지 않는다.**
    registry에 없으면 그 이름 자체가 독립 identity — 추정해서 잇지 않는다."""
    c = canonical(name, date)
    if not c:
        return ""
    if _outside_lifetime(c, date):
        # 그 정당이 아니다. 어느 정당인지는 모른다. 둘을 합치지 않는다 —
        # 같은 이름의 미해소 관측끼리만 묶고, 아는 정당과는 섞지 않는다.
        # 시기 노드를 만들어 주면 이 버킷은 사라진다.
        return f"pid:{c}(미상)"
    return _chains().get(c, f"pid:{c}")


def relation(name: str, date: str = "") -> str | None:
    return (_registry().get(canonical(name, date)) or {}).get("relation")


def policy(prev_name: str, prev_date: str, cur_name: str, cur_date: str) -> str:
    """두 회차의 정당을 **직접 비교해도 되는가**.

    개별 정당이 아니라 **전이**를 묻는 것이다. 처음엔 정당 하나의 relation을 봤는데
    그러면 '미래통합당은 merge로 생겼으니 비교 불가'가 되어버린다. 물어야 할 건
    '미래통합당(2020)과 국민의힘(2024)이 같은 당인가'이고, 답은 rename이므로 그렇다.

      same        같은 identity — 직접 비교
      merge_split 다른 identity인데 합당·분당 관계 — 표를 귀속시킬 근거가 없다
      unrelated   관계 없음 — 각자 센다
    """
    pi, ci = identity(prev_name, prev_date), identity(cur_name, cur_date)
    if pi and pi == ci:
        return "same"
    pr, cr = relation(prev_name, prev_date), relation(cur_name, cur_date)
    if {pr, cr} & {"merge", "split", "alliance"}:
        return "merge_split"
    return "unrelated"


def unregistered(name: str, date: str = "") -> bool:
    return canonical(name, date) not in _registry()


def display_name(pid: str, prefer: dict) -> str:
    """identity → 화면에 쓸 이름. prefer는 {identity: 그 회차에서 쓴 이름}.
    계보 대표(옛 이름)를 라벨로 쓰지 않는다 — '미래통합당'이 2024년 화면에 나오면 안 된다."""
    if pid in prefer:
        return prefer[pid]
    return pid[4:] if pid.startswith("pid:") else pid


def labels_for(races: list, date: str) -> dict:
    """그 회차 결과에서 identity → 실제 사용 이름을 뽑는다."""
    out: dict = {}
    for r in races:
        for c in r.get("candidates") or []:
            n = c.get("party")
            if n and n != "무소속":
                out.setdefault(identity(n, date), n)
    return out
