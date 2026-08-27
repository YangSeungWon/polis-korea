"""회차별 지도 뷰 목록 → data/map_manifest.json. 이미지 파이프라인의 계약.

세 소비자가 같은 목록을 본다:
    페이지 생성기   어떤 <figure>를 낼지
    캡처 스크립트   무엇을 렌더할지
    검사           파일이 실제로 있는지

각자 디렉터리를 스캔하면 셋이 어긋난다 — 실제로 build_share_pages는 og/를,
build_og_maps는 archive/를 스캔해서 한쪽이 아는 뷰를 다른 쪽이 몰랐다.

⚠️ **뷰 목록은 관측이지 예측이 아니다.**
처음엔 race 모양(tc·scope·electors 유무)에서 어떤 뷰가 가능한지 추론하게 짰다가
양방향으로 틀렸다 — 있어야 한다고 한 10회차는 실제로 없어야 할 것이었고, 모른다고
한 46회차엔 파일이 있었다. 뷰를 정하는 조건은 render-sido-view.js의 modesFor 안에
있고, 그걸 파이썬으로 두 번째 구현하는 순간 두 모델이 어긋난다. 그래서 디스크에
있는 것을 적는다. 하네스가 생기면 하네스의 뷰 목록이 정본이 되고 여기가 받아 적는다.

**없는 것과 못 만든 것을 구분한다**(docs/absence.md):
    absent "재보궐 — …"     없는 게 맞다. 만들려 들지 말 것
    absent "캡처를 아직 …"   만들 수 있는데 안 만들었다

사용: python scripts/build/build_map_manifest.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from view_registry import primary_for  # noqa: E402
import result_tables as rt  # noqa: E402

OUT = ROOT / "data" / "map_manifest.json"
MAPS = ROOT / "og" / "maps"
CAPS = ROOT / "data" / "map_captures.json"


def captures() -> dict:
    """캡처가 적어 둔 라벨(회차 → 키 → {label,title,desc,w,h,page}).

    **디스크가 존재의 정본이고, 여기는 그 그림이 무엇인지의 정본이다.** 캡처가 누른
    버튼의 글씨와 섹션 제목을 그대로 들고 있어서, 페이지의 figcaption·alt가 여기서
    나온다 — 레지스트리에 한글 라벨을 손으로 적으면 그림과 어긋날 자리가 생긴다.
    """
    try:
        return json.loads(CAPS.read_text(encoding="utf-8"))["slugs"]
    except Exception:
        return {}


def absent_reason(kind: str, races: list) -> str | None:
    if kind == "byelection":
        return "재보궐 — 일부 선거구에서만 치렀다. 전국 지도가 없는 게 맞다."
    if {(r.get("sg_typecode"), r.get("scope")) for r in races} <= {("1", "nation")}:
        return "간선 — 선거인단이 뽑았다. 지역별 결과가 존재하지 않는다."
    return None


def main() -> int:
    # 정본은 **실제 존재하는 archive 페이지**다. archive_index.json은 재보궐 24개를
    # 빼고 53개만 들고 있어(elections.html 목록용), 그걸 기준으로 삼으면 재보궐이
    # 매니페스트에서 통째로 빠진다 — '없는 게 맞다'고 적을 자리조차 없어진다.
    kinds = {}
    for f in sorted((ROOT / "data/elections").glob("*.json")):
        if f.name == "index.json":
            continue
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if m.get("id"):
            kinds[m["id"]] = m.get("kind") or ""

    caps = captures()
    out: dict = {}
    for d in sorted((ROOT / "archive").iterdir()):
        if not (d / "index.html").is_file():
            continue
        eid, kind = d.name, kinds.get(d.name, "")
        reason = absent_reason(kind, rt.load_races(eid))
        views = sorted(f.stem for f in (MAPS / eid).glob("*.png")) \
            if (MAPS / eid).is_dir() else []
        meta = {k: v for k, v in (caps.get(eid) or {}).items() if k in views}
        # 디스크에 있는데 캡처 기록이 없는 그림은 **적어 둔다.** 조용히 넘기면
        # 라벨 없는 그림이 캡션 자리에 키 슬러그를 찍는다(옛 view_meta가 그랬다).
        unlabeled = [v for v in views if v not in meta]
        if reason and not views:
            out[eid] = {"kind": kind, "views": [], "absent": reason}
        elif not views:
            out[eid] = {"kind": kind, "views": [],
                        "absent": "캡처를 아직 안 돌렸다 — 없는 게 맞는 것과 다르다."}
        else:
            out[eid] = {"kind": kind, "views": views,
                        "primary": primary_for(kind, views), "meta": meta}
            if unlabeled:
                out[eid]["unlabeled"] = unlabeled

    OUT.write_text(json.dumps({
        "_note": "빌드 생성물 — scripts/build/build_map_manifest.py. "
                 "views는 디스크 관측이다. absent에 이유가 적혀 있으면 '없는 게 맞다'는 "
                 "뜻이고, '캡처를 아직'이면 만들 수 있는데 안 만든 것이다. "
                 "meta는 캡처가 적어 둔 라벨(data/map_captures.json)로, 페이지의 "
                 "figcaption·alt가 여기서 나온다. unlabeled는 그림은 있는데 그게 "
                 "무엇인지 아무도 모르는 경우다 — 있으면 안 된다.",
        "elections": dict(sorted(out.items())),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    have = sum(1 for v in out.values() if v["views"])
    right = sum(1 for v in out.values() if v.get("absent", "").startswith(("재보궐", "간선")))
    todo = sum(1 for v in out.values() if v.get("absent", "").startswith("캡처"))
    nolabel = sum(len(v.get("unlabeled") or []) for v in out.values())
    print(f"→ {OUT.relative_to(ROOT)}: {len(out)}회차 · 뷰 있음 {have} · "
          f"없는 게 맞음 {right} · 아직 안 만듦 {todo}"
          + (f" · ⚠️ 라벨 없는 그림 {nolabel}장" if nolabel else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
