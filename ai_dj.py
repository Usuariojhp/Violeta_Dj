#!/usr/bin/env python3
"""
ai_dj.py - Reproductor Terminal Minimalista con Doble Deck y Crossfade Continuo.
Diseño limpio y profesional sin emojis.
Mejoras: navegacion interactiva (flechitas + Enter), vistas de cola/historial,
buscador '/', favoritos, voz, crossfade configurable, persistencia y reanudar.
"""
import os
import sys
import time
import tty
import re
import select
import termios
import random
import threading
from music_scanner import scan_all_device
from dj_commentator import DJCommentator
from dj_mixer import DJMixer
from dj_state import DjState
from dj_brain import get_brain
from set_engine import build_set, next_mood, normalize_mood, DEFAULT_MOOD
from voice_command import get_voice
import threading

ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_GREEN = "\033[92m"
C_CYAN = "\033[96m"
C_YELLOW = "\033[93m"
C_MAGENTA = "\033[95m"
C_RED = "\033[91m"
C_GRAY = "\033[90m"

CROSSFADE_OPTIONS = [0, 3.0, 4.5, 6.0, 8.0]


def _pad_ansi(content, width):
    """Rellena a ancho fijo ignorando los códigos de color ANSI."""
    visible = len(ANSI_RE.sub('', content))
    return content + ' ' * max(0, width - visible)


def _fit_ansi(content, width):
    """Trunca a un ancho visible sin romper ni perder los códigos de color ANSI."""
    res = []
    visible = 0
    i = 0
    while i < len(content):
        m = ANSI_RE.match(content, i)
        if m:
            res.append(m.group(0))
            i = m.end()
            continue
        if visible >= width:
            res.append(C_RESET)
            break
        res.append(content[i])
        visible += 1
        i += 1
    return ''.join(res)


class DJLiviApp:
    W = 62
    H = '─'

    def __init__(self, force_offline=False, rescan=False):
        self.force_offline = force_offline
        self.rescan = rescan
        self.state = DjState()
        self.mixer = DJMixer()
        self.commentator = DJCommentator(force_offline=force_offline)
        self.all_tracks = []
        self.folder_map = {}

        self.current_queue = []
        self.queue_index = 0
        self.history = []
        self.shuffle_mode = bool(self.state['shuffle'])
        self.voice_enabled = bool(self.state['voice_enabled'])
        self.crossfade_sec = float(self.state['crossfade_sec'] or CROSSFADE_OPTIONS[1])
        self.favorites = set(self.state['favorites'])
        self.context_name = "Todo el dispositivo"
        self.status_msg = "Iniciando reproductor..."
        self.running = True
        self._cached_announce = None
        self.brain = get_brain()
        self.voice = get_voice()
        self.mood = None
        self.auto_dj = True
        self._lock = threading.Lock()

        # Modos de navegacion: main | browse | queue | history + buscador
        self.mode = 'main'
        self.folder_names = []
        self.browse_level = 'folders'   # 'folders' | 'tracks'
        self.browse_sel = 0
        self.browse_folder = None
        self.browse_tracks = []
        self.search_active = False
        self.search_query = ''
        self.search_results = []

    # ------------------------------------------------------------------ UI --

    def _top(self):
        return C_CYAN + '┌' + self.H * 26 + C_RESET + C_BOLD + ' VIOLETA ' + C_RESET + C_CYAN + self.H * 27 + '┐' + C_RESET

    def _sep(self):
        return C_CYAN + '├' + self.H * self.W + '┤' + C_RESET

    def _bottom(self):
        return C_CYAN + '└' + self.H * self.W + '┘' + C_RESET

    def _line(self, content, color=C_RESET):
        inner = _pad_ansi(_fit_ansi(content, self.W), self.W)
        return C_CYAN + '│' + C_RESET + ' ' + color + inner + C_RESET + ' ' + C_CYAN + '│' + C_RESET

    def _header(self):
        mode_tag = f"{C_GREEN}ONLINE{C_RESET}" if not self.force_offline else f"{C_RED}OFFLINE{C_RESET}"
        shuf_tag = f"{C_GREEN}ON{C_RESET}" if self.shuffle_mode else f"{C_GRAY}OFF{C_RESET}"
        voice_tag = f"{C_GREEN}ON{C_RESET}" if self.voice_enabled else f"{C_GRAY}OFF{C_RESET}"
        xf_label = f"{self.crossfade_sec:.1f}s" if self.crossfade_sec > 0 else "OFF"
        print(self._top())
        print(self._line("CROSSFADE STUDIO", C_GRAY))
        print(self._line(f"Modo: {mode_tag}   Shuffle: {shuf_tag}   Voz: {voice_tag}    Crossfade: {xf_label}"))
        print(self._line(f"Pistas: {len(self.all_tracks)}   Contexto: {self.context_name}   Favoritos: {len(self.favorites)}", C_GRAY))

    def _render_main(self):
        status = self.mixer.get_status()
        track = status.get('track')
        pos = status.get('pos', 0.0)
        dur = status.get('dur', 0.0)
        paused = status.get('paused', False)
        ducking = status.get('ducking', False)

        print(self._sep())
        if ducking:
            print(self._line(f"[LIVI] {self.status_msg}", C_YELLOW))
        elif paused:
            print(self._line("[PAUSA]", C_RED))
        else:
            print(self._line(f"[PLAY] {self.status_msg}", C_GREEN))

        if track:
            title = track.get('title') or track.get('filename')
            artist = track.get('artist') or track.get('folder')
            folder = track.get('folder') or ''
            q_pos = f"{self.queue_index + 1}/{len(self.current_queue)}" if self.current_queue else "0/0"
            is_fav = track.get('path') in self.favorites
            star = f"{C_YELLOW}*{C_RESET} " if is_fav else ""
            print(self._line(star + f"{C_CYAN}{C_BOLD}{title}{C_RESET}  {C_GRAY}[{q_pos}]{C_RESET}", C_CYAN))
            print(self._line(f"Artista : {artist}", C_GREEN))
            print(self._line(f"Carpeta : {folder}", C_GRAY))

            pct = min(1.0, max(0.0, (pos / dur))) if dur > 0 else 0.0
            bar_len = 30
            filled = int(round(bar_len * pct))
            bar = ('█' * filled).ljust(bar_len, '░')
            time_str = f"{self.format_time(pos)} / {self.format_time(dur)}"
            pct_str = f"{pct * 100:3.0f}%"
            print(self._line(f"{C_GREEN}{bar}{C_RESET} {C_CYAN}{time_str}{C_RESET} {C_BOLD}{pct_str}{C_RESET}"))
        else:
            print(self._line(f"{C_GRAY}Sin pista activa..." + C_RESET, C_GRAY))

        print(self._sep())
        print(self._line(f"{C_BOLD}SPACE{C_RESET} Play/Pause   {C_BOLD}N{C_RESET} Next   {C_BOLD}B{C_RESET} Prev   {C_BOLD}S{C_RESET} Shuffle   {C_BOLD}F{C_RESET} Fav"))
        print(self._line(f"{C_BOLD}<{C_RESET}/ {C_BOLD},{C_RESET} -10s   {C_BOLD}>{C_RESET}/ {C_BOLD}.{C_RESET} +10s   {C_BOLD}E{C_RESET} Explorar   {C_BOLD}C{C_RESET} Cola   {C_BOLD}H{C_RESET} Historial"))
        print(self._line(f"{C_BOLD}/{C_RESET} Buscar   {C_BOLD}V{C_RESET} Voz   {C_BOLD}X{C_RESET} Crossfade   {C_BOLD}Q{C_RESET} Salir"))

        if self.folder_names:
            print(self._sep())
            for start in range(0, len(self.folder_names), 3):
                row = ""
                for j, f in enumerate(self.folder_names[start:start + 3]):
                    row += f"{C_BOLD}[{start + j + 1}]{C_RESET} {C_CYAN}{f}{C_RESET}({len(self.folder_map[f])})  "
                print(self._line(row.rstrip(), C_GRAY))

    def _render_browse(self):
        print(self._sep())
        if self.browse_level == 'folders':
            print(self._line(f"{C_BOLD}Carpetas  {C_GRAY}(flechitas / Enter para reproducir){C_RESET}"))
            for i, f in enumerate(self.folder_names):
                mark = f"{C_GREEN}>{C_RESET} " if i == self.browse_sel else "  "
                sel = f"{C_CYAN}{C_BOLD}{f}{C_RESET}" if i == self.browse_sel else f"{C_RESET}{f}{C_RESET}" if False else f
                label = mark + sel
                if i == self.browse_sel:
                    print(self._line(C_CYAN + label, C_CYAN))
                else:
                    print(self._line(label, C_GRAY))
            print(self._line(f"{C_GRAY}-> para expandir a canciones   ESC: volver{C_RESET}", C_GRAY))
        else:
            name = self.browse_folder
            print(self._line(f"{C_BOLD}{name}  {C_GRAY}({len(self.browse_tracks)} pistas){C_RESET}"))
            shown = self.browse_tracks[max(0, self.browse_sel - 4):][:9]
            offset = max(0, self.browse_sel - 4)
            for i, t in enumerate(shown):
                abs_idx = offset + i
                title = (t.get('title') or t.get('filename'))[:40]
                mark = f"{C_GREEN}>{C_RESET} " if abs_idx == self.browse_sel else "  "
                line_txt = mark + title
                if abs_idx == self.browse_sel:
                    print(self._line(C_CYAN + line_txt, C_CYAN))
                else:
                    print(self._line(line_txt, C_GRAY))
            print(self._line(f"{C_GRAY}<- para volver a carpetas   Enter: reproducir   ESC: salir{C_RESET}", C_GRAY))

    def _render_queue_view(self):
        print(self._sep())
        print(self._line(f"{C_BOLD}COLA  {C_GRAY}(Siguientes pistas){C_RESET}"))
        n = len(self.current_queue)
        for k in range(1, 10):
            idx = self.queue_index + k
            if idx >= n:
                break
            t = self.current_queue[idx]
            title = (t.get('title') or t.get('filename'))[:44]
            prefix = f"{C_CYAN}{k:>2}{C_RESET} " if k < 10 else "   "
            print(self._line(prefix + f"{C_GRAY}{title}{C_RESET}", C_GRAY))
        if n <= self.queue_index + 1:
            print(self._line(f"{C_GRAY}(fin de la cola){C_RESET}", C_GRAY))
        print(self._line(f"{C_GRAY}ESC: volver   espacio: reproducir/PAUSA{C_RESET}", C_GRAY))

    def _render_history_view(self):
        print(self._sep())
        print(self._line(f"{C_BOLD}HISTORIAL  {C_GRAY}(ultimas reproducidas){C_RESET}"))
        if not self.history:
            print(self._line(f"{C_GRAY}(vacio){C_RESET}", C_GRAY))
        for i, t in enumerate(reversed(self.history[-9:])):
            title = (t.get('title') or t.get('filename'))[:46]
            print(self._line(f" {C_CYAN}{i + 1:>2}{C_RESET} {C_GRAY}{title}{C_RESET}", C_GRAY))
        print(self._line(f"{C_GRAY}ESC: volver{C_RESET}", C_GRAY))

    def _render_search(self):
        print(self._sep())
        print(self._line(f"{C_BOLD}Buscar: {C_RESET}{C_GREEN}{self.search_query}{C_RESET}{C_GRAY}_{C_RESET}", C_GREEN))
        for i, t in enumerate(self.search_results[:6]):
            title = (t.get('title') or t.get('filename'))[:38]
            artist = (t.get('artist') or t.get('folder'))[:14]
            icon = f"{C_GREEN}>{C_RESET} " if i == 0 else "  "
            print(self._line(icon + f"{C_CYAN}{title}{C_RESET} {C_GRAY}- {artist}{C_RESET}", C_GRAY))
        if not self.search_results and self.search_query:
            print(self._line("  Sin resultados...", C_GRAY))
        print(self._line(f"{C_GRAY}Enter: reproducir el primero   ESC / borrar: cancelar{C_RESET}", C_GRAY))

    def render_ui(self):
        sys.stdout.write("\033[H\033[J")
        self._header()
        if self.search_active:
            self._render_search()
        elif self.mode == 'browse':
            self._render_browse()
        elif self.mode == 'queue':
            self._render_queue_view()
        elif self.mode == 'history':
            self._render_history_view()
        else:
            self._render_main()
        print(self._bottom())

    # -------------------------------------------------------------- state --

    def _save_state_periodically(self):
        def loop():
            while self.running:
                time.sleep(10)
                self.save_state()
        threading.Thread(target=loop, daemon=True).start()

    def save_state(self):
        self.state['shuffle'] = self.shuffle_mode
        self.state['crossfade_sec'] = self.crossfade_sec
        self.state['voice_enabled'] = self.voice_enabled
        self.state['favorites'] = sorted(self.favorites)
        self.state['last_context'] = self.context_name
        active = self.mixer.get_status()
        if active.get('track'):
            self.state['last_track_path'] = active['track'].get('path')
            self.state['last_pos'] = active.get('pos', 0.0)
        elif self.current_queue:
            track = self.current_queue[self.queue_index]
            self.state['last_track_path'] = track.get('path')
        self.state['last_index'] = self.queue_index
        self.state.save()

    def setup(self):
        print(f"{C_CYAN}Escaneando dispositivo en busca de musica...{C_RESET}")
        self.all_tracks, self.folder_map = scan_all_device(use_cache=not self.rescan)
        total = len(self.all_tracks)
        if total == 0:
            print(f"{C_RED}No se encontraron canciones en el dispositivo.{C_RESET}")
            sys.exit(1)

        self.folder_names = list(self.folder_map.keys())
        print(f"{C_GREEN}[OK] {total} canciones detectadas en {len(self.folder_map)} carpetas.{C_RESET}")
        for folder in self.folder_names[:5]:
            print(f"  * {folder}: {len(self.folder_map[folder])} pistas")

        # Enriquecer pistas con BPM/key y energía (opcional)
        try:
            self.all_tracks, report = enrich_tracks(self.all_tracks)
            print(f"{C_GREEN}[OK] {report['enriched']} pistas enriquecidas con BPM/key.{C_RESET}")
        except Exception as exc:
            print(f"{C_YELLOW}[!] No se pudo enriquecer con BPM/key: {exc}{C_RESET}")

        self.mixer.start()
        self.mixer.set_master_volume(float(self.state['volume'] or 100))

        resume_path = self.state['last_track_path']
        resume_idx = 0
        if resume_path:
            for i, t in enumerate(self.all_tracks):
                if t['path'] == resume_path:
                    resume_idx = i
                    break

        self.current_queue = list(self.all_tracks)
        self.queue_index = resume_idx
        if self.shuffle_mode:
            random.shuffle(self.current_queue)
            if resume_path:
                for i, t in enumerate(self.current_queue):
                    if t['path'] == resume_path:
                        self.queue_index = i
                        break
        saved_pos = float(self.state['last_pos'] or 0.0)
        self._save_state_periodically()
        self.play_current_track(trigger_speech=True, resume_pos=saved_pos)

    # ----------------------------------------------------------- playback --

    def play_current_track(self, trigger_speech=False, resume_pos=0.0):
        if not self.current_queue:
            return
        track = self.current_queue[self.queue_index]
        if trigger_speech and self.voice_enabled:
            script = self.commentator.generate_welcome_script(self.context_name, track)

            def speak(resume_sec=resume_pos):
                self.status_msg = f"[Livi] {script[:50]}..."
                try:
                    speech = self.commentator.prepare_speech(script, "livi_intro.mp3")
                    self.mixer.play_track(track)
                    time.sleep(0.4)
                    if resume_sec > 5.0:
                        self.mixer.seek(resume_sec)
                    self.mixer.play_voice_with_ducking(speech)
                except Exception:
                    self.mixer.play_track(track)
                    if resume_sec > 5.0:
                        self.mixer.seek(resume_sec)
                self.status_msg = "Reproduciendo"
            threading.Thread(target=speak, daemon=True).start()
        else:
            self.mixer.play_track(track, crossfade_sec=self.crossfade_sec)
            if resume_pos > 5.0:
                self.mixer.seek(resume_pos)
            self.status_msg = "Reproduciendo"
        self._prefetch_next_announce()

    def _prefetch_next_announce(self):
        """Pre-genera la voz de la siguiente cancion mientras suena la actual."""
        if not self.voice_enabled or not self.current_queue:
            return
        upcoming = self.current_queue[(self.queue_index + 1) % len(self.current_queue)]

        def gen():
            try:
                script = self.commentator.generate_track_intro_script(upcoming)
                self._cached_announce = self.commentator.prepare_speech(script, "livi_next.mp3")
            except Exception:
                self._cached_announce = None
        threading.Thread(target=gen, daemon=True).start()

    def announce_next(self, track):
        if not self.voice_enabled:
            return

        def speak():
            try:
                speech = getattr(self, '_cached_announce', None)
                self._cached_announce = None
                if not speech:
                    script = self.commentator.generate_track_intro_script(track)
                    speech = self.commentator.prepare_speech(script, "livi_next.mp3")
                if speech:
                    self.mixer.play_voice_with_ducking(speech)
            except Exception:
                pass
        threading.Thread(target=speak, daemon=True).start()

    def advance_track(self, quick=False):
        if not self.current_queue:
            return
        if 0 <= self.queue_index < len(self.current_queue):
            self.history.append(self.current_queue[self.queue_index])

        self.queue_index += 1
        if self.queue_index >= len(self.current_queue):
            # Auto-DJ: si está activo y hay mood, rearma la cola
            if self.auto_dj and self.mood:
                self.build_auto_queue(minutes=45, mood=self.mood)
                # build_auto_queue ya pone queue_index=0 y llama play_current_track
                return
            if self.shuffle_mode:
                random.shuffle(self.current_queue)
            self.queue_index = 0

        next_track = self.current_queue[self.queue_index]
        crossfade = min(self.crossfade_sec, 3.0) if quick else self.crossfade_sec
        self.mixer.play_track(next_track, crossfade_sec=crossfade)
        self.status_msg = f"{next_track.get('title') or next_track.get('filename')}"
        self.announce_next(next_track)
        self._prefetch_next_announce()

    def previous_track(self):
        status = self.mixer.get_status()
        pos = status.get('pos', 0.0)
        if pos > 3.0:
            self.mixer.seek(-99999)
            self.status_msg = "Reiniciando pista actual"
            return

        if self.queue_index > 0:
            self.queue_index -= 1
            prev_track = self.current_queue[self.queue_index]
        elif self.history:
            prev_track = self.history.pop()
        else:
            self.mixer.seek(-99999)
            return

        self.mixer.play_track(prev_track, crossfade_sec=self.crossfade_sec)
        self.status_msg = f"{prev_track.get('title') or prev_track.get('filename')}"
        self.announce_next(prev_track)
        self._prefetch_next_announce()

    def toggle_shuffle(self):
        self.shuffle_mode = not self.shuffle_mode
        if self.shuffle_mode and self.current_queue:
            curr = self.current_queue[self.queue_index] if self.queue_index < len(self.current_queue) else None
            rest = [t for t in self.current_queue if t != curr]
            random.shuffle(rest)
            self.current_queue = ([curr] if curr else []) + rest
            self.queue_index = 0
        self.status_msg = f"Aleatorio: {'ON' if self.shuffle_mode else 'OFF'}"

    def toggle_voice(self):
        self.voice_enabled = not self.voice_enabled
        self.status_msg = f"Voz del DJ: {'ON' if self.voice_enabled else 'SILENCIADA'}"

    def cycle_crossfade(self):
        idx = (CROSSFADE_OPTIONS.index(self.crossfade_sec) + 1) % len(CROSSFADE_OPTIONS) \
            if self.crossfade_sec in CROSSFADE_OPTIONS else 1
        self.crossfade_sec = CROSSFADE_OPTIONS[idx]
        label = f"{self.crossfade_sec:.1f}s" if self.crossfade_sec > 0 else "OFF"
        self.status_msg = f"Crossfade: {label}"

    def toggle_favorite(self, track=None):
        if track is None:
            if not self.current_queue:
                return
            track = self.current_queue[self.queue_index]
        path = track.get('path')
        if path in self.favorites:
            self.favorites.discard(path)
            self.status_msg = "Quitado de Favoritos"
        else:
            self.favorites.add(path)
            self.status_msg = "Agregado a Favoritos"
        self.state['favorites'] = sorted(self.favorites)
        self.state.save()

    def play_folder_by_index(self, idx):
        folders = list(self.folder_map.keys())
        if 0 <= idx < len(folders):
            f_name = folders[idx]
            tracks = list(self.folder_map[f_name])
            if self.shuffle_mode:
                random.shuffle(tracks)
            self.current_queue = tracks
            self.queue_index = 0
            self.context_name = f"Carpeta: {f_name}"
            self.mixer.play_track(self.current_queue[0], crossfade_sec=self.crossfade_sec)
            self.status_msg = f"Carpeta: {f_name}"
            self._prefetch_next_announce()

    def seek_seconds(self, seconds):
        self.mixer.seek(seconds)
        sign = "+" if seconds > 0 else ""
        self.status_msg = f"Posicion {sign}{seconds}s" if seconds > 0 else f"Posicion {seconds}s"

    def format_time(self, seconds):
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    # ------------------------------------------------------ navegacion.py --

    def start_browse(self):
        self.mode = 'browse'
        self.browse_level = 'folders'
        self.browse_sel = 0
        self.browse_folder = None
        self.browse_tracks = []

    def browse_move(self, direction):
        if self.browse_level == 'folders':
            n = len(self.folder_names)
            if n:
                self.browse_sel = (self.browse_sel + direction) % n
        else:
            n = len(self.browse_tracks)
            if n:
                self.browse_sel = (self.browse_sel + direction) % n

    def browse_expand(self):
        if self.browse_level == 'folders' and self.folder_names:
            self.browse_folder = self.folder_names[self.browse_sel]
            self.browse_tracks = list(self.folder_map[self.browse_folder])
            self.browse_sel = 0
            self.browse_level = 'tracks'

    def browse_collapse(self):
        if self.browse_level == 'tracks':
            self.browse_level = 'folders'
            self.browse_sel = self.folder_names.index(self.browse_folder) if self.browse_folder in self.folder_names else 0
            self.browse_folder = None
            self.browse_tracks = []

    def browse_play(self):
        if self.browse_level == 'folders':
            if self.folder_names:
                self.play_folder_by_index(self.browse_sel)
        else:
            if self.browse_tracks:
                self.current_queue = list(self.browse_tracks)
                self.queue_index = self.browse_sel
                self.context_name = f"Carpeta: {self.browse_folder}"
                self.play_current_track(trigger_speech=False)
        self.mode = 'main'

    def update_search(self):
        q = self.search_query.strip().lower()
        if not q:
            self.search_results = []
            return

    def build_auto_queue(self, minutes=45, mood=None, terms=None):
        """Arma una cola armonica usando el motor de sets y la pone a sonar."""
        mood = normalize_mood(mood) or self.mood or DEFAULT_MOOD
        queue, info = build_set(self.all_tracks, minutes=minutes, mood=mood, terms=terms)
        if not queue:
            self.status_msg = "No se encontraron pistas para ese set."
            return False
        self.mood = mood
        with self._lock:
            self.current_queue = queue
            self.queue_index = 0
            self.history = []
        self.context_name = f"Set {info.get('mood_label', mood)} ({info['track_count']} pistas)"
        self.status_msg = f"Set {info.get('mood_label', mood)} - {info['track_count']} pistas - {info['minutes']} min"
        self.play_current_track(trigger_speech=False)
        return True

    def cycle_mood(self):
        """Cambia al mood siguiente y rearma la cola automáticamente."""
        self.mood = next_mood(self.mood)
        self.build_auto_queue(minutes=45, mood=self.mood)

    def handle_voice(self):
        """Escucha, interpreta con el cerebro y ejecuta lo pedido."""
        if self.force_offline or not self.voice.enabled:
            self.status_msg = "Voz no disponible (falta GROQ_API_KEY)."
            return
        try:
            text = self.voice.listen_and_transcribe()
        except Exception as exc:
            self.status_msg = f"Error de voz: {exc}"
            return
        if not text:
            self.status_msg = "No escuche nada."
            return
        data = self.brain.parse_request(text) or {"action": "unknown"}
        action = data.get("action")
        if action == "play_mood":
            self.build_auto_queue(minutes=data.get("minutes") or 45,
                                  mood=data.get("mood"),
                                  terms=data.get("query"))
        elif action == "skip":
            self.advance_track()
        elif action == "prev":
            self.previous_track()
        elif action == "pause":
            self.mixer.toggle_pause()
        elif action == "resume":
            self.mixer.toggle_pause()
        elif action == "volume_up":
            self.mixer.set_volume(90)
        elif action == "volume_down":
            self.mixer.set_volume(30)
        elif action == "say":
            self.say(data.get("text", ""))
        else:
            reply = self.brain.chat_reply(text, None) or \
                "No te entendi bien, pero seguimos sonando."
            self.status_msg = f"[Livi] {reply}"
            try:
                speech = self.commentator.prepare_speech(reply, "livi_chat.mp3")
                self.mixer.play_voice_with_ducking(speech)
            except Exception:
                pass

    def say(self, text):
        """Hace que Livi diga un texto por la mezcla (ducking)."""
        text = (text or "").strip()
        if not text:
            return
        try:
            speech = self.commentator.prepare_speech(text, "livi_say.mp3")
        except Exception as exc:
            return
        status = self.mixer.get_status()
        if status.get('playing'):
            self.mixer.play_voice_with_ducking(speech)
        else:
            self.mixer.play_track(self.mixer.get_status().get('track')
                                  or self.current_queue[0])
            time.sleep(0.3)
            self.mixer.play_voice_with_ducking(speech)

            return
        self.search_results = [
            t for t in self.all_tracks
            if q in (t.get('title') or t.get('filename') or '').lower()
            or q in (t.get('artist') or '').lower()
            or q in (t.get('folder') or '').lower()
        ][:30]

    def commit_search(self):
        if self.search_results:
            self.current_queue = list(self.search_results)
            self.queue_index = 0
            self.context_name = f"Busqueda: {self.search_query.strip()}"
            self.play_current_track(trigger_speech=False)
            self.status_msg = f"{self.search_results[0].get('title') or self.search_results[0].get('filename')}"
        self.search_active = False
        self.search_query = ''
        self.search_results = []
        self.mode = 'main'

    def cancel_transient(self):
        self.mode = 'main'
        self.search_active = False
        self.search_query = ''
        self.search_results = []

    # ---------------------------------------------------------------- run --

    def run(self):
        self.setup()
        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setcbreak(sys.stdin.fileno())
            crossfade_triggered = False

            while self.running:
                self.render_ui()
                status = self.mixer.get_status()
                pos = status.get('pos', 0.0)
                dur = status.get('dur', 0.0)

                # Crossfade automatico antes del final (con fade rapido ~3s)
                xf_quick = min(self.crossfade_sec, 3.0)
                lookahead = min(xf_quick + 1.0, 5.0)
                if status['playing'] and dur > 8 and (dur - pos) <= lookahead:
                    if not crossfade_triggered:
                        crossfade_triggered = True
                        self.advance_track(quick=True)
                else:
                    crossfade_triggered = False

                rlist, _, _ = select.select([sys.stdin], [], [], 0.5)
                if not rlist:
                    continue
                ch = sys.stdin.read(1)

                # --- Buscador activo ---
                if self.search_active:
                    if ch in ('\x7f', '\x08'):
                        self.search_query = self.search_query[:-1]
                        self.update_search()
                    elif ch in ('\r', '\n'):
                        self.commit_search()
                    elif ch == '\x1b':
                        r_esc, _, _ = select.select([sys.stdin], [], [], 0.05)
                        if r_esc:
                            sys.stdin.read(2)
                        self.cancel_transient()
                    elif ch.isprintable():
                        self.search_query += ch
                        self.update_search()
                    continue

                # --- Teclas de modo ---
                if ch in ('e', 'E', 'b', 'B'):
                    if self.mode == 'browse':
                        self.mode = 'main'
                    else:
                        self.start_browse()
                elif ch in ('c', 'C'):
                    self.mode = 'queue' if self.mode != 'queue' else 'main'
                elif ch in ('h', 'H'):
                    self.mode = 'history' if self.mode != 'history' else 'main'
                elif ch == '/':
                    self.search_active = True
                    self.search_query = ''
                    self.update_search()
                    self.mode = 'main'
                elif ch == '\x1b':
                    r_esc, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if not r_esc:
                        self.cancel_transient()
                        continue
                    seq = sys.stdin.read(2)
                    if self.mode == 'browse':
                        if seq == '[A':
                            self.browse_move(-1)
                        elif seq == '[B':
                            self.browse_move(1)
                        elif seq == '[C':
                            self.browse_expand()
                        elif seq == '[D':
                            self.browse_collapse()
                    elif self.mode in ('queue', 'history'):
                        self.mode = 'main'
                    else:
                        if seq == '[C':
                            self.seek_seconds(10)
                        elif seq == '[D':
                            self.seek_seconds(-10)
                        elif seq == '[A':
                            self.advance_track()
                        elif seq == '[B':
                            self.previous_track()
                elif self.mode == 'browse':
                    if ch in ('\r', '\n'):
                        self.browse_play()
                elif self.mode in ('queue', 'history'):
                    if ch == ' ':
                        self.mixer.toggle_pause()
                else:
                    if ch == ' ':
                        self.mixer.toggle_pause()
                    elif ch in ('n', 'N'):
                        self.advance_track()
                    elif ch in ('b', 'B', 'r', 'R'):
                        self.previous_track()
                    elif ch in ('s', 'S'):
                        self.toggle_shuffle()
                    elif ch in ('v', 'V'):
                        self.toggle_voice()
                    elif ch in ('x', 'X'):
                        self.cycle_crossfade()
                    elif ch in ('f', 'F'):
                        self.toggle_favorite()
                    elif ch in ('t', 'T'):
                        self.current_queue = list(self.all_tracks)
                        if self.shuffle_mode:
                            random.shuffle(self.current_queue)
                        self.queue_index = 0
                        self.context_name = "Todo el dispositivo"
                        self.play_current_track(trigger_speech=False)
                    elif ch in ('a', 'A'):
                        self.build_auto_queue(minutes=45, mood=self.mood)
                    elif ch in ('m', 'M'):
                        self.cycle_mood()
                    elif ch in ('z', 'Z'):
                        threading.Thread(target=self.handle_voice, daemon=True).start()
                        self.status_msg = "Te escucho..."
                    elif ch in ('.', '>'):
                        self.seek_seconds(10)
                    elif ch in (',', '<'):
                        self.seek_seconds(-10)
                    elif ch in '12345678':
                        idx = int(ch) - 1
                        self.play_folder_by_index(idx)
                    elif ch in ('q', 'Q'):
                        print("\nCerrando reproductor...")
                        self.running = False
                        break
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            self.mixer.stop()
            self.save_state()


if __name__ == "__main__":
    offline_mode = "--offline" in sys.argv
    rescan_mode = "--rescan" in sys.argv
    app = DJLiviApp(force_offline=offline_mode, rescan=rescan_mode)
    app.run()