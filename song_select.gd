## song_select.gd
## Obtiene la lista de canciones desde el servidor FastAPI.
extends Control

@onready var song_list:         ItemList = $VBox/SongList
@onready var play_button:       Button   = $VBox/PlayButton
@onready var song_name_label:   Label    = $VBox/SongNameLabel
@onready var http:              HTTPRequest = $HTTPRequest

const SERVER := "http://127.0.0.1:8000"

var song_files: Array = []  # Array de dicts {name, file, has_beatmap}
var _loading_beatmap := false


func _ready() -> void:
	play_button.disabled = true
	song_name_label.text = "Cargando canciones..."

	song_list.item_selected.connect(_on_song_selected)
	play_button.pressed.connect(_on_play_pressed)

	var dl_button := get_node_or_null("VBox/DownloadButton")
	if dl_button != null:
		dl_button.pressed.connect(_on_download_pressed)

	var two_player_button := get_node_or_null("VBox/TwoPlayerButton")
	if two_player_button != null:
		two_player_button.pressed.connect(_on_two_player_toggled)
		_update_two_player_button()

	_fetch_songs()


# ── Obtener lista de canciones ────────────────────────────────────────────────

func _fetch_songs() -> void:
	http.request_completed.connect(_on_songs_received, CONNECT_ONE_SHOT)
	http.request(SERVER + "/songs")


func _on_songs_received(_result, response_code, _headers, body) -> void:
	if response_code != 200:
		song_name_label.text = "❌ No se pudo conectar al servidor."
		return

	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if parsed == null or not parsed.has("songs"):
		song_name_label.text = "❌ Respuesta inválida del servidor."
		return

	song_files = parsed["songs"]
	song_list.clear()

	if song_files.is_empty():
		song_name_label.text = "No hay canciones. Descarga alguna primero."
		return

	for song in song_files:
		song_list.add_item(song["name"].replace("_", " ").replace("-", " ").capitalize())

	song_name_label.text = "%d canción(es) encontrada(s)" % song_files.size()


# ── Selección ─────────────────────────────────────────────────────────────────

func _on_song_selected(index: int) -> void:
	play_button.disabled = false
	song_name_label.text = "♪ " + song_files[index]["name"]


# ── Play — carga audio y beatmap desde el servidor ───────────────────────────

func _on_play_pressed() -> void:
	if _loading_beatmap:
		return

	var sel := song_list.get_selected_items()
	if sel.is_empty():
		return

	var song:     Dictionary = song_files[sel[0]]
	var filename: String     = song["file"]

	print("Filename: ", filename)
	print("URL: ", SERVER + "/songs/" + filename.uri_encode() + "/beatmap")

	play_button.disabled = true
	song_name_label.text = "⏳ Cargando beatmap..."
	_loading_beatmap     = true

	var url := SERVER + "/songs/" + filename.uri_encode() + "/beatmap"
	http.request_completed.connect(_on_beatmap_received.bind(filename), CONNECT_ONE_SHOT)
	http.request(url)


func _on_beatmap_received(_result, response_code, _headers, body, filename: String) -> void:
	if response_code != 200:
		song_name_label.text = "❌ Error al obtener beatmap."
		play_button.disabled  = false
		_loading_beatmap      = false
		return

	var beatmap = JSON.parse_string(body.get_string_from_utf8())
	if beatmap == null:
		song_name_label.text = "❌ Beatmap inválido."
		play_button.disabled  = false
		_loading_beatmap      = false
		return

	GameState.current_beatmap = beatmap
	song_name_label.text      = "⏳ Cargando audio..."

	# 2. Descargar el audio desde el servidor
	http.request_completed.connect(_on_audio_received.bind(filename), CONNECT_ONE_SHOT)
	http.request(SERVER + "/songs/" + filename.uri_encode() + "/audio")


func _on_audio_received(_result, response_code, _headers, body, filename: String) -> void:
	_loading_beatmap = false

	if response_code != 200:
		song_name_label.text = "❌ Error al cargar audio."
		play_button.disabled  = false
		return

	# Crear AudioStream desde los bytes recibidos
	var ext    := filename.get_extension().to_lower()
	var stream := _bytes_to_stream(body, ext)

	if stream == null:
		song_name_label.text = "❌ Formato de audio no soportado."
		play_button.disabled  = false
		return

	GameState.selected_stream    = stream
	GameState.selected_song_name = filename.get_basename()
	GameState.selected_song_path = SERVER + "/songs/" + filename

	get_tree().change_scene_to_file("res://scenes/gameplay.tscn")


func _bytes_to_stream(body: PackedByteArray, ext: String) -> AudioStream:
	var stream := AudioStreamMP3.new()
	stream.data = body
	return stream



# ── Navegación ────────────────────────────────────────────────────────────────

func _on_download_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/download_screen.tscn")


func _on_two_player_toggled() -> void:
	GameState.two_player_mode = not GameState.two_player_mode
	_update_two_player_button()


func _update_two_player_button() -> void:
	var btn := get_node_or_null("VBox/TwoPlayerButton")
	if btn == null:
		return
	if GameState.two_player_mode:
		btn.text     = "👥 2 Jugadores: ON"
		btn.modulate = Color(0.3, 1.0, 0.3)
	else:
		btn.text     = "👤 2 Jugadores: OFF"
		btn.modulate = Color(1.0, 1.0, 1.0)
