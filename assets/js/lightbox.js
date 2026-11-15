// 文章图片灯箱：点击正文图片弹出全屏浮层，可按钮 / 滚轮 / 双指缩放、拖拽平移。
// 仅在 front matter 设了 `lightbox: true` 的文章页加载（见 layouts/single.html）。
(() => {
  const imgs = document.querySelectorAll('.post-content img');
  if (!imgs.length) return;

  const MAX_SCALE = 4;   // 最大放大到原图像素的 4 倍
  const STEP = 1.5;      // 按钮 / 键盘每次缩放的倍率

  const icon = (d) => `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
  const box = document.createElement('div');
  box.className = 'lb';
  box.hidden = true;
  box.setAttribute('role', 'dialog');
  box.setAttribute('aria-modal', 'true');
  box.innerHTML = `
    <div class="lb-stage"><img class="lb-img" alt="" draggable="false"></div>
    <div class="lb-caption"></div>
    <div class="lb-bar">
      <button type="button" data-act="out" aria-label="缩小" title="缩小（-）">${icon('<path d="M5 12h14"/>')}</button>
      <button type="button" data-act="actual" class="lb-pct" title="原始大小（1）">100%</button>
      <button type="button" data-act="in" aria-label="放大" title="放大（+）">${icon('<path d="M12 5v14M5 12h14"/>')}</button>
      <button type="button" data-act="fit" aria-label="适应屏幕" title="适应屏幕（0）">${icon('<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>')}</button>
    </div>
    <button type="button" data-act="close" class="lb-close" aria-label="关闭" title="关闭（Esc）">${icon('<path d="M6 6l12 12M18 6L6 18"/>')}</button>`;
  document.body.appendChild(box);

  const stage = box.querySelector('.lb-stage');
  const view = box.querySelector('.lb-img');
  const caption = box.querySelector('.lb-caption');
  const pct = box.querySelector('.lb-pct');
  const btnIn = box.querySelector('[data-act="in"]');
  const btnOut = box.querySelector('[data-act="out"]');

  // w/h：原图尺寸；s：当前缩放；x/y：图片左上角在视口里的位置；fit：适应屏幕时的缩放
  let w = 0, h = 0, s = 1, x = 0, y = 0, fit = 1;

  function fitScale() {
    return Math.min(1, (stage.clientWidth - 48) / w, (stage.clientHeight - 150) / h);
  }

  // 图片比视口小的方向居中，比视口大的方向不让边缘拖进视口内
  function clamp() {
    const vw = stage.clientWidth, vh = stage.clientHeight;
    const iw = w * s, ih = h * s;
    x = iw <= vw ? (vw - iw) / 2 : Math.min(0, Math.max(vw - iw, x));
    y = ih <= vh ? (vh - ih) / 2 : Math.min(0, Math.max(vh - ih, y));
  }

  function render(animate) {
    clamp();
    view.style.transition = animate ? 'transform .2s ease-out' : 'none';
    view.style.transform = `translate(${x}px, ${y}px) scale(${s})`;
    view.classList.toggle('lb-pixel', s > 1);
    pct.textContent = `${Math.round(s * 100)}%`;
    btnOut.disabled = s <= fit + 1e-6;
    btnIn.disabled = s >= MAX_SCALE - 1e-6;
  }

  // 以视口坐标 (cx, cy) 为中心缩放到 ns
  function zoomTo(ns, cx = stage.clientWidth / 2, cy = stage.clientHeight / 2, animate = false) {
    ns = Math.min(MAX_SCALE, Math.max(fit, ns));
    x = cx - (cx - x) * ns / s;
    y = cy - (cy - y) * ns / s;
    s = ns;
    render(animate);
  }

  function reset(animate) {
    fit = fitScale();
    s = fit;
    render(animate);
  }

  // 图片的 alt，没有就用它上方最近的小标题
  function captionFor(img) {
    if (img.alt) return img.alt;
    let el = img;
    while (el.parentElement && !el.parentElement.classList.contains('post-content')) el = el.parentElement;
    for (el = el.previousElementSibling; el; el = el.previousElementSibling) {
      if (/^H[2-4]$/.test(el.tagName)) return el.textContent.replace(/\s*#\s*$/, '').trim();
    }
    return '';
  }

  function open(img) {
    caption.textContent = captionFor(img);
    view.onload = null;
    view.style.visibility = 'hidden';
    // 图片组里的是缩略图，原图地址在 data-full
    view.src = img.dataset.full || img.currentSrc || img.src;
    box.hidden = false;
    document.documentElement.classList.add('lb-open');
    const start = () => {
      w = view.naturalWidth;
      h = view.naturalHeight;
      reset(false);
      view.style.visibility = '';
    };
    if (view.complete && view.naturalWidth) start();
    else view.onload = start;
    box.querySelector('.lb-close').focus({ preventScroll: true });
  }

  function close() {
    box.hidden = true;
    document.documentElement.classList.remove('lb-open');
  }

  imgs.forEach((img) => {
    img.classList.add('lb-zoomable');
    img.addEventListener('click', () => open(img));
  });

  box.addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === 'in') zoomTo(s * STEP, undefined, undefined, true);
    else if (act === 'out') zoomTo(s / STEP, undefined, undefined, true);
    else if (act === 'actual') zoomTo(1, undefined, undefined, true);
    else if (act === 'fit') reset(true);
    else if (act === 'close') close();
  });

  // 拖拽平移、双指缩放、点背景关闭、双击在「原始大小」和「适应屏幕」间切换
  const pts = new Map();
  let moved = 0, downOnBackdrop = false, lastTap = null;

  stage.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    stage.setPointerCapture(e.pointerId);
    if (!pts.size) {
      moved = 0;
      downOnBackdrop = e.target === stage;
    }
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    stage.classList.add('lb-grabbing');
  });

  stage.addEventListener('pointermove', (e) => {
    const p = pts.get(e.pointerId);
    if (!p) return;
    if (pts.size === 1) {
      x += e.clientX - p.x;
      y += e.clientY - p.y;
      moved += Math.abs(e.clientX - p.x) + Math.abs(e.clientY - p.y);
      p.x = e.clientX;
      p.y = e.clientY;
      render(false);
    } else if (pts.size === 2) {
      const [a, b] = [...pts.values()];
      const d0 = Math.hypot(a.x - b.x, a.y - b.y);
      const m0 = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
      p.x = e.clientX;
      p.y = e.clientY;
      const d1 = Math.hypot(a.x - b.x, a.y - b.y);
      const m1 = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
      x += m1.x - m0.x;
      y += m1.y - m0.y;
      moved += 100;
      if (d0 > 0) zoomTo(s * d1 / d0, m1.x, m1.y);
    }
  });

  function pointerEnd(e) {
    if (!pts.delete(e.pointerId) || pts.size) return;
    stage.classList.remove('lb-grabbing');
    if (e.type !== 'pointerup' || moved > 5) return;
    if (downOnBackdrop) {
      close();
      return;
    }
    const now = Date.now();
    if (lastTap && now - lastTap.t < 300 && Math.hypot(e.clientX - lastTap.x, e.clientY - lastTap.y) < 30) {
      lastTap = null;
      if (s < 1 - 1e-6) zoomTo(1, e.clientX, e.clientY, true);
      else reset(true);
    } else {
      lastTap = { t: now, x: e.clientX, y: e.clientY };
    }
  }
  stage.addEventListener('pointerup', pointerEnd);
  stage.addEventListener('pointercancel', pointerEnd);

  // 滚轮缩放；触控板捏合会带 ctrlKey 且 delta 很小，系数放大些
  stage.addEventListener('wheel', (e) => {
    e.preventDefault();
    const delta = e.deltaY * (e.deltaMode === 1 ? 16 : 1);
    zoomTo(s * Math.exp(-delta * (e.ctrlKey ? 0.01 : 0.0015)), e.clientX, e.clientY);
  }, { passive: false });

  document.addEventListener('keydown', (e) => {
    if (box.hidden) return;
    const pan = { ArrowLeft: [80, 0], ArrowRight: [-80, 0], ArrowUp: [0, 80], ArrowDown: [0, -80] }[e.key];
    if (e.key === 'Escape') close();
    else if (e.key === '+' || e.key === '=') zoomTo(s * STEP, undefined, undefined, true);
    else if (e.key === '-' || e.key === '_') zoomTo(s / STEP, undefined, undefined, true);
    else if (e.key === '0') reset(true);
    else if (e.key === '1') zoomTo(1, undefined, undefined, true);
    else if (pan) {
      x += pan[0];
      y += pan[1];
      render(true);
    } else return;
    e.preventDefault();
  });

  window.addEventListener('resize', () => {
    if (box.hidden) return;
    const wasFit = s <= fit + 1e-6;
    fit = fitScale();
    if (wasFit || s < fit) s = fit;
    render(false);
  });
})();
