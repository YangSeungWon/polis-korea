"""선관위 「정당등록 및 창당준비위원회 결성신고 현황」 스냅샷 수집.

## 왜

현재 정당등록현황(cbIdx=1239)은 **살아 있는 정당만** 보여준다. 등록취소된 정당은
거기에도 강령·당헌 목록에도 없어서, 옛 군소정당의 정식명·약칭·등록일을 확인할
1차 자료 경로가 끊긴다. 우리 observed에는 registry에 없는 이름이 213종 있고
그중 104종이 2000년 이후 관측이다.

그런데 선관위는 이 현황을 공고 게시판(cbIdx=1188)에 **그때그때 올려 뒀다.**
각 문서에 그 시점의 `명칭(약칭) · 등록연월일 · 대표자`가 다 들어 있다.

## 어떻게 읽나

문서가 HWP라 Synap 뷰어로 열리는데, 본문은 정적 경로에 있다:

    viewDetail.do?cbIdx=..&bcIdx=..&fileNo=1
      → src="/viewer/skin_view/doc.html?fn={파일}&rs={결과경로}"
    {결과경로}/{파일}.files/1.html          → 본문 HTML

## 스냅샷은 그 날짜의 사실이다

선거일의 사실이 아니다. 2012-03-14 문서에는 기독사랑실천당(기독당)과
기독자유민주당(기민당)이 따로 있는데 둘은 **다음 날 합당**했다. 그 문서만 보고
19대 '기독당'을 고쳤다면 257,190표가 틀린 곳으로 갔을 것이다.
그래서 각 행에 snapshot 날짜를 함께 남긴다 — 판정은 사람이 한다.

사용: python3 scripts/fetch/fetch_nec_party_snapshots.py [--from 10100] [--to 10400]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/raw/nec_party_snapshots.json"
BASE = "https://www.nec.go.kr"
UA = {"User-Agent": "Mozilla/5.0 (polis dataset; contact via github)"}


def get(url: str, timeout: int = 40) -> str:
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")


def doc_body(cb: int, bc: int) -> str | None:
    """공고 → Synap 뷰어 경로 → 본문 HTML의 텍스트."""
    try:
        v = get(f"{BASE}/cmm/dozen/viewDetail.do?cbIdx={cb}&bcIdx={bc}&fileNo=1")
    except Exception:                                            # noqa: BLE001
        return None
    m = re.search(r'fn=([^&"]+)&rs=([^"&]+)', v)
    if not m:
        return None
    fn, rs = m.group(1), m.group(2)
    for page in ("1", "2"):
        try:
            h = get(f"{BASE}{rs}/{fn}.files/{page}.html", timeout=60)
        except Exception:                                        # noqa: BLE001
            continue
        t = re.sub(r"<[^>]+>", " ", h)
        t = re.sub(r"\s+", " ", html.unescape(t))
        if "등록연월일" in t:
            return t
    return None


# 표는 태그를 지우면 한 줄이 된다. 행 경계는 **등록연월일 패턴**으로 잡고,
# 이름에 앞 행의 꼬리(전화번호·활동기간 만료일)와 표 머리글이 붙는 걸 떼어낸다.
_ROW = re.compile(
    r"([^'’‘`]{2,60}?)\s*['’‘`]\s*(\d{2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?\s*"
    r"([^\d(]{2,20}?)\s*\(\s*(\d{2})\s*\)")
_HEAD = ("정당명", "약칭", "등록연월일", "대표자", "생년", "사무소의소재지", "전화번호",
         "창준위명", "신고연월일", "활동기간", "만료일", "현재")


def _clean_name(raw: str) -> tuple[str, str | None]:
    """앞 행 꼬리·머리글을 떼고 (명칭, 약칭)."""
    t = re.sub(r"\s+", "", raw)
    for h in _HEAD:
        t = t.replace(h, "")
    # 앞 행의 전화번호(3786-3000·010-1234-5678)와 만료일(11.10.19.) 잔재
    t = re.sub(r"^.*?\d{2,4}-\d{3,4}", "", t)
    t = re.sub(r"^[\d\.\-·\s\(\)▣]+", "", t)
    m = re.match(r"^(.+?)\(([^)]{1,40})\)$", t)
    if m:
        return m.group(1), m.group(2)
    return t, None


def parse(text: str) -> tuple[str | None, list[dict]]:
    sm = re.search(r"\(?\s*(\d{4})?\s*\.?\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?\s*현재", text)
    snap = None
    if sm:
        y, mo, dd = sm.group(1), int(sm.group(2)), int(sm.group(3))
        snap = f"{y}-{mo:02d}-{dd:02d}" if y else f"?-{mo:02d}-{dd:02d}"
    # 등록 정당과 **창당준비위원회는 다른 것**이다. 창준위는 정당이 아니고 날짜도
    # 등록일이 아니라 신고일이다 — 한 표로 섞으면 없는 정당을 만든다.
    # 제목에도 '창당준비위원회 결성신고'가 있다. 표 머리인 ▣ 표시로 가른다 —
    # 제목을 경계로 잡으면 등록 정당이 통째로 창준위로 분류된다(실제로 그랬다).
    _m2 = re.search(r"▣\s*창당준비위원회", text)
    cut = _m2.start() if _m2 else -1
    sections = [("registered", text[:cut] if cut > 0 else text)]
    if cut > 0:
        sections.append(("prep", text[cut:]))
    rows = []
    for kind, sec in sections:
        for m in _ROW.finditer(sec):
            name, abbr = _clean_name(m.group(1))
            if not name or len(name) < 2:
                continue
            yy = int(m.group(2))
            year = 1900 + yy if yy >= 40 else 2000 + yy
            rows.append({
                "kind": kind,
                "name": name,
                "abbr": abbr,
                ("registered" if kind == "registered" else "filed"):
                    f"{year}-{int(m.group(3)):02d}-{int(m.group(4)):02d}",
                "leader": re.sub(r"\s+", "", m.group(5)),
            })
    return snap, rows


def harvest(cb: int, bc: int) -> dict | None:
    t = doc_body(cb, bc)
    if not t or "정당등록" not in t:
        return None
    snap, rows = parse(t)
    if not rows:
        return None
    return {"cbIdx": cb, "bcIdx": bc, "snapshot": snap, "parties": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="lo", type=int, default=10100)
    ap.add_argument("--to", dest="hi", type=int, default=10400)
    ap.add_argument("--cb", type=int, default=1188)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()

    ids = list(range(a.lo, a.hi + 1))
    out = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for r in ex.map(lambda b: harvest(a.cb, b), ids):
            if r:
                out.append(r)
                print(f"  {r['bcIdx']}  {r['snapshot']}  정당 {len(r['parties'])}",
                      file=sys.stderr)
    out.sort(key=lambda r: (r["snapshot"] or "", r["bcIdx"]))
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"snapshots": []}
    seen = {(s["cbIdx"], s["bcIdx"]) for s in out}
    merged = out + [s for s in prev.get("snapshots", [])
                    if (s["cbIdx"], s["bcIdx"]) not in seen]
    merged.sort(key=lambda r: (r["snapshot"] or "", r["bcIdx"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "_source": "중앙선거관리위원회 공고 「정당등록 및 창당준비위원회 결성신고 현황」",
        "_note": ("각 행은 **그 스냅샷 날짜의 사실**이다. 선거일의 사실이 아니다 — "
                  "2012-03-14 문서의 기독사랑실천당·기독자유민주당은 다음 날 합당했다. "
                  "판정은 사람이 하고, 여기 있는 건 관측된 원문뿐이다."),
        "_fetcher": "scripts/fetch/fetch_nec_party_snapshots.py",
        "snapshots": merged,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = sum(len(s["parties"]) for s in merged)
    print(f"\n스냅샷 {len(merged)}개 · 행 {n} → {OUT.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
