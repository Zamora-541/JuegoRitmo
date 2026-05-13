# -*- coding: utf-8 -*-
# server.py — Backend FastAPI para el rhythm game

import base64
import io
import json
import os
import random
import subprocess
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import librosa
import miniaudio
import numpy as np
import requests
import sqlite3
import soundfile as sf
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydub import AudioSegment

# Carga el archivo .env en desarrollo local.
# En Railway no hace nada (las variables ya están en os.environ via el panel).
load_dotenv()

# ──────────────────────────────────────────────
#  CONFIGURACIÓN
# ──────────────────────────────────────────────
CLIENT_ID  = "baadf3c4"
SONGS_DIR  = Path(__file__).parent / "songs"
DB_PATH    = Path(__file__).parent / "scores.db"
CACHE_DIR  = Path(__file__).parent / "video_cache"
SONGS_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)



VIDEO_FRAME_COUNT = 8
VIDEO_WIDTH       = 320
VIDEO_HEIGHT      = 180
VIDEO_CLIP_SECS   = 30

# ──────────────────────────────────────────────
#  FASTAPI APP
# ──────────────────────────────────────────────


# Lee la API key. En local viene del .env; en Railway viene del panel de Variables.
scriptingString = 'AIzaSyDqYUpcbE-pg1FgOJrh6upqSHovQMUYs9c'

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
#  GENERACIÓN DE BEATMAP
# ──────────────────────────────────────────────
def _generar_beatmap(audio_path: Path) -> dict:
    print(f"\nAnalizando: {audio_path.name}...")
    ext = audio_path.suffix.lower()

    try:
        if ext in (".mp3", ".wav"):
            decoded = miniaudio.decode_file(str(audio_path),
                        output_format=miniaudio.SampleFormat.FLOAT32,
                        nchannels=1, sample_rate=22050)
            sr = decoded.sample_rate
            y  = np.frombuffer(decoded.samples, dtype=np.float32).copy()
        else:
            y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    except Exception as e:
        print(f"  Error cargando audio: {e}")
        raise

    duracion     = librosa.get_duration(y=y, sr=sr)
    tempo, _     = librosa.beat.beat_track(y=y, sr=sr)
    bpm          = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
    print(f"  - BPM Estimado: {bpm:.2f}")

    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True)
    onset_times  = librosa.frames_to_time(onset_frames, sr=sr)
    centroides   = librosa.feature.spectral_centroid(y=y, sr=sr)[0]

    notas              = []
    tiempo_ultima_nota = [-999.0] * 6
    MIN_NOTE_GAP       = 0.09

    for i, tiempo in enumerate(onset_times):
        frame_idx = min(onset_frames[i], len(centroides) - 1)
        freq      = centroides[frame_idx]

        if freq < 1200:
            carril = int(np.random.randint(0, 2))
        elif freq < 3500:
            carril = int(np.random.randint(2, 4))
        else:
            carril = int(np.random.randint(4, 6))

        if (tiempo - tiempo_ultima_nota[carril]) >= MIN_NOTE_GAP:
            notas.append({"time": float(tiempo), "lane": carril})
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
#  ENDPOINTS DE CANCIONES
# ──────────────────────────────────────────────
def _wav_to_mp3(wav_path: Path) -> Path:
    mp3_path = wav_path.with_suffix(".mp3")
    if mp3_path.exists():
        return mp3_path
    try:
        import lameenc
        decoded = miniaudio.decode_file(str(wav_path),
                    output_format=miniaudio.SampleFormat.SIGNED16,
                    nchannels=2, sample_rate=44100)
        encoder = lameenc.Encoder()
        encoder.set_bit_rate(128)
        encoder.set_in_sample_rate(44100)
        encoder.set_channels(2)
        encoder.set_quality(2)
        mp3_data  = encoder.encode(bytes(decoded.samples))
        mp3_data += encoder.flush()
        mp3_path.write_bytes(mp3_data)
        print(f"  [MP3] Convertido: {mp3_path.name}")
        return mp3_path
    except Exception as e:
        print(f"  [ERROR wav→mp3] {e}")
        return wav_path


@app.get("/songs")
def list_songs():
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
    if path.suffix.lower() == ".wav":
        path = _wav_to_mp3(path)
    return FileResponse(str(path), media_type="audio/mpeg")


@app.get("/songs/{filename}/beatmap")
def get_beatmap(filename: str):
    audio_path = SONGS_DIR / filename
    json_path  = audio_path.with_suffix(".json")

    if not audio_path.exists():
        raise HTTPException(404, f"Canción no encontrada: {filename}")

    if not json_path.exists():
        try:
            beatmap = _generar_beatmap(audio_path)
            json_path.write_text(json.dumps(beatmap), encoding="utf-8")
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            raise HTTPException(500, f"Error: {str(e)}")
    else:
        beatmap = json.loads(json_path.read_text(encoding="utf-8"))

    return beatmap


@app.get("/search")
def search_songs(query: str, limit: int = 10):
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
    return {"results": [
        {"id": t["id"], "name": t["name"], "artist": t["artist_name"], "duration": t["duration"]}
        for t in data["results"]
    ]}


@app.post("/download/{track_id}")
def download_track(track_id: str):
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
        json_path = mp3_path.with_suffix(".json")
        if not json_path.exists():
            beatmap = _generar_beatmap(mp3_path)
            json_path.write_text(json.dumps(beatmap), encoding="utf-8")
        else:
            beatmap = json.loads(json_path.read_text(encoding="utf-8"))
        return {"status": "already_exists", "file": mp3_path.name, "beatmap": beatmap}

    audio_r = requests.get(audio_url, stream=True, timeout=60)
    audio_r.raise_for_status()
    with open(mp3_path, "wb") as f:
        for chunk in audio_r.iter_content(8192):
            f.write(chunk)

    beatmap   = _generar_beatmap(mp3_path)
    json_path = mp3_path.with_suffix(".json")
    json_path.write_text(json.dumps(beatmap), encoding="utf-8")
    return {"status": "ok", "file": mp3_path.name, "beatmap": beatmap}


@app.post("/scores")
def save_score(data: dict):
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
    conn = _get_db()
    rows = conn.execute("""
        SELECT player_name, score, accuracy, max_combo, date
        FROM scores WHERE song_name = ?
        ORDER BY score DESC LIMIT 10
    """, [song_name]).fetchall()
    conn.close()
    return {"scores": [dict(r) for r in rows]}

# ──────────────────────────────────────────────
#  VIDEO BACKGROUND
# ──────────────────────────────────────────────

def _yt_search(query: str) -> dict | None:
    if not scriptingString:
        print("  [video_bg] YOUTUBE_API_KEY no configurada.")
        return None
    try:
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={"key": scriptingString, "q": query, "part": "snippet",
                    "type": "video", "maxResults": 1, "videoCategoryId": "10"},
            timeout=8,
        )
        items = r.json().get("items", [])
        if not items:
            return None
        vid = items[0]["id"]["videoId"]
        return {
            "video_id":      vid,
            "title":         items[0]["snippet"]["title"],
            "thumbnail_url": f"https://img.youtube.com/vi/{vid}/mqdefault.jpg",
        }
    except Exception as e:
        print(f"  [video_bg] Error YouTube search: {e}")
        return None


def _extract_frames(video_id: str, cache_path: Path) -> list[str]:
    try:
        import yt_dlp
        from PIL import Image
    except ImportError:
        print("  [video_bg] yt-dlp o Pillow no instalados.")
        return []

    video_file = cache_path / f"{video_id}.mp4"
    if not video_file.exists():
        try:
            with yt_dlp.YoutubeDL({
                "format":      "worst[ext=mp4]/worst",
                "outtmpl":     str(video_file),
                "quiet":       True,
                "noplaylist":  True,
                "download_ranges":         lambda _i, _: [{"start_time": 0, "end_time": VIDEO_CLIP_SECS}],
                "force_keyframes_at_cuts": True,
            }) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
        except Exception as e:
            print(f"  [video_bg] yt-dlp error: {e}")
            return []

    if not video_file.exists():
        return []

    frames = []
    try:
        from PIL import Image
        interval = VIDEO_CLIP_SECS / VIDEO_FRAME_COUNT
        with tempfile.TemporaryDirectory() as tmp:
            cmd = [
                "ffmpeg", "-y", "-i", str(video_file),
                "-vf", f"fps=1/{interval:.2f},scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}",
                "-frames:v", str(VIDEO_FRAME_COUNT), "-q:v", "6",
                str(Path(tmp) / "f_%02d.jpg"),
            ]
            if subprocess.run(cmd, capture_output=True, timeout=30).returncode != 0:
                return []
            for f in sorted(Path(tmp).glob("f_*.jpg")):
                img = Image.open(f).resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=60)
                frames.append(base64.b64encode(buf.getvalue()).decode("utf-8"))
    except Exception as e:
        print(f"  [video_bg] Error extrayendo frames: {e}")

    print(f"  [video_bg] {len(frames)} frames extraídos de {video_id}.")
    return frames


def _thumbnail_b64(url: str) -> str | None:
    try:
        from PIL import Image
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).resize(
            (VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=65)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"  [video_bg] Error thumbnail: {e}")
        return None


@app.get("/video_bg/{song_name}")
def get_video_bg(song_name: str):
    """
    Devuelve frames JPEG en base64 para el fondo animado del gameplay.
    Respuesta: { video_id, title, source, frames: ["<b64 JPEG>", ...] }
    Cachea en disco para que la segunda petición sea instantánea.
    """
    safe_name  = song_name.replace("/", "_").replace("\\", "_").strip()
    cache_path = CACHE_DIR / safe_name
    meta_file  = cache_path / "meta.json"

    # Cache hit — devolver directo sin volver a buscar en YouTube
    if meta_file.exists():
        meta   = json.loads(meta_file.read_text(encoding="utf-8"))
        frames = [
            base64.b64encode(f.read_bytes()).decode("utf-8")
            for f in sorted(cache_path.glob("frame_*.jpg"))
        ]
        if frames:
            return {**meta, "frames": frames}

    yt = _yt_search(f"{song_name} official audio")
    if not yt:
        raise HTTPException(404, f"No se encontró video para: {song_name}")

    cache_path.mkdir(parents=True, exist_ok=True)
    frames = _extract_frames(yt["video_id"], cache_path)
    source = "frames"

    # Fallback: solo thumbnail si yt-dlp o ffmpeg fallan
    if not frames:
        b64 = _thumbnail_b64(yt["thumbnail_url"])
        if not b64:
            raise HTTPException(404, "No se pudo obtener imagen de fondo.")
        frames = [b64]
        source = "thumbnail"

    # Cachear frames en disco
    for i, f_b64 in enumerate(frames):
        (cache_path / f"frame_{i:02d}.jpg").write_bytes(base64.b64decode(f_b64))

    meta = {"video_id": yt["video_id"], "title": yt["title"], "source": source}
    meta_file.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return {**meta, "frames": frames}


# ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
