"""관측된 정당명과 **확인된 정당**을 같은 것으로 다루지 않는가.

registry.json = 정식명·창당·계보를 확인한 정당.
observed.json = 결과에 이름이 나온 것. 여기 있다고 계보를 아는 게 아니다.

둘을 한 집합으로 취급하면 '계보를 안다'는 뜻이 희석된다 — 한 그릇에 두 의미를 담는
그 실패다. 이 검사는 셋을 본다:

  ① 관측 합계가 원자료와 맞는가 (유도값이 실제로 유도된 것인가)
  ② 결과에 나왔다는 이유만으로 registry에 들어가지 않았는가
  ③ 동음이의 큐가 비어 가는가 (예외 목록으로 굳지 않는가)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/build"))
fails: list = []


def ck(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        fails.append(name)
        print(f"  ✗ {name}{' — ' + detail if detail else ''}")


obs = json.loads((ROOT / "data/parties/observed.json").read_text(encoding="utf-8"))
reg = json.loads((ROOT / "data/parties/registry.json").read_text(encoding="utf-8"))["parties"]
hom = json.loads((ROOT / "data/parties/known_homonyms.json").read_text(encoding="utf-8"))
rows = obs["parties"]

# ① 유도값이 실제로 유도된 것인가 — build_runs를 다시 돌려 합계를 맞춘다
from build_party_pages import build_runs  # noqa: E402

runs = build_runs()
tot_o = (sum(r["candidates"] for r in rows), sum(r["votes"] for r in rows),
         sum(r["wins"] for r in rows))
tot_r = (sum(x["candidates"] for rs in runs.values() for x in rs),
         sum(x["votes"] for rs in runs.values() for x in rs),
         sum(x["won"] for rs in runs.values() for x in rs))
ck(f"관측 합계가 원자료와 일치 {tot_o} vs {tot_r}", tot_o == tot_r)
ck("관측 종수가 일치", len(rows) == len([k for k, v in runs.items() if v]))

# ② 결과에 나왔다는 이유만으로 registry에 들어가지 않았는가
#    (registry는 '확인한 것'의 목록이다 — 관측이 그 자격을 주지 않는다)
linked = [r for r in rows if r["registry_id"]]
ck("registry_id는 registry에 실제로 있는 이름만",
   all(r["registry_id"] in reg for r in linked))
unres = [r for r in rows if r["status"] == "unresolved"]
ck("미확인은 registry에 링크되지 않는다", all(not r["registry_id"] for r in unres))
ck("미확인이 존재한다는 사실을 숨기지 않는다", len(unres) > 0, str(len(unres)))

# 추론 금지 필드가 새어 들어오지 않았는가
BANNED = {"founded", "dissolved", "predecessors", "successors", "stream", "lineage"}
for r in rows[:50]:
    leaked = BANNED & set(r)
    ck(f"{r['name']}: 추론 필드가 없다", not leaked, str(leaked))

# ③ 동음이의는 예외 목록이 아니라 큐다 — 사유와 상태가 있어야 한다
ck("동음이의 항목에 사유·상태가 있다",
   all(x.get("reason") and x.get("status") and x.get("note") for x in hom["unresolved"]))
# 개수 상한을 두지 않는다 — **새 동음이의를 발견하면 큐가 느는 게 정상**이다.
# 상한을 걸면 발견을 억제하게 된다. 대신 큐가 큐답게 동작하는지를 본다:
# 해소된 항목이 unresolved로 남아 있지 않은가.
_stale = [x["name"] for x in hom["unresolved"]
          if x.get("status") == "resolved" or x["name"] in reg and "(" in x["name"]]
ck("해소된 항목이 큐에 남아 있지 않다", not _stale, str(_stale))
ck("큐 항목이 실제로 관측된 이름이다",
   all(x["name"] in {r["name"] for r in rows} for x in hom["unresolved"]),
   str([x["name"] for x in hom["unresolved"]
        if x["name"] not in {r["name"] for r in rows}]))

# ③-2 큐에 적은 회차별 판정이 원자료와 맞는가
#
# 기독당은 시대가 겹치는 동음이의가 아니라 **등록약칭 충돌**이다. 회차마다 다른 이름의
# 정당(한국기독당·기독사랑실천당·기독자유민주당·기독당)이 같은 문자열로 들어와 있어서,
# registry에 시점 표기로 나누는 방식으로는 풀리지 않는다.
#
# 실체를 특정한 근거가 **그 회차 비례 득표수**다. 그러니 그 숫자가 원자료와 어긋나면
# 판정 전체를 다시 봐야 한다 — 여기서 대조한다. 문장으로만 적어 두면 조용히 낡는다.
_RES = ROOT / "data/results"
_prop_cache: dict = {}


def prop_votes(date: str, party: str) -> int:
    """그 선거일의 비례(tc7·tc8) 전국·시도 행에서 그 이름의 득표 합."""
    key = (date, party)
    if key in _prop_cache:
        return _prop_cache[key]
    total = 0
    for fp in sorted(_RES.glob("*.json")):
        if ".sigungu" in fp.name:
            continue
        try:
            doc = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        if (doc.get("_meta") or {}).get("election_date") != date:
            continue
        for r in doc.get("races") or []:
            if r.get("sg_typecode") not in ("7", "8"):
                continue
            if r.get("scope") not in ("nation", "proportional_sido"):
                continue
            for c in r.get("candidates") or []:
                if c.get("party") == party:
                    total += c.get("votes") or 0
    _prop_cache[key] = total
    return total


def dist_votes(date: str, district: str, candidate: str) -> int:
    """그 선거일의 지역구(tc2) 행에서 그 선거구·후보의 득표.

    비례에 안 나온 정당은 비례 득표수를 지문으로 쓸 수 없다 — 2012년 민주통일당은
    목포시 후보 한 명뿐이다. 그런 건은 (선거구, 후보)로 잰다.
    """
    for fp in sorted(_RES.glob("*.json")):
        if ".sigungu" in fp.name:
            continue
        try:
            doc = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        if (doc.get("_meta") or {}).get("election_date") != date:
            continue
        for r in doc.get("races") or []:
            if r.get("sg_typecode") != "2":
                continue
            if district not in f'{r.get("sido") or ""} {r.get("district") or ""}':
                continue
            for c in r.get("candidates") or []:
                if c.get("name") == candidate:
                    return c.get("votes") or 0
    return 0


def name_votes(date: str, party: str) -> int:
    """그 선거일의 지역구(tc2) 전체에서 그 정당명의 득표 합.

    후보가 여럿이라 (선거구, 후보) 하나로는 못 재는 경우가 있다 — 1948년 민중당이
    그렇다. 비례가 없던 시절이라 비례 지문도 못 쓴다.
    """
    total = 0
    for fp in sorted(_RES.glob("*.json")):
        if ".sigungu" in fp.name:
            continue
        try:
            doc = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        if (doc.get("_meta") or {}).get("election_date") != date:
            continue
        for r in doc.get("races") or []:
            if r.get("sg_typecode") != "2" or r.get("scope") != "district":
                continue
            for c in r.get("candidates") or []:
                if c.get("party") == party:
                    total += c.get("votes") or 0
    return total


# name_fidelity를 먼저 읽는다 — 큐의 정식명이 그것과 어긋나면 안 된다.
_fid_by_key = {(c["election_date"], c["stored"]): c["official"]
               for c in json.loads((ROOT / "data/parties/name_fidelity.json")
                                   .read_text(encoding="utf-8"))["cases"]}

# ③-0 권위 문서의 수치가 실제와 맞는가
#
# docs/party-identity.md는 이 모델의 정본이다. 거기 적힌 수치가 낡으면 문서가
# 조용히 거짓말을 한다 — 이 저장소가 반복해서 겪은 '문장으로만 적어 두면 낡는다'
# 그대로다. 구조를 말하는 수치만 묶어 둔다(표 수치는 문서 안 날짜 기준).
_DOC = ROOT / "docs/party-identity.md"
if _DOC.exists():
    _t = _DOC.read_text(encoding="utf-8")
    _fid_all = json.loads((ROOT / "data/parties/name_fidelity.json")
                          .read_text(encoding="utf-8"))["cases"]
    _live = {
        "registry": len(reg),
        "observed": len(rows),
        "queue": len(hom["unresolved"]),
        "applied": sum(1 for c in _fid_all if c.get("status") == "applied"),
        "outside": len([r for r in rows if r.get("outside_registry_interval")]),
    }
    for _key, _pat in [("registry", r"\| registry \| 107종 \| \*\*(\d+)종\*\* \|"),
                       ("observed", r"\| observed \| 321종 \| (\d+)종 \|"),
                       ("queue", r"\| homonym 큐 \| 10종 \| (\d+)종 \|"),
                       ("applied", r"applied 11 · deferred 1 \| \*\*applied (\d+)"),
                       ("outside", r"\| \*\*(\d+)종 · [\d,]+표\*\* \|")]:
        _m = re.search(_pat, _t)
        ck(f"docs/party-identity.md의 {_key} 수치가 실제와 같다",
           _m is not None and int(_m.group(1)) == _live[_key],
           f"문서 {_m.group(1) if _m else '없음'} vs 실제 {_live[_key]}")

for _q in hom["unresolved"]:
    for _o in _q.get("occurrences") or []:
        # 해소 층이 이름을 옮긴 회차는 원자료에 다른 문자열이 적혀 있다
        if "district_total_votes" in _o:
            _actual = name_votes(_o["election_date"],
                                 _o.get("stored_as") or _q["name"])
            _want = _o["district_total_votes"]
        elif "district_votes" in _o:
            _actual = dist_votes(_o["election_date"], _o["district"].split()[-1],
                                 _o["candidate"])
            _want = _o["district_votes"]
        else:
            _actual = prop_votes(_o["election_date"],
                                 _o.get("stored_as") or _q["name"])
            _want = _o["proportional_votes"]
        ck(f'{_q["name"]} {_o["election"]}: 큐에 적은 득표가 원자료와 같다',
           _actual == _want, f'큐 {_want:,} vs 원자료 {_actual:,}')
    # 못 푼 이유를 적었으면 **무엇을 못 풀었는지**도 재현 가능해야 한다. blocked_by만
    # 있고 occurrence가 없으면 다음 사람이 처음부터 다시 찾아야 한다.
    if _q.get("blocked_by"):
        ck(f'{_q["name"]}: 막힌 건에 확인 가능한 occurrence가 있다',
           bool(_q.get("occurrences")))
    # ── 판정의 두 축이 섞이지 않는가 ──────────────────────────────────────
    # resolved_to 하나가 '그 회차 정식명'과 'registry 노드'를 같이 담고 있었다.
    # 그래서 registry에 없는 이름(한국기독당·기독사랑실천당…)이 노드 키인 척
    # 네 회차에 들어가 있었다. ended_by·name_fidelity·dissolved에 이은 네 번째다.
    for _o in _q.get("occurrences") or []:
        _node = _o.get("resolved_to")
        ck(f'{_q["name"]} {_o["election"]}: resolved_to는 registry 노드다',
           _node is None or _node in reg, f"{_node}가 registry에 없다")
        _off = _o.get("official_name")
        _k = (_o["election_date"], _o.get("stored_as") or _q["name"])
        _case = _fid_by_key.get(_k)
        if _off and _case:
            ck(f'{_q["name"]} {_o["election"]}: 정식명이 name_fidelity와 같다',
               _off == _case, f"큐 {_off} vs fidelity {_case}")
        if _o.get("status") == "confirmed":
            ck(f'{_q["name"]} {_o["election"]}: confirmed면 둘 중 하나는 채워져 있다',
               bool(_off or _node))
    _open = [o for o in (_q.get("occurrences") or []) if o.get("status") == "open"]
    if _open:
        ck(f'{_q["name"]}: 미해소 회차는 resolved_to를 비워 둔다',
           all(o.get("resolved_to") is None for o in _open),
           str([o["election"] for o in _open if o.get("resolved_to") is not None]))

# ③-3 정당명 충실도 기록이 원자료와 맞는가
#
# 우리가 저장한 문자열이 그 회차 정식명과 다른 사례들(대부분 NEC가 등록약칭을 준다).
# 판정 근거는 여기서도 **그 회차 비례 득표수**다 — 숫자가 어긋나면 판정을 다시 봐야 한다.
_fid = json.loads((ROOT / "data/parties/name_fidelity.json").read_text(encoding="utf-8"))
for _c in _fid["cases"]:
    _actual = prop_votes(_c["election_date"], _c["stored"])
    ck(f'{_c["election"]} {_c["stored"]}→{_c["official"]}: 득표가 원자료와 같다',
       _actual == _c["proportional_votes"],
       f'기록 {_c["proportional_votes"]:,} vs 원자료 {_actual:,}')
    ck(f'{_c["election"]} {_c["stored"]}: 저장 문자열과 정식명이 실제로 다르다',
       _c["stored"] != _c["official"])
ck("충실도 유형 어휘가 정의돼 있다",
   {c["type"] for c in _fid["cases"]} <= set(_fid["_types"]),
   str({c["type"] for c in _fid["cases"]} - set(_fid["_types"])))
# 조사 범위를 적어 두지 않으면 '여기 없으면 없다'로 읽힌다
ck("조사 범위가 적혀 있다", "지역구" in _fid["_scope"] and "총선 비례" in _fid["_scope"])
# 복구한 건은 목록에 남기지 않는다 — 남기면 "아직 그렇다"로 읽힌다
ck("덮어쓰기 사례가 목록에서 빠졌다", all(c["type"] != "pipeline_corruption" for c in _fid["cases"]))
ck("어디로 갔는지는 적어 둔다", "known_homonyms" in _fid.get("_recovered", ""))

# ③-4 registry 링크가 생존 구간을 벗어나면 **그 사실이 적혀 있어야 한다**
#
# 이름이 같다고 그 정당인 게 아니다. 한나라당 관측은 1997~2026인데 노드는 2012-02에
# 끝난다 — 2016·2024·2026의 한나라당은 이름을 다시 쓴 다른 정당이다. 링크를 끊지는
# 않는다(1997~2012 관측은 맞으니까). 대신 **어긋난다는 사실을 계산으로** 붙인다.
_mismatch = []
for r in rows:
    _node = reg.get(r.get("registry_id") or "")
    if not _node:
        ck(f'{r["name"]}: 링크가 없으면 구간 표시도 없다', not r.get("outside_registry_interval"))
        continue
    # 연도만 적힌 경계는 아래를 1월, 위를 12월로 채운다 — 그냥 문자열로 비교하면
    # "1988-04" > "1988"이 참이 되어 없는 어긋남이 생긴다
    _f = (_node.get("founded") or "")[:7]
    _d = (_node.get("dissolved") or "9999-99")[:7]
    _f = _f if len(_f) >= 7 else (_f + "-01" if _f else "")
    _d = _d if len(_d) >= 7 else (_d + "-12" if _d else "")
    _out = bool(_f) and (r["first"][:7] < _f or r["last"][:7] > _d)
    ck(f'{r["name"]}: 구간 표시가 실제 계산과 일치',
       _out == bool(r.get("outside_registry_interval")),
       f'계산 {_out} vs 기록 {bool(r.get("outside_registry_interval"))}')
    if _out:
        _mismatch.append(r["name"])
        ck(f'{r["name"]}: 구간 값이 적혀 있다',
           r["outside_registry_interval"].get("node_span") == f"{_f}~{_d}")
ck(f"구간 밖 링크가 드러나 있다 ({len(_mismatch)}종)", bool(_mismatch))

# ③-5 소급 당적이 canonical identity를 오염시키지 않는가
#
# 출처가 나중 당적을 과거 기록에 소급 적용한 경우가 있다. NEC 당선인명부는 1980-08-27
# 11대 대선(통일주체국민회의 간선) 전두환의 소속을 민주정의당으로 적는데, 그 당은
# 1981-01 창당이다. **원자료는 고치지 않는다** — 출처가 그렇게 기록한 것이 사실이고,
# 이 anomaly를 소비하는 기능도 아직 없다. 대신 **늘어나지 않는지**만 지킨다.
#
# 이 검사가 지키는 진짜 대상은 해소 층이다. 해소를 안 태우면 1967·1971년 '정의당'
# 439행이 2012년 정의당으로 붙는다 — 3건이 439건이 되는 것을 여기서 잡는다.
sys.path.insert(0, str(ROOT / "scripts/build"))
from party_canon import disambiguate_party as _dp  # noqa: E402

KNOWN_ANACHRONISTIC = {
    ("1948-05-10", "대한청년단"),   # 결성 1948-12 — 제헌 총선보다 뒤
    ("1948-05-10", "민중당"),       # registry 민중당은 1965-06 (1948 것은 별개 정당)
    ("1980-08-27", "민주정의당"),   # 창당 1981-01 — 11대 대선 당시엔 없던 당
}
_found = set()
for _fp in sorted(_RES.glob("*.json")):
    if ".sigungu" in _fp.name:
        continue
    try:
        _doc = json.loads(_fp.read_text(encoding="utf-8"))
    except Exception:                                            # noqa: BLE001
        continue
    _dt = (_doc.get("_meta") or {}).get("election_date") or ""
    if not _dt:
        continue
    for _r in _doc.get("races") or []:
        for _c in _r.get("candidates") or []:
            _p = _dp(_c.get("party"), _dt)          # **해소 층을 태운 뒤** 본다
            _n = reg.get(_p or "")
            if not _n:
                continue
            _f = (_n.get("founded") or "")[:7]
            _f = _f if len(_f) >= 7 else (_f + "-01" if _f else "")
            if _f and _dt[:7] < _f:
                _found.add((_dt, _p))
ck(f"소급 당적이 알려진 것뿐이다 ({len(_found)}건)", _found == KNOWN_ANACHRONISTIC,
   f"새로 생김 {sorted(_found - KNOWN_ANACHRONISTIC)} · 사라짐 {sorted(KNOWN_ANACHRONISTIC - _found)}")

# ④ 이름을 재사용한 정당은 **시점으로 갈라져야 한다**
#
# disambiguate_party는 registry의 시기 노드 범위(founded~dissolved)로 가른다. 어느
# 범위에도 안 걸리면 조용히 **베이스 이름 그대로** 남는데, 그게 최신 노드로 흘러든다.
# 실제로 그랬다: 정의당(1967)의 dissolved가 1970으로 잘못 적혀 있어 1971년 7대 대선
# 진복기(정의당) 122,914표가 2012년 심상정 정의당 몫으로 붙어 있었다.
#
# 그래서 '이름'이 아니라 **시점 경계**를 검사한다. 관측 구간이 그 이름의 시기 노드
# 범위 안에 들어와야 한다.
sys.path.insert(0, str(ROOT / "scripts/build"))
from party_canon import _BASE_ERAS, _REUSED_BASES, disambiguate_party  # noqa: E402

_by_name = {r["name"]: r for r in rows}
_j = _by_name.get("정의당")
ck("현대 정의당 관측이 2012-10 이후에서 시작한다",
   bool(_j) and _j["first"][:7] >= "2012-10", _j and _j["first"])
ck("1971년 정의당은 정의당(1967)로 간다",
   disambiguate_party("정의당", "1971-04-27") == "정의당(1967)",
   disambiguate_party("정의당", "1971-04-27"))
ck("정의당(1967) 범위가 그 시절 관측을 덮는다",
   bool(_by_name.get("정의당(1967)"))
   and _by_name["정의당(1967)"]["last"][:7] <= (reg["정의당(1967)"].get("dissolved") or ""),
   str(_by_name.get("정의당(1967)")))

# 같은 구멍이 남은 이름들 — **막지는 않되 보이게 둔다.** 여기 있는 것은 시기 노드
# 범위 밖 관측이 섞여 있다는 뜻이고, 정의당과 같은 방식(1차 자료로 경계 확인)으로
# 하나씩 처리해야 한다. 수를 상한으로 막으면 발견이 억제된다.
_leak = []
for r in rows:
    if r["name"] not in _REUSED_BASES:
        continue
    spans = [(f, d) for nm, f, d in _BASE_ERAS[r["name"]] if nm == r["name"]]
    if not spans:
        continue
    f, d = spans[0]
    if r["first"][:7] < f or r["last"][:7] > d:
        _leak.append(f'{r["name"]}({r["first"][:7]}~{r["last"][:7]} vs {f}~{d})')
if _leak:
    print(f"\n  [다음 큐] 시기 노드 범위 밖 관측이 섞인 이름 {len(_leak)}종")
    for x in _leak:
        print(f"    · {x}")

# ⑤ 원자료에 **우리 표기**가 들어가지 않았는가
#
# registry 캐노니컬 이름은 우리가 만든 것이다. NEC는 '민주당(1955)' 같은 이름을 주지
# 않는다. 그게 data/results에 있다면 정규화가 원자료를 덮어썼다는 뜻이고, 실제로
# 4,796행이 그랬다(f87861d37). 덮어쓰면 두 가지를 잃는다:
#   · 나중에 시기 경계를 고쳐도 저장된 값은 안 따라온다 (2013 재보궐이 그래서 틀려 있었다)
#   · 서로 다른 정당이 한 이름으로 합쳐지면 되돌릴 수 없다 (2016 민주당)
# 시기 분기는 **읽는 시점에** 한다. 원자료는 NEC가 준 그대로 둔다.
import re as _re  # noqa: E402

_ours = []
for _fp in sorted(_RES.glob("*.json")):
    try:
        _doc = json.loads(_fp.read_text(encoding="utf-8"))
    except Exception:                                            # noqa: BLE001
        continue
    for _r in _doc.get("races") or []:
        for _c in _r.get("candidates") or []:
            if _re.search(r"\(\d{4}\)$", _c.get("party") or ""):
                _ours.append(f'{_fp.name}:{_c["party"]}')
ck(f"원자료에 캐노니컬 표기가 없다 ({len(_ours)}건)", not _ours, str(_ours[:3]))

print(f"\n[관측 정당 층] 실패 {len(fails)}")
sys.exit(1 if fails else 0)
