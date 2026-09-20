You are building part P2 (collectibles) of a 2.5D space tutorial game in
Godot 4.6. The ship from P1 exists: scripts/ship.gd is a CharacterBody3D
named "Ship". Emit EXACTLY these 4 files as fenced code blocks
(info string = path):
1. ```scripts/ore.gd
2. ```scenes/ore.tscn
3. ```scripts/debris.gd
4. ```scenes/debris.tscn

Shared behavior (both are Area3D pickups):
- extends Area3D. In _ready(): body_entered.connect(_on_body_entered).
- _on_body_entered(body): only react when body is a CharacterBody3D
  (the ship). On collect: print the marker, then queue_free(). Debris
  refinery logic belongs to the tutorial director (P3), NOT here.
- ore.gd prints exactly: ORE_COLLECTED
- debris.gd prints exactly: DEBRIS_COLLECTED
- Do NOT track counters here; the tutorial director (separate part) does.

ore.tscn: root Area3D named "Ore" with script ore.gd; CollisionShape3D
child with [sub_resource] SphereShape3D radius = 0.4; MeshInstance3D child
with SphereMesh + StandardMaterial3D albedo_color = Color(1.0, 0.85, 0.2, 1.0)
(gold = ORE).

debris.tscn: root Area3D named "Debris" with script debris.gd;
CollisionShape3D child with BoxShape3D size = Vector3(0.7, 0.7, 0.7);
MeshInstance3D child with BoxMesh + StandardMaterial3D
albedo_color = Color(0.55, 0.55, 0.6, 1.0) (gray = DEBRIS).

All z = 0. [gd_scene load_steps=N format=3] with N counted correctly,
ext/sub resources before nodes, SubResource("id") references.
Output contract: four fenced blocks, paths in info strings, no prose.
