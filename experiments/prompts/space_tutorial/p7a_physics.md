Part P7a (physics core) of SIGNAL LOST: System 1. The tutorial game exists
and is human-played; human tester says: controls too twitchy, up/down feel
reversed, no gravity mechanics. You are building the gravity-slingshot
physics core. Emit EXACTLY these 4 files as fenced code blocks
(info string = path):
1. ```scripts/gravity_well.gd
2. ```scenes/planet.tscn
3. ```scenes/star.tscn
4. ```scripts/ship.gd

== gravity_well.gd (extends Area3D) ==
@export var mass: float = 200000.0; add_to_group("gravity_well") in _ready.
METHOD well_pull(from_position: Vector3) -> Vector3: dir = position -
from_position (z zeroed); dist = dir.length() clamped to >= 8.0; return
dir.normalized() * (0.35 * mass / (dist * dist)). Pure math, no physics
areas monitoring needed (pure helper the ship polls).

== scenes/planet.tscn & scenes/star.tscn ==
Both instantiate gravity_well.gd on an Area3D root ("Planet" / "Star")
with @export mass default set in SCENE (planet 250000, star 900000;
star also overrides pull via bigger mass only). Each has CollisionShape3D
(SphereShape3D radius 2.0 for planet, 4.0 star) + MeshInstance3D with
SphereMesh + StandardMaterial3D: planet albedo Color(0.2, 0.4, 1.0, 1),
star Color(1.0, 0.9, 0.3, 1); BOTH materials: emission_enabled = true,
emission = same color as albedo, emission_energy_multiplier = 0.4.
[gd_scene load_steps counted correctly; self-lit = the ANGLE-greyness fix.]

== scripts/ship.gd (full rewrite, zero-G + gravity) ==
extends CharacterBody3D. Constants: THRUST := 420.0, DRAG := 0.55,
MAX_SPEED := 240.0, Y_SIGN := -1.0 (flip-to-taste: human reported up/down
reversed with the old direct mapping). var autopilot_target: Node3D = null.
_physics_process(delta):
1. Gravity always: for well in get_tree().get_nodes_in_group
   ("gravity_well"): if is_instance_valid(well) and
   well.has_method("well_pull"): velocity += well.well_pull(position)*delta.
2. Autopilot when OS.get_cmdline_user_args().has("--autopilot"):
   is_instance_valid-guarded seek, z zeroed, arrive-clamp
   min(MAX_SPEED, dist / max(delta, 0.001)).
3. Human else: input_vec = Vector3(Input.get_axis("move_left",
   "move_right"), Y_SIGN * Input.get_axis("move_up", "move_down"), 0.0);
   velocity += input_vec * THRUST * delta; velocity *= exp(-DRAG * delta);
   cap length at MAX_SPEED.
4. Reset (debug): in _unhandled_input(event): if event is InputEventKey
   and event.pressed and event.physical_keycode == KEY_R:
   position = Vector3(0, -6, 0); velocity = Vector3.ZERO; print("RESET").
5. End: move_and_slide(); position.z = 0.0; velocity.z = 0.0.

Godot 4.6 only, valid TSCN rules from your knowledge, comments only where
a human tunes a value. No prose outside fences.
