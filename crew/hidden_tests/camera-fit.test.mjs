// Hidden tests for camera-fit.js. Every contract row, plus the camera handed to three.js.
import test from "node:test";
import assert from "node:assert/strict";
import * as c from "./camera-fit.js";

const close = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} vs ${b}`);
const closeVec = (a, b, eps = 1e-6) => {
  assert.equal(a.length, 3);
  a.forEach((v, i) => close(v, b[i], eps));
};
const CUBE = { min: [-1, -1, -1], max: [1, 1, 1] };

test("the constants", () => {
  assert.equal(c.DEFAULT_FOV, 50);
  assert.equal(c.DEFAULT_MARGIN, 1.1);
  assert.equal(c.MIN_RADIUS, 0.001);
  assert.equal(c.MAX_ELEVATION, 89);
});

test("boundsOf takes the box around the points", () => {
  assert.deepEqual(c.boundsOf([[-1, -1, -1], [1, 1, 1], [0, 2, 0]]),
    { min: [-1, -1, -1], max: [1, 2, 1] });
  assert.deepEqual(c.boundsOf([[3, 4, 5]]), { min: [3, 4, 5], max: [3, 4, 5] });
});

test("boundsOf refuses nothing and nonsense", () => {
  assert.throws(() => c.boundsOf([]), Error);
  assert.throws(() => c.boundsOf("points"), Error);
  assert.throws(() => c.boundsOf([[1, 2]]), TypeError);
  assert.throws(() => c.boundsOf([[1, 2, NaN]]), TypeError);
  assert.throws(() => c.boundsOf([[1, 2, "3"]]), TypeError);
});

test("boundsOf does not modify the points", () => {
  const points = [[1, 2, 3], [-1, 0, 4]];
  c.boundsOf(points);
  assert.deepEqual(points, [[1, 2, 3], [-1, 0, 4]]);
});

test("sphereOf is the midpoint and half the diagonal", () => {
  const s = c.sphereOf(CUBE);
  assert.deepEqual(s.center, [0, 0, 0]);
  close(s.radius, Math.sqrt(3));
  const t = c.sphereOf({ min: [0, 0, 0], max: [2, 4, 4] });
  assert.deepEqual(t.center, [1, 2, 2]);
  close(t.radius, 3);
});

test("fitDistance: the contract table", () => {
  close(c.fitDistance(1, 60, 1, 1), 2);
  close(c.fitDistance(1, 60, 0.5, 1), 3.605551);
  close(c.fitDistance(2, 90, 2, 1.1), 3.111270);
});

test("fitDistance: a narrow window is limited by its width", () => {
  assert.ok(c.fitDistance(1, 60, 0.5, 1) > c.fitDistance(1, 60, 1, 1));
  // a wide window is limited by its height, so widening it further changes nothing
  close(c.fitDistance(1, 60, 2, 1), c.fitDistance(1, 60, 3, 1));
});

test("fitDistance: defaults and a zero radius", () => {
  close(c.fitDistance(1), 1.1 / Math.sin((50 * Math.PI) / 360));
  assert.equal(c.fitDistance(0, 60, 1, 1), 0);
});

test("fitDistance refuses impossible cameras", () => {
  assert.throws(() => c.fitDistance(-1, 60, 1, 1), RangeError);
  assert.throws(() => c.fitDistance(1, 0, 1, 1), RangeError);
  assert.throws(() => c.fitDistance(1, 180, 1, 1), RangeError);
  assert.throws(() => c.fitDistance(1, 60, 0, 1), RangeError);
  assert.throws(() => c.fitDistance(1, 60, 1, 0), RangeError);
  assert.throws(() => c.fitDistance(Number.NaN, 60, 1, 1), RangeError);
});

test("fitCamera: the contract example", () => {
  const f = c.fitCamera(CUBE, { fovDeg: 60, aspect: 1, direction: [0, 0, 1], margin: 1 });
  closeVec(f.position, [0, 0, 3.464102]);
  assert.deepEqual(f.target, [0, 0, 0]);
  close(f.near, 1.732051);
  close(f.far, 5.196152);
  close(f.distance, 3.464102);
});

test("fitCamera: direction need not be unit length", () => {
  const a = c.fitCamera(CUBE, { direction: [0, 0, 5] });
  const b = c.fitCamera(CUBE, { direction: [0, 0, 1] });
  closeVec(a.position, b.position);
});

test("fitCamera: the default direction is along [1, 1, 1]", () => {
  const f = c.fitCamera(CUBE);
  const d = f.distance / Math.sqrt(3);
  closeVec(f.position, [d, d, d]);
  close(f.distance, c.fitDistance(Math.sqrt(3)));
});

test("fitCamera: the camera stands off the model's centre, not the origin", () => {
  const f = c.fitCamera({ min: [9, 9, 9], max: [11, 11, 11] }, { direction: [1, 0, 0] });
  assert.deepEqual(f.target, [10, 10, 10]);
  closeVec(f.position, [10 + f.distance, 10, 10]);
});

test("fitCamera: a single point still gets a usable camera", () => {
  const f = c.fitCamera({ min: [1, 1, 1], max: [1, 1, 1] }, { direction: [0, 0, 1] });
  close(f.distance, c.fitDistance(c.MIN_RADIUS));
  assert.ok(f.near > 0 && f.far > f.near);
});

test("fitCamera: near never reaches zero, even at a huge field of view", () => {
  const f = c.fitCamera(CUBE, { fovDeg: 179.9, margin: 1 });
  assert.ok(f.near >= f.distance / 1000);
  assert.ok(f.far > f.near);
});

test("fitCamera refuses a bad direction", () => {
  assert.throws(() => c.fitCamera(CUBE, { direction: [0, 0, 0] }), RangeError);
  assert.throws(() => c.fitCamera(CUBE, { direction: [0, 1] }), TypeError);
});

test("orbit: the contract table", () => {
  closeVec(c.orbit([0, 0, 0], 10, 0, 0), [0, 0, 10]);
  closeVec(c.orbit([0, 0, 0], 10, 90, 0), [10, 0, 0]);
  closeVec(c.orbit([1, 2, 3], 10, 0, 90), [1, 11.998477, 3.174524]);
});

test("orbit: below the target, behind it, and the far clamp", () => {
  closeVec(c.orbit([0, 0, 0], 10, 180, 0), [0, 0, -10]);
  closeVec(c.orbit([0, 0, 0], 10, 0, -30), [0, -5, 10 * Math.cos(Math.PI / 6)]);
  closeVec(c.orbit([0, 0, 0], 10, 0, -120), c.orbit([0, 0, 0], 10, 0, -89));
});

test("orbit keeps its distance from the target", () => {
  const p = c.orbit([1, 2, 3], 7, 33, 21);
  close(Math.hypot(p[0] - 1, p[1] - 2, p[2] - 3), 7);
});

test("orbit refuses a bad target or distance", () => {
  assert.throws(() => c.orbit([0, 0], 10, 0, 0), TypeError);
  assert.throws(() => c.orbit([0, 0, 0], -1, 0, 0), RangeError);
});

function fakeCamera() {
  const calls = [];
  const camera = {
    near: 0.1, far: 2000, calls,
    position: { set(x, y, z) { calls.push(["position", x, y, z]); } },
    lookAt(x, y, z) { calls.push(["lookAt", x, y, z, camera.near, camera.far]); },
    updateProjectionMatrix() { calls.push(["project", camera.near, camera.far]); },
  };
  return camera;
}

test("applyTo sets the camera in the order three.js needs", () => {
  const f = c.fitCamera(CUBE, { fovDeg: 60, direction: [0, 0, 1], margin: 1 });
  const camera = fakeCamera();
  const back = c.applyTo(camera, f);
  assert.equal(back, camera);
  assert.deepEqual(camera.calls.map((call) => call[0]), ["position", "lookAt", "project"]);
  assert.deepEqual(camera.calls[0].slice(1), f.position);
  assert.deepEqual(camera.calls[1].slice(1, 4), f.target);
  assert.equal(camera.near, f.near);
  assert.equal(camera.far, f.far);
  // near and far were already set when the projection matrix was rebuilt
  assert.deepEqual(camera.calls[2].slice(1), [f.near, f.far]);
});

test("nothing passed in is modified", () => {
  const bounds = { min: [-1, -1, -1], max: [1, 1, 1] };
  const direction = [0, 2, 0];
  const f = c.fitCamera(bounds, { direction });
  assert.deepEqual(bounds, { min: [-1, -1, -1], max: [1, 1, 1] });
  assert.deepEqual(direction, [0, 2, 0]);
  f.target[0] = 99;
  assert.deepEqual(c.sphereOf(bounds).center, [0, 0, 0]);
});
