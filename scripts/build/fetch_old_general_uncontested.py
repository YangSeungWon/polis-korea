import urllib.request, urllib.parse, gzip, re, json, time
COOKIE='_fwb=115b5RM0PLfpseDBNzs801B.1779451493204; WMONID=GwTrpO9F-R8; JSESSIONID=KaW5OUZ3CNkfCei9qVlLE8SL3thQPH0sjKR9B13dNsH8FK0yTwfHQ4uRKahSkHA9.elecapp3_servlet_engine2'
SIDOMAP={'서울':'서울특별시','부산':'부산광역시','대구':'대구광역시','인천':'인천광역시','광주':'광주광역시','대전':'대전광역시','울산':'울산광역시','경기':'경기도','경기도':'경기도','강원':'강원특별자치도','충북':'충청북도','충남':'충청남도','전북':'전북특별자치도','전남':'전라남도','경북':'경상북도','경남':'경상남도','제주':'제주특별자치도'}
DATES={1:('1st-general-1948','19480510'),2:('2nd-general-1950','19500530'),3:('3rd-general-1954','19540520'),4:('4th-general-1958','19580502'),5:('5th-general-1960','19600729'),6:('6th-general-1963','19631126'),7:('7th-general-1967','19670608'),8:('8th-general-1971','19710525')}
def txt(c): return re.sub(r'<[^>]+>','',c).replace('&nbsp;',' ').strip()
def fetch(en):
    data=urllib.parse.urlencode({'electionId':'0000000000','requestURI':'/electioninfo/0000000000/ep/epei02.jsp','topMenuId':'EP','secondMenuId':'EPEI02','menuId':'EPEI02','statementId':'EPEI02_#91','oldElectionType':'0','electionType':'2','electionName':en,'electionCode':'2','cityCode':'0','x':'95','y':'7'}).encode()
    req=urllib.request.Request('https://info.nec.go.kr/electioninfo/electionInfo_report.xhtml',data=data,headers={'Cookie':COOKIE,'Content-Type':'application/x-www-form-urlencoded','Referer':'https://info.nec.go.kr/electioninfo/electionInfo_report.xhtml','User-Agent':'Mozilla/5.0'})
    raw=urllib.request.urlopen(req,timeout=30).read()
    try: return gzip.decompress(raw).decode('utf-8','replace')
    except: return raw.decode('utf-8','replace')
for n,(aid,en) in DATES.items():
    h=fetch(en); time.sleep(0.3)
    rows=[[txt(x) for x in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>',tr,re.S)] for tr in re.findall(r'<tr[^>]*>(.*?)</tr>',h,re.S)]
    ut=[]
    for r in rows:
        if len(r)<4 or r[0]=='시도명' or not r[0] or '선거구' not in (r[1] or ''): continue
        sido=SIDOMAP.get(r[0].strip(), r[0].strip()); dist=r[1].strip(); party=r[2].strip()
        name=re.sub(r'\(.*?\)','',r[3]).strip()
        ut.append((sido,dist,party,name))
    # archive에 주입 (중복 제외)
    p=f'data/results/{aid}.json'
    d=json.load(open(p))
    have={(r['sido'],r['district']) for r in d['races'] if r.get('scope')=='district'}
    added=0
    for sido,dist,party,name in ut:
        if (sido,dist) in have: continue
        d['races'].append({'sg_typecode':'2','scope':'district','sido':sido,'district':dist,'electors':0,'voters':0,'valid_votes':0,'invalid_votes':0,'is_uncontested':True,'candidates':[{'name':name,'party':party,'votes':0,'pct':None,'rank':1,'won':True,'uncontested':True}]})
        added+=1
    json.dump(d, open(p,'w'), ensure_ascii=False)
    nd=sum(1 for r in d['races'] if r.get('scope')=='district'); print('%d대: 무투표 %d명, 주입 %d -> 총 %d선거구'%(n,len(ut),added,nd))
