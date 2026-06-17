// 인코딩 토글 (공용) — 아이콘 + 두 가족(1위 / 표 비례)을 한 바에 구분자로 묶음.
//   방식(지도/균등/단색/격자/원형)이 곳곳에 흩어진 걸 한 컴포넌트로 통일. 폴·아카이브·역대 공용.
//   EncodingToggle.render(host, { options:[{key,label}], active, onSelect(key) })
//     label = 표시명(아이콘·가족은 label로 매핑). key = 내부 디스패치 값(예 'dorling').
//   가족 게이팅(단독당선=1위만 / 비례·대선=표비례만)은 호출부가 options를 추려 넘김.
(function () {
  // label → { fam: '1위'|'비례', svg: <inner svg markup, currentColor> }
  const ENC = {
    '지도': { fam: '1위', svg: '<path fill="currentColor" d="M2 4l5-2 6 2 5-2v14l-5 2-6-2-5 2V4zm5 0v12l6 2V6L7 4z"/>' },
    '균등': { fam: '1위', svg: '<path fill="currentColor" d="M10 1l7.79 4.5v9L10 19l-7.79-4.5v-9L10 1zm0 2.31L4.21 6.69v6.62L10 16.69l5.79-3.38V6.69L10 3.31z"/>' },
    '단색': { fam: '1위', svg: '<path fill="currentColor" opacity="0.85" d="M10 1l7.79 4.5v9L10 19l-7.79-4.5v-9z"/><path fill="var(--bg,#fff)" opacity="0.35" d="M10 1l7.79 4.5v9L10 19z"/>' },
    '투표율': { fam: '자료', svg: '<path fill="currentColor" opacity="0.85" d="M10 1l7.79 4.5v9L10 19l-7.79-4.5v-9z"/><path fill="var(--bg,#fff)" opacity="0.5" d="M10 1L2.21 5.5v9L10 19z"/>' },
    '격자': { fam: '비례', svg: '<g fill="currentColor"><rect x="2.5" y="2.5" width="6" height="6" rx="1"/><rect x="11.5" y="2.5" width="6" height="6" rx="1" opacity="0.55"/><rect x="2.5" y="11.5" width="6" height="6" rx="1" opacity="0.55"/><rect x="11.5" y="11.5" width="6" height="6" rx="1"/></g>' },
    '원형': { fam: '비례', svg: '<circle cx="10" cy="10" r="8" fill="none" stroke="currentColor" stroke-width="1.5"/><path fill="currentColor" d="M10 10V2a8 8 0 0 1 8 8z"/>' },
  };
  const FAM_LABEL = { '1위': '1위', '비례': '표 비례', '자료': '자료' };

  function iconSvg(label) {
    const e = ENC[label];
    return e ? `<svg class="enc-ic" viewBox="0 0 20 20" width="15" height="15" aria-hidden="true">${e.svg}</svg>` : '';
  }

  function render(host, o) {
    if (!host) return;
    const options = (o.options || []).filter(Boolean);
    const active = o.active;
    // 가족별 그룹(등장 순서 보존, 같은 가족은 한 그룹으로 모음).
    const groups = [];
    for (const op of options) {
      const fam = (ENC[op.label] && ENC[op.label].fam) || '';
      let g = groups.find((x) => x.fam === fam);
      if (!g) { g = { fam, items: [] }; groups.push(g); }
      g.items.push(op);
    }
    // 가족 라벨/구분자는 위계가 실제로 있을 때(둘 이상)만 — 한 가족뿐이면 군더더기라 평범한 아이콘 seg로.
    const showFam = groups.length > 1;
    let html = '';
    groups.forEach((g, gi) => {
      if (gi > 0) html += '<span class="enc-sep" aria-hidden="true"></span>';
      const lbl = showFam ? (FAM_LABEL[g.fam] || g.fam) : '';
      html += `<div class="enc-group">${lbl ? `<span class="enc-fam">${lbl}</span>` : ''}<div class="seg" role="tablist">`;
      for (const op of g.items) {
        const on = op.key === active;
        html += `<button type="button" class="seg-btn${on ? ' is-active' : ''}" role="tab" aria-selected="${on}" data-enc="${op.key}" title="${op.label}">${iconSvg(op.label)}<span>${op.label}</span></button>`;
      }
      html += '</div></div>';
    });
    host.classList.add('enc-toggle');
    host.innerHTML = html;
    host.querySelectorAll('[data-enc]').forEach((b) => b.addEventListener('click', () => {
      host.querySelectorAll('[data-enc]').forEach((x) => { const on = x === b; x.classList.toggle('is-active', on); x.setAttribute('aria-selected', on); });
      if (o.onSelect) o.onSelect(b.dataset.enc);
    }));
  }

  // 외부에서 선택 동기화 (프로그램적 전환·초기 상태). render가 건 클릭과 별개로 active만 갱신.
  function setActive(host, key) {
    if (!host) return;
    host.querySelectorAll('[data-enc]').forEach((b) => {
      const on = b.dataset.enc === key;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-selected', on);
    });
  }

  window.EncodingToggle = { render, setActive, ENC };
})();
