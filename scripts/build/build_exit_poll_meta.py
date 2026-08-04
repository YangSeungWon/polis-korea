"""출구조사 파일에 _meta 요약 생성 — data/exit_polls/*.json.

출처·발표시각은 이미 sources[]에 있었다(name·released_at·quote_after, _legal_note).
없던 것은 그걸 화면이 쓰기 좋게 데이터셋 단위로 요약한 _meta다.

**is_final을 넣지 않는다.** 출구조사에 '확정'을 붙이면 사용자는 '이 결과가 확정됐다'로
읽는다. 실제 의미는 '방송사가 발표한 값이 더 안 바뀐다'일 뿐이고, 예측 자체는 확정 결과가
아니다. 확정/잠정은 선거 결과 데이터에만 적용한다 — docs/trust-states.md의 applicability
규칙 참고.

없는 값은 만들지 않는다. released_at이 비어 있는 회차(21대 대선·22대 총선)는
published_at 없이 나가고, 화면은 그 경우 발표 시각을 빼고 출처만 보인다.

사용: python3 scripts/build/build_exit_poll_meta.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "data/exit_polls"


def build_meta(doc: dict) -> dict:
    srcs = doc.get("sources") or []
    meta: dict = {
        "data_type": "exit_poll" if srcs else "exit_poll_demographics",
        "election_id": doc.get("id"),
        "election_date": doc.get("election_date"),
    }
    if srcs:
        meta["sources"] = [{"key": s.get("key"), "name": s.get("name")} for s in srcs]
        meta["n_sources"] = len(srcs)
        offices = [s.get("office") for s in srcs if s.get("office")]
        if offices:
            meta["offices"] = sorted(set(offices))
        rel = sorted(s["released_at"] for s in srcs if s.get("released_at"))
        if rel:
            meta["published_at"] = rel[0]
        qa = sorted(s["quote_after"] for s in srcs if s.get("quote_after"))
        if qa:
            meta["quote_after"] = qa[0]
    if doc.get("_legal_note"):
        meta["legal_note"] = doc["_legal_note"]
    # is_final은 의도적으로 없다 — 위 docstring 참고.
    return meta


def main():
    n = 0
    for fp in sorted(DIR.glob("*.json")):
        doc = json.loads(fp.read_text(encoding="utf-8"))
        meta = build_meta(doc)
        if doc.get("_meta") == meta:
            continue
        # _meta를 맨 앞에 오도록 재구성 (다른 데이터셋과 같은 순서)
        rest = {k: v for k, v in doc.items() if k != "_meta"}
        fp.write_text(json.dumps({"_meta": meta, **rest}, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
        n += 1
        pub = meta.get("published_at", "발표시각 없음")
        print(f"  {fp.name:<28} {meta['data_type']:<26} {pub}", file=sys.stderr)
    print(f"→ 갱신 {n}개", file=sys.stderr)


if __name__ == "__main__":
    main()
