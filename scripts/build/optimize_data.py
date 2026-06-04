"""브라우저가 fetch하는 JSON 최적화 — 페이지 로딩 무게 감소. (빌드 마지막 단계, 멱등)

1. national_assembly_*.json 의 sigungu(비례 시군구 득표) 분리 → *_sigungu.json.
   history는 총선을 항상 지역구 hex로 그려 sigungu를 안 쓴다(죽은 무게). 데이터는 보존하되 안 받게.
2. geo *_simple.json 좌표 6자리 절삭 (14자리 → 6자리, ~0.1m 정밀도. 지도 영향 0).
3. fetch 대상 JSON minify (indent 제거). 사람이 편집하는 config(elections/sources)는 제외.

사용: .venv/bin/python scripts/build/optimize_data.py
"""
from __future__ import annotations
import glob
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPACT = dict(ensure_ascii=False, separators=(",", ":"))
# minify·절삭 제외 (사람이 편집, fetch돼도 작음)
KEEP_PRETTY = {"elections.json", "sources.json"}


def dump_min(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, **COMPACT), encoding="utf-8")


def round_coords(obj, nd=6):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, list):
        return [round_coords(x, nd) for x in obj]
    if isinstance(obj, dict):
        return {k: round_coords(v, nd) for k, v in obj.items()}
    return obj


def main():
    before = sum(os.path.getsize(f) for pat in ("data/results/*.json", "data/geo/*.json", "data/polls/*.json")
                 for f in glob.glob(str(ROOT / pat)))

    # 1. national_assembly sigungu 분리
    split = 0
    for f in glob.glob(str(ROOT / "data/results/national_assembly_*.json")):
        if f.endswith("_sigungu.json"):
            continue
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        if d.get("sigungu"):
            side = Path(f.replace(".json", "_sigungu.json"))
            dump_min(side, {"_meta": d.get("_meta", {}), "sigungu": d["sigungu"]})
            d.pop("sigungu")
            dump_min(Path(f), d)
            split += 1
    print(f"1. sigungu 분리: {split}개 회차 → *_sigungu.json")

    # 2. geo *_simple 좌표 절삭 (minify는 3에서)
    for f in glob.glob(str(ROOT / "data/geo/*_simple.json")):
        d = round_coords(json.loads(Path(f).read_text(encoding="utf-8")), 6)
        dump_min(Path(f), d)
    print("2. geo *_simple 좌표 6자리 절삭")

    # 3. fetch 대상 minify (config 제외)
    n = 0
    for pat in ("data/results/*.json", "data/geo/*.json", "data/polls/*.json"):
        for f in glob.glob(str(ROOT / pat)):
            if Path(f).name in KEEP_PRETTY:
                continue
            dump_min(Path(f), json.loads(Path(f).read_text(encoding="utf-8")))
            n += 1
    print(f"3. minify: {n}개 파일")

    after = sum(os.path.getsize(f) for pat in ("data/results/*.json", "data/geo/*.json", "data/polls/*.json")
                for f in glob.glob(str(ROOT / pat)))
    print(f"\n총 {before // 1024}KB → {after // 1024}KB ({100 * (before - after) // before}% 감소)")


if __name__ == "__main__":
    main()
