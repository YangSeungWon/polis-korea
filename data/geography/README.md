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

## 출력

- `entities.json` · `events.json` — 사람이 읽을 수 있는 형태
- 지역 타임라인·총선 비교·검색이 전부 여기서 파생한다
