"""data/results/ 안 새 schema 파일들 → manifest.json 재생성.

각 kind별로 사용 가능한 회차 자동 추출. fetch_nec_results 후 호출하면
history.html이 새 회차 자동 인식.

사용:
  python3 scripts/build/rebuild_manifest.py
"""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data/results"

PATTERNS = {
    "presidential":      re.compile(r"^(\d+)(?:st|nd|rd|th)-pres-\d+\.json$"),
    "national_assembly": re.compile(r"^(\d+)(?:st|nd|rd|th)-general-\d+\.json$"),
    "local":             re.compile(r"^(\d+)(?:st|nd|rd|th)-local-\d+\.json$"),
}


def main():
    manifest = {k: [] for k in PATTERNS}
    for f in RESULTS.iterdir():
        if not f.is_file():
            continue
        for kind, pat in PATTERNS.items():
            m = pat.match(f.name)
            if m:
                # 빈 파일·candidates만 있는 patch 파일 제외
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                    if not d.get("races"):
                        break
                except Exception:
                    break
                manifest[kind].append(int(m.group(1)))
                break
    for k in manifest:
        manifest[k] = sorted(set(manifest[k]))
    out = RESULTS / "manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    print(f"→ {out.name}: {manifest}")


if __name__ == "__main__":
    main()
