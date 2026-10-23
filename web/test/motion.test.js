// Plain node: node web/test/motion.test.js
const assert = require('assert');
const M = require('../motion.js');

function run(params, t = 3, dt = 1 / 240, state = { x: 0, v: 0, to: 1 }) {
  let s = state, max = s.x;
  for (let i = 0; i < t / dt; i++) { s = M.step(s, params, dt); max = Math.max(max, s.x); }
  return { s, max };
}
const near = (a, b, e = 1e-9) => assert.ok(Math.abs(a - b) <= e, `${a} !~ ${b}`);

// critically damped: no overshoot, settles
let r = run({ damping: 1, response: 0.35 });
assert.ok(r.max <= 1 + 1e-9, 'critically damped overshoot ' + r.max);
near(r.s.x, 1, 1e-3);
// damping 0.8: overshoots then settles
r = run({ damping: 0.8, response: 0.3 });
assert.ok(r.max > 1.001, 'expected overshoot, max=' + r.max);
near(r.s.x, 1, 1e-3);
// overdamped: no overshoot
assert.ok(run({ damping: 1.6, response: 0.35 }).max <= 1 + 1e-9);
// step is dt-independent (analytic): 1 x 0.5s == 50 x 0.01s
const a = M.step({ x: 0, v: 3, to: 1 }, { damping: 0.7, response: 0.4 }, 0.5);
let b = { x: 0, v: 3, to: 1 };
for (let i = 0; i < 50; i++) b = M.step(b, { damping: 0.7, response: 0.4 }, 0.01);
near(a.x, b.x, 1e-9); near(a.v, b.v, 1e-9);

// retarget keeps value and velocity (fake clock + rAF)
let q = [], clock = 0;
globalThis.requestAnimationFrame = (f) => (q.push(f), q.length);
globalThis.cancelAnimationFrame = () => {};
globalThis.performance = { now: () => clock };
const pump = (n) => { for (let i = 0; i < n; i++) { clock += 16; const f = q.splice(0); f.forEach((fn) => fn(clock)); } };
const sp = M.spring({ from: 0, to: 100, damping: 0.8, response: 0.5 }, () => {});
pump(12);
const x0 = sp.value(), v0 = sp.velocity();
assert.ok(v0 > 0 && x0 > 0 && x0 < 100);
sp.retarget(-50);
assert.ok(Math.abs(sp.value() - x0) < 1e-6, 'value jumped on retarget');
assert.ok(Math.abs(sp.velocity() - v0) < 1e-6, 'velocity jumped on retarget');
pump(400);
near(sp.value(), -50, 1e-6);
// retarget after settle restarts
sp.retarget(10); pump(400); near(sp.value(), 10, 1e-6);

// project / rubberband known values
near(M.project(1000), 499, 1e-9);
near(M.project(-500), -249.5, 1e-9);
near(M.rubberband(100, 400), 400 * (0.1375 / 1.1375), 1e-9);
near(M.rubberband(0, 400), 0);
assert.ok(M.rubberband(1e6, 400) < 400 && M.rubberband(200, 400) > M.rubberband(100, 400));

// pathAt
const pts = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }], cum = [0, 10, 20];
assert.deepStrictEqual(M.pathAt(pts, cum, 15), { x: 10, y: 5 });
console.log('motion.test.js: all assertions passed');
