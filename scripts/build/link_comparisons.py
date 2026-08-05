"""생성된 비교 파일을 회차 메타에 연결한다 — archive에서 '지난 회차 대비'가 뜨도록.

data/comparisons/{현재}__{직전}.json 이 있어도 data/elections/{현재}.json 의
archive.compare_previous 가 비어 있으면 화면에 아무것도 안 나온다. 예전엔 이 값을
손으로 4개만 적어 뒀고, 비교를 21쌍으로 늘려도 화면은 그대로였다.

생성물에서 역으로 채운다 — 비교 파일이 있으면 링크가 있고, 없으면 없다.
손으로 관리하면 둘이 어긋나고, 어긋난 쪽은 조용하다.

사용: python3 scripts/build/link_comparisons.py [--check]
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CMP_DIR = ROOT / "data/comparisons"
ELECTIONS = ROOT / "data/elections"


def pairs() -> dict:
    """현재 회차 → 직전 회차. 같은 현재에 여러 개면 가장 최근 것(사전순 최대)."""
    out = {}
    for fp in sorted(CMP_DIR.glob("*__*.json")):
        cur, prev = fp.stem.split("__", 1)
        out[cur] = prev
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="쓰지 않고 어긋난 것만 보고")
    args = ap.parse_args()

    linked = stale = missing = 0
    drift = []
    for cur, prev in sorted(pairs().items()):
        fp = ELECTIONS / f"{cur}.json"
        if not fp.exists():
            missing += 1
            drift.append(f"{cur}: 회차 메타 없음")
            continue
        d = json.loads(fp.read_text(encoding="utf-8"))
        ar = d.setdefault("archive", {})
        if ar.get("compare_previous") == prev:
            linked += 1
            continue
        drift.append(f"{cur}: {ar.get('compare_previous') or '(없음)'} → {prev}")
        stale += 1
        if not args.check:
            ar["compare_previous"] = prev
            fp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 반대 방향 — 링크는 있는데 비교 파일이 없는 경우(삭제·이름 변경)
    orphan = []
    for fp in sorted(ELECTIONS.glob("*.json")):
        if fp.name == "index.json":     # 회차가 아니라 목록 파일
            continue
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        p = (d.get("archive") or {}).get("compare_previous")
        if p and not (CMP_DIR / f"{fp.stem}__{p}.json").exists():
            orphan.append(f"{fp.stem} → {p} (비교 파일 없음)")
            if not args.check:
                d["archive"].pop("compare_previous", None)
                fp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    verb = "어긋남" if args.check else "연결"
    print(f"→ 이미 연결 {linked} · {verb} {stale} · 끊긴 링크 {len(orphan)} · 메타 없음 {missing}",
          file=sys.stderr)
    for x in (drift + orphan)[:12]:
        print(f"    {x}", file=sys.stderr)
    if args.check and (drift or orphan):
        print("\n✗ 비교 파일과 회차 메타가 어긋났다 — link_comparisons.py를 돌릴 것",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
