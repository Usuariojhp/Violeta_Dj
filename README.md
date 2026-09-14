# 🎧 OmniPlayer DJ - Reproductor con Crossfade Continuo & DJ IA

Reproductor de música inteligente y minimalista para **Linux** y **Android (Termux)** con doble deck virtual, crossfade automático continuo en tiempo real, detección automática de todas las canciones del dispositivo, selección por carpetas o pistas individuales, y soporte para locución con voz de IA.

---

## ✨ Características

* **🎵 Detección automática en todo el dispositivo:** Escanea tu almacenamiento interno (`/sdcard`, `~/Música`, `~/Descargas`, etc.) sin importar dónde guardes tus canciones.
* **🎚️ Crossfade continuo real:** Doble consola MPV (`Deck A` y `Deck B`) para fundir el final de una canción con el inicio de la siguiente sin silencios ni cortes bruscos.
* **📁 Selección por Carpetas o Canción Individual:** Elige escuchar una carpeta específica (ej. álbum o playlist) o salta a cualquier canción suelta.
* **🔀 Modo Aleatorio (Shuffle) inteligente:** Mezcla todo el dispositivo o la carpeta seleccionada manteniendo el crossfade activo.
* **📱 Interfaz Web Táctil Móvil:** Sin necesidad de frameworks pesados, incluye una interfaz web moderna y oscura (`http://localhost:5000`) ideal para usar con una mano en el navegador de tu celular.
* **💻 Interfaz de Terminal (CLI):** Pantalla interactiva en consola para computadoras o terminal Termux.
* **🎙️ DJ Virtual con Locución:** Comentarios dinámicos al iniciar o cambiar de carpeta usando voces neuronales (`Edge-TTS` online o `Piper` 100% offline).

---

## 🚀 Instalación y Uso

### En Linux (PC)

```bash
# Clonar repositorio
git clone https://github.com/TU_USUARIO/omniplayer-dj.git
cd omniplayer-dj

# Dependencias del sistema
sudo dnf install mpv ffmpeg   # En Fedora / RHEL
# o: sudo apt install mpv ffmpeg # En Ubuntu / Debian

# Dependencias Python
pip install edge-tts

# Iniciar la Interfaz Web Táctil (Recomendada):
python3 web_dj.py

# O iniciar en Modo Terminal:
python3 ai_dj.py
```

Luego abre tu navegador en `http://localhost:5000`.

---

### En Android (con Termux)

1. Abre **Termux** y ejecuta:
```bash
bash /sdcard/ai_dj/install_termux.sh
```
2. Para usarlo:
   * Escribe `dj-web` y abre `http://localhost:5000` en Chrome o tu navegador.
   * O escribe `dj` para usarlo directamente en la pantalla de Termux.

---

## 🎮 Controles en Modo Terminal

| Tecla | Acción |
| :---: | :--- |
| `[ESPACIO]` | Pausar / Reanudar |
| `[N]` / `[▲]` | Siguiente canción (Crossfade continuo) |
| `[B]` / `[R]` / `[▼]` | Canción anterior / Reiniciar pista |
| `[.]` / `[►]` | Adelantar 10 segundos |
| `[,]` / `[◄]` | Retroceder 10 segundos |
| `[S]` | Activar / Desactivar Modo Aleatorio (Shuffle) |
| `[T]` | Reproducir todo el dispositivo |
| `[1]` a `[8]` | Reproducir carpeta seleccionada |
| `[Q]` | Salir |

---

## 📄 Licencia

MIT License.
