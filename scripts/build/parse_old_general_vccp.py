import re, json, glob, os
from collections import defaultdict
SIDO={11:'서울특별시',26:'부산광역시',27:'대구광역시',28:'인천광역시',29:'광주광역시',30:'대전광역시',31:'울산광역시',41:'경기도',42:'강원특별자치도',43:'충청북도',44:'충청남도',45:'전북특별자치도',46:'전라남도',47:'경상북도',48:'경상남도',49:'제주특별자치도'}
def tds_html(tr): return re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)
def txt(c): return re.sub(r'<[^>]+>','',c).replace('&nbsp;',' ').strip()
def isint(s): return bool(re.fullmatch(r'[\d,]+', s or ''))
def parse_sido(h, sido):
    rows=[tds_html(tr) for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', h, re.S)]
    races=[]
    for i,r in enumerate(rows):
        if not r: continue
        c0=txt(r[0])
        if not c0 or not re.match(r'^제\s*\d+', c0): continue
        # 후보 셀 = <strong>정당<br>이름</strong>
        cands=[]
        for cell in r:
            m=re.search(r'<strong>(.*?)</strong>', cell, re.S)
            if not m: continue
            parts=re.split(r'<br\s*/?>', m.group(1))
            parts=[re.sub(r'<[^>]+>','',p).strip() for p in parts if p.strip()]
            if len(parts)>=2: cands.append({'party':parts[0],'name':' '.join(parts[1:])})
        if not cands: continue
        K=len(cands)
        # 총계행 = 다음 행 (단일 시군이면 그 행, 다중이면 소계행)
        tot=[txt(x) for x in rows[i+1]] if i+1<len(rows) else []
        nums=[x for x in tot if isint(x)]
        if len(nums)<2+K: continue
        el=int(nums[0].replace(',','')); vo=int(nums[1].replace(',',''))
        votes=[int(nums[2+j].replace(',','')) for j in range(K)]
        valid=int(nums[2+K].replace(',','')) if len(nums)>2+K else sum(votes)
        inv=int(nums[3+K].replace(',','')) if len(nums)>3+K else 0
        cl=[{'name':cands[j]['name'],'party':cands[j]['party'],'votes':votes[j],'pct':round(votes[j]/valid*100,2) if valid else 0} for j in range(K)]
        cl.sort(key=lambda c:-c['votes'])
        for rk,c in enumerate(cl): c['rank']=rk+1; c['won']=(rk==0)
        races.append({'sg_typecode':'2','scope':'district','sido':sido,'district':c0,'electors':el,'voters':vo,'valid_votes':valid,'invalid_votes':inv,'candidates':cl})
    return races
# 1대 서울 검증
races=[]
for cc,sido in SIDO.items():
    f=f'/tmp/oldgen/1/{cc}.html'
    if os.path.exists(f): races+=parse_sido(open(f,encoding='utf-8',errors='replace').read(), sido)
print('1대 총 선거구:', len(races))
jr=next((r for r in races if '종로갑' in r['district']),None)
if jr:
    print('종로갑구:', jr['district'])
    for c in jr['candidates'][:3]: print(f"   {c['name']} {c['party']} {c['votes']:,} {c['pct']}% {'★' if c['won'] else ''}")
from collections import Counter
print('1대 당선 정당:', Counter(r['candidates'][0]['party'] for r in races).most_common(6))

# === 1~8대 전부 빌드 ===
DATES={1:('1st-general-1948','1948-05-10'),2:('2nd-general-1950','1950-05-30'),3:('3rd-general-1954','1954-05-20'),4:('4th-general-1958','1958-05-02'),5:('5th-general-1960','1960-07-29'),6:('6th-general-1963','1963-11-26'),7:('7th-general-1967','1967-06-08'),8:('8th-general-1971','1971-05-25')}
ROOT='/home/whysw/Documents/vote-via-data'
for n,(aid,date) in DATES.items():
    allr=[]
    for cc,sido in SIDO.items():
        f=f'/tmp/oldgen/{n}/{cc}.html'
        if os.path.exists(f): allr+=parse_sido(open(f,encoding='utf-8',errors='replace').read(), sido)
    p=f'{ROOT}/data/results/{aid}.json'
    prev=json.load(open(p)) if os.path.exists(p) else {'_meta':{},'races':[]}
    keep=[r for r in prev.get('races',[]) if not(r.get('scope')=='district' and str(r.get('sg_typecode'))=='2')]
    meta={**prev.get('_meta',{}),'election_id':aid,'election_date':date,'source':'nec-vccp09-개표현황','_district_source':'info.nec.go.kr VCCP09 (전체 후보)'}
    meta.pop('_note',None)
    json.dump({'_meta':meta,'races':keep+allr}, open(p,'w'), ensure_ascii=False)
    from collections import Counter
    top=Counter(r['candidates'][0]['party'] for r in allr).most_common(1)
    print(f'{n}대 {aid}: {len(allr)}선거구, 1위정당 {top}')
