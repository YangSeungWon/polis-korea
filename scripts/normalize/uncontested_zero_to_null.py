"""무투표 당선의 0을 null로 — '0표를 얻었다'와 '투표가 없었다'는 다르다.

## 왜

무투표 당선은 **선거를 치르지 않은 것**이다. 그런데 우리 데이터는 같은 사실을 두
가지로 적고 있었다:

    무투표 후보 1,038명 중  votes: 0 이 691명 · votes: null 이 347명
    무투표 race   817개 중  valid_votes 등이 0 인 것 265개 · null 265→552개

한 파일 안에서도 섞여 있었다(8회 지선 시군구: 0이 106명, null이 80명). 0은
'0표를 얻었다'는 **거짓 진술**이고 null이 '투표가 없었다'는 참이다. 실제로 같은
레코드의 `pct`는 이미 null이었다 — 두 필드가 같은 사실을 다르게 말하고 있었다.

이건 이 저장소가 반복해서 겪은 것과 같다: 0·빈값·오늘 같은 **그럴듯한 기본값**이
'모른다/없다'를 덮어써서, 틀렸는데도 아무도 못 본다.

## 안 하는 것

무투표가 아닌 race의 0표는 건드리지 않는다. 제헌 총선에는 실제로 0표를 얻은
후보가 있다(득표 없이 등록만 한 경우). 그건 사실이다.

사용: python3 scripts/normalize/uncontested_zero_to_null.py [--write]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data/results"
RACE_KEYS = ("electors", "voters", "valid_votes", "invalid_votes")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    n_cand = n_race = n_file = 0
    for fp in sorted(RESULTS.glob("*.json")):
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        touched = False
        for r in d.get("races") or []:
            cs = r.get("candidates") or []
            race_unc = bool(r.get("is_uncontested"))
            if not race_unc and not (cs and all(c.get("uncontested") for c in cs)):
                # race 전체가 무투표가 아니면 **후보 단위 플래그만** 본다
                for c in cs:
                    if c.get("uncontested") and c.get("votes") == 0:
                        c["votes"] = None
                        n_cand += 1
                        touched = True
                continue
            for c in cs:
                if c.get("votes") == 0:
                    c["votes"] = None
                    n_cand += 1
                    touched = True
            for k in RACE_KEYS:
                if r.get(k) == 0:
                    r[k] = None
                    n_race += 1
                    touched = True
        if touched:
            n_file += 1
            if a.write:
                fp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    print(f"무투표 0 → null · 후보 {n_cand} · race 필드 {n_race} · 파일 {n_file}"
          + ("" if a.write else "  (--write 없이 실행 — 저장하지 않음)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
