## database.gd
## Maneja toda la lógica de SQLite para scores y leaderboard.
extends Node
var db: SQLite = null
const DB_PATH := "user://scores.db"


func _ready() -> void:
	db = SQLite.new()
	db.path = DB_PATH
	db.open_db()
	_create_tables()


func _create_tables() -> void:
	db.query("""
		CREATE TABLE IF NOT EXISTS scores (
			id          INTEGER PRIMARY KEY AUTOINCREMENT,
			player_name TEXT    NOT NULL,
			song_name   TEXT    NOT NULL,
			score       INTEGER NOT NULL,
			accuracy    REAL    NOT NULL,
			max_combo   INTEGER NOT NULL,
			hit_notes   INTEGER NOT NULL,
			total_notes INTEGER NOT NULL,
			two_player  INTEGER NOT NULL DEFAULT 0,
			date        TEXT    NOT NULL
		);
	""")


func save_score(player_name: String, song_name: String, score: int,
				accuracy: float, max_combo: int, hit_notes: int,
				total_notes: int, two_player: bool) -> void:
	var date := Time.get_date_string_from_system()
	db.query_with_bindings("""
		INSERT INTO scores
			(player_name, song_name, score, accuracy, max_combo, hit_notes, total_notes, two_player, date)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
	""", [player_name, song_name, score, accuracy, max_combo,
		  hit_notes, total_notes, int(two_player), date])


func get_top10(song_name: String) -> Array:
	db.query_with_bindings("""
		SELECT player_name, score, accuracy, max_combo, date
		FROM scores
		WHERE song_name = ?
		ORDER BY score DESC
		LIMIT 10
	""", [song_name])
	return db.query_result


func close() -> void:
	if db:
		db.close_db()
