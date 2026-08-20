# 지리 계보 (geography lineage)

행정구역과 선거구의 변화를 **하나의 그래프**로 둔다. 지금까지는 변화가 생길 때마다
region generator·comparison·검색 alias·지도 매핑에 각각 특례가 들어갔다. 한 사실을
한 군데만 기록하면 그 모든 기능이 여기서 파생된다.

## 원칙

**entity는 분리, lineage는 연결.**

이천군과 이천시는 서로 다른 entity다. 1995년 데이터에는 이천군이 남아야 한다 —
합쳐버리면 그때 행정단위가 이천시였던 것처럼 왜곡된다. 대신 두 entity를
`promotion` 이벤트로 잇고, UI가 그 관계를 이해한다.

`A → B + C` 같은 분할에서는 어느 쪽도 canonical successor가 아니다. 그래서
`canonical_id` 하나로 뭉개지 않고 **그래프**를 둔다.

**역사가 이어진다 ≠ 숫자가 직접 비교된다.**

계보를 이어도 득표율 delta를 붙일 수 있는지는 별도 판정이다.

## 모델

```
geo_entity   특정 기간에 실재한 단위
  id · kind(admin_unit | electoral_district) · name · parent · valid_from · valid_to

geo_event    무엇이 무엇으로 바뀌었나
  id · type · effective_date · from[] · to[] · evidence[] · label
  type: rename | promotion | transfer | split | merge |
        boundary_change | created | abolished

geo_relation 그래서 비교해도 되는가
  territorial_continuity
  comparison_capability: direct | aggregated | reaggregated | context_only | unknown
```

`admin_unit`과 `electoral_district`는 **같은 인프라를 쓰되 namespace를 분리한다.**
이천군→이천시(행정구역)와 하남시→하남시갑·을(선거구)은 같은 문법이지만 섞이면 안 된다.

## comparison_capability — event type에서 기계적으로 결정하지 않는다

| 등급 | 뜻 | 조건 |
|---|---|---|
| `direct` | 그대로 비교 | 영역이 사실상 같다 (개명·승격·상위지역 편입) |
| `aggregated` | 전신들을 합산해 비교 | 전신 **전체**가 후신에 정확히 포함된다 |
| `reaggregated` | 하위 실측 득표로 재집계 | 읍면동·투표구 **실제 득표**가 있다 |
| `context_only` | 결과는 보여주되 delta 없음 | 계보는 알지만 정확 재집계 불가 |
| `unknown` | 비교 보류 | 관계 자체가 불확실 |

`merge`라도 자료가 부족하면 `context_only`이고, `promotion`이라도 경계가 동시에
바뀌었다면 자동 `direct`가 아니다. **type과 capability는 다른 축이다.**

`reaggregated`는 하위 단위 **실측 득표 provenance가 있을 때만** 허용한다.
인구비례·면적비례로 표를 나누는 것은 하지 않는다 — 그건 추정이지 재집계가 아니다.

## 지금 담긴 것

전국 행정구역사를 먼저 만들지 않는다. **현재 polis 데이터가 실제로 만나는 변화부터**
역으로 채운다. 첫 vertical slice는 네 가지 관계 유형이다:

| 사례 | type | kind | capability |
|---|---|---|---|
| 이천군 → 이천시 | `promotion` | admin_unit | `direct` |
| 경북 군위군 → 대구 군위군 | `transfer` | admin_unit | `direct` |
| 하남시 → 하남시갑·을 | `split` | electoral_district | `context_only` |
| 부천시갑·정 → 부천시갑 | `merge` | electoral_district | `context_only` |

## containment — 합산을 허락하는 근거

결과 집계 단위가 우리 '지역'보다 잘게 나올 때가 있다. 대통령·광역단체장·교육감은
성남시가 아니라 수정구·중원구·분당구로 개표되고, 5·6·7대 대선은 서울 5개 구를
국회의원 선거구(동대문갑구·을구)로 나눠 집계한다. 그 값을 상위 단위로 합치려면
**하위가 상위를 남김없이 나눈다**는 사실이 필요하다. 그 사실이 여기 있다.

없을 때 무슨 일이 나는지는 이미 겪었다. 접지 않아 성남시 페이지에 광역단체장이
0건이었고, '동대문갑구'가 실재하지 않는 지역 페이지가 됐다.

| 필드 | 뜻 |
|---|---|
| `exhaustive` | true일 때만 children의 합을 parent로 쓴다. 일부만 아는 포함관계는 false |
| `aggregation` | `sum` — 득표·선거인수를 더한다 |
| `children_kind` | `admin_unit`(일반구, 실재하는 곳이라 제 페이지를 갖는다) / `electoral_district`(개표만 선거구로 나온 것 — 장소가 아니므로 페이지를 만들지 않는다) |
| `date_basis` | `statutory`(법령 시행일, 사람이 확인) / `observed`(우리 자료에서 그 구성이 처음 관측된 선거일 — **법령 시행일이 아니다**) |
| `caveat` | 검증이 어긋난 회차와 그것이 왜 무해한지 |

`date_basis`를 나눈 이유: 모르는 날짜를 지어내지 않기 위해서다. 합산 여부는 날짜가
아니라 **그 회차에 그 키가 실제로 나왔는지**로 정하므로, observed 날짜가 법령일보다
늦어도 결과가 틀리지 않는다.

`children_kind`는 이름 모양이 아니라 **어떤 scope로 등장하는가**로 가른다. 모양은
사실을 모른다 — '부천시오정구'의 정을 선거구 정으로 읽어 '부천시오구'를 만든 적이
있고, '성남시중원구·분당구'(국회의원 선거구)를 일반구로 센 적이 있다.

### 주장은 매번 다시 센다

`exhaustive: true`는 사실 주장이고, 그 위에서 지역 페이지가 득표를 합산한다. 틀리면
없던 숫자가 만들어진다. `scripts/audit/verify_containment.py`가 게이트마다 두 산술로
확인한다:

1. **시도 총합 무모순** — 그 회차의 Σ(시군구 electors) == 시도 electors.
   겹치면 초과하고 빠지면 모자란다. 350건 오차 0.
2. **상위 앵커 일치** — 같은 회차에 상위 단위 직접 행이 있으면
   Σ(children) == 상위. 오차 0.

②가 불가능한 기록이 13건 있다(옛 대선의 선거구 개표는 상위 단위 행이 없다).
검증기는 그것을 따로 세어 출력한다 — '확인했다'와 '확인할 수 없었다'를 같은 칸에
쓰지 않는다.

## 출력

- `entities.json` · `events.json` — 사람이 읽을 수 있는 형태
- 지역 타임라인·총선 비교·검색이 전부 여기서 파생한다
