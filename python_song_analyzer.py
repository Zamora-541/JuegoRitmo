import librosa
import json
import numpy as np
import os
from pathlib import Path

def crear_beatmap(archivo_audio, archivo_json_salida):
    print(f"\nAnalizando: {Path(archivo_audio).name}...")
    
    try:
        # 1. Cargar audio (sr=None mantiene la calidad y frecuencia original)
        y, sr = librosa.load(archivo_audio, sr=None)
        duracion = librosa.get_duration(y=y, sr=sr)

        # 2. Detección de BPM (Tempo)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
        print(f"  - BPM Estimado: {bpm:.2f}")

        # 3. Detección de Onsets (Los golpes secos / notas)
        onset_frames = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True)
        onset_times = librosa.frames_to_time(onset_frames, sr=sr)

        # 4. Calcular el "Centroide Espectral" para mapear carriles
        centroides = librosa.feature.spectral_centroid(y=y, sr=sr)[0]

        notas = []
        # Cambiamos el historial de 8 a 6 carriles
        tiempo_ultima_nota = [-999.0] * 6
        MIN_NOTE_GAP = 0.09

        for i, tiempo in enumerate(onset_times):
            frame_idx = onset_frames[i]
            if frame_idx >= len(centroides):
                frame_idx = len(centroides) - 1
                
            frecuencia_promedio = centroides[frame_idx]

            # Nuevo mapeo de frecuencias a 6 carriles
            if frecuencia_promedio < 1200:
                carril = int(np.random.randint(0, 2)) # Graves (Carriles 0 y 1)
            elif frecuencia_promedio < 3500:
                carril = int(np.random.randint(2, 4)) # Medios (Carriles 2 y 3)
            else:
                carril = int(np.random.randint(4, 6)) # Agudos (Carriles 4 y 5)

            if (tiempo - tiempo_ultima_nota[carril]) >= MIN_NOTE_GAP:
                notas.append({
                    "time": float(tiempo),
                    "lane": carril
                })
                tiempo_ultima_nota[carril] = float(tiempo)

        # 5. Ensamblar el JSON
        beatmap = {
            "cancion": Path(archivo_audio).name,
            "bpm_estimado": bpm,
            "duration": float(duracion),
            "note_count": len(notas),
            "notes": notas
        }

        # 6. Guardar archivo
        with open(archivo_json_salida, 'w') as f:
            json.dump(beatmap, f, indent=4)
            
        print(f"  ✓ ¡Éxito! {len(notas)} notas guardadas.")
        
    except Exception as e:
        print(f"  ❌ Error al procesar {Path(archivo_audio).name}: {e}")

# ---- LÓGICA DE ESCANEO DE CARPETAS ----
if __name__ == "__main__":
    # Obtiene la ruta de la carpeta "scripts" (donde está este archivo)
    directorio_actual = Path(__file__).parent.resolve()
    
    # Sube un nivel y entra a "songs"
    directorio_canciones = directorio_actual.parent / "songs"
    
    print(f"Buscando canciones en: {directorio_canciones}")
    
    if not directorio_canciones.exists():
        print("La carpeta 'songs' no existe. Por favor, créala en la raíz del proyecto.")
        exit()

    # Formatos de audio soportados
    extensiones_validas = ['.wav', '.ogg', '.mp3']
    archivos_encontrados = 0

    # Escanear la carpeta
    for archivo in directorio_canciones.iterdir():
        if archivo.is_file() and archivo.suffix.lower() in extensiones_validas:
            archivos_encontrados += 1
            
            # Crear el nombre del archivo JSON (ej: KATAMARI.wav -> KATAMARI.json)
            archivo_json = archivo.with_suffix('.json')
            
            # Si el JSON ya existe, no perdemos tiempo volviendo a analizar
            if archivo_json.exists():
                print(f"\nSaltando: {archivo.name} (El beatmap ya existe)")
                continue
                
            # Procesar si no existe
            crear_beatmap(str(archivo), str(archivo_json))

    if archivos_encontrados == 0:
        print("\nNo se encontraron canciones .wav, .ogg o .mp3 en la carpeta 'songs/'.")
    else:
        print("\n=== Procesamiento terminado ===")