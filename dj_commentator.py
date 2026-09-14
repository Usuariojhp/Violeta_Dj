#!/usr/bin/env python3
"""
dj_commentator.py - Generador de guiones y voz de DJ Livi.
Soporta modo online (Edge-TTS) y modo 100% offline (Piper TTS local ultraligero).
"""
import os
import wave
import random
import asyncio
import tempfile

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
        self.user_name = "José"
        self.piper_voice = None

        # Preparar motor Piper si existe el modelo
        if os.path.exists(PIPER_MODEL) and os.path.exists(PIPER_CONFIG):
            try:
                from piper import PiperVoice
                self.piper_voice = PiperVoice.load(PIPER_MODEL, PIPER_CONFIG)
            except Exception as e:
                pass

    def format_track_name(self, track):
        artist = track.get('artist')
        title = track.get('title')
        if artist and title:
            return f"{title} de {artist}"
        return title or track.get('filename', 'este temazo')

    def generate_welcome_script(self, context_name, first_track):
        track_str = self.format_track_name(first_track)
        greetings = [
            f"¡Hola {self.user_name}! Qué bueno tenerte aquí. Soy Livi, tu DJ personal. Hoy la música corre por mi cuenta. Empezamos con {track_str}.",
            f"¡Ey qué tal, {self.user_name}! Aquí Livi en los controles. Reproduciendo desde {context_name}. Arrancamos con {track_str}.",
            f"¡Hola {self.user_name}! Todo listo en la cabina. Sube el volumen que hoy suena {track_str}."
        ]
        return random.choice(greetings)

    def generate_folder_switch_script(self, folder_name, next_track):
        track_str = self.format_track_name(next_track)
        lines = [
            f"Cambiamos a la carpeta {folder_name}. Arrancamos con {track_str}.",
            f"Nos movemos directo a tu música en {folder_name}. Suena {track_str}.",
            f"Explorando {folder_name}. Aquí viene {track_str}."
        ]
        return random.choice(lines)

    def generate_shuffle_intro(self, next_track):
        track_str = self.format_track_name(next_track)
        lines = [
            f"Modo aleatorio activado. Sacando temazos de toda tu biblioteca. Suena {track_str}.",
            f"En aleatorio total. Lo que venga suena increíble, arrancamos con {track_str}.",
            f"Mezclando todo tu dispositivo sin filtro. Escucha {track_str}."
        ]
        return random.choice(lines)

    def generate_track_intro_script(self, track):
        track_str = self.format_track_name(track)
        intros = [
            f"Y a continuación en cabina, escucha {track_str}.",
            f"Seguimos sin pausas con este temazo: {track_str}.",
            f"No le bajes, que ahora suena {track_str}.",
            f"Directo en la mezcla: {track_str}."
        ]
        return random.choice(intros)

    def synthesize_offline_piper(self, text, output_wav_path):
        """Genera voz 100% offline en CPU usando Piper."""
        if not self.piper_voice:
            raise RuntimeError("Piper local no está inicializado.")
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
