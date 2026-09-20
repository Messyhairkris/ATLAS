Part P7c (stage-machine repair) of SIGNAL LOST: System 1. The WSB
playthrough shows your stage machine diverged from the plan and the envoy
chain is broken:
EVIDENCE: TUTORIAL_READY, DEBRIS_COLLECTED, then a SCRIPT ERROR
"Expected 1 argument(s)" on notify_envoy (envoy.gd calls
director.notify_envoy() with ZERO args while your handler takes 1, and
main.gd connects Envoy a second time). Your notify_ore checks
`stage == 0` but notify_beacon already advanced stage 0 -> 1, so the ore
stage can never trigger. No ORE_COLLECTED-driven stage advances happened.

Emit EXACTLY these 2 files (full rewrites; info string = path):
1. ```scripts/tutorial.gd
2. ```scripts/envoy.gd

== EXACT stage contract (this is the design, implement it literally) ==
stage 0: REACH BEACON. notify_beacon: if stage == 0 -> advance.
stage 1: COLLECT ALL 4 ORE. notify_ore: _ore_count += 1, run combo
  scoring, advance when _ore_count >= 4.
stage 2: COLLECT 3 DEBRIS. notify_debris: _debris_count += 1; refinery
  fires EXACTLY ONCE at _debris_count == 2 (score += 200, print
  PLOT_REFINERY, do NOT add ore); advance when _debris_count >= 3.
stage 3: APPROACH ENVOY. notify_envoy: print PLOT_ENVOY, advance.
stage 4: DOCK AT BEACON. notify_beacon: print SCORE_FINAL + str(score),
  print TIME_BEST + str(snapped((Time.get_ticks_msec() -
  level_start_msec) / 1000.0, 0.1)) IF _ore_count >= 4, then print
  PLOT_BEACON_DENIAL and TUTORIAL_COMPLETE.
All 4 handlers: (body: Node = null) optional-arg signature.
get_autopilot_target: stage 0/4 -> beacon path node; 1 -> nearest live
"ore" group node; 2 -> nearest live "debris" group; 3 -> envoy path node.
Keep: signal stage_advanced(int), @export the 4 NodePaths resolved in
_ready, lazy CanvasLayer HUD via _get_hud() with null guard, watchdog
SceneTreeTimer 150.0s printing WATCHDOG_TIMEOUT, combo vars
(combo/last_ore_msec/score/level_start_msec), _nearest_in_group helper
anchored on get_parent().get_node_or_null("Ship").

== envoy.gd (extends Area3D) ==
_ready(): NOTHING but pass. NO body_entered connect here (main.gd
connects Envoy exactly once). Keep any visual setup lines only.

Godot 4.6, exact markers above, no prose outside fences.
