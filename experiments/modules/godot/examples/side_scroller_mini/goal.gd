extends Area2D

signal level_complete


func _ready() -> void:
	body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node2D) -> void:
	if body is CharacterBody2D:
		print("LEVEL_COMPLETE")
		level_complete.emit()
