// 세 레인 동시 재생 — 대선·총선·지선 지도가 같은 연도축을 따라 함께 흐른다.
//
// 프레임은 **이미 있는 PNG**다(og/maps/). 새로 그리지 않는다 — 이 사이트가 회차마다
// 찍어 둔 지도를 연도순으로 넘길 뿐이다. 그래서 재생 중에 렌더 비용이 0이다.
//
// ⚠️ 같은 해에 어느 계열의 선거가 없으면 **직전 결과를 유지한다.** 비우면 '그때 그
// 자리가 비어 있었다'로 읽히는데, 실제로는 직전에 뽑힌 사람들이 계속 그 자리에
// 있었다. 재생의 요점이 '그 시점에 세 자리를 누가 갖고 있었나'다.
//
// ⚠️ 간선을 건너뛰지 않는다. 유신 시기 대선을 빼면 그 시기에 선거가 없었던 것처럼
// 보인다 — 지도 대신 선거인단 점그리드를 쓰고 그렇다고 캡션에 적는다.
(function () {
  'use strict';
  const host = document.getElementById('tl-play');
  if (!host) return;

  const STEP_MS = 900;
  let data = null, years = [], cur = 0, timer = null;

  function frameAt(lane, year) {
    let last = null;
    for (const f of lane.frames) {
      if (f.date.slice(0, 4) > year) break;
      last = f;                       // 그 해까지 치러진 마지막 선거 = 지금 그 자리
    }
    return last;
  }

  function paint() {
    const y = years[cur];
    host.querySelector('.tl-year').textContent = y;
    host.querySelectorAll('.tl-lane').forEach((el, i) => {
      const f = frameAt(data.lanes[i], y);
      const img = el.querySelector('img');
      const cap = el.querySelector('.tl-cap');
      const box = el.querySelector('.tl-none');
      // 그림이 없는 두 경우를 **다르게** 말한다: 아직 그 선거가 없던 때(지선은
      // 1995년 첫 동시지방선거 전)와, 치렀지만 지역별 결과가 없는 때(간선).
      if (!f) {
        img.hidden = true; box.hidden = false;
        box.textContent = data.lanes[i].first || '아직 없음';
        cap.textContent = '';
        return;
      }
      if (f.img) {
        img.hidden = false; box.hidden = true;
        if (img.getAttribute('src') !== f.img) img.src = f.img;
      } else {
        img.hidden = true; box.hidden = false;
        box.textContent = f.note || '그림 없음';
      }
      cap.textContent = `${f.name} · ${f.date}` + (f.note ? ` · ${f.note}` : '');
    });
    const sl = host.querySelector('.tl-slider');
    if (sl && +sl.value !== cur) sl.value = cur;
  }

  function stop() {
    if (timer) { clearInterval(timer); timer = null; }
    host.querySelector('.tl-play-btn').textContent = '▶ 재생';
  }
  function play() {
    if (timer) return stop();
    if (cur >= years.length - 1) cur = 0;
    host.querySelector('.tl-play-btn').textContent = '⏸ 멈춤';
    timer = setInterval(() => {
      cur++;
      if (cur >= years.length) { cur = years.length - 1; paint(); stop(); return; }
      paint();
    }, STEP_MS);
  }

  getJson('data/election_timelapse.json', null).then((d) => {
    if (!d || !d.lanes) { host.remove(); return; }
    data = d;
    const y0 = +d.years[0], y1 = +d.years[1];
    for (let y = y0; y <= y1; y++) years.push(String(y));
    // 각 레인의 '언제부터'를 미리 적어 둔다 — 빈 칸에 이유를 쓰기 위해서.
    for (const L of d.lanes) {
      const f0 = L.frames && L.frames[0];
      L.first = f0 ? `${f0.date.slice(0, 4)}년 첫 선거 이전` : '자료 없음';
    }
    cur = years.length - 1;           // 처음엔 '지금'을 보여준다
    host.innerHTML =
      '<div class="tl-bar">'
      + '<button type="button" class="tl-play-btn">▶ 재생</button>'
      + `<input type="range" class="tl-slider" min="0" max="${years.length - 1}" value="${cur}" aria-label="연도">`
      + '<span class="tl-year"></span></div>'
      + '<div class="tl-lanes">'
      + d.lanes.map((L) =>
        `<figure class="tl-lane"><figcaption class="tl-lane-name">${L.name}`
        + `<span class="tl-lane-means">${L.means}</span></figcaption>`
        + '<img alt="" loading="lazy" decoding="async">'
        + '<div class="tl-none" hidden></div>'
        + '<figcaption class="tl-cap"></figcaption></figure>').join('')
      + '</div>';
    host.querySelector('.tl-play-btn').addEventListener('click', play);
    host.querySelector('.tl-slider').addEventListener('input', (e) => {
      stop(); cur = +e.target.value; paint();
    });
    paint();
  }).catch(() => host.remove());
})();
