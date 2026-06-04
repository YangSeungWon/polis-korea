"""data/raw 스캔 → data/raw/MANIFEST.json (path · kind · source · 재현 방법).

raw 데이터는 git에서 제외되지만(6+ GB), 다른 머신/새 clone에서 재현
가능해야 함. manifest가 각 파일이 어디서·어떻게 왔는지 + 재다운로드
명령을 기록.

종류:
  source     — 외부에서 다운로드한 원본 (PDF · CSV · NEC API 캐시)
  derived    — source에서 파이프라인이 만든 중간 산출물 (parsed · grids)
  reference  — 외부 데이터셋 (OhmyNews · wwolf TSV)
  result_csv — NEC raw 결과 CSV (수동 다운로드)

회차 파이프라인이 새로 raw 파일을 만들면 이 스크립트 재실행으로
manifest 갱신. CI 후크로 자동화 가능 (현재는 수동).

사용:
  python3 scripts/build/build_raw_manifest.py
  python3 scripts/build/build_raw_manifest.py --hash   # SHA256까지 (느림)
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
KST = timezone(timedelta(hours=9))

# 분류 룰 — (pattern, kind, source 설명, regenerate 명령)
RULES = [
    # PDF — NESDC 등록 폴 첨부 (대소문자 PDF/pdf)
    (re.compile(r"^pdf/(\d+)_.*\.(pdf|PDF)$"),
     "source",
     "nesdc_poll_pdf",
     "NESDC view: https://www.nesdc.go.kr/portal/bbs/B0000005/view.do?nttId={ntt_id}&menuNo=200467",
     "python3 scripts/fetch/scrape_nesdc.py"),

    # NESDC CSV — 등록 list export
    (re.compile(r"^nesdc_[a-z0-9]+_polls\.csv$"),
     "source",
     "nesdc_list_csv",
     "NESDC 검색·엑셀 export (https://www.nesdc.go.kr/portal/bbs/B0000005/list.do)",
     "수동 다운로드 또는 python3 scripts/fetch/scrape_nesdc.py 갱신"),
    (re.compile(r"^nesdc_byelection\.csv$"),
     "source", "nesdc_list_csv",
     "NESDC 재보궐 list",
     "수동 다운로드"),

    # NEC roster·candidate cache
    (re.compile(r"^nec_roster_.+\.json$"),
     "source", "nec_api_cache",
     "NEC OpenAPI 후보자검색",
     "python3 scripts/fetch/fetch_nec_roster.py"),
    (re.compile(r"^nec_candidate_(party|office)\.json$"),
     "source", "nec_api_cache",
     "NEC OpenAPI 후보 정당·직위 매핑",
     "python3 scripts/fetch/fetch_nec_results.py 실행 중 자동 캐시"),
    (re.compile(r"^nec_uncontested/.+\.json$"),
     "source", "nec_api_cache",
     "NEC OpenAPI 무투표 당선",
     "python3 scripts/fetch/fetch_uncontested.py"),

    # NEC raw 결과 CSV/XLSX — 수동 다운로드
    (re.compile(r"^results_csv/.+\.(csv|xlsx)$"),
     "result_csv", "nec_raw_results",
     "NEC 선거통계시스템 결과 다운로드 (https://info.nec.go.kr)",
     "수동 다운로드 (legacy 회차)"),
    (re.compile(r"^nec_district/.+\.xlsx$"),
     "result_csv", "nec_raw_results",
     "NEC 선거통계 지역구별 xlsx",
     "수동 다운로드"),

    # OhmyNews 데이터
    (re.compile(r"^ohmynews_.+$"),
     "reference", "ohmynews",
     "오마이뉴스 선거 분석 데이터",
     "외부 source — git 추적 안 함"),

    # wwolf 비례 데이터
    (re.compile(r"^wwolf/.+\.(tsv|csv|xlsx)$"),
     "reference", "wwolf",
     "wwolf 데이터셋 — 비례정당 시군구별 득표",
     "외부 source"),

    # parsed PDF (derived)
    (re.compile(r"^parsed/.+\.json$"),
     "derived", "parsed_pdf",
     "parse_pdf 산출물",
     "python3 scripts/parse/parse_pdf.py 'data/raw/pdf/*.pdf'"),

    # grids (OCR derived)
    (re.compile(r"^grids/.+$"),
     "derived", "ocr_grids",
     "OCR 그리드 추출 산출물",
     "python3 scripts/parse/run_ocr_batch.py"),

    # audit·log
    (re.compile(r"^parse_audit\.json$"),
     "derived", "audit",
     "audit_parse 출력",
     "python3 scripts/audit/audit_parse.py"),
    (re.compile(r".*\.log$"),
     "derived", "log",
     "스크립트 로그",
     "—"),
]


def classify(rel: str) -> dict | None:
    for pat, kind, source_kind, source_note, regen in RULES:
        m = pat.match(rel)
        if not m:
            continue
        rec = {"kind": kind, "source_kind": source_kind, "source": source_note, "regenerate": regen}
        if m.groups():
            rec["ntt_id"] = m.group(1) if source_kind == "nesdc_poll_pdf" else None
            if rec["ntt_id"] is None:
                rec.pop("ntt_id")
        return rec
    return None


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hash", action="store_true", help="SHA256 계산 (느림, ~10분)")
    args = ap.parse_args()

    if not RAW.exists():
        print(f"ERR: {RAW} 없음")
        return

    sources = []        # source·reference·result_csv — 전체 리스트
    derived_agg = {}    # derived → kind별 summary만
    pdf_files = []      # NESDC PDF 전체 (한 ntt_id에 여러 PDF 가능 — 질문지·결과 등)
    unknown = []
    summary = {}        # source_kind → (count, bytes)
    total_bytes = 0
    total_files = 0

    for p in sorted(RAW.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(RAW).as_posix()
        if rel == "MANIFEST.json":
            continue
        total_files += 1
        sz = p.stat().st_size
        total_bytes += sz
        info = classify(rel)
        if not info:
            unknown.append(rel)
            continue
        sk = info["source_kind"]
        c, b = summary.get(sk, (0, 0))
        summary[sk] = (c + 1, b + sz)
        if info["kind"] == "derived":
            agg = derived_agg.setdefault(sk, {"kind": "derived", "regenerate": info["regenerate"], "count": 0, "bytes": 0})
            agg["count"] += 1
            agg["bytes"] += sz
            continue
        mtime = datetime.fromtimestamp(p.stat().st_mtime, KST).isoformat()
        if sk == "nesdc_poll_pdf":
            # 컴팩트: 5000+개. 한 ntt_id에 여러 첨부 가능 (질문지·결과 등).
            ntt_id = info.get("ntt_id")
            entry = {"ntt_id": ntt_id, "path": f"data/raw/{rel}", "bytes": sz, "mtime": mtime}
            if args.hash:
                entry["sha256"] = sha256_of(p)
            pdf_files.append(entry)
            continue
        # 나머지 source/reference/result_csv — 전체 리스트에 풀로
        rec = {"path": f"data/raw/{rel}", **info, "bytes": sz, "mtime": mtime}
        if args.hash:
            rec["sha256"] = sha256_of(p)
        sources.append(rec)

    manifest = {
        "_meta": {
            "scanned_at": datetime.now(KST).isoformat(),
            "total_files": total_files,
            "total_bytes": total_bytes,
            "with_hash": args.hash,
            "_note": "raw 데이터 카탈로그. source 파일은 외부에서 받아온 원본 (다른 머신에서 재현 가능 위해 source URL/재다운로드 명령 기록). derived는 파이프라인이 생성 — count·bytes만.",
        },
        "summary": {sk: {"count": c, "bytes": b} for sk, (c, b) in sorted(summary.items())},
        "sources": sources,
        "nesdc_pdf_files": pdf_files,
        "derived": derived_agg,
        "unknown": unknown,
    }
    out = RAW / "MANIFEST.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    total_gb = manifest["_meta"]["total_bytes"] / 1024 / 1024 / 1024
    print(f"→ {out.relative_to(ROOT)}: {total_files:,} files, {total_gb:.2f} GB")
    for sk, agg in manifest["summary"].items():
        print(f"  {sk:20} {agg['count']:6,} files  {agg['bytes']/1024/1024:8.1f} MB")
    if unknown:
        print(f"\n분류 안 됨 ({len(unknown)}건) — RULES에 패턴 추가 검토:")
        for u in unknown[:10]:
            print(f"  {u}")


if __name__ == "__main__":
    main()
