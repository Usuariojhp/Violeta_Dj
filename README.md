# OmniPlayer - Crossfade Studio

Reproductor de audio inteligente y minimalista para **Linux** y **Android (Termux)** con arquitectura de doble consola virtual MPV, crossfade continuo automatico en tiempo real, deteccion de todas las pistas del almacenamiento, navegacion por carpetas o pistas individuales, y soporte para locucion por voz sintetizada.

---

## Caracteristicas

* **Deteccion total en el almacenamiento:** Escaneo recursivo de directorios (`/sdcard`, `~/Musica`, `~/Descargas`, etc.) omitiendo rutas de sistema o temporales.
* **Crossfade continuo real:** Doble consola MPV (`Deck A` y `Deck B`) para transiciones fluidas de volumen sin silencios entre canciones.
* **Navegacion por Carpetas o Cancion:** Reproduccion de albumes/carpetas completas o seleccion de canciones individuales.
* **Modo Aleatorio (Shuffle):** Mezcla equilibrada de toda la coleccion o de la carpeta activa manteniendo el crossfade.
* **Interfaz Web Tactil:** Diseno de estudio minimalista y oscuro sin dependencias externas pesadas (`http://localhost:5000`), optimizado para navegadores moviles y de escritorio.
* **Interfaz de Consola (CLI):** Vista rapida e interactiva en terminal.
* **Locucion Inteligente:** Intervenciones breves mediante sintesis de voz neuronal (`Edge-TTS` online o `Piper` local offline).

---

## Instalacion y Uso

### En Linux (PC)

```bash
# Clonar repositorio
git clone https://github.com/TU_USUARIO/omniplayer.git
cd omniplayer

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

Abre tu navegador en `http://localhost:5000`.

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
| `[1]` a `[8]` | Reproducir carpeta seleccionada |
| `[Q]` | Salir |

---

## Licencia

MIT License.
