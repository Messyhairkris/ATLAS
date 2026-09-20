You are building part P5 (autopilot polish) of the 2.5D space tutorial.
The assembled level (main.tscn/main.gd) boots under --headless and the
ship has var autopilot_target: Node3D with seek steering when
OS.has_feature("dedicated_server").

The verifier runs the project headless 30s and needs marker evidence that
a playthrough happens WITHOUT a human. Emit EXACTLY 1 file (full rewrite
of the current one — you have its requirements, not its text; rewrite it
completely and correctly):
1. ```scripts/autopilot.gd

autopilot.gd (extends Node — instantiated by main.gd ONLY when
OS.has_feature("dedicated_server") is true; humans never get one):
- _physics_process: read TutorialDirector stage via a get_node path
  configured by main.gd (export var instead: @export var director_path:
  NodePath; @onready var director = get_node(director_path)).
- Each frame: set ship.autopilot_target = director.get_autopilot_target().
- If the current stage's objective is a COUNT (ore/debris stages), target
  the NEAREST live instance each frame (group "ore"/"debris"), because the
  old target may have collected itself and been freed (is_instance_valid
  check REQUIRED — freed targets crash the game).
- If director is null or stage already 4 with TUTORIAL_COMPLETE printed:
  stop steering (ship.autopilot_target = null).
- NO markers printed here (director owns all markers).

main.gd wiring reminder (do not re-emit main.gd; the runner checks this
file only): under dedicated_server, main.gd adds this autopilot node and
passes director_path. If you judge that a 1-line change to main.gd is
strictly required for the autopilot to receive director_path, you MAY
also emit ```main.gd as a second block — but prefer keeping to 1 file.

Output contract: fenced blocks with paths, no prose. Freed-target
is_instance_valid guard is the #1 crash risk — check it twice.
