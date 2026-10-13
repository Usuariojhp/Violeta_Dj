#!/usr/bin/env python3
"""
dj_commentator.py - Generador de guiones y voz de locucion.
Soporta modo online (Edge-TTS) y modo 100% offline (Piper TTS local ultraligero).
"""
import os
import wave
import random
import asyncio
import tempfile

from dj_brain import get_brain

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_VOICE = "es-MX-DaliaNeural"
PIPER_MODEL = os.path.join(SCRIPT_DIR, "voices", "es_ES-sharvard-medium.onnx")
PIPER_CONFIG = os.path.join(SCRIPT_DIR, "voices", "es_ES-sharvard-medium.onnx.json")

class DJCommentator:
    def __init__(self, voice=DEFAULT_VOICE, cache_dir=None, force_offline=False):
        self.voice = voice
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), "dj_livi_audio")
        self.force_offline = force_offline
        os.makedirs(self.cache_dir, exist_ok=True)
        self.user_name = "Jose"
        self.piper_voice = None
        self.brain = get_brain()

        if os.path.exists(PIPER_MODEL) and os.path.exists(PIPER_CONFIG):
            try:
                from piper import PiperVoice
                self.piper_voice = PiperVoice.load(PIPER_MODEL, PIPER_CONFIG)
            except Exception as e:
                pass

    def _pick(self, brain_line, fallback_lines):
        """Prioriza la linea del LLM; si no hay, usa las plantillas de siempre."""
        if brain_line:
            return brain_line
        return random.choice(fallback_lines)

    def format_track_name(self, track):
        artist = track.get('artist')
        title = track.get('title')
        if artist and title:
            return f"{title} de {artist}"
        return title or track.get('filename', 'esta pista')

    def generate_welcome_script(self, context_name, first_track):
        track_str = self.format_track_name(first_track)
        lines = [
            f"Hola {self.user_name}. Todo listo en el reproductor. Iniciamos con {track_str}.",
            f"Saludos {self.user_name}. Reproduciendo tu musica desde {context_name}. A continuacion, {track_str}.",
            f"Sesion iniciada. Disfruta la mezcla continua con {track_str}."
        ]
        if self.force_offline:
            return self._pick(None, lines)
        return self._pick(self.brain.welcome_line(context_name, first_track), lines)

    def generate_folder_switch_script(self, folder_name, next_track):
        track_str = self.format_track_name(next_track)
        lines = [
            f"Cambiando a la carpeta {folder_name}. Iniciamos con {track_str}.",
            f"Reproduciendo desde {folder_name}. Suena {track_str}.",
            f"Seleccion de {folder_name}. En cabina, {track_str}."
        ]
        if self.force_offline:
            return self._pick(None, lines)
        return self._pick(self.brain.folder_switch_line(folder_name, next_track), lines)

    def generate_shuffle_intro(self, next_track):
        track_str = self.format_track_name(next_track)
        lines = [
            f"Modo aleatorio activado. Sonando {track_str}.",
            f"Mezcla aleatoria iniciada. Escuchas {track_str}.",
            f"Reproduccion aleatoria. En cabina, {track_str}."
        ]
        if self.force_offline:
            return self._pick(None, lines)
        return self._pick(self.brain.shuffle_line(next_track), lines)

    def generate_track_intro_script(self, track):
        track_str = self.format_track_name(track)
        lines = [
            f"A continuacion, {track_str}.",
            f"Seguimos sin cortes con {track_str}.",
            f"Directo en la mezcla, {track_str}."
        ]
        if self.force_offline:
            return self._pick(None, lines)
        return self._pick(self.brain.track_intro_line(track), lines)

    def synthesize_offline_piper(self, text, output_wav_path):
        if not self.piper_voice:
            raise RuntimeError("Piper local no esta inicializado.")
        with wave.open(output_wav_path, "wb") as wav_file:
            self.piper_voice.synthesize_wav(text, wav_file)
        return output_wav_path

    async def _synthesize_edge(self, text, output_path):
        import edge_tts
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(output_path)
        return output_path

    def prepare_speech(self, text, filename="livi_speech.mp3"):
        mp3_path = os.path.join(self.cache_dir, filename)
        wav_path = os.path.join(self.cache_dir, filename.replace('.mp3', '.wav'))

        if self.force_offline and self.piper_voice:
            return self.synthesize_offline_piper(text, wav_path)

        try:
            asyncio.run(asyncio.wait_for(self._synthesize_edge(text, mp3_path), timeout=3.5))
            return mp3_path
        except Exception:
            if self.piper_voice:
                return self.synthesize_offline_piper(text, wav_path)
            raise
