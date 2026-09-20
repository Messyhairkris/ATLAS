You are building part P3 (tutorial director + HUD) of a 2.5D space
tutorial game in Godot 4.6. Emit EXACTLY these 3 files as fenced code
blocks (info string = path):
1. ```scripts/tutorial.gd
2. ```scripts/hud.gd
3. ```scenes/hud.tscn

tutorial.gd (extends Node3D — the level's brain; the level instantiates it):
- Signal: signal stage_advanced(new_stage: int)
- var stage := 0; const STAGE_COUNT := 5; var ore_count := 0;
  var debris_count := 0
- METHOD advance(): stage += 1; print("STAGE_" + str(stage) +
  "_COMPLETE"); stage_advanced.emit(stage); update HUD via hud.gd
- METHOD notify_ore(): ore_count += 1; if ore_count == 3 and stage == 1:
  advance(). If stage == 2 and debris refinery fired first, still fine.
- METHOD notify_debris(): debris_count += 1; at debris_count == 2 during
  stage 2: ore_count += 1; print("PLOT_REFINERY"); if ore_count >= 3:
  advance()
- METHOD notify_envoy(): if stage == 3: print("PLOT_ENVOY"); advance()
- METHOD notify_beacon(): if stage == 0: advance() (reaching beacon first
  time); elif stage == 4: print("PLOT_BEACON_DENIAL"); print("TUTORIAL_COMPLETE")
- Stage text table (exact strings, used by HUD):
  0 "QUARRY: Thrust with WASD or arrows. Reach the orange beacon."
  1 "Gold spheres are ORE. Collect 3."
  2 "Gray boxes are DEBRIS. Collect 2 - I refine them into bonus ore."
  3 "Green signature ahead. Directive 12: ignore, collect, report."
  4 "Drills complete. Dock at the beacon to bank the haul."
- Watchdog: a 40s SceneTreeTimer restarted on every advance(); if it
  lapses print("WATCHDOG_TIMEOUT").
- Autopilot assist: expose METHOD get_autopilot_target() -> Node3D
  returning the current objective node's path target (beacon for
  stage 0/4, nearest Ore for 1, nearest Debris for 2, Envoy for 3); the
  level will assign node references on _ready.

hud.gd (extends CanvasLayer): one @onready Label; METHOD
show_text(t: String) sets label text; METHOD set_counters(ore: int,
debris: int) appends a status line. hud.tscn: CanvasLayer root named
"HUD" with hud.gd, child Label named "TutorialText", white text,
top-left default anchors.

Output contract: three fenced blocks, paths in info strings, no prose,
no thinking text. Exact marker strings matter: STAGE_1_COMPLETE ..
STAGE_4_COMPLETE, TUTORIAL_COMPLETE and the PLOT_ markers above.
