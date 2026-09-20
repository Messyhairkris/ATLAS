Part P6 (polish pass) for the SIGNAL LOST tutorial. A human played it:
controls are HARSH (instant velocity, no glide), the ship is not visually
distinct enough, and all ore/debris instances share one flat color.
Rewrite THREE files COMPLETELY (full replacements, same filenames).
Keep every existing marker, signal, and wiring behavior UNLESS this spec
says to change it. Emit exactly these fenced blocks (info string = path):
1. ```scripts/ship.gd
2. ```scripts/tutorial.gd
3. ```main.gd

== scripts/ship.gd — zero-G feel (THE priority change) ==
extends CharacterBody3D. Constants: THRUST := 900.0, DRAG := 0.9,
MAX_SPEED := 320.0. var autopilot_target: Node3D = null.
_physics_process(delta):
- Autopilot branch when OS.get_cmdline_user_args().has("--autopilot")
  (NOT OS.has_feature): if autopilot_target and
  is_instance_valid(autopilot_target): seek with ARRIVE clamp
  speed = min(MAX_SPEED, dist / max(delta, 0.001)) toward
  autopilot_target.position (z forced 0); else velocity = Vector3.ZERO.
- Human branch (else): input := Vector3(Input.get_axis("move_left",
  "move_right"), Input.get_axis("move_up", "move_down"), 0);
  velocity += input * THRUST * delta; then ALWAYS damp:
  velocity *= exp(-DRAG * delta); then if velocity.length() > MAX_SPEED:
  velocity = velocity.normalized() * MAX_SPEED. Result: hold a key to
  build speed, release and the ship GLIDES and slowly settles.
- Both branches: move_and_slide(); position.z = 0.0; velocity.z = 0.0.

== scripts/tutorial.gd — identical to current, ONE change ==
Keep: signal stage_advanced; stage/ore_count/debris_count; @export
beacon_path/ore_path/debris_path/envoy_path NodePaths resolved in _ready;
lazy _hud lookup (find_child may run before HUD is ready — keep the
null check every use); _ready/start watchdog; advance() prints
"STAGE_<n>_COMPLETE" + emits; notify_ore/notify_debris with refinery
(ore+=1 + print("PLOT_REFINERY") at debris 2, advance at ore 3);
notify_envoy prints PLOT_ENVOY at stage 3; notify_beacon advances
stage 0, prints PLOT_BEACON_DENIAL + TUTORIAL_COMPLETE at stage 4;
_nearest_in_group helper(ship-anchored, is_instance_valid guard);
get_autopilot_target match (beacon 0/4, nearest ore 1, nearest debris 2,
envoy 3). All handlers take (_body: Node = null).
CHANGE: watchdog is get_tree().create_timer(90.0) (was 40.0) and prints
WATCHDOG_TIMEOUT. Stage texts unchanged.

== main.gd — keep all wiring, ADD identity + color variety ==
extends Node3D. Keep: TUTORIAL_READY print; ore/debris group adds +
body_entered connects to director.notify_*; Beacon/Envoy connects;
HUD init show_text(0); autopilot init under the cmdline flag;
probe print under the flag; per-frame _physics_process retargeting.
ADD in _ready:
- YOU marker: var you := Label3D.new(); you.text = "YOU";
  you.position = Vector3(0, 2.2, 0); you.billboard = 1;
  you.modulate = Color(0.6, 1.0, 1.0, 1); $Ship.add_child(you)
- Ore tints (each instance its own feel): for i, ore in enumerate over
  [$Ore1, $Ore2, $Ore3, $Ore4]: get its MeshInstance3D child; duplicate
  its material_override (or mesh.material) and set albedo_color to
  PRESETS[i % PRESETS.size()] where
  PRESETS = [Color(1, 0.85, 0.2, 1), Color(1, 0.6, 0.1, 1),
             Color(1, 1, 0.3, 1), Color(0.9, 0.7, 0.05, 1)]
- Debris grays the same way over [$Debris1, $Debris2, $Debris3]:
  [Color(0.5, 0.5, 0.55, 1), Color(0.4, 0.42, 0.5, 1),
   Color(0.62, 0.62, 0.66, 1)]

Rules: Godot 4.6 only, tabs for GDScript blocks you write, all 3 files
complete and self-consistent, no prose outside the fences.
