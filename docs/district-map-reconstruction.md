# 총선 선거구 지도 복원 (history geomap)

역대 총선(9~22대) 지역구 경계를 복원해 history 지도뷰에 표시. 21·22대는 OhmyNews GeoJSON,
9~20대는 SGIS 읍면동 경계를 선거구별로 union해 생성.

## 파이프라인
1. **선거구↔동 매핑** — NEC 개표현황(투표구별 VCCP08). 세션 불필요·POST 직접:
   `POST info.nec.go.kr/electioninfo/electionInfo_report.xhtml`,
   body `statementId=VCCP08_#1, electionType=2, electionName={YYYYMMDD}, electionCode=2,
   cityCode={시도4자리}, townCode={구시군4·5자리}, sggCityCode=-1, oldElectionType=1`.
   구시군 코드는 `selectbox_townCodeBySgJson_Old.json`(cityCode=시도4자리)로 열거.
   → `scripts/fetch/fetch_district_emd.py` → `data/raw/nec/district_emd_{n}.json`.
2. **동 경계** — 통계청 SGIS 읍면동 경계(연도별 1975~2018, UTM-K 5179→WGS84). 선거연도 최근접 센서스.
3. **union** — `scripts/build/build_district_geojson.py`. 선거구별 동 union → `district_{n}_geojson.json`
   + `_geojson_map.json`(name_to_sgg_code, key `{canonSido}|{선거구명}`).
4. **hex 레이아웃** — `init_district_hex.py`(geojson centroid→_cen) + `build_zone_hex.py`.

## 매칭(오매핑 방지 핵심)
NEC 투표구 동명 ↔ SGIS 행정동명 불일치 보정:
- **구코드 학습** — 고유 동매칭 다수결로 NEC구→SGIS구 학습. 하드코딩 conv(행정표준↔통계청 구번호
  불일치, 예 김천 47↔구미류) 폐기. 동명충돌 tiebreak은 학습된 구로만 → **조용한 오매핑 차단**.
- **기하 소거** — 미배정 SGIS 동(고아)을, 그 구에서 미매칭 선거구가 하나뿐일 때만 확정(이름 무관·소거).
- **양방향 퍼지** — 정방향(청운동→청운효자동 통합)·역방향(용담명암산성동⊇용담동+…).
- **정규화** — 제N동(창신제1동↔창신1동)·구분자(용담·명암·산성동↔용담명암산성동)·능릉(정릉↔정능)·구시군접두.
- **합동투표구 파서** — '잠실제3동제5투잠실1동잠실2동'(NEC가 한 투표소에 여러 동) 토큰 분해.

## 회차별 모드·상태
- 21·22대: OhmyNews GeoJSON.
- 17~20대(소선거구): SGIS+NEC동. 99%대.
- 13~16대(소선거구): SGIS 최근접센서스(13·14→1990·15→1995·16→2000)+NEC동. 96~99%.
- 9~12대(중선거구 1구2인): SGIS 1975·80·85+NEC동. 당선 2당 줄무늬 렌더.
- 결과는 `national_assembly_{n}.json`(archive_to_assembly.py로 아카이브→history 변환, 9~12 winners[]).

## 알려진 이슈·발견 (검증 완료)

### 1. 13대 대전권 시도-승격 오매핑 (수정 완료 — sido_override)
1989 대전직할시 승격이 **SGIS 1990 스냅샷과 엇갈림** — 선거(1988) 선거구는 sido=충남(34)인데
SGIS 1990엔 대전 동이 **25xxx**. 그래서 대전 동들이 충남 동에 이름우연 매칭돼 **충남에 잘못 찍힘**.
- 영향: 대전시동구갑·중구·서구(충남 서산권에 오매핑), 대전시동구을(누락), 대덕군·연기군(대덕 일부 대전 편입).
- 확인: 대전 동(대동1동·가양1동·대사동·가수원동) SGIS 1990 코드 전부 25xxx.
- 다른 시도-승격(인천·대구·광주·울산)은 SGIS연도와 선거가 둘 다 승격 前이라 정합(오탐). 13대 대전만 SGIS연도가 승격을 넘음.
- **수정 완료**: CFG[13] `sido_override={"대전시":"25"}` — 선거구명에 '대전시' 포함 시 SGIS 시도코드를 25로
  강제. Pass1/Pass2 매칭에 적용. 대전 4선거구(동구갑·동구을·중구·서구) 위치 정정, 223→224/224 복원.

### 2. NEC 투표구별(동) 데이터 공백 (시군구-union 폴백)
일부 옛 군/구는 **VCCP08(투표구별) 빈값이나 VCCP09(개표현황 선거구별)엔 결과 존재** —
NEC가 그 단위의 **동 breakdown만 미디지털화**(선거구 결과는 있음). 검증 완료:
- 9대 경기 제8(연천·포천·가평·양평), 9대 경남 제5(의령·함안·합천), 11대 부산 북구(제6).
- 전부 통째 군/구 조합 → 동 없이 **SGIS 시군구 경계 union**(bnd_sigungu, 시군구명 직접)으로 복원.

### 3. 감사법 (centroid-in-시도)
선거구 centroid가 제 시도(sido_simple) 안인지 점검 → 오매핑 탐지. **오탐 주의**:
- 시도 승격(옛 인천=경기 등): period-correct 태그라 위치는 맞지만 현재 시도경계 밖 → 오탐.
- 도서 skew(울릉·옹진·여수): centroid가 바다쪽 → 오탐. 17~22대 flag는 전부 이 경우(정상).

### 4. pre-9(5~8대) 한계
VCCP08 동-레벨이 9대부터. 5~8대는 시군구-union만 가능(농촌·통째구 OK, **도심 갑/을/병 분할구는
동-레벨 필요해 미해결**). build `sgg_union` 모드 + 5~8 결과는 기반만(미게이트). 도심 분할은
나무위키/관보 국회의원선거법 별표의 선거구별 법정동 구역 → 행정동 변환 필요.

## 지선 geo 지도 (history, 별도 단위)
총선이 선거구 단위라면 지선은 **광역장/교육감=시도, 기초장=시군구** 단위. `render-local-geo.js`
`renderLocalGeoMap(unit)`가 총선 Leaflet 인프라(geoLeafletMap·mini-map·시도 외곽선·_districtStyleFor)를
재사용해 단색 chloropleth로 그린다(단체장 1명 당선 → 승자독식 단색이 정확). hex의 lifecycle/alias
(effectiveCell·resultForSido/resultForSigungu) 그대로 적용.
- **광역장/교육감(시도, `sido_simple`)**: 전 회차. 단 옛 지선은 광역장이 scope sido만이라
  adaptNewSchema가 offices.sigungu(scope sigungu 필터)에서 누락 → fallback(시군구 breakdown 없으면
  scope-sido 행)으로 1~4회 복원. resultForSido는 양쪽 canonSido 정규화.
- **기초장(시군구)**: 전 회차. 회차별 period-correct SGIS 시군구 경계(`build_sigungu_geojson_years.py` →
  `data/geo/sigungu_{1995,2000,2002,2006,2010}.json`, 6~9회는 `sigungu_simple` 2018). render-local-geo
  `LOCAL_SGG_GEO_YEAR`: 1→1995·2→2000(울산 광역시)·3→2002·4→2006·5→2010·6~9→2018(통합 청주 당선이라).
  일반구('수원시 장안구'·'고양시일산동')는 기초장이 시 단위라 **시로 dissolve**, 출장소(증평·계룡·효자)는
  인접 시군구 최소거리 병합. 4~6회 제주/세종 회색 = 기초단체장 없음(제주특별자치도 2006·세종)으로 정확.
- html script 태그 변경 시 `build_static.py` 재생성 필수(clean-URL 정적 페이지).

## 대선 geo 지도 (margin 명도)
대선은 전국 1명 당선이라 지역 1위 단색은 49:48을 압승처럼 호도 → **승자독식 단색 금지**(no-winner-take-all-pres).
`renderPresGeoMap`/`_presStyleFor`: 1위 정당색을 격차(1위-2위 %p)/40으로 흰색쪽 보간(`_mixWhite`) —
박빙=옅음·압승=원색(미국 purple-map). **16~20대만**(13~15대는 scope=nation 전국 합산만이라 지도 불가).
회차→경계: 16→2002·17→2006·18→2013(세종 출범·당진시 승격 후)·19·20→2018. 경계가 시 단위(일반구 dissolve)여도
resultForSigungu **reverse-merge**(시 경계→일반구/분구 데이터 집계, data.js line 155)로 대선 일반구 개표 집계.
`build_sigungu_geojson_years.py`로 sigungu_2013도 생성(18대용). main.js `presGeoSupported`로 분기.

## 검증 — OhmyNews 21대 대조 (IoU)
복원 방법의 신뢰도를 권위본으로 검증: 21대를 내 파이프라인(NEC VCCP08 동 + SGIS 2020 union)으로
빌드해 OhmyNews 권위본(VW-Lab 행정동 dissolve, MIT)과 253개 선거구 전수 IoU(겹침도) 비교.
- **평균 IoU 0.889 · 중앙 0.906**, IoU>0.8 = 224/253(88%), >0.7 = 244/253.
- 서로 다른 동 소스(통계청 SGIS ↔ VW-Lab)인데 ~89% 일치 → 동-union 방법 타당, 9~20대 복원 신뢰.
- IoU<0.7(9개)은 전부 **도심 갑/을/병 분할**(진주·여수·익산·화성·안산단원·통영고성·대전 동구) —
  시를 동 단위로 쪼개는 경계라 두 동 소스의 미세 차이가 가장 크게 드러남(예상된 결과).
- 21대 생산 지도는 OhmyNews 권위본 유지(내 복원본은 검증용). CFG[21]·district_emd_21은 대조 재현용.

## 출처·라이선스
통계청 SGIS(출처표시·영리가능) · NEC 개표현황(공개) · vuski/admdongkor · WWolf/korea-election ·
OhmyNews(21·22, MIT). `data/geo/district_reconstructed.LICENSE` 참조.
