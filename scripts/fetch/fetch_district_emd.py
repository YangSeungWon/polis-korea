"""NEC 개표현황(투표구별 VCCP08)에서 선거구→읍면동 매핑 회수 — 옛 총선(18·19대 등).

WWolf에 지역구 동매핑이 없는 회차용. 세션 불필요(POST 직접).
흐름: 시도 → selectbox API(구시군 목록) → 구시군별 report POST → 테이블에서 선거구+투표구(동).
구시군 1회 조회가 그 구의 모든 선거구+동을 줌 → (구코드, 동) → 선거구. 구코드=SGIS adm_cd[:4].

출력: data/raw/nec/district_emd_{n}.json — [{sido, sido_code, sgg_code, district, dongs:[]}]
사용: python scripts/build/../fetch/fetch_district_emd.py 19   (electionName 매핑은 ELECTIONS)
"""
from __future__ import annotations
import json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/raw/nec"

ELECTIONS = {9: "19730227", 10: "19781212", 11: "19810325", 12: "19850212",
             13: "19880426", 14: "19920324", 15: "19960411", 16: "20000413",
             17: "20040415", 18: "20080409", 19: "20120411", 20: "20160413",
             21: "20200415"}
SIDO = [  # (cityCode 4자리, 시도명)
    ("1100", "서울특별시"), ("2600", "부산광역시"), ("2700", "대구광역시"),
    ("2800", "인천광역시"), ("2900", "광주광역시"), ("3000", "대전광역시"),
    ("3100", "울산광역시"), ("5100", "세종특별자치시"), ("4100", "경기도"),
    ("4200", "강원도"), ("4300", "충청북도"), ("4400", "충청남도"),
    ("4500", "전라북도"), ("4600", "전라남도"), ("4700", "경상북도"),
    ("4800", "경상남도"), ("4900", "제주특별자치도"),
]
UA = "Mozilla/5.0"
BASE = "https://info.nec.go.kr"
REF = f"{BASE}/main/showDocument.xhtml?electionId=0000000000&topMenuId=VC&secondMenuId=VCCP08"

# 투표구명에 있으면 비지리(투표분류). '계'는 월계·중계·하계동 등 오탐이라 substring 금지 — 정확매칭만.
SKIP_ROW = re.compile(r"투표|부재자|명부|선상|잘못")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": REF,
                                               "Accept-Encoding": "identity"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")


def _post(data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(f"{BASE}/electioninfo/electionInfo_report.xhtml", data=body,
                                 headers={"User-Agent": UA, "Referer": REF,
                                          "Content-Type": "application/x-www-form-urlencoded",
                                          "Accept-Encoding": "identity"})
    return urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")


def sgg_list(date, sido4):
    """selectbox API → 구시군 [(code, name)]."""
    url = (f"{BASE}/bizcommon/selectbox/selectbox_townCodeBySgJson_Old.json?"
           f"electionId=0000000000&electionCode={date}&cityCode={sido4}&subElectionCode=2")
    body = json.loads(_get(url))["jsonResult"]["body"]
    return [(str(x["CODE"]), x["NAME"]) for x in body]


def parse_report(html):
    """테이블 → {선거구: set(동)}. 선거구명=행 첫 alignL, 투표구명=둘째 alignL."""
    out = {}
    cur = None
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip()
                 for c in re.findall(r"<td[^>]*class=alignL[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) < 2:
            continue
        sgg_name, tugu = cells[0], cells[1]
        if sgg_name and not sgg_name.isdigit():
            cur = sgg_name
            out.setdefault(cur, set())
        if cur is None or tugu in ("", "계", "소계") or SKIP_ROW.search(tugu):
            continue
        clean = re.sub(r"제\d+투$", "", tugu)  # 끝 투표구번호 제거
        if "투" in clean:  # 아직 '투' 남음 = 합동투표구(잠실제3동제5투잠실1동잠실2동) → 동 토큰 모두
            for d in re.findall(r"[가-힣]+\d*[동읍면리]", re.sub(r"제\d+투", "", clean)):
                out[cur].add(d)
        else:  # 단일 동 — 동인1·2·4가동·종로1·2·3·4가동 등 결합명 보존
            out[cur].add(clean)
    return out


def main(n):
    date = ELECTIONS[n]
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    for sido4, sido_name in SIDO:
        try:
            sggs = sgg_list(date, sido4)
        except Exception as e:
            print(f"  {sido_name}: selectbox 실패 {e}", file=sys.stderr)
            continue
        if not sggs:
            continue
        nd = 0
        for code, name in sggs:
            data = {"electionId": "0000000000",
                    "requestURI": "/electioninfo/0000000000/vc/vccp08.jsp",
                    "topMenuId": "VC", "secondMenuId": "VCCP08", "menuId": "VCCP08",
                    "statementId": "VCCP08_#1", "oldElectionType": "1",
                    "electionType": "2", "electionName": date, "electionCode": "2",
                    "cityCode": sido4, "sggCityCode": "-1", "townCodeFromSgg": "-1",
                    "townCode": code, "x": "30", "y": "10"}
            try:
                html = _post(data)
            except Exception as e:
                print(f"    {sido_name} {name}: POST 실패 {e}", file=sys.stderr)
                continue
            for district, dongs in parse_report(html).items():
                if dongs:
                    records.append({"sido": sido_name, "sido_code": sido4,
                                    "sgg_code": code, "sgg_name": name,
                                    "district": district, "dongs": sorted(dongs)})
                    nd += len(dongs)
            time.sleep(0.15)
        print(f"  {sido_name}: 구시군 {len(sggs)} → 동 {nd}", file=sys.stderr)
    out = OUT / f"district_emd_{n}.json"
    out.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    ndist = len({(r["sido"], r["district"]) for r in records})
    print(f"\n→ {out.name}: {len(records)} records, 선거구 {ndist}개", file=sys.stderr)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 19)
