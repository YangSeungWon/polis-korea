"""회차별 '여론조사 1위 vs 실제 1위' → data/polls/accuracy.json.

계산은 scripts/build/poll_accuracy.py가 갖는다(왜 옮겼는지도 거기 적혀 있다).
이 스크립트는 회차를 돌며 그 계산을 적용하고 결과를 적는다.

세 계열이 서로 다른 것을 센다 — **한 표에 줄세우면 오해가 생긴다**:
    지선  광역단체장·교육감은 시도, 기초단체장은 시군구
    대선  시도 1위 (전국 승자가 아니다 — 박빙 시도가 많으면 낮게 나온다)
    총선  지역구 (조사가 있던 지역구만)

⚠️ 인용 의무. 지역별 행은 특정 조사를 인용하므로 의뢰자·기관·기간·표본수·응답률·
표본오차를 함께 적는다(poll_accuracy.CITE_FIELDS). 표를 만들 때 빠뜨릴 수 없게
데이터에 묶어 둔다.

사용: python scripts/build/build_poll_accuracy.py [--slug 9th-local-2026]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import poll_accuracy as PA  # noqa: E402
from poll_accuracy import NATIONAL_WINDOW  # noqa: E402
from build_static import _poll_election_meta  # noqa: E402  회차→데이터 경로 단일 출처

OUT = ROOT / "data" / "polls" / "accuracy.json"
# 실제 결과의 sg_typecode → 직위. adapter.js _TC_TO_OFFICE/_TC_OFFICE_EXTRA와 같은 표.
TC_OFFICE = {"3": "광역단체장", "4": "기초단체장", "11": "교육감",
             "1": "대통령", "2": "국회의원", "7": "비례대표"}


def load_json(rel: str):
    p = ROOT / rel
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def races_of(meta: dict) -> list:
    out = []
    for key in ("results_path", "results_sigungu_path"):
        d = load_json(meta[key]) if meta.get(key) else None
        if isinstance(d, dict):
            out += d.get("races") or []
        elif isinstance(d, list):
            out += d
    return out


def actual_top(race: dict) -> dict | None:
    cs = sorted(race.get("candidates") or [], key=lambda c: -(c.get("votes") or 0))
    return cs[0] if cs else None


def build(meta: dict, P: PA.Parties) -> dict:
    date_s = meta["date"]
    ref = datetime.fromisoformat(date_s).timestamp() * 1000
    polls = (load_json(meta["polls_path"]) or {}).get("polls") or []
    # 정당·후보 본인 의뢰 조사 제외 — assets/polls/core.js:129가 전역에서 하는 일이고,
    # 페이지가 스스로 "정당·후보자 본인 의뢰 조사는 표시에서 제외됩니다"라고 적어 뒀다.
    # 이걸 빠뜨리면 20대 총선이 125개 지역구가 된다(런타임은 119).
    polls = [p for p in polls if not p.get("is_self_poll")]
    races = races_of(meta)
    kind = meta["kind"]
    offices: dict[str, dict] = {}
    # 직위 → {ntt_id: 인용정보}. **표에 적힌 숫자를 만든 조사 전부**다.
    # 지선은 여러 조사의 시간감쇠 가중 종합이라 그 지역의 모든 조사가 들어가고,
    # 대선·총선은 막판 조사 1건만 쓰므로 행마다 1건이다. 인용 의무는 '종합했다'고
    # 줄여 주지 않는다 — 숫자를 만든 조사는 전부 밝힌다.
    used: dict[str, dict] = {}

    def mark(off: str, ps: list) -> None:
        u = used.setdefault(off, {})
        for q in ps:
            if q.get("ntt_id"):
                u.setdefault(q["ntt_id"], PA.cite(q))

    def row(region: str, win, act, cited) -> dict:
        pp = win.get("party") if win else None
        ap = act.get("party") if act else None
        hit = P.same(pp, ap, date_s) if (pp and ap) else None
        return {
            "region": region,
            "poll": None if not win else {
                "party": pp, "name": win.get("name"), "pct": win.get("pct"),
                "n_polls": win.get("n_polls"), "sample_error": win.get("sample_error"),
            },
            "actual": None if not act else {
                "party": ap, "name": act.get("name"), "pct": act.get("pct"),
            },
            "hit": hit,
            "cite": PA.cite(cited),
        }

    if kind == "local":
        by_sido, by_sgg = {}, {}
        for r in races:
            off = TC_OFFICE.get(r.get("sg_typecode"))
            if not off:
                continue
            top = actual_top(r)
            if not top:
                continue
            if r.get("scope") == "sido":
                by_sido[(PA.canon_sido(r.get("sido")), off)] = top
            elif r.get("scope") == "sigungu":
                by_sgg[(PA.canon_sido(r.get("sido")), r.get("sigungu"), off)] = top
        for off in ("광역단체장", "교육감"):
            rows = []
            for sd in PA.sido_list(date_s, off):
                sel = [p for p in polls if p.get("office_level") == off
                       and PA.canon_sido(p.get("sido")) == PA.canon_sido(sd) and not p.get("sigungu")]
                if not sel and PA.SIDO_MERGE.get(sd):
                    tgt = PA.SIDO_MERGE[sd]
                    sel = [p for p in polls if p.get("office_level") == off
                           and PA.canon_sido(p.get("sido")) == tgt and not p.get("sigungu")]
                rows.append(row(sd, PA.summarize_latest(sel, ref), by_sido.get((sd, off)),
                                PA.latest_poll(sel)))
                if rows[-1]["hit"] is not None:
                    mark(off, sel)
            offices[off] = {"unit": "시도", "rows": rows}
        rows = []
        for (sd, sgg, off), top in sorted(by_sgg.items()):
            if off != "기초단체장":
                continue
            sel = [p for p in polls if p.get("office_level") == off
                   and PA.canon_sido(p.get("sido")) == sd and p.get("sigungu") == sgg]
            if not sel:
                # 일반구 → 모도시(수원시장안구 → 수원시). adapter.parentSigungu와 같은 규칙.
                import re as _re
                m = _re.match(r"^([가-힣]+시)[가-힣]+구$", sgg or "")
                if m:
                    sel = [p for p in polls if p.get("office_level") == off
                           and PA.canon_sido(p.get("sido")) == sd and p.get("sigungu") == m.group(1)]
            rows.append(row(f"{sd}|{sgg}", PA.summarize_latest(sel, ref), top, PA.latest_poll(sel)))
            if rows[-1]["hit"] is not None:
                mark(off, sel)
        offices["기초단체장"] = {"unit": "시군구", "rows": rows}

    if kind == "presidential":
        # 전국 후보별 — 대선 조사는 대부분 전국 단위라 시도 표만으로는 페이지가 얇다.
        # '여론조사가 얼마나 맞았나'에 가장 직접 답하는 표이기도 하다.
        #
        # ⚠️ **선거일 이후 조사를 빼야 한다.** period_end가 선거일보다 뒤인 조사가
        # 21대 6건·20대 1건 있다(사후 조사). 지역 단위엔 없어서 적중률은 무사했지만,
        # 여기서 '막판 조사'로 잡으면 결과를 알고 난 뒤의 숫자가 예측인 척한다.
        from datetime import date as _d, timedelta as _td
        lo = (_d.fromisoformat(date_s) - _td(days=NATIONAL_WINDOW)).isoformat()
        sel = [p for p in polls if p.get("office_level") == "대통령" and not p.get("sido")
               and lo <= (p.get("period_end") or "") <= date_s]
        nat = next((r for r in races
                    if r.get("scope") == "nation" and r.get("sg_typecode") == "1"), None)
        if sel and nat:
            agg = PA.mean_by_name(sel)
            rows = []
            for c in sorted(nat.get("candidates") or [], key=lambda c: -(c.get("votes") or 0)):
                got = agg.get(c.get("name"))
                rows.append({
                    "name": c.get("name"), "party": c.get("party"),
                    "poll_pct": round(got["pct"], 1) if got else None,
                    "n_polls": got["n"] if got else 0,
                    "actual_pct": c.get("pct"),
                    "err": (round(got["pct"] - c["pct"], 1)
                            if got and c.get("pct") is not None else None),
                })
            offices["_national"] = {
                "unit": "전국 후보", "rows": rows, "window_days": NATIONAL_WINDOW,
                "n_polls": len(sel),
                "cited": sorted((PA.cite(q) for q in sel if q.get("ntt_id")),
                                key=lambda c: (c.get("period_end") or ""), reverse=True),
            }

    if kind == "presidential":
        # 대선은 집계가 아니라 **시도별 가장 나중 조사 한 건**을 쓴다(adapter.cellsFromPolls).
        act = {PA.canon_sido(r.get("sido")): actual_top(r) for r in races
               if r.get("scope") == "sido" and r.get("sg_typecode") == "1"}
        rows = []
        for sd, top in sorted(act.items()):
            sel = [p for p in polls if p.get("office_level") == "대통령"
                   and PA.canon_sido(p.get("sido")) == sd and not p.get("sigungu")]
            lp = PA.latest_poll(sel)
            win = None
            if lp:
                cs = sorted([c for c in lp["candidates"] if c.get("pct") is not None],
                            key=lambda c: -(c.get("pct") or 0))
                if cs:
                    win = {"party": cs[0].get("party"), "name": cs[0].get("name"),
                           "pct": cs[0].get("pct"), "n_polls": len(sel), "sample_error": None}
            rows.append(row(sd, win, top, lp))
            if rows[-1]["hit"] is not None and lp:
                mark("대통령", [lp])
        offices["대통령"] = {"unit": "시도 1위", "rows": rows}

    elif kind == "general_election":
        layout = load_json(f"data/geo/district_hex_{meta['n']}.json") or []
        act = {}
        for r in races:
            if r.get("scope") != "district" or r.get("sg_typecode") != "2":
                continue
            act[(PA.canon_sido(r.get("sido")), r.get("district") or r.get("name"))] = actual_top(r)
        rows = []
        for d in layout:
            key = (PA.canon_sido(d.get("sido")), d.get("name"))
            sel = [p for p in polls if p.get("office_level") == "국회의원"
                   and PA.canon_sido(p.get("sido")) == key[0] and p.get("district") == key[1]]
            lp = PA.latest_poll(sel)
            if not lp:
                continue          # 조사가 없는 지역구는 분모에 안 들어간다(JS와 같다)
            cs = sorted([c for c in lp["candidates"] if c.get("pct") is not None],
                        key=lambda c: -(c.get("pct") or 0))
            win = {"party": cs[0].get("party"), "name": cs[0].get("name"), "pct": cs[0].get("pct"),
                   "n_polls": len(sel), "sample_error": None} if cs else None
            rows.append(row(f"{key[0]}|{key[1]}", win, act.get(key), lp))
            if rows[-1]["hit"] is not None:
                mark("국회의원", [lp])
        offices["국회의원"] = {"unit": "지역구", "rows": rows,
                            "districts_total": len(layout)}

    for off, o in offices.items():
        if off == "_national":
            continue                  # 적중이 아니라 오차를 재는 표다
        hits = [r["hit"] for r in o["rows"] if r["hit"] is not None]
        o["match"], o["total"] = sum(1 for h in hits if h), len(hits)
        o["cited"] = sorted((used.get(off) or {}).values(),
                            key=lambda c: (c.get("period_end") or "", c.get("agency") or ""),
                            reverse=True)

    # 기관별 — (시도, 시군구, 직위) → 실제 득표순 후보. 대선은 시도, 총선은 지역구를
    # sigungu 자리에 넣어 폴의 키와 같은 모양으로 맞춘다.
    act_idx: dict = {}
    for r in races:
        off = TC_OFFICE.get(r.get("sg_typecode"))
        if not off:
            continue
        cands = sorted(r.get("candidates") or [], key=lambda c: -(c.get("votes") or 0))
        if not cands:
            continue
        sub = (r.get("sigungu") if r.get("scope") == "sigungu"
               else (r.get("district") if r.get("scope") == "district" else "")) or ""
        act_idx[(PA.canon_sido(r.get("sido")), sub, off)] = cands
    # 총선 폴은 district 필드를 쓴다 — sigungu 자리에 옮겨 키를 맞춘다.
    pol_for_ag = [dict(p, sigungu=(p.get("district") or p.get("sigungu")))
                  if p.get("district") else p for p in polls]
    return {"slug": meta["slug"], "name": meta["name"], "date": date_s,
            "kind": kind, "offices": offices,
            "agencies": PA.agency_rows(pol_for_ag, act_idx, date_s, P)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    args = ap.parse_args()
    P = PA.Parties()
    idx = load_json("data/polls/election_index.json") or []
    out = {}
    for e in idx:
        if args.slug and e["slug"] != args.slug:
            continue
        el = load_json(f"data/elections/{e['slug']}.json")
        meta = _poll_election_meta(el) if el else None
        if not meta:
            print(f"  {e['slug']}: 폴 메타 없음 — skip")
            continue
        out[e["slug"]] = build(meta, P)
        for off, o in out[e["slug"]]["offices"].items():
            if off == "_national":
                print(f"  {e['slug']:22} {'전국':8} 후보 {len(o['rows'])} · 조사 {o['n_polls']}건")
            else:
                print(f"  {e['slug']:22} {off:8} {o['match']:4}/{o['total']:<4} ({o['unit']})")
    if args.slug and OUT.is_file():
        prev = json.loads(OUT.read_text(encoding="utf-8")).get("elections") or {}
        prev.update(out)
        out = prev
    OUT.write_text(json.dumps({
        "_runtime_diff": {
            "_": "2026-08-27 런타임(JS)과 전량 대조. 15개 (회차×직위) 중 13개가 "
                 "글자 그대로 일치했다. 남은 둘은 **JS 쪽 결함**이라 여기서 따라 하지 "
                 "않는다. 2단계에서 JS가 이 파일을 읽게 되면 저절로 고쳐진다.",
            "대선 시도 1위": "JS adapter.cellsFromPolls가 candidates[0]을 **pct로 "
                          "정렬하지 않고** 그대로 1위로 쓴다(render-pres.js:165). "
                          "조사표에 처음 적힌 후보가 곧 1위가 된다 — 20대 대선 조사의 "
                          "49%가 후보순≠득표순이라 헤드라인이 7/17로 나왔다. 실제는 "
                          "13/17. 지도 **색은 맞다**(shared.js:254가 그리기 전에 "
                          "정렬한다) — 틀린 것은 적중 숫자와 빗나감 점선 색이다.",
            "9회 지선 광역단체장": "JS accuracyForOffice가 SIDO_HEX_LAYOUT 17개를 도는데, "
                              "2026-06-03 신설 전남광주특별시는 그 표에 없다. 광주·전남 "
                              "둘 다 실제 결과를 못 찾아 제외되어 **통합 1선거가 통째로 "
                              "빠진다**(13/15). 여기서는 통합 셀을 한 번 센다(14/16).",
            "교육감": "0/0이 맞다 — 교육감 선거는 정당을 표방하지 않아 비교할 정당이 "
                   "없다. 런타임도 빈칸이다.",
        },
        "_note": "빌드 생성물 — scripts/build/build_poll_accuracy.py. "
                 "여론조사 1위 vs 실제 1위. 계산 정본은 scripts/build/poll_accuracy.py다 "
                 "(JS는 이 파일을 읽기만 한다). cite는 인용 의무 항목 — 표에 그 조사를 "
                 "적을 때 반드시 함께 표시할 것(공직선거법·NESDC). "
                 "계열마다 세는 단위가 다르다(unit) — 한 표에 줄세우면 오해가 생긴다.",
        "elections": dict(sorted(out.items())),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"→ {OUT.relative_to(ROOT)}: {len(out)}회차")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
