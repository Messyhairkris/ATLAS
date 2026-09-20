Part P7b (world + scoring) of SIGNAL LOST: System 1. The physics core
files from P7a exist on disk (scripts/gravity_well.gd with well_pull(),
scenes/planet.tscn mass 250000, scenes/star.tscn mass 900000, damped
ship.gd). You assemble the solar system level and the scoring director.
Emit EXACTLY these 3 files (full rewrites; info string = path):
1. ```main.tscn
2. ```main.gd
3. ```scripts/tutorial.gd

== main.tscn (the WHOLE System 1 scene) ==
Keep EVERYTHING that exists and works: TutorialDirector Node3D with
scripts/tutorial.gd + its 4 @export NodePaths set
(beacon_path/ore_path/debris_path/envoy_path as NodePath("../X")),
HUD instance, Camera3D (position Vector3(0, 0, 20), current), Ship at
(0, -6, 0), 4 Ore instances, 3 Debris instances, Envoy (Area3D with
green capsule + scripts/envoy.gd), Beacon (Area3D orange box + collision),
planet backdrop MeshInstance3D. ADD as siblings under root:
- Star instance (scenes/star.tscn) at Vector3(0, 26, 0)
- Planet instance (scenes/planet.tscn) at Vector3(16, 2, 0)
- Second planet instance named PlanetB with mass = 150000 override at
  Vector3(-18, -12, 0)
Correct load_steps for the NEW ext_resource additions. Positions are
spec, do not improvise others.

== main.gd (full rewrite; keep every working behavior) ==
Keep: _hud CanvasLayer lookups with cast + null guards; _tutorial =
$TutorialDirector; TUTORIAL_READY print (in _ready); ore/debris group
adds + body_entered connects to director.notify_*; Beacon/Envoy
connects; YOU Label3D (font_size 96, billboard, Color(0.6, 1.0, 1.0, 1),
position Vector3(0, 2.6, 0)) added to $Ship; ore tints + debris grays
via duplicated materials (NOW ALSO set each material's
emission_enabled = true, emission = albedo color,
emission_energy_multiplier = 0.4); autopilot init + probe print under
the --autopilot user arg; per-frame retargeting.
ADD:
- Camera follow in _physics_process (ALL modes, not just autopilot):
  $Camera3D.position.x = $Ship.position.x;
  $Camera3D.position.y = $Ship.position.y (z unchanged).
- Bounds in _physics_process: BOUNDS_X := 30.0 / 22.0 soft-clamp
  34.0/26.0; if abs(ship.position.x) > 30.0 or abs(ship.position.y) >
  18.0: push velocity inward (toward origin, strength 400 * delta) and
  HUD warn "RETURN TO BELT — drifting out" (safe: call only while
  violated); hard clamp position to the soft limits.

== scripts/tutorial.gd (full rewrite; System 1 scoring) ==
Keep EVERYTHING from the current version: signal stage_advanced; stage
machine 0-4; counters; @export NodePaths resolved in _ready; lazy
CanvasLayer HUD; watchdog BUT at 150.0s printing WATCHDOG_TIMEOUT;
notify_ore/notify_debris semantics incl. refinery; notify_envoy;
notify_beacon (advance at stage 0; at stage 4 print PLOT_BEACON_DENIAL
AND TUTORIAL_COMPLETE); _nearest_in_group (typed vars,
get_parent().get_node_or_null("Ship") anchor, is_instance_valid guards);
get_autopilot_target match. Stage-0 text becomes:
"QUARRY: Thrust with WASD/arrows. Gravity pulls - use it. Reach the
orange beacon."
ADD scoring: var level_start_msec: int set in _ready
(Time.get_ticks_msec()); var combo := 0; var last_ore_msec := 0;
var score := 0. In notify_ore: if Time.get_ticks_msec() - last_ore_msec
<= 5000: combo += 1 else: combo = 1; last_ore_msec = now; bonus =
100 * combo; score += 100 + bonus; if combo > 1: print("COMBO_x" +
str(combo)). In notify_beacon at stage 4: elapsed = (now -
level_start_msec) / 1000.0; if ore_count >= 4: print("SCORE_FINAL " +
str(score)); print("TIME_BEST " + str(snapped(elapsed, 0.1))).

Godot 4.6 only, exact markers preserved, no prose outside fences.
