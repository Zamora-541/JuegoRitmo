## analyzer_screen.gd
## Pantalla de carga: Verifica si existe el JSON, si no, ejecuta Python en segundo plano.

extends Control

@onready var progress_bar:    ProgressBar = $VBox/ProgressBar
@onready var status_label:    Label       = $VBox/StatusLabel
@onready var song_name_label: Label       = $VBox/SongNameLabel

var _analysis_thread: Thread

func _ready() -> void:
	var display := GameState.selected_song_name.replace("_", " ").replace("-", " ").capitalize()
	song_name_label.text = "♪ " + display
	progress_bar.value   = 0.0

	await get_tree().process_frame
	await get_tree().process_frame
	
	_check_and_load()


func _check_and_load() -> void:
	var audio_path := GameState.selected_song_path
	var json_path  := audio_path.get_basename() + ".json"
	
	# 1. Si el JSON ya existe, nos saltamos Python y vamos directo al juego
	if FileAccess.file_exists(json_path):
		_load_beatmap(json_path)
		return
		
	# 2. Si no existe, preparamos la UI y llamamos a Python
	status_label.text = "Analizando con Python por primera vez (Esto toma unos segundos)..."
	progress_bar.value = 40.0 
	
	# Creamos un hilo para que la pantalla no se congele
	_analysis_thread = Thread.new()
	_analysis_thread.start(_run_python_script)


func _run_python_script() -> void:
	var output := []
	var script_path = ProjectSettings.globalize_path("res://scripts/python_song_analyzer.py")
	
	OS.execute("python", [script_path], output, true)
	
	# === LÍNEAS NUEVAS PARA DEPURAR ===
	# Imprime la ruta final que Godot está intentando ejecutar (para verificar)
	print("Depurando OS.execute:")
	print(" - Ruta del script detectada: ", script_path)
	
	# Imprime todo lo que Python respondió (aquí estará el verdadero error)
	if output.is_empty():
		print(" - Python no respondió nada (¿Está instalado en el PATH?)")
	else:
		print(" - RESPUESTA DE PYTHON (ERRORES AQUÍ):")
		for line in output:
			print("   > ", line)
	# =================================
	
	call_deferred("_on_python_finished")


func _on_python_finished() -> void:
	# Limpiamos el hilo (obligatorio en Godot)
	_analysis_thread.wait_to_finish() 
	
	var audio_path := GameState.selected_song_path
	var json_path  := audio_path.get_basename() + ".json"
	
	# Verificamos si Python hizo su trabajo y creó el archivo
	if FileAccess.file_exists(json_path):
		_load_beatmap(json_path)
	else:
		status_label.text = "❌ Error: Python falló al generar el JSON. Revisa la consola."
		progress_bar.modulate = Color.RED


func _load_beatmap(json_path: String) -> void:
	status_label.text = "Cargando beatmap..."
	
	var file := FileAccess.open(json_path, FileAccess.READ)
	var json_text := file.get_as_text()
	file.close()

	var parsed_data = JSON.parse_string(json_text)
	
	if parsed_data == null or typeof(parsed_data) != TYPE_DICTIONARY:
		status_label.text = "❌ Error: El archivo JSON está corrupto."
		progress_bar.modulate = Color.RED
		return

	progress_bar.value = 100.0
	status_label.text  = "✓ %d notas cargadas. Iniciando juego..." % parsed_data.get("note_count", 0)
	GameState.current_beatmap = parsed_data

	await get_tree().create_timer(0.6).timeout
	get_tree().change_scene_to_file("res://scenes/gameplay.tscn")
