// Reference implementation of contracts/three_camera_fit.md (never given to the crew).

export const DEFAULT_FOV = 50;
export const DEFAULT_MARGIN = 1.1;
export const MIN_RADIUS = 0.001;
export const MAX_ELEVATION = 89;

const DEG = Math.PI / 180;

function isVec3(v) {
  return Array.isArray(v) && v.length === 3 && v.every((n) => Number.isFinite(n));
}

export function boundsOf(points) {
  if (!Array.isArray(points) || points.length === 0) {
    throw new Error("boundsOf needs at least one point");
  }
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const p of points) {
    if (!isVec3(p)) throw new TypeError("every point must be [x, y, z] numbers");
    for (let i = 0; i < 3; i++) {
      min[i] = Math.min(min[i], p[i]);
      max[i] = Math.max(max[i], p[i]);
    }
  }
  return { min, max };
}

export function sphereOf(bounds) {
  const center = [0, 1, 2].map((i) => (bounds.min[i] + bounds.max[i]) / 2);
  const d = [0, 1, 2].map((i) => bounds.max[i] - bounds.min[i]);
  return { center, radius: Math.hypot(d[0], d[1], d[2]) / 2 };
}

export function fitDistance(radius, fovDeg = DEFAULT_FOV, aspect = 1,
  margin = DEFAULT_MARGIN) {
  if (!(radius >= 0)) throw new RangeError("radius must be 0 or more");
  if (!(fovDeg > 0 && fovDeg < 180)) throw new RangeError("fovDeg must be in (0, 180)");
  if (!(aspect > 0)) throw new RangeError("aspect must be above 0");
  if (!(margin > 0)) throw new RangeError("margin must be above 0");
  const vFov = fovDeg * DEG;
  const hFov = 2 * Math.atan(Math.tan(vFov / 2) * aspect);
  return (margin * radius) / Math.sin(Math.min(vFov, hFov) / 2);
}

export function fitCamera(bounds, options = {}) {
  const { fovDeg = DEFAULT_FOV, aspect = 1, direction = [1, 1, 1],
    margin = DEFAULT_MARGIN } = options;
  if (!isVec3(direction)) throw new TypeError("direction must be [x, y, z] numbers");
  const length = Math.hypot(direction[0], direction[1], direction[2]);
  if (length === 0) throw new RangeError("direction cannot be zero");
  const sphere = sphereOf(bounds);
  const radius = Math.max(sphere.radius, MIN_RADIUS);
  const distance = fitDistance(radius, fovDeg, aspect, margin);
  const position = sphere.center.map((c, i) => c + (direction[i] / length) * distance);
  return {
    position,
    target: sphere.center,
    near: Math.max(distance - margin * radius, distance / 1000),
    far: distance + margin * radius,
    distance,
  };
}

export function orbit(target, distance, azimuthDeg, elevationDeg) {
  if (!isVec3(target)) throw new TypeError("target must be [x, y, z] numbers");
  if (!(distance >= 0)) throw new RangeError("distance must be 0 or more");
  const el = Math.max(-MAX_ELEVATION, Math.min(MAX_ELEVATION, elevationDeg)) * DEG;
  const az = azimuthDeg * DEG;
  return [
    target[0] + distance * Math.cos(el) * Math.sin(az),
    target[1] + distance * Math.sin(el),
    target[2] + distance * Math.cos(el) * Math.cos(az),
  ];
}

export function applyTo(camera, fit) {
  camera.position.set(fit.position[0], fit.position[1], fit.position[2]);
  camera.near = fit.near;
  camera.far = fit.far;
  camera.lookAt(fit.target[0], fit.target[1], fit.target[2]);
  camera.updateProjectionMatrix();
  return camera;
}
