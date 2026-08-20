// 신뢰 상태 UI — docs/trust-states.md 스펙 구현.
//
// 이 UI는 '데이터가 얼마나 믿을 만한가'를 평가하지 않는다. '이 숫자가 무엇이고 어디서
// 왔으며 어느 생애주기에 있는가'를 설명한다. 그래서 잠정·추정·무투표·출구조사에
// 좋음/나쁨의 뉘앙스를 붙이지 않는다.
//
// 만능 badge를 만들지 않는다. 개념이 다른 셋을 분리한다:
//   DatasetProvenance  확정/잠정 · 출처 · 발표시각 · 모집단   → 섹션 제목 아래 한 줄
//   FieldProvenance    polis 계산 / 추정 / 자동 분류          → 그 값 옆 칩
//   DomainFact         무투표 등                              → 신뢰가 아니라 사실
//
// renderer가 원시 _meta를 직접 읽지 않는다. derive*()가 표현 모델로 바꾼 뒤 render*()가
// 그린다. _meta 필드명이 바뀌어도 derive만 고치면 된다.
(function () {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  // 내부 source 코드 → 사용자에게 보일 이름. 모르는 값은 그대로 두지 않고 버린다
  // (내부 식별자가 화면에 새는 것보다 출처를 안 보이는 편이 낫다).
  const SOURCE_LABEL = {
    'nec-openapi': 'NEC OpenAPI',
    'nec-live-portal': 'NEC 실시간',
    'nec-openapi-ElecPrmsInfoInqireService': 'NEC 선거공약 API',
    'nec-vccp09-개표현황': 'NEC 개표현황',
  };

  function sourceLabel(raw) {
    if (!raw) return null;
    if (SOURCE_LABEL[raw]) return SOURCE_LABEL[raw];
    if (/NESDC/i.test(raw)) return 'NESDC 등록 조사';
    if (/^https?:/.test(raw)) return null;
    return raw.length <= 24 ? raw : null;
  }

  function fmtTime(iso) {
    if (!iso) return null;
    const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (!m) return String(iso).slice(0, 10) || null;
    return `${+m[2]}. ${+m[3]}. ${m[4]}:${m[5]}`;
  }

  // ── DatasetProvenance ─────────────────────────────────────────────────────
  // 확정/잠정은 **선거 결과에만** 붙인다. 출구조사에 '확정'을 쓰면 사용자는 '이 결과가
  // 확정됐다'로 읽는데, 실제 의미는 '발표값이 더 안 바뀐다'일 뿐 예측은 확정이 아니다.
  // data_type이 exit_poll이거나 is_final이 아예 없으면 lifecycle을 만들지 않는다.
  function deriveDataset(meta, opts) {
    meta = meta || {};
    opts = opts || {};
    const type = meta.data_type || opts.dataType || null;
    const resultLike = !type || type === 'election_result';

    let lifecycle = null;
    if (resultLike && typeof meta.is_final === 'boolean') {
      lifecycle = meta.is_final ? 'final' : 'provisional';
    }
    // 진행도는 잠정일 때만 뜻이 있다. 확정본의 count_pct는 무투표 race의 100뿐이라
    // '개표 100%'를 붙이면 없는 정보를 있는 것처럼 보이게 한다.
    let progress = null;
    if (lifecycle === 'provisional' && typeof opts.countPct === 'number' && opts.countPct < 100) {
      progress = `개표 ${opts.countPct.toFixed(1)}%`;
    }
    // 개표율과 같은 이유로 확정본에는 붙이지 않는다. '확정 · 58곳 일부 집계 중'은
    // 그 자체로 모순이다 — 확정은 개표가 끝났다는 뜻이다. 개표율 쪽만 막혀 있어
    // 이쪽으로 같은 모순이 샜다.
    let incomplete = null;
    if (lifecycle !== 'final' && opts.pendingCount) {
      incomplete = `${opts.pendingCount.toLocaleString()}곳 일부 집계 중`;
    }
    return {
      lifecycle,
      sourceLabel: opts.sourceLabel || sourceLabel(meta.source) || null,
      progress,
      incomplete,
      publishedAt: fmtTime(meta.published_at || (lifecycle === 'provisional' ? meta.fetched_at : null)),
      scopeLabel: opts.scopeLabel
        || (meta.roster_scope === 'all_candidates' ? '등록 후보 전체'
          : meta.roster_scope === 'winners_only' ? '당선인만' : null),
    };
  }

  const LIFECYCLE_TEXT = { final: '확정', provisional: '잠정' };

  function renderDataset(model) {
    if (!model) return '';
    const bits = [];
    if (model.lifecycle) {
      bits.push(`<b class="tr-life tr-${model.lifecycle}">${LIFECYCLE_TEXT[model.lifecycle]}</b>`);
    }
    if (model.progress) bits.push(esc(model.progress));
    if (model.sourceLabel) bits.push(esc(model.sourceLabel));
    if (model.publishedAt) bits.push(`${esc(model.publishedAt)} 발표`);
    if (model.scopeLabel) bits.push(esc(model.scopeLabel));
    if (model.incomplete) bits.push(esc(model.incomplete));
    if (!bits.length) return '';
    return `<p class="tr-line">${bits.join(' · ')}</p>`;
  }

  // ── FieldProvenance ───────────────────────────────────────────────────────
  // 값 하나에 붙는다. 섹션 전체를 오염시키지 않는다 — 공약 분야 2,909건이 추정이라고
  // 회차 전체가 '추정'이 되면 안 된다.
  const FIELD = {
    calculated: ['polis 계산', '원자료에서 polis가 계산한 값입니다.'],
    estimated: ['polis 추정', '원자료에 없어 polis가 규칙으로 보완한 값입니다.'],
    autoClassified: ['polis 자동 분류', '원자료에 분류가 없어 polis가 자동 분류한 값입니다.'],
  };

  function fieldChip(kind, note) {
    const f = FIELD[kind];
    if (!f) return '';
    return `<span class="tr-chip" title="${esc(note || f[1])}">${esc(f[0])}</span>`;
  }

  // ── DomainFact ────────────────────────────────────────────────────────────
  // 신뢰 상태가 아니다. 무투표는 데이터가 부실한 게 아니라 투표가 없었던 것이다.
  // 앞으로 후보 사퇴·단독 출마 같은 게 생겨도 여기 두고 provenance와 섞지 않는다.
  const FACT = {
    uncontested: ['무투표', '후보가 정수 이하라 투표 없이 당선됐습니다. 선거인수·투표율이 없습니다.'],
  };

  function domainFact(kind) {
    const f = FACT[kind];
    if (!f) return '';
    return `<span class="tr-fact" title="${esc(f[1])}">${esc(f[0])}</span>`;
  }

  // 부모 scope에 공통 provenance를 두고, 자식 섹션에는 **다른 사실만** 남긴다.
  // 같은 'NEC OpenAPI 확정'이 섹션마다 반복되면 정보가 아니라 잡음이 된다.
  // 부모와 같은 값이면 자식 줄을 지우고, 다른 게 있으면 그 차이만 낸다.
  function mountGroup(groupEl, parentModel, childOverrides) {
    if (!groupEl || !parentModel) return;
    const title = groupEl.querySelector('.ar-group-title');
    if (title) {
      let el = groupEl.querySelector(':scope > .tr-line');
      const html = renderDataset(parentModel);
      if (html) {
        if (!el) { el = document.createElement('p'); el.className = 'tr-line'; title.after(el); }
        el.outerHTML = html;
      }
    }
    for (const [id, model] of Object.entries(childOverrides || {})) {
      const diff = onlyDifferent(parentModel, model);
      mount(id, diff);
    }
  }

  // 부모와 다른 항목만 남긴 모델. 전부 같으면 null → 자식 줄을 안 그린다.
  function onlyDifferent(parent, child) {
    if (!child) return null;
    const out = {};
    let any = false;
    for (const k of ['lifecycle', 'sourceLabel', 'progress', 'publishedAt', 'scopeLabel', 'incomplete']) {
      if (child[k] && child[k] !== parent[k]) { out[k] = child[k]; any = true; }
    }
    return any ? out : null;
  }

  // 섹션 제목 바로 아래에 한 줄을 넣는다(있으면 교체).
  function mount(sectionId, model) {
    const sec = document.getElementById(sectionId);
    if (!sec) return;
    const html = renderDataset(model);
    let el = sec.querySelector(':scope > .tr-line');
    if (!html) { if (el) el.remove(); return; }
    const title = sec.querySelector('.ar-section-title');
    if (!el) {
      el = document.createElement('p');
      el.className = 'tr-line';
      title ? title.after(el) : sec.prepend(el);
    }
    el.outerHTML = html;
  }

  window.Trust = { deriveDataset, renderDataset, fieldChip, domainFact, mount,
    mountGroup, onlyDifferent, sourceLabel };
})();
