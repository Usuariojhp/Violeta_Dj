#!/usr/bin/env python3
"""
dj_brain.py - Cerebro LLM multi-proveedor para el AI DJ (OmniPlayer).

Proveedores gratuitos soportados (elegir con DJ_LLM_PROVIDER):
  - google      : Google AI Studio (Gemini)      -> key GOOGLE_API_KEY
  - groq        : Groq, compatible OpenAI        -> key GROQ_API_KEY
  - openrouter  : OpenRouter, modelos ':free'    -> key OPENROUTER_API_KEY

Si no hay keys configuradas, no hay internet o el proveedor falla, el cerebro
queda en modo plantillas y el reproductor sigue funcionando sin interrupcion.
Las respuestas del LLM se piden siempre como JSON para poder validarlas.
"""
import os
import re
import json
import time
import random
import threading

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(os.path.expanduser("~/.cache/ai_dj"))
os.makedirs(CACHE_DIR, exist_ok=True)

PERSONA = (
    "Sos Livi, la DJ de cabina de OmniPlayer. Hablas en espanol neutro y "
    "coloquial, como un DJ de radio nocturna. Frases cortas (max 14 palabras), "
    "sin emojis, sin comillas, sin signos raros. Nunca inventes canciones: "
    "solo hablas de la pista que te pasan."
)

PROVIDER_DEFAULTS = {
    "google": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "model": "gemini-3-flash-lite",
        "key_env": "GOOGLE_API_KEY",
    },
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "key_env": "GROQ_API_KEY",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "qwen/qwen3-coder:free",
        "key_env": "OPENROUTER_API_KEY",
    },
}

MOOD_LABELS = {
    "chill": "tranquilo, relajado, para escuchar de fondo",
    "energico": "en ascenso, con ritmo y ganas de moverse",
    "fiesta": "explosivo, bailable, para cantar a los gritos",
    "enfoque": "instrumental o suave, para concentrarse",
}


def _env(name, default=None):
    return os.environ.get(name, default)


class DJBrain:
    """Cerebro del DJ. Si no hay proveedor usable trabaja en modo plantillas."""

    def __init__(self, provider=None, model=None, timeout=None, cache_lines=True):
        self.provider = (provider or _env("DJ_LLM_PROVIDER", "google")).strip().lower()
        conf = PROVIDER_DEFAULTS.get(self.provider, PROVIDER_DEFAULTS["google"])
        self.model = model or _env("DJ_LLM_MODEL", conf["model"])
        self.timeout = float(timeout or _env("DJ_BRAIN_TIMEOUT", 8))
        self.api_key = _env(conf["key_env"])
        self.conf = conf
        self.enabled = bool(self.api_key and requests is not None)
        self.cache_lines = cache_lines
        self._lock = threading.Lock()
        self._cache = {}
        self._cache_path = os.path.join(CACHE_DIR, "livi_lines.json")
        self._load_cache()
        self._recent = []

    # ------------------------------------------------------------------ cache
    def _load_cache(self):
        if not self.cache_lines:
            return
        try:
            with open(self._cache_path, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
        except Exception:
            self._cache = {}

    def _save_cache(self):
        if not self.cache_lines:
            return
        try:
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False)
        except Exception:
            pass

    # ------------------------------------------------------------- transporte
    def _post(self, url, payload, headers, timeout=None):
        if not self.enabled:
            raise RuntimeError("cerebro sin proveedor configurado")
        resp = requests.post(url, json=payload, headers=headers,
                             timeout=timeout or self.timeout)
        if resp.status_code != 200:
            raise RuntimeError("HTTP %s: %s" % (resp.status_code, resp.text[:200]))
        return resp.json()

    def _call_provider(self, prompt, max_tokens=200):
        """Devuelve texto puro del proveedor configurado o lanza excepcion."""
        system = PERSONA
        if self.provider == "google":
            url = self.conf["url"].format(model=self.model)
            data = self._post(
                url,
                {
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user",
                                  "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.9,
                        "maxOutputTokens": max_tokens,
                        "responseMimeType": "application/json",
                    },
                },
                {"x-goog-api-key": self.api_key},
            )
            return data["candidates"][0]["content"]["parts"][0]["text"]

        headers = {"Authorization": "Bearer %s" % self.api_key,
                   "Content-Type": "application/json"}
        if self.provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/Usuariojhp/AI-Dj-1"
        data = self._post(
            self.conf["url"],
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.9,
                "max_tokens": max_tokens,
            },
            headers,
        )
        return data["choices"][0]["message"]["content"]

    # ---------------------------------------------------------------- parsing
    @staticmethod
    def _extract_json(text):
        """Saca el primer objeto JSON valido de una respuesta de LLM."""
        if not text:
            return None
        t = text.strip()
        t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.MULTILINE).strip()
        for start in range(len(t)):
            if t[start] != "{":
                continue
            depth = 0
            for end in range(start, len(t)):
                if t[end] == "{":
                    depth += 1
                elif t[end] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(t[start:end + 1])
                        except Exception:
                            break
        try:
            return json.loads(t)
        except Exception:
            return None

    def _ask_json(self, prompt, max_tokens=200, retries=1):
        """Llama al LLM pidiendo JSON, con reintentos. None si falla."""
        if not self.enabled:
            return None
        last = None
        for attempt in range(max(1, retries + 1)):
            try:
                raw = self._call_provider(prompt, max_tokens=max_tokens)
                parsed = self._extract_json(raw)
                if isinstance(parsed, dict):
                    return parsed
                last = ValueError("no era JSON: %r" % (raw or "")[:120])
            except Exception as exc:
                last = exc
            time.sleep(0.4 * (attempt + 1))
        if _env("DJ_BRAIN_DEBUG"):
            print("[dj_brain] fallback por: %s" % last)
        return None

    # ------------------------------------------------------------- comentarios
    def _track_ctx(self, track):
        artist = (track or {}).get("artist") or "desconocido"
        title = (track or {}).get("title") or (track or {}).get("filename") or "pista"
        folder = (track or {}).get("folder") or ""
        bpm = (track or {}).get("bpm")
        musical_key = (track or {}).get("key")
        bits = ["artista: %s" % artist, "titulo: %s" % title]
        if folder:
            bits.append("carpeta: %s" % folder)
        if bpm:
            bits.append("bpm: %s" % bpm)
        if musical_key:
            bits.append("tonalidad: %s" % musical_key)
        return "; ".join(bits)

    def _line(self, prompt, cache_key, track):
        """Obtiene una linea del LLM o None; cachea por pista para no repetir."""
        if not self.enabled:
            return None
        with self._lock:
            hits = [l for l in self._cache.get(cache_key, []) if l not in self._recent]
            if hits:
                self._recent.append(hits[0])
                self._recent = self._recent[-12:]
                return hits[0]
        data = self._ask_json(prompt, max_tokens=140)
        line = None
        if data and isinstance(data.get("line"), str):
            line = data["line"].strip()
        if not line:
            return None
        if len(line) > 160:
            line = line[:160].rsplit(" ", 1)[0]
        with self._lock:
            bucket = self._cache.setdefault(cache_key, [])
            if line not in bucket:
                bucket.append(line)
                self._save_cache()
            self._recent.append(line)
            self._recent = self._recent[-12:]
        return line

    def track_intro_line(self, track):
        ctx = self._track_ctx(track)
        return self._line(
            "Escribi una linea de DJ presentando esta pista. Devolve SOLO JSON: "
            "{\"line\": \"...\"}.\nPista -> " + ctx,
            "intro|%s" % (track or {}).get("path", "?"),
            track,
        )

    def folder_switch_line(self, folder_name, track):
        ctx = self._track_ctx(track)
        return self._line(
            "Acabamos de cambiar a la carpeta '%s'. Escribi una linea de DJ "
            "anunciando el cambio y la pista. Devolve SOLO JSON: {\"line\": \"...\"}.\n"
            "Pista -> %s" % (folder_name, ctx),
            "folder|%s|%s" % (folder_name, (track or {}).get("path", "?")),
            track,
        )

    def shuffle_line(self, track):
        ctx = self._track_ctx(track)
        return self._line(
            "Activamos modo aleatorio. Escribi una linea de DJ arrancando la "
            "mezcla aleatoria con esta pista. Devolve SOLO JSON: {\"line\": \"...\"}.\n"
            "Pista -> " + ctx,
            "shuffle|%s" % (track or {}).get("path", "?"),
            track,
        )

    def welcome_line(self, context_name, track):
        ctx = self._track_ctx(track)
        return self._line(
            "Se inicia una sesion desde '%s'. Escribi una linea de DJ dandole "
            "la bienvenida al oyente y presentando la primera pista. "
            "Devolve SOLO JSON: {\"line\": \"...\"}.\nPista -> %s"
            % (context_name, ctx),
            "welcome|%s|%s" % (context_name, (track or {}).get("path", "?")),
            track,
        )

    # --------------------------------------------------------- pedidos/hablar
    def parse_request(self, text, library_summary=None):
        """Convierte un pedido en lenguaje natural en una accion estructurada.

        Respuesta: {"action": str, "mood": str|None, "query": str|None,
                    "minutes": int|None, "reply": str}
        """
        actions = (
            "play_folder | play_track | play_mood | skip | prev | pause | "
            "resume | volume_up | volume_down | chat | unknown"
        )
        prompt = [
            "Pedido del oyente: \"%s\"" % text,
            "",
            "Devolve SOLO JSON con estas claves:",
            "{\"action\": \"<una de: %s>\"," % actions,
            " \"mood\": \"chill|energico|fiesta|enfoque|null\",",
            " \"query\": \"texto de busqueda o null\",",
            " \"minutes\": numero de minutos o null,",
            " \"reply\": \"tu respuesta hablada, max 14 palabras, en espanol\"}",
            "Ejemplo: pedido 'pone algo tranquilo para estudiar' -> "
            '{"action": "play_mood", "mood": "enfoque", "query": null, '
            '"minutes": 45, "reply": "Modo enfoque, cuarenta y cinco minutos."}',
        ]
        if library_summary:
            prompt.append("Biblioteca disponible (resumen): %s" % library_summary)
        data = self._ask_json("\n".join(prompt), max_tokens=220, retries=1)
        if not data or data.get("action") not in (
            "play_folder", "play_track", "play_mood", "skip", "prev",
            "pause", "resume", "volume_up", "volume_down", "chat", "unknown",
        ):
            return None
        data.setdefault("reply", "Listo.")
        return data

    def chat_reply(self, question, status=None):
        """Respuesta conversacional de Livi sobre lo que esta sonando."""
        ctx = "Sin pista activa."
        if isinstance(status, dict) and status.get("track"):
            ctx = self._track_ctx(status["track"])
        data = self._ask_json(
            "Pregunta del oyente: \"%s\"\nSonando ahora -> %s\n"
            "Responde como DJ, en espanol, max 20 palabras. Devolve SOLO JSON: "
            "{\"reply\": \"...\"}" % (question, ctx),
            max_tokens=180,
            retries=1,
        )
        if data and isinstance(data.get("reply"), str):
            return data["reply"].strip()
        return None

    def status_info(self):
        return {
            "enabled": self.enabled,
            "provider": self.provider if self.enabled else None,
            "model": self.model if self.enabled else None,
            "reason": None if self.enabled else
            ("requests ausente" if requests is None else "sin API key"),
        }


_brain_singleton = None


def get_brain():
    global _brain_singleton
    if _brain_singleton is None:
        _brain_singleton = DJBrain()
    return _brain_singleton
