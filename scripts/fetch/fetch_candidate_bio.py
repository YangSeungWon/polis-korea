"""NEC 후보자 통합검색 API로 후보 생년월일·한자명 수집 (동명이인 분리용).

CndaSrchService/getCndaSrchInqire 는 이름으로 조회 시 후보별
birthday·hanjaName·huboid·sgId·sgggName·jdName 등을 반환한다(당락 무관·비국회의원 포함).
이름만으로 묶이던 동명이인(김선동 보수/진보, 이수진 7명, 김종규 6명…)을
(이름+생년월일)로 정확히 가르기 위한 데이터.

입력: assets/person-index.json 의 인물 이름 (기본 2회+ 출마자, --all 로 전체)
출력: data/raw/nec_candidate_bio.json  (resumable — 이미 받은 이름은 건너뜀)
  { "_done": ["이름", ...],
    "records": [ {"name","hanja","birthday","huboid","sgId","tc","sd","sgg","jd"} , ... ] }

키: 환경변수 NEC_KEY 또는 --key. 사용:
  NEC_KEY=... python3 scripts/fetch/fetch_candidate_bio.py [--all] [--limit N]
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PI = ROOT / "assets/person-index.json"
OUT = ROOT / "data/raw/nec_candidate_bio.json"
API = "https://apis.data.go.kr/9760000/CndaSrchService/getCndaSrchInqire"


def load_cache():
    if OUT.exists():
        d = json.loads(OUT.read_text(encoding="utf-8"))
        return set(d.get("_done", [])), d.get("records", [])
    return set(), []


def save_cache(done, records):
    OUT.write_text(json.dumps({"_done": sorted(done), "records": records},
                              ensure_ascii=False), encoding="utf-8")


def fetch_name(key, name):
    url = f"{API}?serviceKey={key}&name={urllib.parse.quote(name)}&pageNo=1&numOfRows=100"
    with urllib.request.urlopen(url, timeout=20) as r:
        x = r.read().decode("utf-8", "replace")
    if "INFO-03" in x:        # 데이터 없음(그 이름 후보 없음) — 정상, 빈 결과
        return []
    if "INFO-00" not in x and "NORMAL" not in x:   # 쿼터·키오류 등 진짜 오류
        raise RuntimeError(x[:200])
    out = []
    for it in ET.fromstring(x).iter("item"):
        g = lambda t: (it.findtext(t) or "").strip()
        out.append({"name": g("name"), "hanja": g("hanjaName"), "birthday": g("birthday"),
                    "huboid": g("huboid"), "sgId": g("sgId"), "tc": g("sgTypecode"),
                    "sd": g("sdName"), "sgg": g("sggName"), "jd": g("jdName")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default=os.environ.get("NEC_KEY", ""))
    ap.add_argument("--all", action="store_true", help="전체 이름(기본: 2회+ 출마자만)")
    ap.add_argument("--limit", type=int, default=0, help="이번 실행 최대 이름 수")
    args = ap.parse_args()
    if not args.key:
        sys.exit("NEC_KEY 환경변수 또는 --key 필요")

    persons = json.loads(PI.read_text(encoding="utf-8"))["persons"]
    if args.all:
        names = sorted({p["name"] for p in persons})
    else:
        names = sorted({p["name"] for p in persons if len(p.get("races", [])) >= 2})

    done, records = load_cache()
    todo = [n for n in names if n not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"대상 {len(names)}명 · 남은 {len(names)-len(done)} · 이번 {len(todo)}")

    n_err = 0
    for i, nm in enumerate(todo, 1):
        try:
            recs = fetch_name(args.key, nm)
            records.extend(recs)
            done.add(nm)
        except Exception as e:
            n_err += 1
            print(f"  ! {nm}: {e}", file=sys.stderr)
            if n_err >= 20:
                print("연속 오류 많음 — 중단(쿼터?)", file=sys.stderr)
                break
            time.sleep(2)
            continue
        if i % 50 == 0:
            save_cache(done, records)
            print(f"  {i}/{len(todo)} (records {len(records)})")
        time.sleep(0.12)
    save_cache(done, records)
    print(f"완료: done {len(done)} · records {len(records)} · err {n_err}")


if __name__ == "__main__":
    main()
