## note.gd
## Una nota que cae por un carril. Maneja movimiento, ventana de golpe y miss.

extends Node2D

signal note_hit(lane: int, accuracy: float)
signal note_missed(lane: int)

# Asignados por gameplay.gd al instanciar
var lane:       int   = 0
var beat_time:  float = 0.0
var fall_speed: float = 400.0
var miss_y:     float = 750.0

# Ventanas de tiempo (segundos)
const HIT_WINDOW_PERFECT := 0.060
const HIT_WINDOW_GOOD    := 0.100
const HIT_WINDOW_BAD     := 0.20

var _judged := false

@onready var visual: ColorRect = $Visual


func _process(delta: float) -> void:
	position.y += fall_speed * delta

	if position.y > miss_y and not _judged:
		_judged = true
		note_missed.emit(lane)
		queue_free()


## Intenta registrar un golpe. Devuelve true si fue valido.
func try_hit(song_time: float) -> bool:
	if _judged:
		return false

	var diff: float = abs(song_time - beat_time)
	if diff > HIT_WINDOW_BAD:
		return false

	_judged = true

	# Inicializar con valor por defecto para evitar warning de inferencia de Variant
	var accuracy: float = 0.3
	if   diff <= HIT_WINDOW_PERFECT:
		accuracy = 1.0
	elif diff <= HIT_WINDOW_GOOD:
		accuracy = 0.6

	note_hit.emit(lane, accuracy)
	queue_free()
	return true


## Esta nota esta dentro de la ventana de golpe?
func is_hittable(song_time: float) -> bool:
	return not _judged and abs(song_time - beat_time) <= HIT_WINDOW_BAD


## Cambia el color visual de la nota
func set_color(c: Color) -> void:
	if visual:
		visual.color = c
