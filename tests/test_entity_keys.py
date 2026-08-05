"""이름 ≠ identity — entity 키에 namespace·상위·시점이 들어 있는가.

같은 함정을 세 번 밟았다.

  정당    '민중당'은 1965년 것과 2017년 것이 다른 당인데 한 덩어리로 세어졌다.
          2020년에 등록한 군소 '한나라당'이 1997년 한나라당 계보로 묶여, 198개
          지역구에서 2016년 새누리당 득표가 '한나라당'으로 표시됐다.
  지역    시도 개명(강원도→강원특별자치도)으로 slug가 갈라졌다.
  선거구  '남구'는 부산·대구·인천·광주·울산에 다 있다. 시군구 하나씩 돌릴 땐 안
          보이다가 전국 실행에서 254곳이 244곳으로 줄어드는 걸로 드러났다 —
          다른 선거구의 표가 한 덩어리로 합쳐지고 있었다.

세 번 반복됐으면 취향이 아니라 규칙이다.

    entity 키 = namespace + 상위(부모) + 시점       화면에 쓰는 이름은 따로.

이 검사는 **키가 이름 단독인 곳**을 찾는다. 표시용 이름은 대상이 아니다.

실행: .venv/bin/python tests/test_entity_keys.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fails: list[str] = []

SIDO = ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기",
        "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주")
# 시도가 여럿에 걸치는 이름 — 이것만으로 키를 잡으면 반드시 충돌한다
AMBIGUOUS = {"남구", "북구", "동구", "서구", "중구", "중원구", "덕진구"}


def ck(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    print("\n[선거구] 키에 시도가 들어 있는가")
    for f in sorted((ROOT / "data/reaggregated").glob("*.json")):
        if f.name.startswith("validation_"):
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        keys = list(d["districts"])
        bare = [k for k in keys if not k.split(" ")[0] in SIDO]
        ck(f"{f.stem}: 모든 키가 '시도 선거구'", not bare, str(bare[:4]))
        clash = [k for k in keys if k.split(" ", 1)[-1] in AMBIGUOUS]
        # 충돌 이름이 있으면 시도가 붙어 있어야 서로 구별된다
        ck(f"{f.stem}: 동명 선거구가 구별된다 ({len(clash)}곳)",
           len(clash) == len(set(clash)))

    lin = ROOT / "data/district_lineage/22__21.json"
    if lin.exists():
        d = json.loads(lin.read_text(encoding="utf-8"))
        ks = [u["district"] for u in d["units"]]
        ck("계보: 선거구 키가 유일하다", len(ks) == len(set(ks)),
           str([k for k in ks if ks.count(k) > 1][:3]))
        ck("계보: 키에 시도가 있다", all(k.split(" ")[0] in SIDO for k in ks),
           str([k for k in ks if k.split(" ")[0] not in SIDO][:3]))
        # 시도를 떼면 실제로 충돌한다는 것 — 규칙이 필요한 이유가 데이터에 있다
        bare = [k.split(" ", 1)[-1] for k in ks]
        dup = {b for b in bare if bare.count(b) > 1}
        ck(f"시도를 떼면 충돌이 생긴다 ({len(dup)}종) — 규칙의 근거",
           len(dup) > 0, "충돌이 없으면 이 검사의 전제를 다시 봐야 한다")

    print("\n[읍면동] 동 키에 시군구가 있는가")
    mem = sorted((ROOT / "data/geography/dong_membership").glob("*.json"))
    for f in mem[:4]:
        d = json.loads(f.read_text(encoding="utf-8"))
        ks = list(d["membership"])
        ck(f"{f.stem}: 동 키가 '시군구코드:이름'",
           all(":" in k for k in ks), str([k for k in ks if ":" not in k][:3]))
    # 규칙의 근거는 데이터에 있어야 한다. 전국 파일에서 실제로 충돌하는지 센다 —
    # 무조건 통과하는 검사는 검사가 없는 것보다 나쁘다.
    nat = [f for f in mem if f.stem.endswith("_all")]
    if nat:
        d = json.loads(nat[0].read_text(encoding="utf-8"))
        bare = [k.split(":", 1)[-1] for k in d["membership"]]
        dup = {b for b in bare if bare.count(b) > 1}
        ck(f"시군구를 떼면 동 이름이 충돌한다 ({len(dup)}종) — 규칙의 근거",
           len(dup) > 50, f"{len(dup)}종 — 충돌이 없으면 이 검사의 전제를 다시 봐야 한다")
    else:
        ck("전국 동 membership 파일이 있다", False, "regen 필요")

    print("\n[지리 entity] id에 namespace와 시점이 있는가")
    ev = ROOT / "data/geography/events.json"
    if ev.exists():
        d = json.loads(ev.read_text(encoding="utf-8"))
        ids = [x["id"] for e in d["events"] for x in (e.get("to") or []) + (e.get("from") or [])]
        ck("entity id에 namespace(kind:)가 있다",
           all(":" in i for i in ids), str([i for i in ids if ":" not in i][:3]))
        ed = [i for i in ids if i.startswith("electoral_district:")]
        # 선거구는 회차마다 다른 entity다 — 21대 부천시갑과 22대 부천시갑은 다른 영역이다
        ck("선거구 id에 회차가 있다",
           all(re.match(r"electoral_district:\d+:", i) for i in ed),
           str([i for i in ed if not re.match(r"electoral_district:\d+:", i)][:3]))
        ck("선거구 id에 시도가 있다",
           all(len(i.split(":")) >= 4 for i in ed))
        au = [i for i in ids if i.startswith("admin_unit:")]
        ck("행정구역 id에 상위(시도)가 있다",
           all(len(i.split(":")) >= 3 for i in au), str(au[:3]))

    print("\n[정당] 비교 키가 이름이 아니라 identity인가")
    sys.path.insert(0, str(ROOT / "scripts/build"))
    import party_identity as PI
    ck("동명 다른 당이 갈린다 (민중당 1965 ↔ 2017)",
       PI.identity("민중당", "1967-06-08") != PI.identity("민중당", "2020-04-15"))
    ck("개명은 이어진다 (미래통합당 → 국민의힘)",
       PI.identity("미래통합당", "2020-04-15") == PI.identity("국민의힘", "2024-04-10"))
    ck("흡수는 이어지지 않는다 (국민의당2020 ↛ 국민의힘)",
       PI.identity("국민의당(2020)", "2020-04-15")
       != PI.identity("국민의힘", "2024-04-10"))
    ck("identity_id는 표시용이 아니다 (pid: 접두)",
       PI.identity("국민의힘", "2024-04-10").startswith("pid:"))
    for f in sorted((ROOT / "data/reaggregated").glob("*.json")):
        if f.name.startswith("validation_"):
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        for k, v in d["districts"].items():
            for blk in ("attributable", "prev_reaggregated"):
                sh = (v.get(blk) or {}).get("share") or {}
                bad = [p for p in sh if not (p.startswith("pid:") or p == "무소속")]
                if bad:
                    ck(f"{f.stem}/{k}: {blk} 키가 identity", False, str(bad[:3]))
                    break
    ck("재집계 산출의 정당 키가 전부 identity", True)

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
