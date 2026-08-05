"""NEC 투표구별 개표(VCCP08)에서 **후보별 득표까지** 회수 — 재집계의 원자료.

`fetch_district_emd.py`는 같은 표에서 선거구→읍면동 **소속만** 뽑고 득표 컬럼을 버렸다.
재집계에는 소속만으로는 부족하다. 소속만 가지고 과거 선거구 총득표를 면적·인구로
쪼개는 건 추정이지 집계가 아니다. 그래서 같은 표의 득표 컬럼을 그대로 가져온다.

표 구조 (2020 하남시 실측):
    헤더 [선거구명, 투표구명, 선거인수, 투표수, '후보자별 득표수', 무효투표수, 기권자수,
          <후보1>, …, <후보N>, 계]
    행   [선거구명, 투표구명, 선거인수, 투표수, 득표1, …, 득표N, 유효계, 무효, 기권]
    → 후보명은 헤더 7번째부터 '계' 직전까지. 데이터 열은 N+7개.

행의 종류가 세 가지고, 이 구분이 재집계의 전부다:
    · **동 블록**   소계 → 관내사전투표 → 투표구들. 관내사전은 그 동 유권자의 표라
                    동에 귀속된다. 투표구명에서 '제N투'를 떼면 동 이름이다.
    · **귀속 불가** 거소·선상 / 관외사전 / 국외부재자 — 어느 동 표인지 알 수 없다.
                    인구비로 나누지 않는다. 세어서 제외하고 그 사실을 남긴다.
    · **집계행**    맨 위 '계', 각 블록 '소계' — 검산에만 쓰고 합산하지 않는다.

출력: data/raw/nec/emd_votes_{n}.json
사용: python scripts/fetch/fetch_emd_votes.py 21 --sgg 4100:4131
      python scripts/fetch/fetch_emd_votes.py 22            (전국)
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_district_emd import ELECTIONS, SIDO, SIDO_OVERRIDE, _post, sgg_list  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/raw/nec"

# 어느 동의 표인지 알 수 없는 행. 이 표들은 **버리지 않고 따로 센다** — 재집계
# 커버리지를 밝히려면 분모를 알아야 하기 때문이다.
UNATTRIBUTABLE = {
    "거소·선상투표": "home_ship",
    "거소투표": "home_ship",
    "선상투표": "home_ship",
    "관외사전투표": "out_of_area_early",
    "국외부재자투표": "overseas",
    "국외부재자투표(공관)": "overseas",
    "재외투표": "overseas",
    "잘못 투입·구분된 투표지": "misplaced",
}
SUBTOTAL = {"계", "소계", "합계"}


def _num(s: str):
    t = s.replace(",", "").replace("\xa0", " ").strip()
    if t in ("", "-"):
        return 0
    try:
        return int(t)
    except ValueError:
        return None


def _cells(tr: str) -> list[str]:
    return [re.sub(r"<[^>]+>", "", c).replace("\xa0", " ").strip()
            for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]


def dong_of(tugu: str) -> str | None:
    """투표구명 → 동 이름. 합동투표구·비지리 행은 None."""
    if tugu in SUBTOTAL or tugu in UNATTRIBUTABLE:
        return None
    t = re.sub(r"제\d+투$", "", tugu)
    t = re.sub(r"투표소$", "", t)
    if "투" in t:          # 합동투표구 — 여러 동이 한 투표구를 쓴다
        return None
    return t or None


def parse(html: str) -> dict:
    """VCCP08 HTML → {candidates, rows}. 파싱 실패는 예외로 드러낸다.

    후보 이름이 오는 자리가 두 가지다.
      · 구시군에 선거구가 **하나**면  thead에 들어간다.
      · **둘 이상**이면 (2024 하남 갑/을) 선거구 블록마다 표 안에 이름 행이 따로 오고,
        열 수는 그 구시군의 최대 후보 수로 패딩된다. 빈 슬롯은 무시한다.
    어느 쪽이든 열 배치는 같다: [선거구, 투표구, 선거인수, 투표수, 후보×K, 유효계, 무효, 기권].
    """
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    lens = [len(_cells(t)) for t in trs]
    lens = [n for n in lens if n >= 8]
    if not lens:
        return {"candidates": [], "rows": []}         # 무투표선거구 등
    ncol = max(set(lens), key=lens.count)
    k = ncol - 7                                       # 후보 슬롯 수

    cur = []                                           # 현 선거구의 (슬롯, 이름)
    th = re.search(r"<thead.*?</thead>", html, re.S)
    if th:
        hdr = [re.sub(r"<[^>]+>", "", c).replace("\xa0", " ").strip()
               for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", th.group(0), re.S)]
        # thead는 '후보자별 득표수' 병합칸이 하나 더 붙어 데이터 열보다 1개 많다
        if hdr[-1] == "계" and len(hdr) - 8 == k:       # 단일 선거구 — thead에 이름
            cur = [(i, n) for i, n in enumerate(hdr[7:-1]) if n]

    seen, rows, cur_sgg = [], [], None
    for tr in trs:
        c = _cells(tr)
        if len(c) != ncol:
            continue
        # 후보 이름 행: 앞 네 칸이 비고 '계' 자리에 '계'가 있다
        if not c[2] and not c[3] and c[4 + k] == "계":
            cur = [(i, n) for i, n in enumerate(c[4:4 + k]) if n]
            continue
        if c[0]:
            cur_sgg = c[0]
        nums = [_num(x) for x in c[2:]]
        if any(v is None for v in nums) or not cur:
            continue
        per = {n: nums[2 + i] for i, n in cur}
        valid, invalid = nums[2 + k], nums[3 + k]
        if sum(per.values()) != valid:
            raise ValueError(f"후보합≠유효계: {cur_sgg}/{c[1]} {sum(per.values())}≠{valid}")
        for n in (n for _, n in cur):
            if n not in seen:
                seen.append(n)
        tugu = c[1]
        rows.append({"district": cur_sgg, "unit": tugu,
                     "kind": ("subtotal" if tugu in SUBTOTAL
                              else UNATTRIBUTABLE.get(tugu) or "precinct"),
                     "dong": dong_of(tugu), "electors": nums[0], "votes": nums[1],
                     "valid": valid, "invalid": invalid, "per_candidate": per})
    return {"candidates": seen, "rows": _assign_blocks(rows)}


def _assign_blocks(rows: list[dict]) -> list[dict]:
    """블록(소계 단위)의 동 이름을 그 블록의 모든 행에 물려준다.

    `관내사전투표`는 자기 행에 동 이름이 없다 — 그 동 유권자가 사전투표소에서 넣은
    표라서 동 블록 안에 들어 있을 뿐이다. 블록을 안 보면 이 표가 전부 '귀속 불가'로
    새고 커버리지가 절반이 된다(하남 51%). 실제로는 귀속 가능한 표다.

    블록은 '소계'로 **시작한다** — 소계, 관내사전투표, 투표구들 순이다(2020 하남 실측:
    소계 6,616 = 관내사전 1,594 + 천현동 3개 투표구 5,022). 소계부터 다음 소계 직전까지가
    한 동이고, 그 안의 투표구 이름들이 한 동을 가리키면 그 동을 블록에 쓴다.
    갈리면(합동투표구 등) 비워 둔다 — 추정하지 않는다.
    """
    def flush(buf: list[dict]) -> None:
        names = {x["dong"] for x in buf if x["dong"]}
        if len(names) != 1:
            return
        d = next(iter(names))
        for x in buf:
            if x["dong"] is None and x["kind"] == "precinct":
                x["dong"] = d

    buf: list[dict] = []
    for r in rows:
        if r["kind"] == "subtotal" and r["unit"] != "계":
            flush(buf)
            buf = []
        buf.append(r)
    flush(buf)
    return rows


def fetch(n: int, city: str, town: str) -> str:
    return _post({"electionId": "0000000000",
                  "requestURI": "/electioninfo/0000000000/vc/vccp08.jsp",
                  "topMenuId": "VC", "secondMenuId": "VCCP08", "menuId": "VCCP08",
                  "statementId": "VCCP08_#1", "oldElectionType": "1",
                  "electionType": "2", "electionName": ELECTIONS[n],
                  "electionCode": "2", "cityCode": city, "sggCityCode": "-1",
                  "townCodeFromSgg": "-1", "townCode": town, "x": "30", "y": "10"})


def main(n: int, only: list[str] | None = None, fixture: str = "") -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ov = SIDO_OVERRIDE.get(n, {})
    out = []
    for sido4, sido_name in SIDO:
        sido4 = ov.get(sido_name, sido4)
        if only and not any(s.startswith(sido4) for s in only):
            continue
        try:
            sggs = sgg_list(ELECTIONS[n], sido4)
        except Exception as e:                                   # noqa: BLE001
            print(f"  {sido_name}: selectbox 실패 {e}", file=sys.stderr)
            continue
        for code, name in sggs:
            if only and f"{sido4}:{code}" not in only:
                continue
            try:
                p = parse(fetch(n, sido4, code))
            except Exception as e:                               # noqa: BLE001
                print(f"    {sido_name} {name}: {e}", file=sys.stderr)
                continue
            if p["rows"]:
                out.append({"sido": sido_name, "sido_code": sido4,
                            "sgg_code": code, "sgg_name": name, **p})
                nd = len({r["dong"] for r in p["rows"] if r["dong"]})
                print(f"    {sido_name} {name}: 행 {len(p['rows'])} · 동 {nd} "
                      f"· 후보 {len(p['candidates'])}", file=sys.stderr)
            time.sleep(0.15)
    # 회차마다 구시군 집합이 다를 수 있다 — 부천은 2024년에 3개 구로 부활했고
    # 군위군은 경북에서 대구로 옮겨 갔다. 그래서 fixture 이름으로 짝을 맞춘다.
    tag = ("_" + fixture if fixture else
           "" if not only else "_" + "-".join(s.replace(":", "") for s in only))
    f = OUT / f"emd_votes_{n}{tag}.json"
    f.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n→ {f.name}: 구시군 {len(out)}", file=sys.stderr)


if __name__ == "__main__":
    a = sys.argv[1:]
    rnd = int(a[0])
    sel = a[a.index("--sgg") + 1].split(",") if "--sgg" in a else None
    nm = a[a.index("--name") + 1] if "--name" in a else ""
    main(rnd, sel, nm)
