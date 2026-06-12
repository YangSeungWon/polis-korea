"""옛 총선(3·4·5대) 선거구 획정 별표 — 위키백과 시도별 '선거구역' 표 파싱.

각 시도 하위문서(예 '대한민국 제3대 국회의원 선거 경상북도')의 `== 선거구 ==` 표는
`선거구 | 선거구역` 두 칼럼이며, 선거구역의 굵은('''…''') 토큰이 모(母)시군이다.
이를 파싱해 선거구별 시군 획정을 캡처 → data/geo/old_district_boundaries_{n}.json.

5대는 양원제 — `=== 민의원의원 ===` 절의 표만 사용(참의원은 도 단위라 제외).
재현: python scripts/build/scrape_old_district_boundaries.py [3 4 5]
"""
import json, re, sys, time
import urllib.request, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"
UA = "vote-via-data-research/1.0 (election history; hislab.mueller@gmail.com)"

PROVS = ["서울특별시", "경기도", "강원도", "충청북도", "충청남도",
         "전라북도", "전라남도", "경상북도", "경상남도", "제주도"]
ORD = {1: "제1대", 2: "제2대", 3: "제3대", 4: "제4대", 5: "제5대",
       6: "제6대", 7: "제7대", 8: "제8대"}


def fetch(page):
    u = ("https://ko.wikipedia.org/w/api.php?action=parse&page="
         + urllib.parse.quote(page) + "&prop=wikitext&format=json")
    req = urllib.request.Request(u, headers={"User-Agent": UA})
    return json.loads(urllib.request.urlopen(req, timeout=25).read())["parse"]["wikitext"]["*"]


def link_name(s):
    """[[A|B]] → B, [[A (xx)|B]] → B, [[포항시 (1950년 선거구)|포항시]] → 포항시"""
    m = re.search(r"\[\[([^\]]+)\]\]", s)
    if not m:
        return s.strip().strip("'")
    inner = m.group(1)
    if "|" in inner:
        return inner.split("|")[-1].strip()
    return re.sub(r"\s*\(.*?\)\s*", "", inner).strip()


def bold_sggs(area):
    """선거구역 셀에서 굵은('''시군''') 모구역 토큰 추출 (복수 가능)."""
    return [b.strip() for b in re.findall(r"'''([^']+?)'''", area)]


def parse_section_table(wt):
    """`== 선거구 ==` 섹션의 (민의원) 표에서 (선거구명, [시군], 선거구역) 행 리스트."""
    m = re.search(r"\n==\s*선거구\s*==\s*\n", wt)
    if not m:
        return []
    end = re.search(r"\n==[^=]", wt[m.end():])
    sec = wt[m.end(): m.end() + end.start()] if end else wt[m.end():]
    # 5대 양원제: 민의원 절만
    mm = re.search(r"===\s*민의원[^\n=]*===\s*\n", sec)
    if mm:
        sec = sec[mm.end():]
    # 첫 wikitable
    t = re.search(r"\{\|.*?\n(.*?)\n\|\}", sec, re.S)
    if not t:
        return []
    body = t.group(1)
    rows = []
    # 행: |-  로 구분, 각 행에 '| [[선거구]]' 다음 '| 선거구역'
    cells = re.split(r"\n\|-", body)
    for c in cells:
        cl = [x for x in re.split(r"\n\|", c) if x.strip() and not x.strip().startswith("!")]
        # 헤더 셀(! 선거구) 제외 후, [[..]] 포함 셀 = 선거구, 그 다음 셀 = 선거구역
        if len(cl) < 2:
            continue
        if "[[" not in cl[0]:
            continue
        name = link_name(cl[0])
        area = cl[1].strip()
        sggs = bold_sggs(area)
        rows.append({"district": name, "sigungu": sggs, "area": re.sub(r"'''", "", area)})
    return rows


def build(n):
    out = {}
    total = 0
    for prov in PROVS:
        page = f"대한민국 {ORD[n]} 국회의원 선거 {prov}"
        try:
            wt = fetch(page)
        except Exception as e:
            print(f"  [skip] {page}: {type(e).__name__}", file=sys.stderr)
            continue
        rows = parse_section_table(wt)
        if rows:
            out[prov] = rows
            total += len(rows)
        print(f"  {prov}: {len(rows)} 선거구", file=sys.stderr)
        time.sleep(0.3)
    (GEO / f"old_district_boundaries_{n}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{n}대: 총 {total} 선거구 → old_district_boundaries_{n}.json", file=sys.stderr)


if __name__ == "__main__":
    for a in (sys.argv[1:] or [3, 4, 5]):
        build(int(a))
