## results.gd
extends Control

# ── Nodos UI ──────────────────────────────────────────────────────────────────
@onready var song_label:      Label       = $VBox/SongLabel
@onready var name_field_p1:   LineEdit    = $VBox/NamesBox/NameFieldP1
@onready var name_field_p2:   LineEdit = $VBox/NamesBox/NameFieldP2
@onready var label_p2:        Label       = $VBox/NamesBox/LabelP2
@onready var save_button:     Button      = $VBox/SaveButton
@onready var leaderboard:     ItemList    = $VBox/Leaderboard
@onready var back_button:     Button      = $VBox/BackButton
@onready var http:            HTTPRequest = $HTTPRequest

@onready var score_label_p1:    Label   = $VBox/ResultsBox/P1/ScoreLabel
@onready var accuracy_label_p1: Label   = $VBox/ResultsBox/P1/AccuracyLabel
@onready var combo_label_p1:    Label   = $VBox/ResultsBox/P1/ComboLabel

@onready var results_box_p2:    Control = $VBox/ResultsBox/P2
@onready var score_label_p2:    Label   = $VBox/ResultsBox/P2/ScoreLabel
@onready var accuracy_label_p2: Label   = $VBox/ResultsBox/P2/AccuracyLabel
@onready var combo_label_p2:    Label   = $VBox/ResultsBox/P2/ComboLabel

const SERVER := "http://127.0.0.1:8000"

var _saved := false


func _ready() -> void:
	var two_p := GameState.two_player_mode
	var song  := GameState.selected_song_name

	song_label.text = "♪ %s" % song

	# Resultados P1
	score_label_p1.text    = "Score: %d"      % GameState.last_score
	accuracy_label_p1.text = "Accuracy: %s"   % _fmt_accuracy(GameState.last_accuracy)
	combo_label_p1.text    = "Max Combo: %d"  % GameState.last_max_combo

	# Mostrar/ocultar P2
	results_box_p2.visible = two_p
	label_p2.visible       = two_p
	name_field_p2.visible  = two_p

	if two_p:
		score_label_p2.text    = "Score: %d"     % GameState.last_score_p2
		accuracy_label_p2.text = "Accuracy: %s"  % _fmt_accuracy(GameState.last_accuracy_p2)
		combo_label_p2.text    = "Max Combo: %d" % GameState.last_max_combo_p2
		name_field_p2.placeholder_text = "Nombre Jugador 2"

	name_field_p1.placeholder_text = "Nombre Jugador 1"
	name_field_p1.text = GameState.player1_name if GameState.player1_name != "P1" else ""
	name_field_p2.text = GameState.player2_name if GameState.player2_name != "P2" else ""

	save_button.pressed.connect(_on_save_pressed)
	back_button.pressed.connect(_on_back_pressed)

	# Cargar leaderboard inicial
	_load_leaderboard(song)


# ── GUARDAR SCORE ─────────────────────────────────────────────────────────────

func _on_save_pressed() -> void:
	if _saved:
		return

	var name_p1 := name_field_p1.text.strip_edges()
	if name_p1.is_empty():
		name_p1 = "Anónimo"
	GameState.player1_name = name_p1

	save_button.disabled = true
	save_button.text     = "⏳ Guardando..."

	# Construir payload P1
	var payload_p1 := {
		"player_name": name_p1,
		"song_name":   GameState.selected_song_name,
		"score":       GameState.last_score,
		"accuracy":    GameState.last_accuracy,
		"max_combo":   GameState.last_max_combo,
		"hit_notes":   GameState.last_hit_notes,
		"total_notes": GameState.last_total_notes,
		"date":        Time.get_date_string_from_system(),
	}

	if GameState.two_player_mode:
		# Guardar P1 primero, P2 se guarda en el callback
		http.request_completed.connect(_on_p1_saved, CONNECT_ONE_SHOT)
	else:
		http.request_completed.connect(_on_save_completed, CONNECT_ONE_SHOT)

	_post_score(payload_p1)


func _on_p1_saved(_result, response_code, _headers, _body) -> void:
	if response_code != 200:
		_on_save_error()
		return

	# Ahora guardar P2
	var name_p2 := name_field_p2.text.strip_edges()
	if name_p2.is_empty():
		name_p2 = "Anónimo 2"
	GameState.player2_name = name_p2

	var payload_p2 := {
		"player_name": name_p2,
		"song_name":   GameState.selected_song_name,
		"score":       GameState.last_score_p2,
		"accuracy":    GameState.last_accuracy_p2,
		"max_combo":   GameState.last_max_combo_p2,
		"hit_notes":   GameState.last_hit_notes_p2,
		"total_notes": GameState.last_total_notes,
		"date":        Time.get_date_string_from_system(),
	}

	http.request_completed.connect(_on_save_completed, CONNECT_ONE_SHOT)
	_post_score(payload_p2)


func _on_save_completed(_result, response_code, _headers, _body) -> void:
	if response_code != 200:
		_on_save_error()
		return

	_saved           = true
	save_button.text = "✅ Guardado"

	# Recargar leaderboard con los nuevos datos
	_load_leaderboard(GameState.selected_song_name)


func _on_save_error() -> void:
	save_button.disabled = false
	save_button.text     = "Guardar Puntuacion"


func _post_score(payload: Dictionary) -> void:
	var body    := JSON.stringify(payload)
	var headers := ["Content-Type: application/json"]
	http.request(SERVER + "/scores", headers, HTTPClient.METHOD_POST, body)


# ── LEADERBOARD ───────────────────────────────────────────────────────────────

func _load_leaderboard(song_name: String) -> void:
	leaderboard.clear()
	leaderboard.add_item("⏳ Cargando leaderboard...")

	var url := SERVER + "/scores/" + song_name.uri_encode()
	http.request_completed.connect(_on_leaderboard_received, CONNECT_ONE_SHOT)
	http.request(url)


func _on_leaderboard_received(_result, response_code, _headers, body) -> void:
	leaderboard.clear()

	if response_code != 200:
		leaderboard.add_item("❌ No se pudo cargar el leaderboard.")
		return

	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if parsed == null or not parsed.has("scores"):
		leaderboard.add_item("❌ Respuesta inválida.")
		return

	var rows: Array = parsed["scores"]

	if rows.is_empty():
		leaderboard.add_item("Sin registros aún. ¡Sé el primero!")
		return

	for i in rows.size():
		var row: Dictionary = rows[i]
		var acc  := "%.1f%%" % (float(row["accuracy"]) * 100.0)
		var entry := "#%d  %-15s  %7d pts  %s  combo:%d  %s" % [
			i + 1,
			row["player_name"],
			row["score"],
			acc,
			row["max_combo"],
			row["date"],
		]
		leaderboard.add_item(entry)

		# Resaltar entradas del jugador actual en verde
		if row["player_name"] == GameState.player1_name or \
		   row["player_name"] == GameState.player2_name:
			leaderboard.set_item_custom_fg_color(i, Color(0.3, 1.0, 0.5))


# ── HELPERS ───────────────────────────────────────────────────────────────────

func _fmt_accuracy(val: float) -> String:
	return "%.1f%%" % (val * 100.0)


func _on_back_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/song_select.tscn")
