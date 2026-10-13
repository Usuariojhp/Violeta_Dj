"""Tests del motor de sets: Moods, Camelot y determinismo."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from set_engine import (  # noqa: E402
    build_set, filter_tracks, normalize_mood, next_mood,
    energy_at_phase, MOOD_ORDER,
)
from track_intel import camelot_compatible, camelot_from_key  # noqa: E402


def _track(path, energy, artist=None, duration=200, bpm=None, camelot=None):
    return {"path": path, "filename": os.path.basename(path),
            "artist": artist, "duration": duration, "energy": energy,
            "bpm": bpm, "camelot": camelot, "folder": "carpeta"}


def _biblioteca(n=60):
    tracks = []
    for i in range(n):
        tracks.append(_track(
            "carpeta/cancion_%03d.mp3" % i,
            energy=(i % 10) / 10.0,
            artist="artista_%d" % (i % 10),
            duration=180,
            bpm=100 + (i % 40),
            camelot=None,
        ))
    return tracks


def test_normalize_mood_aliases():
    assert normalize_mood("Chill") == "chill"
    assert normalize_mood("Fiesta") == "fiesta"
    assert normalize_mood("estudiar") == "enfoque"
    assert normalize_mood("para enfocar") == "enfoque"
    assert normalize_mood("rumba") == "fiesta"
    assert normalize_mood("joda") == "fiesta"
    assert normalize_mood("nonsense") is None
    assert normalize_mood(None) is None


def test_next_mood_rota():
    current = MOOD_ORDER[0]
    for _ in range(len(MOOD_ORDER)):
        current = next_mood(current)
    assert current in MOOD_ORDER


def test_curva_de_energia_subey_baja():
    chill = [energy_at_phase("chill", p) for p in (0, 0.5, 0.95, 1.0)]
    # sube hasta el pico y cierra por debajo del pico
    assert chill[1] > chill[0] and chill[1] > chill[3]
    fiesta = [energy_at_phase("fiesta", p) for p in (0, 0.5, 1.0)]
    assert fiesta[0] < fiesta[1] and fiesta[2] < fiesta[1]
    # fiesta arranca mas alta que chill
    assert energy_at_phase("fiesta", 0) > energy_at_phase("chill", 0)


def test_camelot_compatibilidad():
    assert camelot_from_key("A minor") == "8A"
    assert camelot_from_key("C major") == "8B"
    assert camelot_from_key("G major") == "9B"
    assert camelot_from_key("E minor") == "9A"
    assert camelot_from_key("garbage") is None
    assert camelot_compatible("8A", "8B")  # relativa
    assert camelot_compatible("8A", "9A")  # +1
    assert camelot_compatible("8A", "8A")
    assert not camelot_compatible("8A", "3A")  # lejano
    assert camelot_compatible(None, None)  # sin datos no restringe


def test_filter_tracks():
    lib = _biblioteca(20)
    assert len(filter_tracks(lib, "artista_3")) == 2
    assert len(filter_tracks(lib, ["artista_1", "artista_2"])) == 4
    assert len(filter_tracks(lib, "noexiste")) == 0
    assert len(filter_tracks(lib, None)) == 20


def test_build_set_determinista():
    lib = _biblioteca(60)
    a, info_a = build_set(lib, minutes=45, mood="fiesta", seed=42)
    b, info_b = build_set(lib, minutes=45, mood="fiesta", seed=42)
    assert [t["path"] for t in a] == [t["path"] for t in b]
    assert info_a["track_count"] == info_b["track_count"]
    assert info_a["mood"] == "fiesta"
    assert info_a["minutes"] >= 44


def test_build_set_mood_energia_ascendente():
    lib = _biblioteca(60)
    queue, info = build_set(lib, minutes=45, mood="fiesta", seed=7)
    assert queue, "cola vacia"
    assert queue[0]["energy"] >= 0.4  # fiesta arranca alta
    # sin repetir artista dos veces seguidas
    artists = [t["artist"] for t in queue]
    for prev, cur in zip(artists, artists[1:]):
        assert prev != cur


def test_build_set_sin_candidatos():
    queue, info = build_set(_biblioteca(5), minutes=10,
                            terms="noexiste")
    assert queue == []
    assert info["error"] == "sin_candidatos"
