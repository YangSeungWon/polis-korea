"""NESDC 등록현황 메타 스크래퍼.

VT026 = 제9회 전국동시지방선거 (2026-06-03).
- 등록현황 페이지 페이지네이션 순회 → 행 메타 + nttId 추출
- 각 상세페이지 방문 → 표본·조사방법·접촉률·첨부파일 ID 추출
- 첨부 PDF 자동 다운로드 (data/raw/pdf/{nttId}_{fileSn}.pdf)
- 메타 → data/raw/nesdc_9th_polls.csv (신규만 append)
"""

from __future__ import annotations
import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from urllib.parse import urljoin, unquote, parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.nesdc.go.kr"
LIST_URL = BASE + "/portal/bbs/B0000005/list.do"
VIEW_URL = BASE + "/portal/bbs/B0000005/view.do"
FILE_URL = BASE + "/portal/cmm/fms/FileDown.do"

POLL_GUBUN_9TH_LOCAL = "VT026"

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PDF_DIR = RAW / "pdf"
CSV_PATH = RAW / "nesdc_9th_polls.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (vote-via-data scraper; +https://polis.ysw.kr)"
}


@dataclass
class PollMeta:
    ntt_id: str
    source_url: str       # NESDC 원본 링크 (traceability)
    reg_no: str           # 등록 글번호
    poll_name: str        # 여론조사 명칭
    poll_gubun: str       # 선거구분 (예: 제9회 전국동시지방선거)
    region: str           # 지역 (시도)
    sub_election: str     # 선거명 (예: 시도지사, 시장, 도지사)
    requester: str        # 조사의뢰자
    agency: str           # 조사기관명
    co_agency: str        # 공동조사기관명
    survey_region: str    # 조사지역 (상세)
    survey_period: str    # 조사일시 (raw)
    survey_start: str     # 조사 시작일 (ISO)
    survey_end: str       # 조사 종료일 (ISO)
    survey_days: str      # 조사일수
    method: str           # 조사방법 (목록 페이지)
    sample_frame: str     # 표본 추출틀 (목록 페이지)
    reg_date: str         # 등록일
    sido_label: str       # 시·도 (목록 컬럼)
    sample_size: str      # 표본의 크기 전체 (조사완료 사례수)
    sample_error: str     # 표본오차 (raw 텍스트)
    contact_rate: str     # 접촉률 %
    response_rate: str    # 응답률 %
    pdf_files: str        # ;로 구분된 atchFileId|fileSn|bbsId|bbsKey 4-tuple


def fetch(url: str, params: dict | None = None, retries: int = 3, backoff: float = 3.0) -> str:
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            r.raise_for_status()
            r.encoding = "utf-8"
            return r.text
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            wait = backoff * (attempt + 1)
            print(f"  ! 재시도 {attempt+1}/{retries} after {wait:.0f}s ({type(e).__name__})", file=sys.stderr)
            time.sleep(wait)
    raise last_err  # type: ignore


def parse_list_rows(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for a in soup.select("a.row.tr"):
        href = a.get("href", "")
        m = re.search(r"nttId=(\d+)", href)
        if not m:
            continue
        ntt_id = m.group(1)
        # NESDC가 <div> → <span class="col">로 변경됨. div fallback도 유지.
        cells = [c.get_text(strip=True) for c in a.select("span.col")]
        if not cells:
            cells = [c.get_text(strip=True) for c in a.find_all("div")]
        rows.append({"ntt_id": ntt_id, "cells": cells})
    return rows


def get_last_page(html: str) -> int:
    soup = BeautifulSoup(html, "lxml")
    last = soup.select_one("button.page.cont.last")
    if not last:
        nums = soup.select("button.page.num")
        if not nums:
            return 1
        # onclick 들 중 가장 큰 pageIndex
        max_p = 1
        for b in nums:
            oc = b.get("onclick", "")
            m = re.search(r"pageIndex=(\d+)", oc)
            if m:
                max_p = max(max_p, int(m.group(1)))
        return max_p
    oc = last.get("onclick", "")
    m = re.search(r"pageIndex=(\d+)", oc)
    return int(m.group(1)) if m else 1


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def parse_detail(html: str, ntt_id: str) -> dict:
    """상세페이지에서 메타 + 첨부파일 ID 추출 (BeautifulSoup table 구조 기반)."""
    soup = BeautifulSoup(html, "lxml")
    out: dict = {"ntt_id": ntt_id}

    # th-td 직접 페어 (인접 sibling)
    label_map = {
        "등록 글번호": "reg_no",
        "선거구분": "poll_gubun",
        "지역": "region",
        "선거명": "sub_election",
        "조사의뢰자": "requester",
        "조사기관명": "agency",
        "공동조사기관명": "co_agency",
        "조사지역": "survey_region",
        "조사일시": "survey_period",
        "조사일수": "survey_days",
        "표본오차": "sample_error",
    }

    for th in soup.find_all("th"):
        txt = _normalize_ws(th.get_text(strip=True))
        if txt in label_map:
            td = th.find_next_sibling("td")
            if td:
                out.setdefault(label_map[txt], _normalize_ws(td.get_text(" ", strip=True)))

    # 조사일시 → 시작·종료 ISO 추출
    period_raw = out.get("survey_period", "")
    dates = re.findall(r"(\d{4})[-./]\s*(\d{1,2})[-./]\s*(\d{1,2})", period_raw)
    iso_dates = []
    for y, m, d in dates:
        try:
            iso_dates.append(f"{int(y):04d}-{int(m):02d}-{int(d):02d}")
        except ValueError:
            continue
    out["survey_start"] = iso_dates[0] if iso_dates else ""
    out["survey_end"] = iso_dates[-1] if iso_dates else ""

    # 표본의 크기 (전체 사례수) — '표본의 크기' th가 속한 table 첫 td 값
    sample_size = ""
    for th in soup.find_all("th"):
        if "표본의 크기" in _normalize_ws(th.get_text(strip=True)):
            tbl = th.find_parent("table")
            if tbl:
                for td in tbl.find_all("td"):
                    t = _normalize_ws(td.get_text(" ", strip=True))
                    if re.fullmatch(r"\d{2,6}", t):
                        sample_size = t
                        break
            if sample_size:
                break
    out["sample_size"] = sample_size

    # 접촉률 / 응답률 — th 텍스트에 키워드 포함되는 첫 td
    for th in soup.find_all("th"):
        ttxt = _normalize_ws(th.get_text(strip=True))
        if "접촉률" in ttxt and "contact_rate" not in out:
            td = th.find_next_sibling("td")
            if td:
                val = _normalize_ws(td.get_text(" ", strip=True))
                m = re.search(r"(\d+\.?\d*)\s*%", val)
                if m:
                    out["contact_rate"] = m.group(1)
        if "응답률" in ttxt and "response_rate" not in out:
            td = th.find_next_sibling("td")
            if td:
                val = _normalize_ws(td.get_text(" ", strip=True))
                m = re.search(r"(\d+\.?\d*)\s*%", val)
                if m:
                    out["response_rate"] = m.group(1)

    # 첨부파일 — view('atchFileId', 'fileSn', 'bbsId', 'bbsKey') JS 호출
    pdfs = []
    for m in re.finditer(
        r"view\('([^']+)',\s*'([^']+)',\s*'([^']+)',\s*'([^']+)'\)",
        html,
    ):
        atch, file_sn, bbs_id, bbs_key = m.groups()
        pdfs.append(f"{atch}|{file_sn}|{bbs_id}|{bbs_key}")
    out["pdf_files"] = ";".join(pdfs)

    return out


def list_iter(poll_gubun: str, max_pages: int | None = None, delay: float = 0.5):
    """등록현황 페이지 순회. (row_meta, total_pages) 페어들 생성."""
    page = 1
    html = fetch(LIST_URL, {"menuNo": "200467", "pollGubuncd": poll_gubun, "pageIndex": page})
    total = get_last_page(html)
    if max_pages:
        total = min(total, max_pages)
    while page <= total:
        if page > 1:
            html = fetch(
                LIST_URL,
                {"menuNo": "200467", "pollGubuncd": poll_gubun, "pageIndex": page},
            )
        rows = parse_list_rows(html)
        for r in rows:
            yield r, page, total
        time.sleep(delay)
        page += 1


def detail_iter(ntt_ids: list[str], delay: float = 0.4):
    for nid in ntt_ids:
        html = fetch(VIEW_URL, {"nttId": nid, "menuNo": "200467"})
        yield nid, html
        time.sleep(delay)


RESULT_KEYWORDS = ("결과", "집계", "통계", "보고", "분석")  # 결과 PDF만 다운로드용 필터 (집계표 포함)


def download_pdfs(detail_meta: dict, out_dir: Path, result_only: bool = True,
                  pdf_delay: float = 0.8) -> list[str]:
    """첨부 파일 다운로드. 저장 경로 리스트 반환.

    result_only=True이면 파일명에 결과·통계·보고·분석 키워드 있는 것만.
    """
    saved = []
    pdfs = detail_meta.get("pdf_files", "")
    if not pdfs:
        return saved
    for triple in pdfs.split(";"):
        parts = triple.split("|")
        if len(parts) != 4:
            continue
        atch, file_sn, bbs_id, bbs_key = parts
        # FileDown.do는 atchFileId가 이미 URL-encoded이므로 raw 전달
        url = (
            f"{FILE_URL}?atchFileId={atch}&fileSn={file_sn}"
            f"&bbsId={bbs_id}&bbsKey={bbs_key}"
        )
        try:
            r = requests.get(url, headers=HEADERS, timeout=25, stream=True)
            r.raise_for_status()
        except Exception as e:
            print(f"  ! 다운로드 실패 ntt={detail_meta['ntt_id']} sn={file_sn}: {e}", file=sys.stderr)
            continue
        # Content-Disposition에서 파일명 추출
        cd = r.headers.get("Content-Disposition", "")
        fname_m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
        if fname_m:
            raw_fname = unquote(fname_m.group(1))
        else:
            raw_fname = f"{detail_meta['ntt_id']}_{file_sn}.bin"
        # result_only 필터: 파일명 키워드 검사
        if result_only and not any(k in raw_fname for k in RESULT_KEYWORDS):
            r.close()
            continue
        # 파일명 정규화
        safe = re.sub(r'[\\/<>:"|?*\x00-\x1f]', "_", raw_fname).strip()
        out_path = out_dir / f"{detail_meta['ntt_id']}_{file_sn}_{safe}"
        # 이미 받은 파일은 skip
        if out_path.exists():
            r.close()
            saved.append(str(out_path.relative_to(ROOT)))
            continue
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        saved.append(str(out_path.relative_to(ROOT)))
        time.sleep(pdf_delay)
    return saved


def load_existing_ids(csv_path: Path) -> set[str]:
    if not csv_path.exists():
        return set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        return {row["ntt_id"] for row in csv.DictReader(f)}


ELECTIONS_DIR = ROOT / "data" / "elections"


def load_active_targets() -> list[tuple[str, Path, str]]:
    """data/elections/index.json의 active 선거들 → [(gubun, csv_path, id)].
    각 메타의 nesdc.{gubun,csv}에서 읽음 — 워크플로가 선거별 코드를 하드코딩 안 하게.
    NESDC 미개설(gubun/csv 미설정) 선거는 경고 후 skip."""
    idx = json.loads((ELECTIONS_DIR / "index.json").read_text(encoding="utf-8"))
    targets = []
    for eid in idx.get("active", []):
        meta_path = ELECTIONS_DIR / f"{eid}.json"
        if not meta_path.exists():
            print(f"  ! active '{eid}': 메타 파일 없음 — skip", file=sys.stderr)
            continue
        n = json.loads(meta_path.read_text(encoding="utf-8")).get("nesdc") or {}
        gubun, csv_rel = n.get("gubun"), n.get("csv")
        if not (gubun and csv_rel):
            print(f"  ! active '{eid}': nesdc.gubun/csv 미설정 — skip (NESDC 미개설?)",
                  file=sys.stderr)
            continue
        targets.append((gubun, ROOT / csv_rel, eid))
    return targets


def scrape_one(gubun: str, csv_path: Path, args) -> None:
    """단일 (gubun, csv) 스크랩 — 목록 순회 → 상세·PDF → CSV append."""
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    existing = load_existing_ids(csv_path)
    print(f"기존 CSV: {len(existing)}건 / gubun={gubun or '전체(전국필터)'}", file=sys.stderr)
    n_region_skip = 0

    # 신규 nttId 수집 (목록 순회). 목록은 최신순(pageIndex=1=최신)이라 신규는 앞쪽에 몰림.
    # --stop-after-known-pages N: 마지막 신규 이후 N페이지 연속 전부 기존이면 조기 종료
    # (정기 증분 run이 매번 전체 목록을 안 훑게. 0이면 비활성=전체 순회, daily 기본).
    list_rows = []
    last_new_page = 1
    for row, page, total in list_iter(
        gubun, max_pages=args.max_pages, delay=args.delay
    ):
        if args.stop_after_known_pages and page - last_new_page >= args.stop_after_known_pages:
            print(f"  조기종료: {page}p까지 {args.stop_after_known_pages}p 연속 기존 — 중단", file=sys.stderr)
            break
        # --all-list: 목록 sido 칸(cell 7)이 '전국'인 정기조사만. 지역(지선·재보선 후보) 제외.
        if getattr(args, "all_list", False):
            cells = row.get("cells", [])
            sido = cells[7] if len(cells) > 7 else ""
            if "전국" not in sido:
                n_region_skip += 1
                continue
        if row["ntt_id"] in existing:
            continue
        last_new_page = page
        list_rows.append(row)
        if args.limit and len(list_rows) >= args.limit:
            break
        if len(list_rows) % 50 == 0:
            print(f"  ... 목록 {page}/{total} 진행, 신규 {len(list_rows)}건", file=sys.stderr)
    print(f"신규 nttId: {len(list_rows)}건"
          + (f" (지역 폴 {n_region_skip}건 제외)" if n_region_skip else ""), file=sys.stderr)

    # 상세 + PDF
    cell_keys = ["reg_no_list", "agency_list", "requester_list", "method_list",
                 "sample_frame_list", "poll_name_list", "reg_date_list", "sido_label"]

    fieldnames = [f.name for f in fields(PollMeta)]
    write_header = not csv_path.exists()

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()

        ntt_ids = [r["ntt_id"] for r in list_rows]
        list_by_id = {r["ntt_id"]: r["cells"] for r in list_rows}

        for idx, nid in enumerate(ntt_ids):
            try:
                html = fetch(VIEW_URL, {"nttId": nid, "menuNo": "200467"})
            except Exception as e:
                print(f"  ! fetch 실패 ntt={nid}: {e} — skip", file=sys.stderr)
                continue
            time.sleep(args.delay)
            try:
                d = parse_detail(html, nid)
            except Exception as e:
                print(f"  ! 파싱 실패 ntt={nid}: {e}", file=sys.stderr)
                continue

            cells = list_by_id.get(nid, [])
            # 목록 셀 매핑 (관찰 기반: 등록번호·기관·의뢰자·방법·추출틀·명칭(지역)·등록일·시도)
            cell_pick = lambda i: cells[i] if i < len(cells) else ""

            meta = PollMeta(
                ntt_id=nid,
                source_url=f"{VIEW_URL}?nttId={nid}&menuNo=200467",
                reg_no=d.get("reg_no", "") or cell_pick(0),
                poll_name=cell_pick(5),
                poll_gubun=d.get("poll_gubun", ""),
                region=d.get("region", ""),
                sub_election=d.get("sub_election", ""),
                requester=d.get("requester", "") or cell_pick(2),
                agency=d.get("agency", "") or cell_pick(1),
                co_agency=d.get("co_agency", ""),
                survey_region=d.get("survey_region", ""),
                survey_period=d.get("survey_period", ""),
                survey_start=d.get("survey_start", ""),
                survey_end=d.get("survey_end", ""),
                survey_days=d.get("survey_days", ""),
                method=cell_pick(3),
                sample_frame=cell_pick(4),
                reg_date=cell_pick(6),
                sido_label=cell_pick(7),
                sample_size=d.get("sample_size", ""),
                sample_error=d.get("sample_error", ""),
                contact_rate=d.get("contact_rate", ""),
                response_rate=d.get("response_rate", ""),
                pdf_files=d.get("pdf_files", ""),
            )
            writer.writerow(asdict(meta))
            f.flush()

            if not args.skip_pdf and meta.pdf_files:
                saved = download_pdfs(
                    d, PDF_DIR,
                    result_only=not args.all_pdf,
                    pdf_delay=args.pdf_delay,
                )
                if saved:
                    print(f"  ntt={nid} PDF {len(saved)}개", file=sys.stderr)

    print("완료", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=None, help="목록 페이지 상한 (테스트용)")
    ap.add_argument("--limit", type=int, default=None, help="신규 처리 건수 상한 (테스트용)")
    ap.add_argument("--skip-pdf", action="store_true", help="PDF 다운로드 생략")
    ap.add_argument("--all-pdf", action="store_true",
                    help="결과 PDF뿐 아니라 질문지 PDF도 전부 다운로드")
    ap.add_argument("--delay", type=float, default=1.5,
                    help="요청 간 지연 초 (default 1.5, DOS 방지)")
    ap.add_argument("--pdf-delay", type=float, default=0.8, help="PDF 다운로드 간격")
    ap.add_argument("--stop-after-known-pages", type=int, default=0,
                    help="마지막 신규 이후 N페이지 연속 기존이면 조기 종료(증분용·0=전체 순회)")
    ap.add_argument("--active", action="store_true",
                    help="elections/index.json의 active 선거들 gubun·csv 자동 순회(daily용·"
                         "선거 코드 하드코딩 제거)")
    ap.add_argument("--all-list", action="store_true",
                    help="gubun 필터 없이 전체 목록 순회 + sido='전국'만 채택. NESDC가 정기조사를 "
                         "언급 선거(대선 등) gubun으로 분류해 VT012 밖에 두는 폴(갤럽 자체조사 등)을 "
                         "회수. 트래커 소스용 — --csv는 nesdc_etc_polls.csv 권장.")
    ap.add_argument("--gubun", default=POLL_GUBUN_9TH_LOCAL,
                    help="선거구분 코드 (VT026=9회지선, VT039=2026재보궐). --active면 무시")
    ap.add_argument("--csv", default=str(CSV_PATH), help="출력 CSV 경로. --active면 무시")
    args = ap.parse_args()

    if args.active:
        targets = load_active_targets()
        if not targets:
            print("active 선거 중 NESDC 설정(gubun/csv)된 게 없음 — 종료", file=sys.stderr)
            return
        print(f"active 선거 {len(targets)}개: {', '.join(t[2] for t in targets)}", file=sys.stderr)
        for gubun, csv_path, eid in targets:
            print(f"\n=== {eid} (gubun={gubun}) → {csv_path.name} ===", file=sys.stderr)
            scrape_one(gubun, csv_path, args)
    elif args.all_list:
        print(f"전체목록 모드 — gubun 무시, 전국 정기조사만 → {Path(args.csv).name}", file=sys.stderr)
        scrape_one("", Path(args.csv), args)
    else:
        scrape_one(args.gubun, Path(args.csv), args)


if __name__ == "__main__":
    main()
