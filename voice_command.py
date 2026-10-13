#!/usr/bin/env python3
"""
voice_command.py - Comandos por voz para el AI DJ.

Graba del microfono (sounddevice), transcribe con el free tier de Groq
(whisper-large-v3-turbo) y deja listo el texto para que dj_brain lo
convierta en accion. Si falta GROQ_API_KEY, sounddevice o soundfile, el
modulo queda deshabilitado y la app sigue funcionando normalmente.
"""
import io
import os
import math
import wave
import struct
import threading

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

try:
    import sounddevice as sd
except Exception:  # pragma: no cover
    sd = None

SAMPLE_RATE = 16000
STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
STT_MODEL = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo")


def _env(name, default=None):
    return os.environ.get(name, default)


def _rms(block):
    if not block:
        return 0.0
    count = len(block) // 2
    if count == 0:
        return 0.0
    shorts = struct.unpack("<%dh" % count, block)
    return math.sqrt(sum(s * s for s in shorts) / count)


class VoiceController:
    def __init__(self, language="es"):
        self.language = language
        self.api_key = _env("GROQ_API_KEY")
        self.enabled = bool(self.api_key and requests is not None and sd is not None)
        self.listening = False

    def status(self):
        if not requests:
            return {"enabled": False, "reason": "requests ausente"}
        if not self.api_key:
            return {"enabled": False, "reason": "sin GROQ_API_KEY"}
        if not sd:
            return {"enabled": False, "reason": "sounddevice ausente"}
        return {"enabled": True, "provider": "groq", "model": STT_MODEL}

    # ------------------------------------------------------------- grabacion
    def record(self, max_seconds=6.0, silence_ms=900, energy_threshold=500.0):
        """Graba hasta silencio (o max_seconds) y devuelve WAV bytes."""
        if not self.enabled:
            raise RuntimeError("voz no disponible")
        blocks = []
        silence_chunks = int((silence_ms / 1000.0) * SAMPLE_RATE / 1024)
        quiet = 0
        started = False
        max_chunks = int((max_seconds * SAMPLE_RATE) / 1024)
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=1024,
                               dtype="int16", channels=1) as stream:
            for _ in range(max_chunks):
                block, _ = stream.read(1024)
                blocks.append(block)
                energy = _rms(block)
                if energy > energy_threshold:
                    started = True
                    quiet = 0
                elif started:
                    quiet += 1
                    if quiet >= silence_chunks:
                        break
                elif len(blocks) > 20:
                    blocks = blocks[-20:]
        audio = b"".join(blocks)
        return _wav_bytes(audio)

    def listen_and_transcribe(self, **kwargs):
        audio = self.record(**kwargs)
        if not audio:
            return None
        return self.transcribe(audio)

    # --------------------------------------------------------- transcripcion
    def transcribe(self, wav_bytes):
        if not self.enabled:
            raise RuntimeError("voz no disponible")
        resp = requests.post(
            STT_URL,
            headers={"Authorization": "Bearer %s" % self.api_key},
            files={"file": ("voz.wav", wav_bytes, "audio/wav")},
            data={"model": STT_MODEL, "language": self.language,
                  "temperature": 0},
            timeout=15,
        )
        if resp.status_code != 200:
            raise RuntimeError("STT HTTP %s: %s" % (resp.status_code, resp.text[:200]))
        text = (resp.json().get("text") or "").strip()
        return text or None


def _wav_bytes(pcm):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)
    return buf.getvalue()


_voice_singleton = None


def get_voice():
    global _voice_singleton
    if _voice_singleton is None:
        _voice_singleton = VoiceController()
    return _voice_singleton
