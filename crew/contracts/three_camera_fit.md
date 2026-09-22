# Contract: camera-fit.js — point a three.js camera at what is in the scene

One JavaScript ES module, `camera-fit.js`, holding the camera arithmetic every
three.js scene needs and most get subtly wrong: fit the camera so the whole model is in
view on a screen of any shape, orbit around a target, and hand the result to a real
`THREE.PerspectiveCamera`.

It does **not** import three.js. It works on plain arrays `[x, y, z]`, which is what
lets it be tested anywhere, and `applyTo` takes the camera as an argument - anything
with three.js's camera shape will do.

three.js conventions, which every rule below assumes: **Y is up**, the coordinate
system is right-handed, a camera looks down its own −Z, and `PerspectiveCamera.fov`
is the **vertical** field of view in **degrees**.

## Public API (all of these names must exist)

```js
export const DEFAULT_FOV = 50;       // three.js's own PerspectiveCamera default
export const DEFAULT_MARGIN = 1.1;   // 10% breathing room around the model
export const MIN_RADIUS = 0.001;     // a single point still gets a usable camera
export const MAX_ELEVATION = 89;     // degrees; never exactly overhead

export function boundsOf(points) { }
export function sphereOf(bounds) { }
export function fitDistance(radius, fovDeg = DEFAULT_FOV, aspect = 1, margin = DEFAULT_MARGIN) { }
export function fitCamera(bounds, options = {}) { }
export function orbit(target, distance, azimuthDeg, elevationDeg) { }
export function applyTo(camera, fit) { }
```

No imports at all. No globals: not `window`, not `document`, not `THREE`.

A vector is always an array of exactly three finite numbers. Every function returns
new arrays; nothing passed in is modified, except the camera in `applyTo`.

## boundsOf(points)

The axis-aligned box around a list of points: `{ min: [x, y, z], max: [x, y, z] }`.

- an empty list, or anything that is not an array, throws an `Error`;
- a point that is not three finite numbers throws a `TypeError`.

`boundsOf([[-1, -1, -1], [1, 1, 1], [0, 2, 0]])` → `{ min: [-1, -1, -1], max: [1, 2, 1] }`

## sphereOf(bounds)

The sphere that encloses the box: `{ center, radius }`, where `center` is the box's
midpoint and `radius` is **half the length of the box's diagonal**.

`sphereOf({ min: [-1, -1, -1], max: [1, 1, 1] })` → `{ center: [0, 0, 0], radius: √3 }`
(1.7320508075688772)

## fitDistance(radius, fovDeg, aspect, margin)

How far from a sphere's centre the camera must stand for the whole sphere, grown by
`margin`, to fit on screen.

1. The vertical field of view is `fovDeg` in radians.
2. The horizontal field of view is `2 * atan(tan(vertical / 2) * aspect)`.
3. The limiting angle is the **smaller** of the two - a tall, narrow window is limited
   by its width, which is the case most fitting code forgets.
4. Distance = `margin * radius / sin(limiting / 2)`.

Throws a `RangeError` when `radius` is below 0, `fovDeg` is not strictly between 0 and
180, `aspect` is not above 0, or `margin` is not above 0. A radius of 0 gives 0.

| call | result |
|---|---|
| `fitDistance(1, 60, 1, 1)` | `2` |
| `fitDistance(1, 60, 0.5, 1)` | `3.605551...` (width limits it) |
| `fitDistance(2, 90, 2, 1.1)` | `3.111270...` |

## fitCamera(bounds, options)

Options, all optional: `{ fovDeg = DEFAULT_FOV, aspect = 1, direction = [1, 1, 1],
margin = DEFAULT_MARGIN }`. `direction` is where the camera stands relative to the
model's centre; it need not be unit length.

Returns `{ position, target, near, far, distance }`:

1. `radius` is `sphereOf(bounds).radius`, but never less than `MIN_RADIUS`;
2. `distance` is `fitDistance(radius, fovDeg, aspect, margin)`;
3. `target` is the sphere's centre;
4. `position` is `target + normalised(direction) * distance`;
5. `near` is `max(distance - margin * radius, distance / 1000)`;
6. `far` is `distance + margin * radius`.

`direction` that is not three finite numbers throws a `TypeError`; a zero-length one
throws a `RangeError`.

`fitCamera({ min: [-1, -1, -1], max: [1, 1, 1] }, { fovDeg: 60, aspect: 1,
direction: [0, 0, 1], margin: 1 })` →
`position [0, 0, 3.464102]`, `target [0, 0, 0]`, `near 1.732051`, `far 5.196152`,
`distance 3.464102` (to six places).

## orbit(target, distance, azimuthDeg, elevationDeg)

A camera position on a sphere around `target`, as `[x, y, z]`:

- azimuth 0 puts the camera on **+Z** (in front, looking back at the target); azimuth
  90 puts it on **+X**;
- elevation 0 is level; positive is above. It is clamped to
  `[-MAX_ELEVATION, MAX_ELEVATION]` so a camera using three.js's default up vector never
  looks straight down its own up axis;
- position = `target + distance * [cos(el)·sin(az), sin(el), cos(el)·cos(az)]`.

`target` that is not three finite numbers throws a `TypeError`; a negative `distance`
throws a `RangeError`.

| call | result |
|---|---|
| `orbit([0, 0, 0], 10, 0, 0)` | `[0, 0, 10]` |
| `orbit([0, 0, 0], 10, 90, 0)` | `[10, 0, 0]` |
| `orbit([1, 2, 3], 10, 0, 90)` | `[1, 11.998477, 3.174524]` - clamped to 89° |

## applyTo(camera, fit)

Puts a `fitCamera` result onto a three.js camera, **in this order**, and returns the
camera:

1. `camera.position.set(x, y, z)`
2. `camera.near = fit.near` and `camera.far = fit.far`
3. `camera.lookAt(x, y, z)` with the target
4. `camera.updateProjectionMatrix()`

The order matters: `lookAt` uses the position, and a changed `near`/`far` does nothing
until the projection matrix is rebuilt - forgetting that last call is the most common
three.js camera bug there is.

## Style

See `JS_HOUSE_STYLE.md`, which is part of this contract.
