#!/usr/bin/env python3
"""
dj_state.py - Persistencia ligera del reproductor (JSON).
Guarda: últimos ajustes, favoritos, canción/pista donde quedaste y posición.
"""
import os
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, 'dj_state.json')

DEFAULTS = {
    'favorites': [],
    'shuffle': False,
    'last_track_path': None,
    'last_index': 0,
    'last_pos': 0.0,
    'last_context': 'Todo el dispositivo',
    'crossfade_sec': 3.0,
    'volume': 100,
    'voice_enabled': True,
}

class DjState:
    """Contenedor simple de estado con carga/guardado atómicos."""
    def __init__(self, path=None):
        self.path = path or STATE_FILE
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            if not os.path.exists(self.path):
                return
            with open(self.path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            for k, default in DEFAULTS.items():
                self.data[k] = loaded.get(k, default)
        except Exception:
            pass

    def save(self):
        try:
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            pass

    # Convenienza tipo dict
    def __getitem__(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key, value):
        self.data[key] = value