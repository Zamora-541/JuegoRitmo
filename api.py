# -*- coding: utf-8 -*-
# download_songs.py
# Colócalo en la misma carpeta que generate_beatmaps.py
# Uso: python download_songs.py

import sys
import requests
import subprocess
import json
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ──────────────────────────────────────────────
#  CONFIGURACIÓN
# ──────────────────────────────────────────────

# Regístrate gratis en https://devportal.jamendo.com para obtener tu CLIENT_ID
CLIENT_ID = "baadf3c4"

# Carpeta donde viven tus canciones (misma lógica que tu script)
DIRECTORIO_ACTUAL   = Path(__file__).parent.resolve()
DIRECTORIO_CANCIONES = DIRECTORIO_ACTUAL.parent / "songs"

# Búsquedas a realizar — edita a tu gusto
BUSQUEDAS = [
    "electronic upbeat",
    "rock energetic",
    "chiptune",
]

CANCIONES_POR_BUSQUEDA = 3  # cuántas canciones bajar por cada búsqueda

# ──────────────────────────────────────────────
#  DESCARGA
# ──────────────────────────────────────────────

def buscar_canciones(query: str, limit: int) -> list:
    url = "https://api.jamendo.com/v3.0/tracks/"
    params = {
        "client_id":    CLIENT_ID,
        "format":       "json",
        "limit":        limit,
        "search":       query,
        "audioformat":  "mp32",
        "include":      "musicinfo",
        "boost":        "popularity_total",  # las más populares primero
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data["headers"]["status"] != "success":
            print(f"  [ERROR API] {data['headers'].get('error_message', 'desconocido')}")
            return []
        return data["results"]
    except Exception as e:
        print(f"  [ERROR red] {e}")
        return []


def descargar_cancion(track: dict) -> bool:
    nombre    = track["name"].strip()
    artista   = track["artist_name"].strip()
    audio_url = track["audio"]
    duracion  = int(track.get("duration", 0))

    # Ignorar canciones muy cortas (menos de 60 segundos)
    if duracion < 60:
        print(f"  Saltando '{nombre}' — muy corta ({duracion}s)")
        return False

    # Nombre de archivo seguro
    safe = f"{artista} - {nombre}".replace("/", "_").replace("\\", "_") \
                                   .replace(":", "-").replace("?", "")
    ruta_mp3  = DIRECTORIO_CANCIONES / f"{safe}.mp3"
    ruta_json = DIRECTORIO_CANCIONES / f"{safe}.json"

    # Si ya existe el audio o el beatmap, saltar
    if ruta_mp3.exists():
        print(f"  Ya existe : {ruta_mp3.name}")
        return False
    if ruta_json.exists():
        print(f"  Beatmap ya existe para : {safe}")
        return False

    print(f"  Descargando : {artista} - {nombre} ({duracion}s) ...")
    try:
        r = requests.get(audio_url, stream=True, timeout=30)
        r.raise_for_status()
        with open(ruta_mp3, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"  [OK] Guardado en {ruta_mp3.name}")
        convertir_a_wav(ruta_mp3)
        return True
    except Exception as e:
        print(f"  [ERROR descarga] {e}")
        # Borrar archivo incompleto si quedó
        if ruta_mp3.exists():
            ruta_mp3.unlink()
        return False
def buscar_preview(query: str, limit: int = 10) -> list:
    """Solo busca y devuelve resultados sin descargar nada."""
    url = "https://api.jamendo.com/v3.0/tracks/"
    params = {
        "client_id":   CLIENT_ID,
        "format":      "json",
        "limit":       limit,
        "search":      query,
        "audioformat": "mp32",
        "include":     "musicinfo",
        "boost":       "popularity_total",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data["headers"]["status"] != "success":
            return []
        results = []
        for t in data["results"]:
            results.append({
                "id":       t["id"],
                "name":     t["name"],
                "artist":   t["artist_name"],
                "duration": t["duration"],
                "audio":    t["audio"],
            })
        return results
    except Exception as e:
        print(f"[ERROR] {e}")
        return []


def descargar_por_id(track_id: str, tracks_cache: list) -> bool:
    """Descarga una canción específica por su ID desde el cache de búsqueda."""
    track = next((t for t in tracks_cache if str(t["id"]) == str(track_id)), None)
    if track is None:
        print(f"[ERROR] No se encontró el track con id {track_id}")
        return False

    # Convertir al formato que espera descargar_cancion
    track_fmt = {
        "name":        track["name"],
        "artist_name": track["artist"],  # ← buscar_preview usa "artist", descargar_cancion espera "artist_name"
        "audio":       track["audio"],
        "duration":    track["duration"],
    }
    return descargar_cancion(track_fmt)
def convertir_a_wav(ruta_mp3: Path) -> Path:
    """Convierte mp3 a wav usando ffmpeg."""
    ruta_wav = ruta_mp3.with_suffix(".wav")
    if ruta_wav.exists():
        return ruta_wav
    try:
        subprocess.run([
            "ffmpeg", "-i", str(ruta_mp3),
            "-ar", "44100",
            "-ac", "2",
            str(ruta_wav)
        ], check=True, capture_output=True)
        ruta_mp3.unlink()  # borrar el mp3 original
        print(f"  [WAV] Convertido: {ruta_wav.name}")
        return ruta_wav
    except Exception as e:
        print(f"  [ERROR ffmpeg] {e}")
        return ruta_mp3
# ──────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--query",    default="", help="Búsqueda de canciones")
    parser.add_argument("--limit",    default=10, type=int)
    parser.add_argument("--download", default="", help="ID del track a descargar")
    parser.add_argument("--auto",     action="store_true")
    args = parser.parse_args()

    if CLIENT_ID == "tu_client_id_aqui":
        print("ERROR: Configura tu CLIENT_ID")
        raise SystemExit(1)

    DIRECTORIO_CANCIONES.mkdir(parents=True, exist_ok=True)

    # Modo búsqueda — devuelve JSON con resultados
    if args.query and not args.download:
        results = buscar_preview(args.query, args.limit)
        print("RESULTS:" + json.dumps(results, ensure_ascii=False))
        raise SystemExit(0)

    # Modo descarga — descarga un track específico por ID
    if args.download and args.query:
        results = buscar_preview(args.query, args.limit)
        ok = descargar_por_id(args.download, results)
        print("DESCARGA_OK" if ok else "DESCARGA_FAIL")
        raise SystemExit(0)

    # Modo automático original
    if args.auto:
        descargadas = 0
        for query in BUSQUEDAS:
            tracks = buscar_canciones(query, args.limit)
            for track in tracks:
                if descargar_cancion(track):
                    descargadas += 1
        if descargadas > 0:
            script_beatmap = DIRECTORIO_ACTUAL / "python_song_analyzer.py"
            if script_beatmap.exists():
                subprocess.run([sys.executable, str(script_beatmap)], check=True)
        print(f"Descargadas: {descargadas}")