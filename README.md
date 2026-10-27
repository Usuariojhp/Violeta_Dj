# Violeta - Crossfade Studio

Reproductor de audio inteligente para **Linux** y **Android (Termux)** con arquitectura de doble consola MPV (Deck A / Deck B), crossfade continuo en tiempo real, detección automática de toda la biblioteca del dispositivo, navegación por carpetas, favoritos, carátulas, letras sincronizadas, locución por voz sintetizada, interfaz web instalable (PWA), control remoto por Telegram y **cerebro IA con Auto-DJ armónico, moods y comandos por voz**.

---

## Características

* **Detección total del almacenamiento:** escaneo recursivo de `/sdcard`, `~/Música`, `~/Descargas`, etc., omitiendo rutas de sistema. Caché del índice (`.library_cache.json`) con TTL y `--rescan` para forzar actualización.
* **Crossfade continuo real:** doble consola MPV para transiciones sin silencios.
* **Avance automático ágil:** el salto de canción a canción usa un crossfade corto (~3 s) para que la siguiente llegue al máximo justo al terminar la anterior.
* **Navegación por carpetas o canción individual**, modo aleatorio (Shuffle) y cola/historial.
* **Favoritos, volumen maestro y crossfade configurables**, persistentes entre sesiones.
* **Carátulas reales** extraídas con `mutagen` desde los archivos (caché en `covers/`).
* **Letras con resaltado sincronizado (LRC)** vía `syncedlyrics` (cacheadas en `lyrics/`), con búsqueda perezosa al cambiar de pista.
* **Interfaz web glassmorphism** optimizada para móvil y escritorio, con buscador con resaltado, filtro de favoritos, ecualizador animado y reanudación de la última pista. **Instalable como app (PWA)** desde el navegador.
* **Interfaz de consola (CLI)** interactiva con explorador de carpetas, buscador `/`, vistas de cola e historial y rediseñado con caja ANSI.
* **Locución inteligente:** intervenciones breves con voz neuronal (`Edge-TTS` online o `Piper` offline), pre-generada para la canción siguiente mientras suena la actual para evitar esperas.
* **Control remoto por Telegram:** `/play /next /vol 80 /xf 4.5 /voz /shuffle ...` desde el teléfono.
* **Launcher unificado** `start_violeta.sh` (web + bot en tmux con auto-reinicio y wake-lock).
* **Cerebro IA (Violeta):** Auto-DJ armónico con mezcla Camelot, moods (chill/energico/fiesta/enfoque), pedidos en lenguaje natural, comandos por voz (STT via Groq), MCP para agentes.

---

## Arquitectura / Módulos

| Archivo | Función |
| --- | --- |
| `web_dj.py` | Motor del reproductor + servidor web/API (controla MPV), PWA, carátulas, letras, favoritos, Telegram. |
| `ai_dj.py` | Interfaz de terminal (explorador, buscador, cola, historial, favoritos, Auto-DJ, voz). |
| `dj_mixer.py` | Doble deck MPV (Deck A/B), crossfade con lock anti-carrera, volumen 0-150, ducking. |
| `dj_commentator.py` | Generación de la voz de Violeta (Edge-TTS / Piper). Delega en cerebro LLM con fallback. |
| `dj_state.py` | Persistencia de estado (favoritos, shuffle, crossfade, volumen, última pista + posición). |
| `music_scanner.py` | Escaneo de la biblioteca + metadatos con `mutagen` + caché TTL (`.library_cache.json`). |
| `dj_brain.py` | Cerebro LLM multi-proveedor (Google AI Studio / Groq / OpenRouter, todos gratis). Fallback a plantillas. |
| `set_engine.py` | Auto-DJ: mezcla armónica (Camelot), curva de energía por mood, variedad de artistas. |
| `track_intel.py` | Enriquece pistas con BPM, tonalidad (librosa opcional) y energía heurística. |
| `voice_command.py` | Comandos por voz: mic -> STT (Groq Whisper). Opcional. |
| `dj_mcp.py` | Servidor MCP (stdio) que expone el reproductor como tools para agentes (opencode, Claude Code). |
| `dj_state.py` | Persistencia de estado (favoritos, shuffle, crossfade, volumen, última pista + posición). |
| `pwa_assets.py` | Genera iconos PNG y manifest para PWA instalable. |
| `start_violeta.sh` | Launcher tmux (web + bot), auto-reinicio, wake-lock, IP. |

---

## Estructura de proyectos

```
~/violeta/          Violeta (DJ): web_dj.py, ai_dj.py, dj_*.py, music_scanner.py,
                    pwa_assets.py, start_violeta.sh, covers/, lyrics/, pwa_icons/, README.md
~/telegram_bot/     Bot de Telegram: telegram_bot_interactive.py, bot_control.sh,
                    bot.env, bot.log (+ variantes antiguas)
~/tik-tok-downloader/   Proyecto independiente
```

---

## Instalación y Uso

### En Linux (PC)

```bash
git clone https://github.com/TU_USUARIO/violeta.git
cd violeta

# Dependencias del sistema
sudo apt install mpv ffmpeg        # Ubuntu / Debian
# sudo dnf install mpv ffmpeg      # Fedora

# Dependencias Python
pip install -e '.[audio]'   # librosa + syncedlyrics (opcional, para BPM/key reales y letras)
pip install -e '.[voz]'     # sounddevice (opcional, para comandos por voz)

# Interfaz web (puerto 5000 por defecto)
python3 web_dj.py

# O terminal interactivo
python3 ai_dj.py
```

Abre el navegador en `http://localhost:5000`.

**Flags útiles:** `--offline` (sin LLM, solo plantillas + Piper), `--enrich-audio` (analiza BPM/key reales con librosa, lento la 1ra vez), `--port=5001`. Con `DJ_SCAN_ROOTS=/ruta1:/ruta2` limitas el escaneo.

### El cerebro (opcional pero recomendado)

Copiá `.env.example` a `.env` y completá **una** key (todas gratuitas):

| Proveedor | Key | Notas |
| --- | --- | --- |
| `VIOLETA_LLM_PROVIDER=google` | `GOOGLE_API_KEY` | [AI Studio](https://aistudio.google.com/apikey), sin tarjeta |
| `VIOLETA_LLM_PROVIDER=groq` | `GROQ_API_KEY` | [Groq](https://console.groq.com/keys), rápido; también habilita la voz |
| `VIOLETA_LLM_PROVIDER=openrouter` | `OPENROUTER_API_KEY` | [OpenRouter](https://openrouter.ai/keys), modelos `:free` |

Sin keys el reproductor funciona igual (locuciones por plantillas + Piper).

Extras: `pip install -e '.[audio]'` (BPM/key reales), `pip install -e '.[voz]'` (comandos por voz), `pip install -e '.[dev]'` (tests).

### Control por agente (opencode / Claude Code)

Con `web_dj.py` corriendo, abrí opencode en esta carpeta, reinicialo (para que cargue el MCP) y elegí el agente `violeta`. Podes pedirle:

> "Armame una hora de rock sin repetir bandas"
> "Pone algo tranqui para enfocar"
> "Salta esta, decime que suena"

Las herramientas disponibles: `dj_status`, `dj_library`, `dj_queue`, `dj_mood`, `dj_enqueue`, `dj_ask`, `dj_say`, `dj_skip`, `dj_prev`, `dj_toggle_pause`, `dj_play_all`, `dj_brain`.

---

### En Android (con Termux)

1. Abre **Termux**, ejecuta `bash /sdcard/violeta/install_termux.sh` y concede `termux-setup-storage` si hace falta.
2. Arranca todo el sistema con el launcher:

```bash
bash violeta/start_violeta.sh start
```

3. Abre la URL indicada (por defecto `http://localhost:8000` desde el propio teléfono).

> 📌 **PWA:** en el navegador móvil usa "Añadir a pantalla de inicio" para dejar Violeta como app. La instalación completa requiere HTTPS (LAN es HTTP); los iconos, manifest y modo standalone ya funcionan.

---

## Operación diaria (Termux)

### `start_violeta.sh` — DJ web

| Comando | Efecto |
| :--- | :--- |
| `bash violeta/start_violeta.sh start` | Arranca el DJ web en tmux (sesión `violeta`) con auto-reinicio, genera iconos PWA y asegura el bot. |
| `bash violeta/start_violeta.sh stop` | Detiene el DJ (el bot sigue). |
| `bash violeta/start_violeta.sh restart` | Reinicia todo. |
| `bash violeta/start_violeta.sh status` | Estado de sesiones. |
| `bash violeta/start_violeta.sh logs` | Logs del DJ en vivo (Ctrl+C para salir). |
| `bash violeta/start_violeta.sh attach` | Consola del DJ (Ctrl+B luego D para salir). |
| `bash violeta/start_violeta.sh ip` | IP local y URL. |

El puerto se controla con `VIOLETA_PORT` (por defecto `8000`).

### `telegram_bot/bot_control.sh` — Bot de Telegram

`start | stop | restart | status | logs | attach | clearlogs` — gestiona el bot independiente (sesión tmux `tg_bot`), que se reinicia solo si cae.

---

## Interfaz Web

* **Controles centrales:** Play/Pausa, Siguiente, Anterior, ±10 s, barra de progreso con `seek`.
* **Pills:** Shuffle, Reproducir todo, Voz de Violeta (on/off).
* **Volumen** deslizador 0–150 (persistente).
* **Crossfade** configurable (0 / 3 / 4.5 / 6 / 8 s).
* **Favoritos:** estrella por canción + filtro "Favs" con contador.
* **Letra:** botón que abre modal con la letra sincronizada (LRC) y resalta la línea según la posición real.
* **Buscador** con resaltado `<mark>` y áreas de canciones/carpetas.
* **Carátulas** reales junto a cada pista y en el vinilo girando.
* **Panel de Violeta:** chat, botones de mood (chill/energico/fiesta/enfoque), comando de voz.
* Cada 6 s autoguarda estado y se reanuda la última pista al reiniciar.

---

## Control remoto por Telegram

El bot (sesión `tg_bot`) también controla el reproductor. Requiere que el DJ esté encendido (`bash violeta/start_violeta.sh start`). Detecta el puerto automáticamente.

| Comando | Efecto |
| :--- | :--- |
| `/dj` | Estado actual + ayuda. |
| `/now` | Estado actual. |
| `/play` | Pausar / reanudar. |
| `/next` · `/prev` | Canción siguiente / anterior. |
| `/vol 80` | Volumen (0–150). |
| `/xf 4.5` | Crossfade en segundos. |
| `/voz` | Voz de Violeta on/off. |
| `/shuffle` | Modo aleatorio on/off. |

> El bot sigue haciendo su función original: envíale cualquier enlace (YouTube, TikTok, Instagram...) para descargarlo.

---

## Controles en Modo Terminal (`ai_dj.py`)

| Tecla | Acción |
| :---: | :--- |
| `ESPACIO` | Pausar / Reanudar |
| `N` | Siguiente pista (crossfade) |
| `B` / `R` | Pista anterior |
| `S` | Shuffle on/off |
| `V` | Voz de Violeta on/off |
| `X` | Ciclar crossfade (0 / 3 / 4.5 / 6 / 8 s) |
| `F` | Marcar / desmarcar favorito |
| `E` | Modo explorador (navegación por carpetas) |
| `C` | Vista de cola (siguientes) |
| `H` | Vista de historial |
| `/` | Buscador (escribe, `Enter` reproduce la primera coincidencia, `Esc` cancela, `Borrar` borra) |
| `A` | Auto-DJ: arma set armonico de 45 min |
| `M` | Cambiar mood (chill > energico > fiesta > enfoque) |
| `Z` | Comando de voz (requiere `GROQ_API_KEY`) |
| `T` | Reproducir todo el dispositivo |
| `1` – `8` | Reproducir carpeta |
| `.` / `>` | Adelantar 10 s |
| `,` / `<` | Retroceder 10 s |
| `↑` / `↓` | Siguiente / anterior (en modo normal) |
| `→` / `←` | Adelantar / retroceder 10 s (en modo normal) |
| `Q` | Salir |

### Modo explorador (`E`)

`↑`/`↓` se mueven entre carpetas, `→` expande a las canciones de la carpeta, `↓`/`↑` navegan pistas, `Enter` reproduce, `←` o `Esc` vuelven al nivel anterior y `E` sale del explorador.

---

## Persistencia y datos (dentro de `violeta/`)

| Elemento | Contenido |
| :--- | :--- |
| `dj_state.json` | Favoritos, shuffle, crossfade, volumen, última pista + posición. |
| `.library_cache.json` | Índice del escaneo (TTL). |
| `covers/` | Carátulas extraídas (servidas por `/api/cover`). |
| `lyrics/` | Letras LRC cacheadas por `_lyrics_for`. |
| `pwa_icons/` | Iconos de la PWA. |
| `voices/` | Voces Piper locales (modo offline). |

---

## Notas de rendimiento

* El avance **automático** entre canciones usa un crossfade corto de máximo **3 s** para que no sientas el cambio lento; el crossfade largo (configurado con `X` o en web) aplica a saltos manuales.
* La voz de la **siguiente** canción se sintetiza en segundo plano mientras suena la actual (`_prefetch_next_announce`) y se reutiliza al avanzar, evitando esperas por red.
* Las letras se buscan bajo demanda y quedan cacheadas.
* El Auto-DJ rearma la cola automáticamente cuando se termina el set (si `auto_dj=True` y hay mood activo).

---

## Licencia

Este proyecto está bajo la licencia **MIT** — ver el archivo [LICENSE](LICENSE).

Puedes usar, copiar, modificar y distribuir libremente el código, incluido con fines comercionales, siempre que se conserve el aviso de copyright y la licencia.