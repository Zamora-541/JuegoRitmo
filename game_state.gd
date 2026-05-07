## game_state.gd
## Autoload/Singleton — persiste datos entre escenas.
## Registrado en project.godot como: GameState = res://scripts/game_state.gd

extends Node

var selected_stream:    AudioStream = null
var selected_song_name: String      = ""
var current_beatmap:    Dictionary  = {}
var selected_song_path: String = ""
# Resultados de la última partida (para la pantalla de resultados)
var last_score:       int   = 0
var last_max_combo:   int   = 0
var last_accuracy:    float = 0.0
var last_hit_notes:   int   = 0
var last_total_notes: int   = 0
var player1_name: String = "P1"
var player2_name: String = "P2"
var two_player_mode: bool = false
var last_score_p2:     int   = 0
var last_max_combo_p2: int   = 0
var last_accuracy_p2:  float = 0.0
var last_hit_notes_p2: int   = 0
