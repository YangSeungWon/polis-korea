"""aggregated.json 품질 sanity check — 회귀 자동 검출.

7가지 검사:
  1. 시계열 outlier (같은 시도·office·후보 median±4*MAD)
  2. 메이저정당 4+ 후보 (적합도/경선 잔존)
  3. 정당명-as-후보 (parse 오류 잔존)
  4. 광역의원·기초의원 분류 false positive (NEC roster typecode 대조)
  5. 합계 의심 (<30% 또는 >110%)
  6. NEC roster 누락 의심 (≥3 PDF 등장 + 정당 일관 + 다른 race 후보들 등록)
  7. build_golden 회귀 (tests/test_build_golden.py 결과)

각 검사 결과 → severity (info/warn/error). 누적 카운트 출력 + JSON 저장
(data/audits/YYYY-MM-DD.json). 이전 audit과 diff로 신규 outlier alert.

사용:
  python3 scripts/audit_quality.py             # 전체 검사 + 저장
  python3 scripts/audit_quality.py --no-save   # 화면만 (CI 모드)
  python3 scripts/audit_quality.py --strict    # warn도 exit 1

exit code: 0 = clean, 1 = error 1+ (또는 strict 시 warn 1+).
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
AGG = ROOT / "data/polls/aggregated.json"
ROSTER = ROOT / "data/raw/nec_roster_9th.json"
AUDIT_DIR = ROOT / "data/audits"


MAJOR_PARTIES = {"더불어민주당", "국민의힘", "조국혁신당", "개혁신당", "진보당",
                 "정의당", "민주당"}
PARTY_AS_NAME = {"더불어", "민주당", "국민의힘", "조국혁신", "조국혁신당",
                 "개혁신당", "진보당", "무소속", "정의당"}


def check_outliers(polls: list, roster: dict) -> dict:
    """1. 시계열 outlier (Δ > max(15, 4*MAD)에 절대 15pp 이상)."""
    series = defaultdict(list)
    for p in polls:
        if p.get("is_pending"):
            continue
        if p["office_level"] not in ("광역단체장", "기초단체장", "교육감"):
            continue
        for c in p.get("candidates", []):
            n, pct = c.get("name"), c.get("pct")
            if not n or pct is None:
                continue
            series[(p.get("sido", ""), p.get("sigungu", ""), p["office_level"], n)].append(
                (p.get("period_end", ""), p["ntt_id"], pct))
    hits = []
    for key, samples in series.items():
        pcts = [s[2] for s in samples]
        if len(pcts) < 3:
            continue
        med = median(pcts)
        mad = median(abs(x - med) for x in pcts)
        if mad < 2.0:
            continue
        for ed, ntt, pct in samples:
            dev = abs(pct - med)
            if dev > max(15, 4 * mad):
                hits.append({
                    "ntt": ntt, "key": list(key), "pct": pct,
                    "median": round(med, 1), "mad": round(mad, 1),
                    "dev": round(dev, 1), "period_end": ed,
                })
    return {"name": "시계열 outlier", "severity": "warn" if hits else "info",
            "count": len(hits), "items": hits[:20]}


def check_party_inflate(polls: list) -> dict:
    """2. 메이저정당 4+ 후보 race (적합도/경선 잔존)."""
    hits = []
    for p in polls:
        if p.get("is_pending"):
            continue
        if p["office_level"] not in ("광역단체장", "기초단체장"):
            continue
        pc = Counter(c.get("party", "") for c in p.get("candidates", [])
                     if c.get("party") in MAJOR_PARTIES)
        for party, cnt in pc.items():
            if cnt >= 4:
                hits.append({
                    "ntt": p["ntt_id"], "office": p["office_level"],
                    "sido": p.get("sido", "")[:5], "sigungu": p.get("sigungu", ""),
                    "party": party, "count": cnt,
                })
                break
    return {"name": "메이저정당 4+ 후보 잔존", "severity": "error" if hits else "info",
            "count": len(hits), "items": hits[:15]}


def check_party_as_name(polls: list) -> dict:
    """3. 정당명-as-후보 (parse 오류)."""
    hits = []
    for p in polls:
        if p.get("is_pending"):
            continue
        bad = [c for c in p.get("candidates", []) if c.get("name") in PARTY_AS_NAME]
        if bad:
            hits.append({
                "ntt": p["ntt_id"], "office": p["office_level"],
                "sido": p.get("sido", "")[:5], "sigungu": p.get("sigungu", ""),
                "names": [c["name"] for c in bad],
            })
    return {"name": "정당명-as-후보", "severity": "error" if hits else "info",
            "count": len(hits), "items": hits[:15]}


def check_office_classification(polls: list, roster: dict) -> dict:
    """4. 광역/기초의원 분류 false positive (NEC typecode 단체장인데 의원 분류).
    또는 단체장 분류인데 typecode 의원."""
    hits = []
    expect_tc = {"광역단체장": "3", "기초단체장": "4", "교육감": "11",
                 "광역의원후보": "5", "기초의원후보": "6"}
    for p in polls:
        if p.get("is_pending"):
            continue
        ol = p["office_level"]
        if ol not in expect_tc:
            continue
        sido = p.get("sido", "")
        tcs = []
        for c in p.get("candidates", []):
            n = c.get("name", "")
            if not n:
                continue
            v = roster.get(f"{sido}|{n}")
            if isinstance(v, dict) and v.get("sg_typecode"):
                tcs.append(v["sg_typecode"])
        if not tcs:
            continue
        top_tc = Counter(tcs).most_common(1)[0][0]
        if top_tc != expect_tc[ol] and top_tc in expect_tc.values():
            hits.append({
                "ntt": p["ntt_id"], "office": ol,
                "sido": sido[:5], "sigungu": p.get("sigungu", ""),
                "expected_tc": expect_tc[ol], "actual_tc": top_tc,
                "title": p.get("table_title", "")[:30],
            })
    return {"name": "office 분류 false positive", "severity": "warn" if hits else "info",
            "count": len(hits), "items": hits[:15]}


def check_sum_sanity(polls: list) -> dict:
    """5. 합계 의심 (<30% 또는 >110%). 교육감 거론율 제외."""
    hits = []
    for p in polls:
        if p.get("is_pending"):
            continue
        if p["office_level"] not in ("광역단체장", "기초단체장"):
            continue
        s = sum(c.get("pct") or 0 for c in p.get("candidates", []) if c.get("pct") is not None)
        if s < 30 or s > 110:
            hits.append({
                "ntt": p["ntt_id"], "office": p["office_level"],
                "sido": p.get("sido", "")[:5], "sigungu": p.get("sigungu", ""),
                "sum": round(s, 1), "title": p.get("table_title", "")[:30],
            })
    return {"name": "합계 의심", "severity": "warn" if hits else "info",
            "count": len(hits), "items": hits[:15]}


def check_roster_gaps(polls: list, roster: dict) -> dict:
    """6. NEC roster 누락 의심 (≥3 PDF 등장 + 정당 일관 + race 다른 후보 등록률 ≥50%).
    빈 dict({})로 명시 비등록만. 거론 후보일 가능성 높지만 신규 등록 후보 가능성 알람."""
    by_cand = defaultdict(list)
    for p in polls:
        if p.get("is_pending"):
            continue
        if p["office_level"] not in ("광역단체장", "기초단체장"):
            continue
        sido = p.get("sido", "")
        cs = p.get("candidates", [])
        for c in cs:
            n, pty = c.get("name", ""), c.get("party", "")
            if not n or not pty:
                continue
            if not re.match(r"^[가-힣]{2,4}$", n):
                continue
            other = [cc.get("name", "") for cc in cs if cc.get("name") != n]
            by_cand[n].append((sido, pty, other))
    hits = []
    for name, entries in by_cand.items():
        if len(entries) < 3:
            continue
        sido = Counter(s for s, _, _ in entries).most_common(1)[0][0]
        v = roster.get(f"{sido}|{name}")
        if v != {}:
            continue
        # 다른 후보 등록률
        reg_n = tot_n = 0
        for s, _, other in entries:
            for on in other:
                tot_n += 1
                ov = roster.get(f"{s}|{on}")
                if isinstance(ov, dict) and ov.get("jd"):
                    reg_n += 1
        if tot_n > 0 and reg_n / tot_n < 0.5:
            continue
        pty = Counter(p for _, p, _ in entries).most_common(1)[0][0]
        hits.append({"name": name, "sido": sido[:5], "party": pty,
                     "n_pdf": len(entries),
                     "other_reg_ratio": f"{reg_n}/{tot_n}"})
    return {"name": "NEC roster 누락 의심", "severity": "info",
            "count": len(hits), "items": hits[:20]}


def check_build_golden() -> dict:
    """7. build_golden 회귀."""
    try:
        r = subprocess.run([sys.executable, str(ROOT / "tests/test_build_golden.py")],
                           capture_output=True, text=True, timeout=60)
        # 마지막 줄 "총 N cases: X pass, Y warn, Z fail"
        last = [ln for ln in r.stdout.split("\n") if ln.strip()][-1]
        m = re.search(r"(\d+)\s*pass,\s*(\d+)\s*warn,\s*(\d+)\s*fail", last)
        if m:
            n_pass, n_warn, n_fail = map(int, m.groups())
            return {"name": "build_golden 회귀", "severity": "error" if n_fail else "info",
                    "count": n_fail, "items": [last]}
        return {"name": "build_golden 회귀", "severity": "warn", "count": -1,
                "items": [last]}
    except Exception as e:
        return {"name": "build_golden 회귀", "severity": "error", "count": -1,
                "items": [str(e)]}


def diff_vs_prev(now: dict) -> list[str]:
    """이전 audit 파일과 카운트 diff. 신규 outlier 알림."""
    if not AUDIT_DIR.exists():
        return []
    prevs = sorted(AUDIT_DIR.glob("*.json"))
    if not prevs:
        return []
    prev = json.loads(prevs[-1].read_text(encoding="utf-8"))
    diffs = []
    for check in now["checks"]:
        prev_check = next((c for c in prev.get("checks", []) if c["name"] == check["name"]),
                          None)
        if prev_check is None:
            continue
        delta = check["count"] - prev_check["count"]
        if delta > 0:
            diffs.append(f"  +{delta} {check['name']} ({prev_check['count']}→{check['count']})")
        elif delta < 0:
            diffs.append(f"  {delta} {check['name']} ({prev_check['count']}→{check['count']})")
    return diffs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-save", action="store_true", help="audit JSON 저장 안 함")
    ap.add_argument("--strict", action="store_true", help="warn도 exit 1")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    polls = json.load(open(AGG, encoding="utf-8"))["polls"]
    roster = json.load(open(ROSTER, encoding="utf-8")) if ROSTER.exists() else {}

    checks = [
        check_outliers(polls, roster),
        check_party_inflate(polls),
        check_party_as_name(polls),
        check_office_classification(polls, roster),
        check_sum_sanity(polls),
        check_roster_gaps(polls, roster),
        check_build_golden(),
    ]

    n_error = sum(1 for c in checks if c["severity"] == "error" and c["count"] != 0)
    n_warn = sum(1 for c in checks if c["severity"] == "warn" and c["count"] != 0)

    print(f"=== polis audit — {date.today()} ===\n")
    for c in checks:
        marker = {"error": "✗", "warn": "⚠", "info": "ⓘ"}[c["severity"]]
        cnt = c["count"]
        flag = "" if cnt == 0 or c["severity"] == "info" else f" [{c['severity'].upper()}]"
        print(f"  {marker} {c['name']}: {cnt}건{flag}")
        if args.verbose and c["items"]:
            for it in c["items"][:5]:
                print(f"      {it}")

    result = {
        "date": str(date.today()),
        "polls_total": len(polls),
        "polls_data": sum(1 for p in polls if not p.get("is_pending")),
        "polls_pending": sum(1 for p in polls if p.get("is_pending")),
        "checks": checks,
    }
    diffs = diff_vs_prev(result)
    if diffs:
        print("\n--- 이전 audit 대비 변동 ---")
        for d in diffs:
            print(d)

    print(f"\n총: {n_error} error / {n_warn} warn")

    if not args.no_save:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        out = AUDIT_DIR / f"{date.today()}.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"→ {out.relative_to(ROOT)}")

    if n_error > 0:
        sys.exit(1)
    if args.strict and n_warn > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
