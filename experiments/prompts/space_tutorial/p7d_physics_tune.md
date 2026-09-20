Part P7d (gravity tuning) of SIGNAL LOST: System 1. Verified failure: the
autopilot ship ORBIT-LOCKS around the beacon — the star's pull at close
range (beacon is only 22 world units from the star) cancels the seek
constant-speed approach, so no pickup or dock ever completes. The fix is a
per-well DEADZONE: no gravity inside a radius, smooth ramp in beyond it.
Values are spec, not invented: star deadzone 40.0 (covers beacon + all ore
waypoints), planet deadzone 18.0. Beyond deadzone: ramp factor
min(1.0, (dist - deadzone) / 10.0).

Emit EXACTLY these 3 files (full rewrites; info string = path):
1. ```scripts/gravity_well.gd
2. ```scenes/star.tscn
3. ```scenes/planet.tscn

== scripts/gravity_well.gd (extends Area3D) ==
@export var mass: float = 200000.0
@export var deadzone: float = 18.0
_ready(): add_to_group("gravity_well").
func well_pull(from_position: Vector3) -> Vector3:
  dir = position - from_position; dir.z = 0
  dist = max(dir.length(), 8.0)
  if dist <= deadzone: return Vector3.ZERO
  ramp = min(1.0, (dist - deadzone) / 10.0)
  return dir.normalized() * (0.35 * mass / (dist * dist)) * ramp
Sanity: star (mass 900000) at 50u gives 0.35 * 900000 / 2500 = 126 u/s²
full-ramp. At 41.9u, just past its 40u deadzone: ~180 u/s² * 0.19 ramp
≈ 34 u/s². Intended feel: strong at range, harmless near the play space
(THRUST is 420 u/s² for reference).

== scenes/star.tscn ==
As current (gravity_well.gd on Area3D "Star", huge yellow emissive sphere,
CollisionShape3D SphereShape3D) BUT mass = 900000 and deadzone = 40.0
set as instance defaults in the scene.

== scenes/planet.tscn ==
As current (blue emissive sphere) BUT mass = 250000 and deadzone = 18.0.

Godot 4.6, 4-arg colors, correct load_steps, no prose outside fences.
