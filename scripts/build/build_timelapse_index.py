"""회차별 지도 프레임 목록 → data/election_timelapse.json (timeline.html 재생용).

**새로 그리는 그림이 없다.** 이미 찍어 둔 og/maps/{회차}/{키}.png를 연도순으로
엮기만 한다. 대선·총선·지선 세 레인이 같은 연도축을 따라 함께 흐른다 — 한 계열만
보면 '같은 시기에 어땠나'가 안 보인다.

⚠️ **간선을 건너뛰지 않는다.** 유신 시기 대선 6회를 빼면 그 시기에 선거가 없었던
것처럼 보인다. 지역별 결과가 없으니 지도 대신 선거인단 점그리드(electors.png)를
쓰고, 그게 다른 그림이라고 라벨에 적는다. 4대 대선(1960-08 국회 양원합동회의)은
전국 1행뿐이라 그림 자체가 없다 — 그것도 자리를 남기고 '그림 없음'이라 적는다.
없는 것을 없다고 말하는 것과 아예 지우는 것은 다르다(docs/absence.md).

사용: python3 scripts/build/build_timelapse_index.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import result_tables as _rt  # noqa: E402

OUT = ROOT / "data" / "election_timelapse.json"
# 계열 → (레인 이름, 쓸 그림 키 우선순위, 그림이 뜻하는 것)
LANES = [
    ("presidential", "대선", ["sido-hex", "electors"], "시도별 1위 후보"),
    ("general_election", "총선", ["sidoseat-hex"], "시도별 지역구 의석"),
    ("local", "지선", ["gov-hex"], "광역단체장 1위"),
]


def main() -> int:
    mf = json.loads((ROOT / "data/map_manifest.json").read_text(encoding="utf-8"))["elections"]
    ai = {e["slug"]: e for e in json.loads(
        (ROOT / "data/archive_index.json").read_text(encoding="utf-8"))}
    lanes = []
    for kind, name, keys, means in LANES:
        frames = []
        rows = sorted(((s, e) for s, e in mf.items() if e.get("kind") == kind),
                      key=lambda x: (ai.get(x[0], {}).get("date") or ""))
        for slug, e in rows:
            meta = ai.get(slug) or {}
            date_s = meta.get("date") or ""
            if not date_s:
                continue
            views = e.get("views") or []
            key = next((k for k in keys if k in views), None)
            f = {
                "slug": slug, "date": date_s, "name": meta.get("name") or slug,
                "img": f"/og/maps/{slug}/{key}.png" if key else None,
                "key": key,
            }
            if key:
                wh = _rt.png_size(ROOT / "og" / "maps" / slug / f"{key}.png")
                if wh:
                    f["w"], f["h"] = wh
            # 지도가 아닌 그림·그림 없음은 **말로 밝힌다**. 조용히 건너뛰면 그 시기에
            # 선거가 없었던 것처럼 보인다.
            if key == "electors":
                f["note"] = "간선 — 지역별 결과 없음(선거인단)"
            elif not key:
                f["note"] = "간선 — 그림 없음"
            frames.append(f)
        lanes.append({"kind": kind, "name": name, "means": means, "frames": frames})

    years = sorted({f["date"][:4] for L in lanes for f in L["frames"]})
    OUT.write_text(json.dumps({
        "_note": "빌드 생성물 — scripts/build/build_timelapse_index.py. timeline.html의 "
                 "세 레인 재생이 읽는다. 그림은 새로 안 만든다 — og/maps/에 이미 있는 "
                 "것을 연도순으로 엮을 뿐이다. img가 null이면 그림이 없는 회차이고, "
                 "note가 그 이유를 적는다(간선 등).",
        "years": [years[0], years[-1]] if years else [],
        "lanes": lanes,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tot = sum(len(L["frames"]) for L in lanes)
    hole = sum(1 for L in lanes for f in L["frames"] if not f["img"])
    alt = sum(1 for L in lanes for f in L["frames"] if f.get("key") == "electors")
    print(f"→ {OUT.relative_to(ROOT)}: 레인 {len(lanes)} · 프레임 {tot} "
          f"(지도 아닌 것 {alt} · 그림 없음 {hole}) · {years[0]}~{years[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
