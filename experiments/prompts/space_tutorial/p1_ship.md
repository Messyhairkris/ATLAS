You are building part P1 (player ship) of a 2.5D space tutorial game in
Godot 4.6. The project ALREADY EXISTS from a template: project.godot (with
run/main_scene="res://main.tscn"), main.tscn, main.gd. Do not re-emit those.

Emit EXACTLY these 2 files as fenced code blocks (info string = path):
1. ```scripts/ship.gd
2. ```scenes/ship.tscn

ship.gd requirements (CharacterBody3D, 2.5D = XY plane, z always 0):
- extends CharacterBody3D, class signal-collecting space ship.
- const SPEED := 300.0; const ACCEL := 6.0 (lerp factor).
- Input actions move_left/move_right/move_up/move_down (declared in
  project.godot already — DO NOT add or verify them, just use Input.get_axis).
- _physics_process(delta): build Vector3(get_axis_x, get_axis_y, 0), lerp
  velocity toward input*SPEED, call move_and_slide() with NO arguments,
  then force position.z = 0 and velocity.z = 0 (hard plane lock).
- AUTOPILOT: if OS.has_feature("dedicated_server"), IGNORE human input and
  run self-test flight: fly toward the beacon then ore waypoints provided
  by the level — expose `var autopilot_target: Node3D` and steer toward
  autopilot_target.position when set (simple seek: direction * SPEED).
- No gravity anywhere. No print markers here (level owns markers).

ship.tscn requirements:
- [gd_scene load_steps=N format=3], all ext/sub resources BEFORE nodes.
- Root: CharacterBody3D named "Ship" with script ship.gd.
- Child CollisionShape3D with [sub_resource] CapsuleShape3D
  (radius = 0.5, height = 1.5).
- Child MeshInstance3D with [sub_resource] CapsuleMesh (same radius/height)
  and [sub_resource] StandardMaterial3D albedo_color = Color(0.2, 0.9, 1.0, 1.0)
  (cyan = ship symbol). StandardMaterial3D goes on the mesh instance
  material_override or the mesh material slot — pick one, be consistent.
- z = 0 on all nodes. No Camera3D here (level owns it).

Output contract: two fenced blocks, paths in the info strings, no prose,
no thinking text, no ```gdscript language tags.
