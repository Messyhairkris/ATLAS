# Godot 4.6 — bare-minimum knowledge (verified 2026-09-18)

## Output contract
- One fenced code block per file. The fence info string IS the file path:
  ```` ```scripts/player.gd ```` — not ```gdscript, not ```xml.
- No prose before, between, or after blocks. Do not reason in the answer.

## Minimum project structure
- `project.godot` MUST exist and MUST define the main scene:
  ```
  config_version=5
  [application]
  run/main_scene="res://main.tscn"
  ```
  Without `run/main_scene` Godot loads nothing and every run hangs.
- Every `res://...` path referenced anywhere must be a file you also emit.
- Start from the provided skeleton. Keep it working; extend it.

## .tscn scene format (exact rules)
- First line: `[gd_scene load_steps=N format=3]` where
  N = (count of [ext_resource]) + (count of [sub_resource]) + 1.
- All `[ext_resource]` and `[sub_resource]` blocks come BEFORE any `[node]`.
- Node block: `[node name="Player" type="CharacterBody2D"]`, then bare
  `key = value` lines. `parent="."` or `parent="Ground"` for children.
- PARENT RULE, memorize: the scene's ROOT node is not addressable by its
  own name. A direct child of the root is ALWAYS `parent="."`.
  `parent="Ship"` (root's name) silently DROPS the child at instantiation
  ("Parent path has vanished") — your collisions/labels will be missing.
  Named parents are only for nodes declared EARLIER in the same file.
- Sibling nodes may not be ready in _ready (ready order is bottom-up).
  Access siblings lazily (get_node_or_null at first use) or use
  call_deferred / signaling; never cache a sibling child ref in @onready
  across scene boundaries.
- Instancing a scene: the header carries it —
  `[node name="Player" parent="." instance=ExtResource("2_player")]`.
  An instanced node has NO `type=`.
- `instance=ExtResource("N")` is ONLY for ext_resources of
  type="PackedScene". NEVER instance a Script: for a plain scripted node
  write `[node name="X" type="Node3D" parent="."]` and attach
  `script = ExtResource("N")` as a body property line.
- Shapes are sub_resource blocks, referenced by id:
  `[sub_resource type="CapsuleShape2D" id="CapsuleShape2D_body"]` with
  `radius = 18.0` / `height = 52.0`, used as
  `shape = SubResource("CapsuleShape2D_body")`.
- `RectangleShape2D` uses `size = Vector2(2000, 64)`. There is NO `extents`
  property in Godot 4.
- NEVER write scenes as XML, JSON, or GDScript-with-braces. Only the
  `[section]` / `key = value` format above parses.

## GDScript 4.6 essentials
- Line 1 of a script is `extends CharacterBody2D` (or Node2D, Area2D, ...).
  No comment or placeholder before it. Never use `...` or `_ = call()`.
- Input constants are `KEY_D`, `KEY_A`, `KEY_SPACE` — `Key.D` is Godot 3
  and does not exist.
- Prefer declaring input actions in project.godot `[input]` (see reference
  example). Runtime binding, if needed:
  ```
  InputMap.add_action("move_right")
  var ev := InputEventKey.new()
  ev.physical_keycode = KEY_D
  InputMap.action_add_event("move_right", ev)
  ```
  `add_action` alone binds no keys.
- Signals: `body_entered.connect(_on_body_entered)` — the Godot 3 form
  `connect("body_entered", ...)` is removed.
- Ray casting changed in Godot 4: no arguments to intersect_ray at all.
  Build a parameters object instead:
  ```
  var q := PhysicsRayQueryParameters2D.create(from, to)
  var hit := get_world_2d().direct_space_state.intersect_ray(q)
  ```
  3D is the same with `PhysicsRayQueryParameters3D.create(...)`. The 3-arg
  form is Godot 3 and is a parse-time SCRIPT ERROR.
- `yield` is gone; use `await`.
- Movement: `CharacterBody2D` + `move_and_slide()` takes NO arguments;
  set `velocity` first. Gravity:
  `ProjectSettings.get_setting("physics/2d/default_gravity")`.
- Standard player: `CharacterBody2D` + `CollisionShape2D` child.
  Ground: `StaticBody2D` + `CollisionShape2D`. Goal/trigger: `Area2D`
  + `CollisionShape2D`, and its script connects `body_entered`.

## 2.5D (3D nodes, gameplay locked to the XY plane)
- Same scene format rules; only TYPE names change. Movement: `Vector3`,
  `position`, `velocity` — always keep `z = 0` on every gameplay node.
- Player: `CharacterBody3D` + `CollisionShape3D` child. Move with
  `velocity = Vector3(input.x, input.y, 0) * SPEED` then
  `move_and_slide()` (no args). SPACE HAS NO GRAVITY: never add gravity.
- Pickups/triggers: `Area3D` + `CollisionShape3D` child, connect
  `body_entered`. Static props: `StaticBody3D` or plain `Node3D`.
- Shapes as [sub_resource]: `SphereShape3D` (`radius = 0.5`),
  `BoxShape3D` (`size = Vector3(1, 1, 1)`), `CapsuleShape3D`
  (`radius`, `height`).
- Placeholder visuals: `MeshInstance3D` + [sub_resource] `BoxMesh` or
  `SphereMesh` + `StandardMaterial3D` with `albedo_color = Color(...)`.
  Set the SAME shape on the sibling `CollisionShape3D`.
- `Color` in scene files ALWAYS takes 4 args: `Color(1, 0.85, 0.2, 1)`.
  The 3-arg form parses nowhere — it is a load-time Parse Error
  ("Expected 4 arguments for constructor") that kills the whole scene.
- Camera: `Camera3D` with `position = Vector3(0, 0, 20)`,
  `current = true`, `projection = 0` (perspective → 2.5D depth).
- HUD: `CanvasLayer` + `Label` children (2D UI floats over 3D world;
  HUD nodes have NO position on the plane — set via anchors/default).
- Headless autopilot: on EDITOR builds (like this machine's Godot),
  `OS.has_feature("dedicated_server")` is FALSE even under --headless —
  never use it as the autopilot gate. Instead check
  `OS.get_cmdline_user_args().has("--autopilot")` (true only when the
  harness launches with `-- --autopilot`). Human play never passes it.
- `Input.get_axis("move_left", "move_right")` works identically; input
  actions still live in project.godot `[input]`.
- Seek steering MUST clamp speed by distance:
  `speed = min(SPEED, dist / max(delta, 0.001))`. Constant-speed seek at
  300 u/s moves ~5 units/frame and tunnels past ~1 unit targets —
  oscillating forever without ever overlapping an Area3D.

## Verifier failure → actual cause
- `missing [gd_scene]/[gd_resource] header` → you wrote XML or prose
  instead of scene format.
- `node section without type` → `[node]` header missing `type=`/`instance=`.
- `project.godot has no run/main_scene` → add it under `[application]`.
- `Parse Error: Identifier 'Key' not declared` → Godot 3 constant; use `KEY_*`.
- `run never completed (180s)` → main scene missing/broken; Godot hung.
- Files extracted = 0 → your fences lacked file paths.
