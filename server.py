# -*- coding: utf-8 -*-
# server.py — Backend FastAPI para el rhythm game

import json
import random
import requests
import numpy as np
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import sqlite3
import librosa
import io
import soundfile as sf
from pydub import AudioSegment
import miniaudio


# ──────────────────────────────────────────────
#  CONFIGURACIÓN
CLIENT_ID  = "baadf3c4"
SONGS_DIR = Path(__file__).parent / "songs" #Path(r"C:\Users\GAMER\Downloads\proyecto-integrador_Cambiado\proyecto-integrador\songs")
DB_PATH    = Path(__file__).parent.parent / "scores.db"
SONGS_DIR.mkdir(exist_ok=True)

# ──────────────────────────────────────────────
#  FASTAPI APP
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_db()
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
#  BASE DE DATOS
# ──────────────────────────────────────────────
def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT    NOT NULL,
            song_name   TEXT    NOT NULL,
            score       INTEGER NOT NULL,
            accuracy    REAL    NOT NULL,
            max_combo   INTEGER NOT NULL,
            hit_notes   INTEGER NOT NULL,
            total_notes INTEGER NOT NULL,
            date        TEXT    NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# ──────────────────────────────────────────────
#  GENERACIÓN DE BEATMAP — tu lógica original
# ──────────────────────────────────────────────
def _generar_beatmap(audio_path: Path) -> dict:
    print(f"\nAnalizando: {audio_path.name}...")

    ext = audio_path.suffix.lower()

    try:
        if ext == ".mp3":
            import miniaudio
            decoded = miniaudio.decode_file(str(audio_path),
                        output_format=miniaudio.SampleFormat.FLOAT32,
                        nchannels=1,
                        sample_rate=22050)
            sr = decoded.sample_rate
            y  = np.frombuffer(decoded.samples, dtype=np.float32).copy()

        elif ext == ".wav":
            import miniaudio
            decoded = miniaudio.decode_file(str(audio_path),
                        output_format=miniaudio.SampleFormat.FLOAT32,
                        nchannels=1,
                        sample_rate=22050)
            sr = decoded.sample_rate
            y  = np.frombuffer(decoded.samples, dtype=np.float32).copy()

        else:
            y, sr = librosa.load(str(audio_path), sr=None, mono=True)

    except Exception as e:
        print(f"  Error cargando audio: {e}")
        raise

    duracion = librosa.get_duration(y=y, sr=sr)

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm      = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
    print(f"  - BPM Estimado: {bpm:.2f}")

    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True)
    onset_times  = librosa.frames_to_time(onset_frames, sr=sr)
    centroides   = librosa.feature.spectral_centroid(y=y, sr=sr)[0]

    notas              = []
    tiempo_ultima_nota = [-999.0] * 6
    MIN_NOTE_GAP       = 0.09

    for i, tiempo in enumerate(onset_times):
        frame_idx = onset_frames[i]
        if frame_idx >= len(centroides):
            frame_idx = len(centroides) - 1

        frecuencia_promedio = centroides[frame_idx]

        if frecuencia_promedio < 1200:
            carril = int(np.random.randint(0, 2))
        elif frecuencia_promedio < 3500:
            carril = int(np.random.randint(2, 4))
        else:
            carril = int(np.random.randint(4, 6))

        if (tiempo - tiempo_ultima_nota[carril]) >= MIN_NOTE_GAP:
            notas.append({
                "time": float(tiempo),
                "lane": carril
            })
            tiempo_ultima_nota[carril] = float(tiempo)

    print(f"  ✓ {len(notas)} notas generadas.")

    return {
        "cancion":      audio_path.name,
        "bpm_estimado": bpm,
        "duration":     float(duracion),
        "note_count":   len(notas),
        "notes":        notas,
    }

# ──────────────────────────────────────────────
#  ENDPOINTS
# ──────────────────────────────────────────────
def _wav_to_mp3(wav_path: Path) -> Path:
    """Convierte WAV a MP3 usando miniaudio + lameenc."""
    mp3_path = wav_path.with_suffix(".mp3")
    if mp3_path.exists():
        return mp3_path
    try:
        import lameenc
        decoded = miniaudio.decode_file(str(wav_path),
                    output_format=miniaudio.SampleFormat.SIGNED16,
                    nchannels=2,
                    sample_rate=44100)
        encoder = lameenc.Encoder()
        encoder.set_bit_rate(128)
        encoder.set_in_sample_rate(44100)
        encoder.set_channels(2)
        encoder.set_quality(2)
        mp3_data = encoder.encode(bytes(decoded.samples))
        mp3_data += encoder.flush()
        mp3_path.write_bytes(mp3_data)
        print(f"  [MP3] Convertido: {mp3_path.name}")
        return mp3_path
    except Exception as e:
        print(f"  [ERROR wav→mp3] {e}")
        return wav_path
    
@app.get("/songs")
def list_songs():
    """Lista todas las canciones disponibles."""
    songs = []
    for f in sorted(SONGS_DIR.iterdir()):
        if f.suffix.lower() in {".mp3", ".wav", ".ogg"}:
            songs.append({
                "name":        f.stem,
                "file":        f.name,
                "has_beatmap": f.with_suffix(".json").exists(),
            })
    return {"songs": songs}


@app.get("/songs/{filename}/audio")
def get_audio(filename: str):
    path = SONGS_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Audio no encontrado")

    # Convertir WAV a MP3 para compatibilidad con Godot Web
    if path.suffix.lower() == ".wav":
        path = _wav_to_mp3(path)

    return FileResponse(str(path), media_type="audio/mpeg")


@app.get("/songs/{filename}/beatmap")
def get_beatmap(filename: str):
    audio_path = SONGS_DIR / filename
    json_path  = audio_path.with_suffix(".json")

    print(f"Buscando: {audio_path}")
    print(f"Existe: {audio_path.exists()}")

    if not audio_path.exists():
        raise HTTPException(404, f"Canción no encontrada: {filename}")

    if not json_path.exists():
        try:
            print("Generando beatmap...")
            beatmap = _generar_beatmap(audio_path)
            json_path.write_text(json.dumps(beatmap), encoding="utf-8")
            print("Beatmap generado OK")
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            raise HTTPException(500, f"Error: {str(e)}")
    else:
        print("Beatmap ya existe, cargando...")
        beatmap = json.loads(json_path.read_text(encoding="utf-8"))

    return beatmap


@app.get("/search")
def search_songs(query: str, limit: int = 10):
    """Busca canciones en Jamendo."""
    url    = "https://api.jamendo.com/v3.0/tracks/"
    params = {
        "client_id":   CLIENT_ID,
        "format":      "json",
        "limit":       limit,
        "search":      query,
        "audioformat": "mp32",
        "include":     "musicinfo",
        "boost":       "popularity_total",
    }
    r    = requests.get(url, params=params, timeout=10)
    data = r.json()

    if data["headers"]["status"] != "success":
        raise HTTPException(500, "Error en Jamendo API")

    results = [
        {
            "id":       t["id"],
            "name":     t["name"],
            "artist":   t["artist_name"],
            "duration": t["duration"],
        }
        for t in data["results"]
    ]
    return {"results": results}


@app.post("/download/{track_id}")
def download_track(track_id: str):
    """Descarga una canción de Jamendo y genera su beatmap."""
    url    = "https://api.jamendo.com/v3.0/tracks/"
    params = {"client_id": CLIENT_ID, "format": "json",
              "id": track_id, "audioformat": "mp32"}
    r      = requests.get(url, params=params, timeout=10)
    data   = r.json()

    if not data["results"]:
        raise HTTPException(404, "Track no encontrado")

    track     = data["results"][0]
    nombre    = track["name"].strip()
    artista   = track["artist_name"].strip()
    audio_url = track["audio"]
    duracion  = int(track.get("duration", 0))

    if duracion < 60:
        raise HTTPException(400, "Canción muy corta")

    safe     = f"{artista} - {nombre}".replace("/","_").replace("\\","_").replace(":","−")
    mp3_path = SONGS_DIR / f"{safe}.mp3"

    if mp3_path.exists():
        # Ya existe, solo devolver beatmap
        json_path = mp3_path.with_suffix(".json")
        if not json_path.exists():
            beatmap = _generar_beatmap(mp3_path)
            json_path.write_text(json.dumps(beatmap), encoding="utf-8")
        else:
            beatmap = json.loads(json_path.read_text(encoding="utf-8"))
        return {"status": "already_exists", "file": mp3_path.name, "beatmap": beatmap}

    # Descargar MP3
    audio_r = requests.get(audio_url, stream=True, timeout=60)
    audio_r.raise_for_status()
    with open(mp3_path, "wb") as f:
        for chunk in audio_r.iter_content(8192):
            f.write(chunk)

    # Generar beatmap
    beatmap   = _generar_beatmap(mp3_path)
    json_path = mp3_path.with_suffix(".json")
    json_path.write_text(json.dumps(beatmap), encoding="utf-8")

    return {"status": "ok", "file": mp3_path.name, "beatmap": beatmap}


@app.post("/scores")
def save_score(data: dict):
    """Guarda un score en la base de datos."""
    conn = _get_db()
    conn.execute("""
        INSERT INTO scores
            (player_name, song_name, score, accuracy, max_combo, hit_notes, total_notes, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [data["player_name"], data["song_name"], data["score"],
          data["accuracy"],    data["max_combo"],  data["hit_notes"],
          data["total_notes"], data["date"]])
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.get("/scores/{song_name}")
def get_scores(song_name: str):
    """Devuelve el Top 10 de una canción."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT player_name, score, accuracy, max_combo, date
        FROM scores
        WHERE song_name = ?
        ORDER BY score DESC
        LIMIT 10
    """, [song_name]).fetchall()
    conn.close()
    return {"scores": [dict(r) for r in rows]}

