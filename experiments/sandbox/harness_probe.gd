extends Node
# Harness-owned probe (ATLAS api-harness). Injected as an autoload into the
# sandbox COPY of a project for each run; never part of the agent's files.
# The host trusts HARNESS_PROBE lines carrying this run's nonce, so "the main
# scene really loaded" no longer depends on a marker the agent's code prints.
# Nodes the agent (or a plan) puts in group "harness_track" get their position
# logged every heartbeat: runtime tuning bugs (orbit-lock, stalls) show up as
# numbers in the log instead of needing a human to watch.

const NONCE := "__NONCE__"
const HEARTBEAT_S := 5.0
const NO_SCENE_AFTER_S := 10.0

var _t := 0.0
var _beat := 0.0
var _frames := 0
var _scene_reported := false


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_emit("BOOT", "godot=%s" % Engine.get_version_info().string)


func _process(delta: float) -> void:
	_t += delta
	_frames += 1
	var scene: Node = get_tree().current_scene
	if not _scene_reported:
		if scene != null:
			_scene_reported = true
			_emit("SCENE_LOADED", "scene=%s nodes=%d" % [scene.scene_file_path, _count(scene)])
		elif _t > NO_SCENE_AFTER_S:
			_scene_reported = true
			_emit("NO_SCENE", "t=%.1f" % _t)
	_beat += delta
	if _beat >= HEARTBEAT_S:
		_beat = 0.0
		_heartbeat(scene)


func _heartbeat(scene: Node) -> void:
	var nodes := 0
	if scene != null:
		nodes = _count(scene)
	_emit("HEARTBEAT", "t=%.1f frames=%d nodes=%d" % [_t, _frames, nodes])
	for node in get_tree().get_nodes_in_group("harness_track"):
		if node is Node2D or node is Node3D:
			_emit("TRACK", "%s pos=%s" % [node.name, str(node.position)])


func _count(root: Node) -> int:
	var total := 1
	for child in root.get_children():
		total += _count(child)
	return total


func _emit(kind: String, detail: String) -> void:
	print("HARNESS_PROBE %s %s %s" % [NONCE, kind, detail])
