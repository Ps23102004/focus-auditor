/* Spring physics + choreography. Vanilla, no deps. Animates transform/opacity only (text for countUp). */
(function (root) {
  'use strict';
  const TAU = Math.PI * 2;
  const raf = (f) => (root.requestAnimationFrame ? root.requestAnimationFrame(f) : setTimeout(() => f(now()), 16));
  const now = () => (root.performance ? root.performance.now() : Date.now());

  // Analytic damped-spring step (exact for any dt, so retargeting never jumps).
  // state {x, v, to}; params {damping (ratio), response (seconds)}.
  function step(state, params, dt) {
    const { x, v, to } = state;
    if (!(dt > 0)) return { x, v, to };
    const z = params.damping == null ? 1 : params.damping;
    const w = TAU / (params.response == null ? 0.35 : params.response);
    const d = x - to;
    const e = Math.exp(-z * w * dt);
    let nx, nv;
    if (Math.abs(z - 1) < 1e-9) {
      const c = v + w * d;
      nx = (d + c * dt) * e;
      nv = (v - w * c * dt) * e;
    } else if (z < 1) {
      const wd = w * Math.sqrt(1 - z * z), a = z * w, b = (v + a * d) / wd;
      const cs = Math.cos(wd * dt), sn = Math.sin(wd * dt);
      nx = e * (d * cs + b * sn);
      nv = e * (-a * (d * cs + b * sn) + (-d * wd * sn + b * wd * cs));
    } else {
      const wd = w * Math.sqrt(z * z - 1), a = z * w, b = (v + a * d) / wd;
      const ch = Math.cosh(wd * dt), sh = Math.sinh(wd * dt);
      nx = e * (d * ch + b * sh);
      nv = e * (-a * (d * ch + b * sh) + (d * wd * sh + b * wd * ch));
    }
    return { x: to + nx, v: nv, to };
  }

  function spring(opts, onUpdate, onDone) {
    const p = { damping: opts.damping == null ? 1 : opts.damping, response: opts.response == null ? 0.35 : opts.response };
    const eps = opts.eps == null ? 0.002 : opts.eps;
    let s = { x: opts.from, v: opts.velocity || 0, to: opts.to };
    let id = 0, last = 0, settled = false;
    function frame(t) {
      id = 0;
      const dt = Math.min(Math.max((t - last) / 1000, 0), 1 / 30);
      last = t;
      s = step(s, p, dt);
      if (Math.abs(s.v) < eps && Math.abs(s.x - s.to) < eps) {
        s = { x: s.to, v: 0, to: s.to };
        settled = true;
        if (onUpdate) onUpdate(s.x);
        if (onDone) onDone();
        return;
      }
      if (onUpdate) onUpdate(s.x);
      id = raf(frame);
    }
    function start() { settled = false; last = now(); if (!id) id = raf(frame); }
    start();
    return {
      retarget(to, velocity, params) {
        s = { x: s.x, v: velocity === undefined ? s.v : velocity, to };
        if (params) Object.assign(p, params);
        if (settled || !id) start();
      },
      stop() { if (id && root.cancelAnimationFrame) root.cancelAnimationFrame(id); id = 0; settled = true; },
      value: () => s.x,
      velocity: () => s.v,
    };
  }

  const project = (v, decel = 0.998) => (v / 1000) * decel / (1 - decel);
  const rubberband = (over, dim, c = 0.55) => (over <= 0 ? 0 : (1 - 1 / ((over * c) / dim + 1)) * dim);
  const reduced = () => !!(root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches);

  function fade(el) {
    el.style.transition = 'opacity 120ms linear';
    el.style.opacity = '0';
    raf(() => { el.style.opacity = '1'; });
    setTimeout(() => { el.style.transition = ''; el.style.opacity = ''; }, 200);
  }

  function countUp(el, to, opts = {}) {
    const from = opts.from == null ? 0 : opts.from;
    const fmt = opts.format || ((n) => String(n));
    el.dataset.count = String(to);
    el.setAttribute('aria-label', fmt(to));
    if (reduced() || from === to) { el.textContent = fmt(to); return null; }
    el.textContent = fmt(from);
    return spring({ from, to, damping: 0.9, response: 0.6 }, (v) => { el.textContent = fmt(Math.round(v)); },
      () => { el.textContent = fmt(to); });
  }

  function stagger(elements, { step: gap = 50, distance = 12 } = {}) {
    const list = Array.from(elements);
    if (reduced()) { list.forEach(fade); return []; }
    return list.map((el, i) => {
      el.style.opacity = '0';
      el.style.transform = `translateY(${distance}px)`;
      const h = { timer: 0, spring: null };
      h.timer = setTimeout(() => {
        h.spring = spring({ from: 0, to: 1, response: 0.45 }, (p) => {
          el.style.opacity = String(p);
          el.style.transform = `translateY(${(1 - p) * distance}px)`;
        }, () => { el.style.opacity = ''; el.style.transform = ''; });
      }, i * gap);
      return h;
    });
  }

  // Point at arc length s along a polyline (clamped).
  function pathAt(points, cum, s) {
    if (s <= 0) return points[0];
    for (let i = 1; i < points.length; i++) {
      if (s <= cum[i]) {
        const t = (s - cum[i - 1]) / ((cum[i] - cum[i - 1]) || 1);
        return { x: points[i - 1].x + (points[i].x - points[i - 1].x) * t, y: points[i - 1].y + (points[i].y - points[i - 1].y) * t };
      }
    }
    return points[points.length - 1];
  }

  const balls = new WeakMap(); // ball element -> {x, y, ctl}
  const place = (b, el, ox = 0, oy = 0) => el.setAttribute('transform', `translate(${b.x + ox} ${b.y + oy})`);

  // Move an SVG circle along a polyline: one spring on arc length, retargeted at each waypoint so velocity carries
  // through corners. opts: {speed px/s, from:'current'|'start', onArrive(i), walls:[{dir:[dx,dy], count}], onDone}
  function travel(ball, points, opts = {}) {
    let b = balls.get(ball);
    if (!b) { b = { x: points[0].x, y: points[0].y, ctl: null }; balls.set(ball, b); ball.setAttribute('cx', '0'); ball.setAttribute('cy', '0'); }
    if (b.ctl) b.ctl.stop();
    if (reduced() || !points.length) { b.ctl = null; return { stop() {} }; }
    const pts = opts.from === 'start' || b.x == null ? points.slice() : [{ x: b.x, y: b.y }].concat(points);
    if (opts.from === 'start') { b.x = pts[0].x; b.y = pts[0].y; }
    const cum = [0];
    for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y));
    const speed = opts.speed || 900, offset = pts.length - points.length;
    const resp = (i) => Math.min(0.5, Math.max(0.2, (cum[i] - cum[i - 1]) / speed));
    let next = 1, sp = null, dead = false;
    const ctl = { stop() { dead = true; if (sp) sp.stop(); } };
    b.ctl = ctl;
    ball.style.opacity = '1';
    function finish() { if (!dead) bounceWalls(b, ball, opts.walls || [], opts.onDone, ctl); }
    if (pts.length < 2 || cum[cum.length - 1] < 1) { place(b, ball); finish(); return ctl; }
    sp = spring({ from: 0, to: cum[1], damping: 0.9, response: resp(1) }, (s) => {
      const p = pathAt(pts, cum, s);
      b.x = p.x; b.y = p.y; place(b, ball);
      // retarget early at intermediate waypoints so we do not brake at corners
      if (next < pts.length - 1 && cum[next] - s < Math.max(10, 0.12 * (cum[next] - cum[next - 1]))) {
        if (opts.onArrive) opts.onArrive(next - offset);
        next++;
        sp.retarget(cum[next], undefined, { response: resp(next) });
      }
    }, () => {
      if (opts.onArrive) opts.onArrive(pts.length - 1 - offset);
      finish();
    });
    return ctl;
  }

  // "Hits the wall": push 14px into the boundary with rubberband resistance, spring back, twice per wall.
  function bounceWalls(b, ball, walls, onDone, ctl) {
    const dim = 200, want = 14, x = want / (dim - want), over = (x * dim) / 0.55; // raw drag whose rubberband == 14px
    const push = rubberband(over, dim);
    const queue = [];
    walls.forEach((w) => { for (let i = 0; i < (w.count || 2); i++) queue.push(w.dir); });
    function next() {
      if (ctl.stopped || !queue.length) { if (onDone) onDone(); return; }
      const [dx, dy] = queue.shift();
      const sp = spring({ from: 0, to: push, damping: 0.8, response: 0.14 }, (u) => place(b, ball, dx * u, dy * u), () => {
        sp2 = spring({ from: push, to: 0, damping: 0.6, response: 0.22 }, (u) => place(b, ball, dx * u, dy * u), next);
        ctl.stop = () => { sp2.stop(); };
      });
      let sp2 = null;
      ctl.stop = () => { ctl.stopped = true; sp.stop(); if (sp2) sp2.stop(); };
    }
    next();
  }

  const Motion = { step, spring, project, rubberband, reduced, countUp, stagger, travel, pathAt, fade, ballPosition: (el) => balls.get(el) };
  if (typeof module === 'object' && module.exports) module.exports = Motion;
  else root.Motion = Motion;
})(typeof window !== 'undefined' ? window : globalThis);
