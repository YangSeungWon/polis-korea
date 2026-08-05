"""비교 모델 불변조건 — data/comparisons/*.json.

비교 엔진은 화면보다 불변조건이 중요하다. 단위가 조용히 사라지거나 중복 매칭되면
'실제로 없던 변화'가 만들어지는데, 눈으로는 그럴듯해 보여서 안 잡힌다.

실행: python3 tests/test_comparison.py
"""
from __future__ import annotations
import glob
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECT = ("exact", "renamed")
REASON_CODES = {"merged_into", "sido_transferred", "boundary_reorganized",
                "new_unit", "abolished_unit"}
OUTCOMES = {"party_hold", "party_flip", "independent_to_independent"}

fails = []


def ck(name, cond, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}{' — ' + str(detail) if detail else ''}")
        fails.append(name)


def check_file(fp: Path):
    d = json.loads(fp.read_text(encoding="utf-8"))
    print(f"\n[{fp.name}]")
    for tc, o in (d.get("offices") or {}).items():
        n, label = o["counts"], o["label"]
        units, nc = o["units"], o["not_compared"]

        # 1. flip + hold + 무소속끼리 = 직접 비교 가능 수
        ck(f"{label}: 결과 분류 합 = 직접비교 수",
           n["party_flip"] + n["party_hold"] + n["independent_to_independent"]
           == n["direct_comparable"],
           f"{n['party_flip']}+{n['party_hold']}+{n['independent_to_independent']}"
           f" != {n['direct_comparable']}")

        # 2. 단위가 조용히 사라지지 않는다 — 양쪽 총수가 맞아야 한다
        ck(f"{label}: 이전 = 직접비교 + 이전 미매칭",
           n["direct_comparable"] + n["previous_unmatched"] == n["previous_units"])
        ck(f"{label}: 현재 = 직접비교 + 현재 미매칭",
           n["direct_comparable"] + n["current_unmatched"] == n["current_units"])

        # 3. units 배열 길이도 같은 수여야 한다(모델과 카운트 불일치 방지)
        ck(f"{label}: units 길이 = 직접비교 수", len(units) == n["direct_comparable"],
           f"{len(units)} != {n['direct_comparable']}")

        # 4. 1:1 매칭 — 어느 쪽에서도 중복으로 잡히지 않는다
        keys = [(u["sido"], u["unit"]) for u in units]
        ck(f"{label}: 매칭 단위 중복 없음", len(keys) == len(set(keys)))

        # 5. exact/renamed가 아니면 직접 delta를 만들지 않는다
        ck(f"{label}: 비교 단위는 전부 exact·renamed",
           all(u["match_type"] in DIRECT for u in units),
           sorted({u["match_type"] for u in units}))
        ck(f"{label}: 제외 단위에 직접 비교값 없음",
           all("margin_delta" not in x for x in nc))

        # 6. 모든 제외 단위에 사유 코드가 있다
        ck(f"{label}: 제외 사유 코드 존재·유효",
           all(x.get("reason_code") in REASON_CODES for x in nc),
           sorted({x.get("reason_code") for x in nc}))

        # 7. outcome 값이 정의된 것뿐
        ck(f"{label}: outcome 값 유효",
           all(u["outcome"] in OUTCOMES for u in units),
           sorted({u["outcome"] for u in units}))

        # 8. 비교분만 증감의 합은 0 — 같은 단위 집합에서 정당만 이동하므로
        ck(f"{label}: 비교분 증감 총합 0",
           sum(o["delta_compared_only"].values()) == 0,
           o["delta_compared_only"])

        # 9. 전체 증감 합 = 단위 수 변화 (통합·개편의 구조적 몫)
        ck(f"{label}: 전체 증감 합 = 단위 수 변화",
           sum(o["party_seats"]["delta"].values()) == n["current_units"] - n["previous_units"],
           f"{sum(o['party_seats']['delta'].values())} vs "
           f"{n['current_units'] - n['previous_units']}")

        # 10. 무소속끼리를 '유지'로 세지 않았다
        indep = [u for u in units
                 if u["prev_party"] == "무소속" and u["cur_party"] == "무소속"]
        ck(f"{label}: 무소속→무소속을 party_hold로 세지 않음",
           all(u["outcome"] == "independent_to_independent" for u in indep),
           f"{len(indep)}건")

    # 11. 투표율은 전국 단일 필드 — 지역 투표율과 섞지 않는다
    t = d.get("turnout") or {}
    ck("투표율: previous·current·delta만",
       set(t) <= {"previous", "current", "delta"}, sorted(t))
    if t.get("previous") is not None and t.get("current") is not None:
        ck("투표율: delta = current - previous",
           abs((t["current"] - t["previous"]) - t["delta"]) < 0.05)


def check_rename(ck):
    """개명은 정권 교체가 아니다.

    한나라당→새누리당(2012)·새정치민주연합→더불어민주당(2015)을 문자열로 비교하면
    '전부 정당 교체'가 된다. 실제로 6회 지선 광역단체장이 party_flip 16·hold 0으로
    찍히고 있었다 — 화면에는 '16곳 전부 정당이 바뀌었다'로 나간다. 명백한 오독이다.
    합당·분당은 이어 붙이지 않는다. 그건 정말로 정치적 변화다.
    """
    import sys as _s
    from pathlib import Path as _P
    _s.path.insert(0, str(_P(__file__).resolve().parents[1] / "scripts/build"))
    from build_comparison import same_party
    ck("개명은 같은 당 — 한나라당↔새누리당", same_party("한나라당", "새누리당"))
    ck("개명 사슬 2단계 — 새누리당↔자유한국당", same_party("새누리당", "자유한국당"))
    ck("개명은 같은 당 — 새정치민주연합↔더불어민주당",
       same_party("새정치민주연합", "더불어민주당"))
    ck("다른 당은 다르다 — 더불어민주당↔국민의힘",
       not same_party("더불어민주당", "국민의힘"))
    ck("합당은 잇지 않는다 — 한나라당↔민주당(2008)",
       not same_party("한나라당", "민주당(2008)"))
    ck("빈 값은 같다고 하지 않는다", not same_party("", ""))

    # 실데이터 — 개명이 걸린 회차에서 hold가 0이면 보정이 안 된 것이다.
    import json
    from pathlib import Path
    fp = Path(__file__).resolve().parents[1] / "data/comparisons/6th-local-2014__5th-local-2010.json"
    if fp.exists():
        c = json.loads(fp.read_text(encoding="utf-8"))["offices"]["3"]["counts"]
        ck(f"6회 지선 광역단체장 유지 {c['party_hold']}곳 (개명 보정 전엔 0이었다)",
           c["party_hold"] > 0, str(c))


def main():
    files = sorted(glob.glob(str(ROOT / "data/comparisons/*.json")))
    if not files:
        print("비교 파일 없음 — skip")
        return 0
    for f in files:
        check_file(Path(f))
    check_rename(ck)
    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
