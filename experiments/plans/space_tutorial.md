# Plan: "SIGNAL LOST" — 2.5D space tutorial level (Hoss, 2h wall)

Author: Crush (large model, task structure). Executor: Hoss (gpt-oss-120b).
Mission: playable tutorial level in Godot 4.6 proving small models can be
useful teammates: cheap, gated, honest. Human-playable is the acceptance bar.
Cost discipline: parts, gates, budgets, senior-only-on-threshold.

## Fiction (creative seeds → planted)
You are a salvage pilot quarantined in the Kessler Belt, working a standard
reclamation contract "in service of TERRA-9." Problem: your memory of TERRA-9
is gone — no face, no sky, not even its position on the charts — and the
homeworld channel returns static. The ship AI, QUARRY, trains you anyway;
training is safety-certified even when history isn't. Mid-lesson, a silent
alien envoy (green signature) watches you work. QUARRY's protocol line:
"Unknown envoy. Directive 12: ignore, collect, report." At lesson's end you
dock at the contract beacon to bank your haul — the beacon answers:
"TERRA-9 DENIES YOUR CONTRACT. ORIGIN RECORD SEALED." Tutorial over, hook set.

## World geometry (2.5D, Z = 0 for all gameplay)
- Player ship: `CharacterBody3D`, thrust on X/Y, no gravity (space).
- Ore: gold spheres (`Area3D`, SphereShape3D, SphereMesh, Color(1.0, 0.85, 0.2, 1.0)).
- Debris: gray boxes (`Area3D`, BoxShape3D, BoxMesh, Color(0.55, 0.55, 0.6, 1.0)).
- Ship visual: cyan capsule (CapsuleShape3D/CapsuleMesh, Color(0.2, 0.9, 1.0, 1.0)).
- Alien envoy: green capsule, stationary `Area3D` watch zone (Color(0.3, 1.0, 0.4, 1.0)).
- Beacon: orange crystal = BoxMesh rotated 45deg, `Area3D` dock zone (Color(1.0, 0.55, 0.1, 1.0)).
- Backdrop planet: huge blue `MeshInstance3D` sphere at z = -600 (Color(0.15, 0.3, 0.8, 1.0)), NO collision, NO script.
- Camera: `Camera3D` at Vector3(0, 0, 20), current = true.
- HUD: CanvasLayer + one Label (tutorial text + counters), white on default.

## Controls (input actions in project.godot [input])
move_left/right/up/down = A/D/W/S + arrow keys. Collect = fly through items.

## Tutorial stages (staged array in level script; HUD Label + counters)
0. "QUARRY: Thrust with WASD or arrows. Reach the orange beacon." (beacon proximity)
1. "Gold spheres are ORE. Collect 3." (ore counter >= 3)
2. "Gray boxes are DEBRIS. Worthless alone — collect 2 and QUARRY refines a bonus ore." (debris >= 2, +1 ore, print PLOT_REFINERY)
3. "Green signature ahead. Directive 12: ignore, collect, report. Approach — do not collide." (envoy watch-zone enter triggers PLOT_ENVOY line)
4. "Drills complete. Dock at the beacon to bank the haul." (dock zone → PLOT_BEACON_DENIAL + TUTORIAL_COMPLETE)

## Markers (print(); the WSB verifier reads these)
TUTORIAL_READY at scene _ready. STAGE_1_COMPLETE … STAGE_4_COMPLETE on each
advance. ORE_COLLECTED / DEBRIS_COLLECTED per pickup. PLOT_REFINERY,
PLOT_ENVOY, PLOT_BEACON_DENIAL at story beats. TUTORIAL_COMPLETE at dock.
WATCHDOG_TIMEOUT if a 40s SceneTreeTimer lapses without stage progress.
Autopilot: when OS.has_feature("dedicated_server"), the ship steers itself
through beacon → 3 ore → 2 debris → envoy → beacon-dock; humans always
control.

## Part plan (each part = one call + verify gates + <=1 repair; budget 20k/part)
P0 scaffold — template autoinstall, NO TOKENS (project.godot, main.tscn, main.gd).
P1 ship — scripts/ship.gd, scenes/ship.tscn. Gates: check-only; uses
    Input.get_axis, move_and_slide, z locked 0, autopilot hook present.
P2 pickups — scripts/ore.gd, scenes/ore.tscn, scripts/debris.gd,
    scenes/debris.tscn. Gates: check-only + structural; body_entered connect,
    markers printed with item kind, queue_free after collect.
P3 tutorial director — scripts/tutorial.gd, scripts/hud.gd, scenes/hud.tscn.
    Gates: check-only; stage array of 5 stages; emits stage advance; holds
    counters; print constants exactly as markers listed above.
P4 assembly — main.tscn + REPLACE main.gd as levels/tutorial scene:
    ship, 4+ ore, 3+ debris spread on the plane, envoy, beacon, planet
    backdrop, camera, HUD instanced, tutorial.gd wired. Gates: structural on
    ALL tscn, project-config (run/main_scene intact → main.tscn), check-only
    all gd. NO WSB yet.
P5 human playable — autopilot patrol in autopilot.gd or ship.gd; WSB run
    30s: PASS = TUTORIAL_READY + at least STAGE_1_COMPLETE or ORE_COLLECTED
    in log; STRETCH = TUTORIAL_COMPLETE. Human play: Kris runs the project
    windowed afterwards (autopilot inert without --headless).

## Thresholds & escalation
Per part: FAIL → repair once with verbatim gate errors → still FAIL →
SENIOR REVIEW (Kimi via --senior; Claude when on PATH; Crush if alive).
Global: 20k tok/part cap; 2 consecutive part failures = abort + senior
post-mortem; wall clock 7200s hard stop (elapsed reported per part).
Success definition: P0–P4 green AND P5 WSB markers; honesty rule — partial
markers = partial verdict, no rounding up.
