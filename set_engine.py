#!/usr/bin/env python3
"""
set_engine.py - Motor de Auto-DJ: arma la cola usando mezcla armonica
(rueda de Camelot), curva de energia por mood y variedad de artistas.

build_set() es determinista: con la misma semilla y la misma biblioteca
devuelve la misma cola, lo que permite testearlo.
"""
import math
import random

from track_intel import camelot_compatible

MOODS = {
    # curva de energia por tercios del set: (inicio, desarrollo, cierre)
    "chill":    (0.15, 0.35, 0.20),
    "energico": (0.45, 0.85, 0.60),
    "fiesta":   (0.70, 0.95, 0.85),
    "enfoque":  (0.10, 0.25, 0.15),
}

MOOD_LABELS = {
    "chill": "tranquilo",
    "energico": "energico",
    "fiesta": "de fiesta",
    "enfoque": "para enfocar",
}

DEFAULT_MOOD = "chill"
MOOD_ORDER = ["chill", "energico", "fiesta", "enfoque"]


def normalize_mood(mood):
    if not mood:
        return None
    text = str(mood).strip().lower()
    sin_acento = (text.replace("á", "a").replace("é", "e")
                  .replace("í", "i").replace("ó", "o").replace("ú", "u"))
    for candidate in (sin_acento, text):
        if candidate in MOODS:
            return candidate
    aliases = {
        "tranqui": "chill", "relajado": "chill", "calmado": "chill",
        "suave": "chill", "chillout": "chill", "relax": "chill",
        "bailable": "fiesta", "fiesta": "fiesta", "rumba": "fiesta",
        "joda": "fiesta", "party": "fiesta", "fiestera": "fiesta",
        "fuerte": "energico", "rock": "energico", "gym": "energico",
        "entrenar": "energico", "ejercicio": "energico",
        "estudiar": "enfoque", "concentrar": "enfoque", "enfocar": "enfoque",
        "trabajar": "enfoque", "focus": "enfoque", "concentracion": "enfoque",
    }
    for alias, mapped in aliases.items():
        if alias in sin_acento:
            return mapped
    return None


def energy_at_phase(mood, phase):
    """phase = progreso 0-1 del set."""
    start, peak, end = MOODS.get(mood, MOODS[DEFAULT_MOOD])
    if phase < 0.8:
        frac = phase / 0.8
        return start + (peak - start) * frac
    frac = (phase - 0.8) / 0.2
    return peak + (end - peak) * frac


def _duration(track):
    dur = track.get("duration")
    return float(dur) if dur and float(dur) > 1 else 240.0


def _artist_of(track):
    return (track.get("artist") or track.get("folder") or "").strip().lower()


def _key_compatible(track, previous):
    if not previous:
        return True
    camelot = track.get("camelot")
    prev_camelot = previous.get("camelot")
    if not camelot or not prev_camelot:
        return True  # sin analisis de audio, no restringimos
    return camelot_compatible(prev_camelot, camelot)


def _bpm_compatible(track, previous):
    if not previous:
        return True
    bpm_a, bpm_b = track.get("bpm"), previous.get("bpm")
    if not bpm_a or not bpm_b:
        return True
    ratio = bpm_b and max(bpm_a, bpm_b) / min(bpm_a, bpm_b)
    return ratio is None or ratio <= 1.15


def filter_tracks(tracks, terms):
    """Filtra pistas por uno o varios terminos (path/nombre/carpeta/genero)."""
    if not terms:
        return list(tracks)
    if isinstance(terms, str):
        terms = [terms]
    terms = [str(t).lower().strip() for t in terms if str(t).strip()]
    if not terms:
        return list(tracks)
    out = []
    for track in tracks:
        blob = " ".join(str(track.get(k) or "").lower()
                        for k in ("filename", "folder", "artist",
                                   "title", "genre", "path"))
        if any(term in blob for term in terms):
            out.append(track)
    return out


def build_set(all_tracks, minutes=45, mood=DEFAULT_MOOD, terms=None,
              avoid_repeat=True, seed=None, max_tracks=None):
    """Arma una cola ordenada segun mood y duracion objetivo.

    Devuelve (tracks_ordenados, info).
    """
    mood = normalize_mood(mood) or DEFAULT_MOOD
    candidates = filter_tracks(all_tracks, terms)
    if not candidates:
        return [], {"error": "sin_candidatos", "mood": mood, "minutes": minutes}

    rng = random.Random(seed)
    pool = list(candidates)
    rng.shuffle(pool)

    target_sec = float(minutes) * 60.0 if minutes else 0
    queue = []
    used_keys = set()
    last_artist = None
    previous = None
    total = 0.0

    while pool:
        if target_sec and total >= target_sec:
            break
        phase = (total / target_sec) if target_sec else len(queue) / max(1, len(candidates))
        phase = max(0.0, min(1.0, phase))
        target_energy = energy_at_phase(mood, phase)

        best = None
        best_score = None
        for track in pool[:400]:
            energy = float(track.get("energy") or 0.5)
            score = abs(energy - target_energy)
            if not _key_compatible(track, previous):
                score += 0.25
            if not _bpm_compatible(track, previous):
                score += 0.2
            if avoid_repeat:
                artist = _artist_of(track)
                if artist and artist == last_artist:
                    score += 0.6
                if path_key(track) in used_keys:
                    score += 0.4
            score += rng.random() * 0.08  # pequena busqueda aleatoria
            if best_score is None or score < best_score:
                best, best_score = track, score
        if best is None:
            break
        pool.remove(best)
        queue.append(best)
        used_keys.add(path_key(best))
        last_artist = _artist_of(best)
        previous = best
        total += _duration(best)
        if max_tracks and len(queue) >= max_tracks:
            break

    if not queue:
        return [], {"error": "cola_vacia", "mood": mood, "minutes": minutes}

    info = {
        "mood": mood,
        "mood_label": MOOD_LABELS.get(mood, mood),
        "minutes": round(total / 60.0, 1),
        "track_count": len(queue),
        "terms": terms,
        "energy_start": round(queue[0].get("energy", 0.5), 2),
        "energy_end": round(queue[-1].get("energy", 0.5), 2),
    }
    return queue, info


def path_key(track):
    return track.get("path") or track.get("filename") or id(track)


def next_mood(current):
    """Rota el mood (para el atajo de teclado M)."""
    current = normalize_mood(current) or DEFAULT_MOOD
    idx = MOOD_ORDER.index(current)
    return MOOD_ORDER[(idx + 1) % len(MOOD_ORDER)]
