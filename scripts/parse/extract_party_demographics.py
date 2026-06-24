#!/usr/bin/env python3
"""전국 여론조사 PDF의 '응답자 특성별 정당지지도' cross-tab → 성×연령 추출.

후보지지(extract_pres_demographics)와 PDF 표 구조가 동일하다 — 성별(남·여)/연령/
성×연령 행 × 정당 열. 차이는 '열=정당'이라는 점뿐이라, 검증된 헬퍼(decode·norm_age·
row_pcts·블록 귀속 로직)를 그대로 재사용하고 로스터만 정당으로 갈아끼운다.

정당지지는 특정 선거에 매이지 않는 상시 신호 → 트래커(정당지지 연속 추적)에 성연령
차원으로 붙는다(이대남·이대녀 정당 지지 시계열).

로스터: data/parties/registry.json (정식명/abbr/aliases). 동음이의 abbr(민주당 등)는
충돌 시 최신 창당으로 귀속 — NESDC 데이터(2017+)는 대체로 현대 정당.

출력: data/raw/parsed/party_demographics.json =
  { ntt_id: { "성별": {남성:[row], 여성:[row]},
              "연령": {"18-29":[row], ...},
              "성연령": {"남성": {...}, "여성": {...}} } }
  row = [{name, party, pct}]  (name=party=정식명, 또는 무당층/없음/기타 등 특수 열)

사용:
  python scripts/parse/extract_party_demographics.py --pdf <경로>     # 단건 검증
  python scripts/parse/extract_party_demographics.py                  # 전량 스캔(캐시·재개)
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_pres_demographics import decode, norm_age  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW_PDF = ROOT / "data/raw/pdf"
PARSED = ROOT / "data/raw/parsed"
REGISTRY = ROOT / "data/parties/registry.json"
PAGE_CAP = 22

# 지지정당 없음·유보 계열 — 정당 아니지만 열로 등장. 이름 그대로 보존(party="" → 중립색).
_SPECIAL = {"없음", "지지정당없음", "무당층", "지지하는정당없음", "기타", "기타정당",
            "모름", "무응답", "모름/무응답", "태도유보", "유보"}


def build_party_roster():
    """정당 표기 변종 → 정식명. 정식명·aliases는 무충돌, abbr 동음이의는 최신 창당으로."""
    reg = json.load(open(REGISTRY, encoding="utf-8"))["parties"]
    variant2canon: dict[str, str] = {}
    for canon, info in reg.items():
        variant2canon.setdefault(canon, canon)
        for a in (info.get("aliases") or []):
            variant2canon.setdefault(a, canon)
    abbr_owners: dict[str, list] = {}
    for canon, info in reg.items():
        ab = info.get("abbr")
        if ab:
            abbr_owners.setdefault(ab, []).append(canon)
    for ab, owners in abbr_owners.items():
        if ab in variant2canon:
            continue
        variant2canon[ab] = (owners[0] if len(owners) == 1
                             else max(owners, key=lambda c: reg[c].get("founded") or ""))
    return variant2canon


def _match_party(s: str, i: int, variants: list[str]):
    """위치 i에서 시작하는 가장 긴 정당/특수 변종 → (정식명_or_특수, 길이). 없으면 (None,0)."""
    for v in variants:               # 긴 것 우선(longest-match)
        if s.startswith(v, i):
            return v, len(v)
    return None, 0


_NUMRE = re.compile(r"^\d+\.\d+$|^\d+$")
_PARENNUM = re.compile(r"^\(.*\)$|.*[,)]$")


def _map_name(frag: str, v2c: dict, variants: list[str]) -> str:
    """헤더 조각(접두 잡음 가능, 예 '조사완료더불어민주당') 안에서 가장 긴 정당/특수 변종 → 정식명."""
    best, bl = None, 0
    for i in range(len(frag)):
        v, ln = _match_party(frag, i, variants)
        if v and ln > bl:
            best, bl = v, ln
    return v2c.get(best, best) if best else (frag.strip() or "?")


def _cluster_rows(words, ytol=3.2):
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    rows = []
    for w in ws:
        if rows and abs(w["top"] - rows[-1]["top"]) <= ytol:
            rows[-1]["ws"].append(w)
        else:
            rows.append({"top": w["top"], "ws": [w]})
    for r in rows:
        r["ws"].sort(key=lambda w: w["x0"])
        r["text"] = "".join(w["text"] for w in r["ws"])
    return rows


def _datanums(ws):
    """행의 pct 후보 숫자워드(괄호 사례수 제외), x순."""
    return [w for w in ws if _NUMRE.match(w["text"]) and not _PARENNUM.match(w["text"])]


def parse_page_pos(words, v2c, variants, party_of=None, known=None):
    """위치기반 — 쌓인(다줄) 헤더를 x좌표로 복원. 컬럼=완전데이터행 숫자 x중심.
    party_of(name)=열 정당(없으면 기본: 특수는 '', 그 외 정식명=name). 후보 추출기는 후보→정당 맵 주입.
    known=실제 엔티티 집합(주면 헤더에 known ≥2 요구 — 지역·정당파편 오매칭 차단). 없으면 비특수 ≥2."""
    for w in words:
        w["text"] = decode(w["text"])
    rows = _cluster_rows(words)
    drows = [r for r in rows if len(_datanums(r["ws"])) >= 3]
    if not drows:
        return None
    # 컬럼 앵커 = 숫자열이 가장 많은 행(전체/계, 가장 완전). 그 숫자들의 x중심.
    anchor = max(drows, key=lambda r: len(_datanums(r["ws"])))
    cols = [(w["x0"] + w["x1"]) / 2 for w in _datanums(anchor["ws"])]
    C = len(cols)
    if C < 2:
        return None
    span = (max(cols) - min(cols)) / max(C - 1, 1)
    # 헤더 = 앵커행 위쪽 비숫자 워드. x로 최근접 컬럼에 귀속·세로 연결.
    frags = [[] for _ in range(C)]
    for r in rows:
        if r["top"] >= anchor["top"]:
            continue
        for w in r["ws"]:
            if _NUMRE.match(w["text"]) or _PARENNUM.match(w["text"]):
                continue
            cx = (w["x0"] + w["x1"]) / 2
            j = min(range(C), key=lambda k: abs(cols[k] - cx))
            if abs(cols[j] - cx) <= span * 0.7:
                frags[j].append((w["top"], w["text"]))
    order = [_map_name("".join(t for _, t in sorted(f)), v2c, variants) for f in frags]
    real = set(p for p in order if p in known) if known is not None else set(p for p in order if p not in _SPECIAL)
    if len(real) < 2:
        return None
    return _assign_rows(rows, anchor, cols, span, order, v2c, party_of)


def _assign_rows(rows, anchor, cols, span, order, v2c, party_of=None):
    C = len(cols)
    if party_of is None:
        party_of = lambda nm: "" if nm in _SPECIAL else nm

    def row(vals):
        return [{"name": order[i], "party": party_of(order[i]),
                 "pct": vals[i]} for i in range(C)]

    def vals_of(ws):
        v = [None] * C
        for w in _datanums(ws):
            cx = (w["x0"] + w["x1"]) / 2
            j = min(range(C), key=lambda k: abs(cols[k] - cx))
            if abs(cols[j] - cx) <= span * 0.7 and v[j] is None:
                v[j] = float(w["text"])
        return v if all(x is not None for x in v) else None

    out = {"성별": {}, "연령": {}, "성연령": {"남성": {}, "여성": {}}}
    male = re.compile(r"^(성별)?(남성|남자)")
    female = re.compile(r"^(성별)?(여성|여자)")
    STOP = re.compile(r"권역|지역|이념|직업|규모|학력|지지후보|적합")
    age_blocks, cur, started = [], None, False
    for r in rows:
        if r["top"] <= anchor["top"]:
            continue
        lab = "".join(w["text"] for w in r["ws"] if not _NUMRE.match(w["text"]))
        flat = lab.replace(" ", "")
        age = norm_age(flat)
        if STOP.search(flat) and not age:
            if started:
                break
            continue
        vals = vals_of(r["ws"])
        if not vals:
            continue
        if (male.match(flat) or female.match(flat)) and not age:
            out["성별"].setdefault("남성" if male.match(flat) else "여성", row(vals))
            started = True
        elif age:
            if cur is None or (age == "18-29" and "18-29" in cur):
                cur = {}
                age_blocks.append(cur)
            cur[age] = row(vals)
            started = True
    if age_blocks:
        out["연령"] = age_blocks[0]
    if len(age_blocks) >= 3:
        out["성연령"]["남성"] = age_blocks[1]
        out["성연령"]["여성"] = age_blocks[2]
    return _finalize(out)


def _finalize(out):
    sums = [sum(c["pct"] for c in r) for sec in ("성별", "연령") for r in out[sec].values()]
    sums += [sum(c["pct"] for c in r) for g in out["성연령"].values() for r in g.values()]
    if not sums:
        return None
    sums.sort()
    if not (95 <= sums[len(sums) // 2] <= 105):
        return None
    if out["성별"] or out["연령"] or out["성연령"]["남성"] or out["성연령"]["여성"]:
        return out
    return None


def parse_pdf(pdf_path: Path, v2c: dict, variants: list[str], party_of=None, known=None):
    try:
        with pdfplumber.open(pdf_path) as doc:
            for pg in doc.pages[:PAGE_CAP]:
                ws = pg.extract_words(x_tolerance=1.5, y_tolerance=2)
                if not ws:
                    continue
                # 후보/정당 ≥2 + 성/연령 신호 있는 페이지만(빠른 선별)
                flat = decode("".join(w["text"] for w in ws))
                if not (("남" in flat and "여" in flat) and ("대" in flat or "세" in flat)):
                    continue
                res = parse_page_pos(ws, v2c, variants, party_of, known)
                if res:
                    return res
    except Exception:
        return None
    return None


def _iter_party_polls():
    """정당지지 질문이 있는 파싱 JSON → (ntt_id, pdf_stem)."""
    seen = set()
    for f in PARSED.glob("*.json"):
        if f.name.startswith("."):
            continue
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if any(q.get("election_office") == "정당지지" for q in d.get("questions", [])):
            stem = f.name[:-5]
            if stem not in seen:
                seen.add(stem)
                yield str(d.get("ntt_id") or stem.split("_")[0]), stem


def main():
    v2c = build_party_roster()
    variants = sorted(set(list(v2c) + list(_SPECIAL)), key=len, reverse=True)
    for s in _SPECIAL:
        v2c.setdefault(s, s)

    if len(sys.argv) >= 3 and sys.argv[1] == "--pdf":
        res = parse_pdf(Path(sys.argv[2]), v2c, variants)
        print(json.dumps(res, ensure_ascii=False, indent=2) if res else "추출 실패")
        return

    cache_path = PARSED / ".party_demo_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    out, ok = {}, 0
    todo = list(_iter_party_polls())
    print(f"정당지지 폴 {len(todo)}건 — 성×연령 cross-tab 스캔...", flush=True)
    for i, (ntt, stem) in enumerate(todo):
        if stem in cache:
            rows = cache[stem]
        else:
            pdfs = list(RAW_PDF.glob(stem + ".*"))
            rows = parse_pdf(pdfs[0], v2c, variants) if pdfs else None
            cache[stem] = rows
        if rows:
            out[ntt] = rows
            ok += 1
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(todo)}, 추출 {ok}", flush=True)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False))
    cache_path.write_text(json.dumps(cache, ensure_ascii=False))
    dst = PARSED / "party_demographics.json"
    dst.write_text(json.dumps(out, ensure_ascii=False))
    g = sum(1 for v in out.values() if v.get("성연령", {}).get("남성"))
    print(f"정당지지: {len(todo)}건 중 추출 {ok}건 (성×연령 그리드 {g}건) → {dst.name}")


if __name__ == "__main__":
    main()
