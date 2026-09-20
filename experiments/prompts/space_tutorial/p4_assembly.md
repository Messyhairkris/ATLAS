You are building part P4 (level assembly) of a 2.5D space tutorial game
in Godot 4.6. Existing parts you MUST instance (do NOT re-emit them):
scenes/ship.tscn (CharacterBody3D "Ship" with autopilot_target var),
scenes/ore.tscn, scenes/debris.tscn (Area3D pickups printing
ORE_COLLECTED/DEBRIS_COLLECTED), scenes/hud.tscn (CanvasLayer "HUD"),
scripts/tutorial.gd (Node3D director with advance/notify_*/signals).

Emit EXACTLY these 3 files as fenced code blocks (info string = path);
main.tscn/main.gd REPLACE the template versions (keep run/main_scene
pointing at res://main.tscn — do not touch project.godot):
1. ```main.tscn
2. ```main.gd
3. ```scripts/envoy.gd  (alien envoy: Area3D, connect body_entered to the
   tutorial director's notify_envoy via group or signal; stationary;
   green capsule visual CapsuleMesh + StandardMaterial3D
   albedo_color = Color(0.3, 1.0, 0.4, 1.0))

main.tscn (the WHOLE tutorial level, [gd_scene] with correct load_steps;
every ext_resource/sub_resource declared before nodes):
- Root Node3D named "Tutorial1" with main.gd.
- Child: tutorial director (instance scripts/tutorial.gd on a Node3D
  named "TutorialDirector"), HUD instance, Camera3D at Vector3(0, 0, 20)
  current = true projection perspective.
- Ship instance at Vector3(0, -6, 0).
- 4 Ore instances around (e.g. Vector3(4, 2, 0), Vector3(-5, 4, 0),
  Vector3(6, -3, 0), Vector3(-3, -4, 0)).
- 3 Debris instances (e.g. Vector3(2, 6, 0), Vector3(-6, -1, 0),
  Vector3(5, 5, 0)).
- Envoy instance (scripts/envoy.gd on Area3D, green capsule + collision)
  at Vector3(0, 8, 0).
- Beacon: Area3D named "Beacon" with CollisionShape3D (BoxShape3D
  size Vector3(1.2, 1.2, 1.2)) and MeshInstance3D BoxMesh rotated 45
  degrees orange Color(1.0, 0.55, 0.1, 1.0) at Vector3(0, 4, 0); its script
  behavior lives in main.gd (connect body_entered → notify_beacon).
- Planet backdrop: MeshInstance3D SphereMesh radius large (e.g. 220) blue
  Color(0.15, 0.3, 0.8, 1.0) at Vector3(0, 0, -600). NO collision, NO script.

main.gd (extends Node3D):
- _ready(): print("TUTORIAL_READY"); wire every Ore/Debris instance
  (via groups "ore"/"debris" or direct signal connect) to
  TutorialDirector.notify_ore()/notify_debris(); connect Beacon and Envoy
  the same way; on HUD ready call show_text for stage 0; if
  OS.has_feature("dedicated_server"): assign ship.autopilot_target from
  TutorialDirector.get_autopilot_target() and re-assign it on every
  stage_advanced signal.
- Keep every gameplay node at z = 0; only the planet has z != 0.

Output contract: three fenced blocks, paths in info strings, no prose.
Exact markers matter. This part determines whether the level boots —
check your load_steps arithmetic twice.
