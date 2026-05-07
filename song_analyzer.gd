## song_analyzer.gd
## Analiza una cancion completa ANTES de jugar (AOT - Ahead of Time).
## Tecnica: Fast-Forward — reproduce a 8x velocidad en un bus silenciado
## y muestrea el SpectrumAnalyzer para detectar picos de energia por banda.
## Al terminar emite analysis_complete(beatmap: Dictionary).
##
## IMPORTANTE: El WAV debe importarse con compress/mode=0 (PCM) en el .import
## para que el SpectrumAnalyzer reciba datos reales. IMA ADPCM (mode=2) no funciona.

extends Node

signal analysis_complete(beatmap: Dictionary)
signal analysis_progress(progress: float)

const ANALYSIS_BUS_NAME   := "AnalysisBus"
const ANALYSIS_SPEED      := 8.0
const SAMPLE_INTERVAL     := 0.022       # Intervalo de muestreo a velocidad 1x
const MIN_NOTE_GAP        := 0.09        # Separacion minima entre notas por carril (seg)

# Umbrales: cuanto debe superar la energia actual al promedio historico
# para considerarse un "golpe". Bajarlos = mas notas. Subirlos = menos notas.
const THRESHOLD_BASS      := 1.6
const THRESHOLD_MID       := 1.4
const THRESHOLD_HIGH      := 1.3
const ENERGY_HISTORY_SIZE := 43

var _player:   AudioStreamPlayer = null
var _spectrum                    = null   # AudioEffectSpectrumAnalyzerInstance (Variant)
var _bus_idx:  int               = -1

var _is_analyzing:         bool  = false
var _spectrum_ready:       bool  = false
var _song_finished:        bool  = false
var _song_duration:        float = 0.0
var _sample_timer:         float = 0.0
var _real_sample_interval: float = 0.0

var _hist_bass: Array = []
var _hist_mid:  Array = []
var _hist_high: Array = []

var _notes:          Array = []
var _last_note_time: Array = []

# Para debug: imprime las magnitudes maximas que se detectaron
var _debug_max_bass:  float = 0.0
var _debug_max_mid:   float = 0.0
var _debug_max_high:  float = 0.0
var _debug_samples:   int   = 0


func _ready() -> void:
	_last_note_time.resize(8)
	_last_note_time.fill(-999.0)
	set_process(false)


func analyze(stream: AudioStream) -> void:
	if _is_analyzing:
		return
	_reset_state()
	_song_duration = stream.get_length()
	if _song_duration <= 0.0:
		push_error("SongAnalyzer: duracion invalida.")
		return
	print("SongAnalyzer: stream tipo = %s | duracion = %.2fs" % [stream.get_class(), _song_duration])
	_real_sample_interval = SAMPLE_INTERVAL / ANALYSIS_SPEED
	_start_analysis(stream)


func _start_analysis(stream: AudioStream) -> void:
	_remove_bus()

	AudioServer.add_bus()
	_bus_idx = AudioServer.bus_count - 1
	AudioServer.set_bus_name(_bus_idx, ANALYSIS_BUS_NAME)
	AudioServer.set_bus_send(_bus_idx, "Master")
	AudioServer.set_bus_mute(_bus_idx, true)

	var fx := AudioEffectSpectrumAnalyzer.new()
	fx.buffer_length = 0.5   # Buffer mas largo = lecturas mas estables
	fx.fft_size      = AudioEffectSpectrumAnalyzer.FFT_SIZE_2048
	AudioServer.add_bus_effect(_bus_idx, fx)

	_player = AudioStreamPlayer.new()
	add_child(_player)
	_player.stream      = stream
	_player.bus         = ANALYSIS_BUS_NAME
	_player.pitch_scale = ANALYSIS_SPEED
	_player.volume_db   = 0.0   # Volumen normal (el bus esta muteado, no el player)
	_player.finished.connect(_on_player_finished)

	_is_analyzing   = true
	_song_finished  = false
	_spectrum_ready = false
	set_process(true)
	_player.play()

	print("SongAnalyzer > %.0fx velocidad | Duracion: %.2fs | Tiempo real estimado: %.1fs" \
		% [ANALYSIS_SPEED, _song_duration, _song_duration / ANALYSIS_SPEED])

	# Esperar frames suficientes para que el bus este activo y el buffer lleno
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame

	_spectrum = AudioServer.get_bus_effect_instance(_bus_idx, 0)
	if _spectrum == null:
		push_error("SongAnalyzer: no se pudo obtener la instancia del SpectrumAnalyzer.")
		_finish()
		return

	_spectrum_ready = true
	print("SongAnalyzer: spectrum listo, iniciando muestreo.")


func _on_player_finished() -> void:
	_song_finished = true


func _process(delta: float) -> void:
	if not _is_analyzing or not _spectrum_ready:
		return

	# Acumulamos el tiempo solo si la canción seguía reproduciéndose
	if not _song_finished:
		_sample_timer += delta

	# Calculamos la posición real para la barra de progreso
	var pos_real: float = _player.get_playback_position()
	
	if _song_finished:
		pos_real = _song_duration # Forzamos el tiempo final exacto

	analysis_progress.emit(clampf(pos_real / _song_duration, 0.0, 1.0))

	# DRENADO DE BÚFER: 
	# Procesamos todas las muestras acumuladas, incluso si la canción acaba de terminar
	while _sample_timer >= _real_sample_interval:
		_sample_timer -= _real_sample_interval
		_sample(pos_real)

	# Ahora sí, si la canción terminó y ya procesamos todo, cerramos
	if _song_finished:
		_sample(_song_duration) # Una última muestra de seguridad
		_finish()


func _sample(song_time: float) -> void:
	_debug_samples += 1

	var e_bass: float = _spectrum.get_magnitude_for_frequency_range(20.0,   200.0).length()
	var e_mid:  float = _spectrum.get_magnitude_for_frequency_range(200.0,  2000.0).length()
	var e_high: float = _spectrum.get_magnitude_for_frequency_range(2000.0, 16000.0).length()

	# Trackear maximos para debug
	if e_bass > _debug_max_bass: _debug_max_bass = e_bass
	if e_mid  > _debug_max_mid:  _debug_max_mid  = e_mid
	if e_high > _debug_max_high: _debug_max_high = e_high

	_push(_hist_bass, e_bass)
	_push(_hist_mid,  e_mid)
	_push(_hist_high, e_high)

	# Esperar historial minimo antes de detectar
	if _hist_bass.size() < ENERGY_HISTORY_SIZE:
		return

	var avg_bass: float = _avg(_hist_bass)
	var avg_mid:  float = _avg(_hist_mid)
	var avg_high: float = _avg(_hist_high)

	if avg_bass > 0.00001 and e_bass > avg_bass * THRESHOLD_BASS:
		_place_note(song_time, [0, 1, 2])
	if avg_mid  > 0.00001 and e_mid  > avg_mid  * THRESHOLD_MID:
		_place_note(song_time, [3, 4, 5])
	if avg_high > 0.00001 and e_high > avg_high * THRESHOLD_HIGH:
		_place_note(song_time, [6, 7])


func _place_note(time: float, lanes: Array) -> void:
	var best: int = lanes[0]
	for l in lanes:
		var li: int = l
		if _last_note_time[li] < _last_note_time[best]:
			best = li
	if (time - _last_note_time[best]) < MIN_NOTE_GAP:
		return
	_notes.append({ "time": time, "lane": best })
	_last_note_time[best] = time


func _finish() -> void:
	if not _is_analyzing:
		return
	_is_analyzing   = false
	_spectrum_ready = false
	_song_finished  = false
	set_process(false)

	# Imprimir info de debug sobre las magnitudes detectadas
	print("SongAnalyzer DEBUG: %d muestras tomadas" % _debug_samples)
	print("  Max bass : %.6f" % _debug_max_bass)
	print("  Max mid  : %.6f" % _debug_max_mid)
	print("  Max high : %.6f" % _debug_max_high)

	if is_instance_valid(_player):
		_player.queue_free()
	_player = null
	_remove_bus()

	_notes.sort_custom(func(a, b): return a["time"] < b["time"])

	var beatmap := {
		"duration":   _song_duration,
		"note_count": _notes.size(),
		"notes":      _notes.duplicate(true)
	}
	print("SongAnalyzer OK: %d notas detectadas." % _notes.size())
	analysis_complete.emit(beatmap)


func _reset_state() -> void:
	_notes.clear()
	_last_note_time.fill(-999.0)
	_hist_bass.clear()
	_hist_mid.clear()
	_hist_high.clear()
	_sample_timer    = 0.0
	_spectrum_ready  = false
	_song_finished   = false
	_debug_max_bass  = 0.0
	_debug_max_mid   = 0.0
	_debug_max_high  = 0.0
	_debug_samples   = 0


func _push(arr: Array, val: float) -> void:
	arr.append(val)
	if arr.size() > ENERGY_HISTORY_SIZE:
		arr.pop_front()


func _avg(arr: Array) -> float:
	if arr.is_empty():
		return 0.0
	var s: float = 0.0
	for v in arr:
		s += float(v)
	return s / arr.size()


func _remove_bus() -> void:
	var idx := AudioServer.get_bus_index(ANALYSIS_BUS_NAME)
	if idx != -1:
		AudioServer.remove_bus(idx)
	_bus_idx  = -1
	_spectrum = null
