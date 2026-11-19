// 범위 하나(시작~끝)를 고르는 손잡이 둘짜리 슬라이더.
//
// 실제 <input type=range> 두 개를 한 줄에 겹친다 — 키보드·스크린리더가 그대로 된다.
// 끌 때마다 onInput(from, to)를 부른다(동적 질의: 놓을 때가 아니라 움직이는 동안).
// 연표(연도 범위)가 쓴다.
//
//   const rf = RangeFilter.mount(host, { min, max, step, from, to, label, fmt, onInput })
//   rf.set(from, to)   rf.get() → [from, to]   rf.isFull() → 전체 범위인가
(function () {
  function mount(host, o) {
    const step = o.step || 1;
    const fmt = o.fmt || String;
    host.classList.add('rf');
    host.innerHTML = `<span class="rf-label">${o.label || ''}</span>
      <span class="rf-track"><span class="rf-fill"></span>
        <input type="range" class="rf-lo" min="${o.min}" max="${o.max}" step="${step}" aria-label="${o.label || ''} 시작">
        <input type="range" class="rf-hi" min="${o.min}" max="${o.max}" step="${step}" aria-label="${o.label || ''} 끝">
      </span>
      <output class="rf-out" aria-live="polite"></output>`;
    const lo = host.querySelector('.rf-lo'), hi = host.querySelector('.rf-hi');
    const fill = host.querySelector('.rf-fill'), out = host.querySelector('.rf-out');
    const span = (o.max - o.min) || 1;

    function paint() {
      const a = +lo.value, b = +hi.value;
      fill.style.left = `${((a - o.min) / span) * 100}%`;
      fill.style.right = `${100 - ((b - o.min) / span) * 100}%`;
      out.textContent = isFull() ? (o.fullText || `${fmt(a)} – ${fmt(b)}`) : `${fmt(a)} – ${fmt(b)}`;
      // 두 손잡이가 겹치면 위에 있는 쪽만 잡힌다 — 끝에 몰렸을 때 '시작'을 앞으로.
      lo.style.zIndex = a >= o.max - step ? 3 : '';
    }
    function isFull() { return +lo.value <= o.min && +hi.value >= o.max; }
    function set(a, b) {
      a = Math.max(o.min, Math.min(o.max, a == null ? o.min : +a));
      b = Math.max(o.min, Math.min(o.max, b == null ? o.max : +b));
      if (a > b) [a, b] = [b, a];
      lo.value = a; hi.value = b;
      paint();
    }
    function onMove(e) {
      // 시작이 끝을 넘지 못한다 — 넘으면 움직인 쪽을 멈춘다.
      if (+lo.value > +hi.value) {
        if (e.target === lo) lo.value = hi.value; else hi.value = lo.value;
      }
      paint();
      if (o.onInput) o.onInput(+lo.value, +hi.value);
    }
    lo.addEventListener('input', onMove);
    hi.addEventListener('input', onMove);
    set(o.from, o.to);
    return { set, get: () => [+lo.value, +hi.value], isFull };
  }

  window.RangeFilter = { mount };
})();
