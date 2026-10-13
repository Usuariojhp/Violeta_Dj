# OmniPlayer - Crossfade Studio

Reproductor de audio inteligente y minimalista para **Linux** y **Android (Termux)** con arquitectura de doble consola virtual MPV, crossfade continuo automatico en tiempo real, deteccion de todas las pistas del almacenamiento, navegacion por carpetas o pistas individuales, y soporte para locucion por voz sintetizada.

**Nuevo en v2: Auto-DJ real con IA.** Livi, la DJ de cabina, tiene ahora un cerebro LLM (Google AI Studio, Groq u OpenRouter, todos gratis) que escribe locuciones sobre la pista que suena, arma sets armonicos de N minutos por mood, entiende pedidos en lenguaje natural y comandos por voz. Y todo se puede controlar desde un agente (opencode / Claude Code) por MCP.

---

## Caracteristicas

* **Deteccion total en el almacenamiento:** Escaneo recursivo de directorios (`/sdcard`, `~/Musica`, `~/Descargas`, etc.) omitiendo rutas de sistema o temporales.
* **Crossfade continuo real:** Doble consola MPV (`Deck A` y `Deck B`) para transiciones fluidas de volumen sin silencios entre canciones.
* **Navegacion por Carpetas o Cancion:** Reproduccion de albumes/carpetas completos o seleccion de canciones individuales.
* **Modo Aleatorio (Shuffle):** Mezcla equilibrada de toda la coleccion o de la carpeta activa manteniendo el crossfade.
* **Interfaz Web Tactil:** Diseno de estudio minimalista y oscuro sin dependencias externas pesadas (`http://localhost:5000`), optimizada para navegadores moviles y de escritorio.
* **Interfaz de Consola (CLI):** Vista rapida e interactiva en terminal.
* **Locucion Inteligente:** Intervenciones breves mediante sintesis de voz neuronal (`Edge-TTS` online o `Piper` local offline).
* **Auto-DJ armonico:** Sets por mood (chill / energico / fiesta / enfoque) con mezcla armatica (rueda de Camelot), curva de energia y variedad de artistas.
* **Cerebro Livi (LLM):** Locuciones generadas segun artista, BPM y tonalidad reales. Sin internet ni keys: fallback automatico a plantillas + Piper.
* **Pedidos en lenguaje natural:** "pone algo tranqui para estudiar" → arma el set y te responde por voz.
* **Comandos por voz:** Microfono → Whisper (Groq) → accion. Tecla `V` en CLI, boton "Hablar" en la web.
* **Control por agente:** Servidor MCP + agente `dj` para opencode/Claude Code.

---

## Instalacion y Uso

### En Linux (PC)

```bash
# Clonar repositorio
git clone https://github.com/Usuariojhp/AI-Dj-1.git
cd AI-Dj-1

# Dependencias del sistema
sudo dnf install mpv ffmpeg   # En Fedora / RHEL
# o: sudo apt install mpv ffmpeg # En Ubuntu / Debian

# Dependencias Python
pip install edge-tts

# Iniciar la interfaz Web (Recomendado):
python3 web_dj.py

# O iniciar en terminal:
python3 ai_dj.py
```

Abrí tu navegador en `http://localhost:5000`.

**Flags utiles:** `--offline` (sin LLM, solo plantillas), `--enrich-audio`
(analiza BPM y tonalidad reales con librosa, es lento la primera vez),
`--port=5001`. Con `DJ_SCAN_ROOTS=/ruta1:/ruta2` limitas el escaneo.

### El cerebro (opcional pero recomendado)

Copiá `.env.example` a `.env` y completa **una** key (todas gratuitas):

| Proveedor | Key | Notas |
| --- | --- | --- |
| `DJ_LLM_PROVIDER=google` | `GOOGLE_API_KEY` | [AI Studio](https://aistudio.google.com/apikey), sin tarjeta |
| `DJ_LLM_PROVIDER=groq` | `GROQ_API_KEY` | [Groq](https://console.groq.com/keys), rapido; tambien habilita la voz |
| `DJ_LLM_PROVIDER=openrouter` | `OPENROUTER_API_KEY` | [OpenRouter](https://openrouter.ai/keys), modelos `:free` |

Sin keys el reproductor funciona igual (locuciones por plantillas + Piper).

Extras: `pip install -e '.[audio]'` (BPM/key reales), `pip install -e '.[voz]'`
(comandos por voz), `pip install -e '.[dev]'` (tests).

### Control por agente (opencode / Claude Code)

Con `web_dj.py` corriendo, abrí opencode en esta carpeta, reinicialo (para
que cargue el MCP) y elegi el agente `dj`. Podes pedirle:

> "Armame una hora de rock sin repetir bandas"
> "Pone algo tranqui para enfocar"
> "Salta esta, decime que suena"

Las herramientas disponibles: `dj_status`, `dj_library`, `dj_queue`,
`dj_mood`, `dj_enqueue`, `dj_ask`, `dj_say`, `dj_skip`, `dj_prev`,
`dj_toggle_pause`, `dj_play_all`, `dj_brain`.

---

### En Android (con Termux)

1. Abre **Termux** y ejecuta:
```bash
bash /sdcard/ai_dj/install_termux.sh
```
2. Para ejecutar:
   * Escribe `dj-web` y abre `http://localhost:5000` en tu navegador movil.
   * O escribe `dj` para usarlo directamente en la terminal.

---

## Controles en Modo Terminal

| Tecla | Accion |
| :---: | :--- |
| `[ESPACIO]` | Pausar / Reanudar |
| `[N]` / `[Flecha Arriba]` | Siguiente pista (Crossfade) |
| `[B]` / `[R]` / `[Flecha Abajo]` | Pista anterior / Reiniciar |
| `[.]` / `[Flecha Derecha]` | Adelantar 10 segundos |
| `[,]` / `[Flecha Izquierda]` | Retroceder 10 segundos |
| `[S]` | Activar / Desactivar Shuffle |
| `[T]` | Reproducir todo el dispositivo |
| `[A]` | Auto-DJ: armar set armonico de 45 minutos |
| `[M]` | Cambiar mood (chill > energico > fiesta > enfoque) |
| `[V]` | Comando de voz (requiere `GROQ_API_KEY`) |
| `[1]` a `[8]` | Reproducir carpeta seleccionada |
| `[Q]` | Salir |

---

## Licencia

MIT License.
