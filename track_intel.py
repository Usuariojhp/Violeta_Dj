#!/usr/bin/env python3
"""
track_intel.py - Enriquece las pistas con metadatos reales (mutagen) y,
si se pide, BPM y tonalidad con librosa (dependencia opcional).

Todo se cachea en ~/.cache/ai_dj/intel.json (por ruta + mtime + tamano),
asi que el segundo escaneo es instantaneo. En Android/Termux donde librosa
pesa demasiado, el modo heuristico deduce energia por nombre/carpeta/genero.
"""
import os
import json

CACHE_PATH = os.path.join(os.path.expanduser("~/.cache/ai_dj"), "intel.json")

# Rueda de Camelot: clase de tono -> (numero, letra) segun modo
PITCH_CLASS = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
               "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 10}

GENRE_ENERGY = {
    "reggaeton": 0.95, "electro": 0.9, "techno": 0.92, "house": 0.88,
    "pop": 0.75, "rock": 0.8, "metal": 0.88, "punk": 0.85, "trap": 0.85,
    "hip hop": 0.8, "rap": 0.8, "cumbia": 0.85, "salsa": 0.88,
    "jazz": 0.4, "blues": 0.35, "clasica": 0.3, "clásico": 0.3,
    "ambient": 0.15, "lofi": 0.3, "acustico": 0.4, "acústico": 0.4,
    "balada": 0.35, "romantico": 0.35, "romántico": 0.35, "infantil": 0.5,
    "bailable": 0.9, "dance": 0.9, "edm": 0.92, "trance": 0.9,
}

KEY_ALIAS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}


def _load_cache():
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass


def _major_number(pc):
    """Numero Camelot de una tonalidad mayor (C major = 8)."""
    return ((pc * 7 + 7) % 12) + 1


def camelot_from_key(key_str):
    """'A minor' -> '8A', 'C major' -> '8B'. None si no se puede mapear."""
    if not key_str:
        return None
    parts = key_str.strip().split()
    if len(parts) < 2:
        return None
    tonic, mode = parts[0], parts[1].lower()
    tonic = KEY_ALIAS.get(tonic, tonic)
    if tonic not in PITCH_CLASS:
        return None
    pc = PITCH_CLASS[tonic]
    if mode.startswith("minor") or mode in ("min", "m"):
        # la relativa mayor esta 3 semitonos arriba: A minor -> C major
        pc = (pc + 3) % 12
        return "%dA" % _major_number(pc)
    return "%dB" % _major_number(pc)


def camelot_compatible(a, b):
    """Mezcla armonica: mismo numero, +-1 numero misma letra, o relativo."""
    if not a or not b or a == b:
        return True
    try:
        na, la = int(a[:-1]), a[-1].upper()
        nb, lb = int(b[:-1]), b[-1].upper()
    except Exception:
        return True
    if la == lb and abs((na - nb) % 12) in (0, 1):
        return True
    if na == nb and la != lb:
        return True  # relativa mayor/menor
    return (na - nb) % 12 in (1, 11) and la == lb


def detect_bpm_key(path):
    """Devuelve (bpm, key) o (None, None). Requiere librosa."""
    try:
        import librosa
    except Exception:
        return None, None
    try:
        y, sr = librosa.load(path, sr=22050, mono=True, duration=90)
        if y.size == 0:
            return None, None
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(round(float(tempo), 1)) if tempo is not None else None
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
        import numpy as np
        maj = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19,
                        2.39, 3.66, 2.29, 2.88])
        mnr = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75,
                        3.98, 2.69, 3.34, 3.17])
        names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        scores_maj = [(float(np.corrcoef(chroma, np.roll(maj, i))[0, 1]), i, 0)
                      for i in range(12)]
        scores_min = [(float(np.corrcoef(chroma, np.roll(mnr, i))[0, 1]), i, 1)
                      for i in range(12)]
        best = max(scores_maj + scores_min)
        key = "%s %s" % (names[best[1]], "major" if best[2] == 0 else "minor")
        return bpm, key
    except Exception:
        return None, None


def _duration_seconds(track):
    return float(track.get("duration") or 0) or 0.0


def heuristic_energy(track):
    """Energia estimada 0-1 sin analizar audio (para Termux / rapidez)."""
    blob = " ".join(str(track.get(k) or "").lower()
                    for k in ("filename", "folder", "artist", "title", "genre"))
    energy = None
    for word, val in GENRE_ENERGY.items():
        if word in blob:
            energy = val if energy is None else max(energy, val)
    if energy is None:
        energy = 0.5
    return min(1.0, max(0.05, energy))


def enrich_tracks(tracks, use_audio=False, force=False):
    """Completa cada track con: artist, title, duration, genre, bpm, key,
    energy (0-1). Devuelve la lista de tracks modificada y el reporte."""
    cache = _load_cache()
    updated = 0
    for track in tracks:
        path = track.get("path", "")
        key = path or track.get("filename", "?")
        entry = cache.get(key)
        stamp = None
        try:
            st = os.stat(path)
            stamp = "%d-%d" % (int(st.st_mtime), int(st.st_size))
        except OSError:
            stamp = None
        if entry and entry.get("stamp") == stamp and not force:
            track.update({k: entry.get(k) for k in
                          ("duration", "genre", "bpm", "key", "energy")})
            continue

        try:
            from mutagen import File as MutagenFile
        except Exception:
            MutagenFile = None

        duration = None
        genre = None
        if MutagenFile and os.path.isfile(path):
            try:
                audio = MutagenFile(path)
                if audio is not None:
                    duration = float(audio.info.length) if audio.info else None
                    tags = audio.tags or {}
                    for tag in ("TCON", "genre", "GENRE"):
                        if tag in tags:
                            val = tags[tag]
                            val = val[0] if isinstance(val, list) else val
                            genre = str(getattr(val, "text", [""])[0]
                                        if hasattr(val, "text") else val)
                            break
            except Exception:
                pass

        bpm = key = None
        if use_audio and os.path.isfile(path):
            bpm, key = detect_bpm_key(path)
            if key:
                key_full = camelot_from_key(key)

        if not duration and track.get("duration"):
            duration = track["duration"]

        enriched = {"stamp": stamp, "duration": duration, "genre": genre,
                    "bpm": bpm, "key": key}
        track.update(enriched)
        if key:
            track["camelot"] = camelot_from_key(key)
        track["energy"] = heuristic_energy(track)
        cache[key] = dict(enriched, energy=track["energy"])
        updated += 1

    _save_cache(cache)
    for track in tracks:
        if track.get("energy") is None:
            track["energy"] = heuristic_energy(track)
    return tracks, {"enriched": updated, "total": len(tracks),
                    "audio_analysis": bool(use_audio)}
