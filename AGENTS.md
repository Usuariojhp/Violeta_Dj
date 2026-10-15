# AGENTS.md - Violeta / AI DJ

Reproductor de audio con doble deck MPV, crossfade real y DJ con voz (Violeta).
Corre en Linux y en Android (Termux). Este documento es la fuente de verdad
para cualquier agente que trabaje en este repo.

## Como correrlo

```bash
python3 web_dj.py            # UI web recomendada (http://localhost:5000)
python3 web_dj.py --offline  # sin LLM: solo plantillas + Piper
python3 web_dj.py --enrich-audio  # analiza BPM/key real con librosa (lento)
python3 ai_dj.py             # interfaz de terminal
```

Tests: `python3 -m pytest tests/ -q`

## Arquitectura

| Archivo | Rol |
| --- | --- |
| `music_scanner.py` | Escanea el dispositivo y arma `all_tracks` + `folder_map`. Parsea "Artista - Titulo". Cache TTL en `.library_cache.json`. |
| `dj_mixer.py` | Doble deck MPV (Deck A/B), crossfade, ducking de voz, volumen 0-150, crossfade configurable. |
| `dj_commentator.py` | Guiones de Violeta. Delega en el cerebro LLM, con fallback a plantillas. |
| `dj_brain.py` | Cerebro LLM multi-proveedor (google / groq / openrouter). Sin keys -> modo plantillas. |
| `track_intel.py` | Metadatos (mutagen), BPM/key opcional (librosa), cache en ~/.cache/violeta. |
| `set_engine.py` | Auto-DJ: mezcla armonica (Camelot), curva de energia por mood, variedad. |
| `voice_command.py` | Comandos por voz: mic -> STT (Groq whisper). Opcional. |
| `web_dj.py` | API HTTP stdlib (`/api/*`) + UI web embebida (PWA, caratulas, letras, favoritos, Telegram). |
| `dj_mcp.py` | Servidor MCP (stdio) que expone el reproductor como tools para agentes. |
| `dj_state.py` | Persistencia de estado (favoritos, shuffle, crossfade, vol, ultima pista + pos). |
| `pwa_assets.py` | Genera iconos y manifest para PWA instalable. |
| `start_violeta.sh` | Launcher tmux (web + bot), auto-reinicio, wake-lock, IP. |
| `.opencode/agent/violeta.md` | Agente primario que opera el reproductor. |

## Reglas duras

1. **El thread del mixer nunca se bloquea.** Toda llamada de red (LLM, TTS,
   STT) va en threads separados o con timeout corto.
2. **Fallback obligatorio.** Si el LLM falla o no hay internet, el
   comentario cae a las plantillas. Nunca se interrumpe la musica.
3. **Lineas cortas.** Los comentarios de voz deben tener max ~14 palabras:
   el TTS tiene timeout de 3.5s y si no, suena cortado.
4. **Las API keys van solo por variables de entorno** (ver `.env.example`).
   Nunca en el codigo ni en el repo.
5. Los comentarios estan en espanol neutro, sin emojis.
6. Si tocas `set_engine.build_set`, debe seguir siendo determinista con
   `seed` fija (los tests dependen de eso).

## Variables de entorno

| Variable | Default | Para que |
| --- | --- | --- |
| `VIOLETA_LLM_PROVIDER` | `google` | `google` \| `groq` \| `openrouter` |
| `GOOGLE_API_KEY` | - | cerebro con Google AI Studio |
| `GROQ_API_KEY` | - | cerebro + STT (Whisper) con Groq |
| `OPENROUTER_API_KEY` | - | cerebro con modelos `:free` de OpenRouter |
| `VIOLETA_LLM_MODEL` | por proveedor | forzar un modelo concreto |
| `VIOLETA_BRAIN_TIMEOUT` | `8` | segundos por llamada al LLM |
| `VIOLETA_BRAIN_DEBUG` | - | imprime por que cayo al fallback |
| `VIOLETA_API_URL` | `http://127.0.0.1:5000` | destino del servidor MCP |

## MCP / agente

El MCP `violeta` se levanta con `web_dj.py` corriendo. Para usarlo desde
opencode: reiniciar opencode dentro de esta carpeta (la config no se
recarga en caliente) y elegir el agente `violeta`.