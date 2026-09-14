#!/usr/bin/env python3
"""
ai_dj.py - Reproductor Terminal con Doble Deck, Crossfade Continuo, Modo Carpetas y Canciones.
Detecta todas las canciones del dispositivo, soporte para shuffle y crossfade automático.
"""
import os
import sys
import time
import tty
import select
import termios
import random
import threading
from music_scanner import scan_all_device
from dj_commentator import DJCommentator
from dj_mixer import DJMixer

C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_GREEN = "\033[92m"
C_CYAN = "\033[96m"
C_YELLOW = "\033[93m"
C_MAGENTA = "\033[95m"
C_RED = "\033[91m"
C_GRAY = "\033[90m"

class DJLiviApp:
    def __init__(self, force_offline=False):
        self.force_offline = force_offline
        self.mixer = DJMixer()
        self.commentator = DJCommentator(force_offline=force_offline)
        self.all_tracks = []
        self.folder_map = {}
        
        self.current_queue = []
        self.queue_index = 0
        self.history = []
        self.shuffle_mode = False
        self.context_name = "Todo el dispositivo"
        self.status_msg = "Iniciando reproductor..."
        self.running = True

    def setup(self):
        print(f"{C_CYAN}{C_BOLD}🎵 Escaneando todo el dispositivo en busca de música...{C_RESET}")
        self.all_tracks, self.folder_map = scan_all_device()
        total = len(self.all_tracks)
        if total == 0:
            print(f"{C_RED}No se encontraron canciones en el dispositivo.{C_RESET}")
            sys.exit(1)

        print(f"{C_GREEN}✔ ¡{total} canciones detectadas en {len(self.folder_map)} carpetas!{C_RESET}")
        for folder, tracks in list(self.folder_map.items())[:5]:
            print(f"  • {folder}: {len(tracks)} canciones")

        self.mixer.start()
        self.current_queue = list(self.all_tracks)
        self.queue_index = 0
        self.play_current_track(trigger_speech=True)

    def play_current_track(self, trigger_speech=False):
        if not self.current_queue:
            return
        track = self.current_queue[self.queue_index]
        if trigger_speech:
            script = self.commentator.generate_welcome_script(self.context_name, track)
            def speak():
                self.status_msg = f"🎙️ Livi: \"{script[:50]}...\""
                try:
                    speech = self.commentator.prepare_speech(script, "livi_intro.mp3")
                    self.mixer.play_track(track)
                    time.sleep(0.4)
                    self.mixer.play_voice_with_ducking(speech)
                except Exception:
                    self.mixer.play_track(track)
                self.status_msg = "🎵 Reproduciendo"
            threading.Thread(target=speak, daemon=True).start()
        else:
            self.mixer.play_track(track, crossfade_sec=3.5)
            self.status_msg = "🎵 Reproduciendo"

    def advance_track(self):
        if not self.current_queue:
            return
        if 0 <= self.queue_index < len(self.current_queue):
            self.history.append(self.current_queue[self.queue_index])

        self.queue_index += 1
        if self.queue_index >= len(self.current_queue):
            if self.shuffle_mode:
                random.shuffle(self.current_queue)
            self.queue_index = 0

        next_track = self.current_queue[self.queue_index]
        self.mixer.play_track(next_track, crossfade_sec=4.5)
        self.status_msg = f"🎵 {next_track.get('title') or next_track.get('filename')}"

    def previous_track(self):
        status = self.mixer.get_status()
        pos = status.get('pos', 0.0)
        if pos > 3.0:
            self.mixer.seek(-99999)
            self.status_msg = "⏮️ Reiniciando pista actual"
            return

        if self.queue_index > 0:
            self.queue_index -= 1
            prev_track = self.current_queue[self.queue_index]
        elif self.history:
            prev_track = self.history.pop()
        else:
            self.mixer.seek(-99999)
            return

        self.mixer.play_track(prev_track, crossfade_sec=3.0)
        self.status_msg = f"⏮️ {prev_track.get('title') or prev_track.get('filename')}"

    def toggle_shuffle(self):
        self.shuffle_mode = not self.shuffle_mode
        if self.shuffle_mode and self.current_queue:
            curr = self.current_queue[self.queue_index] if self.queue_index < len(self.current_queue) else None
            rest = [t for t in self.current_queue if t != curr]
            random.shuffle(rest)
            self.current_queue = ([curr] if curr else []) + rest
            self.queue_index = 0
        self.status_msg = f"🔀 Aleatorio {'ACTIVADO' if self.shuffle_mode else 'DESACTIVADO'}"

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
            self.mixer.play_track(self.current_queue[0], crossfade_sec=3.5)
            self.status_msg = f"📁 Reproduciendo carpeta: {f_name}"

    def seek_seconds(self, seconds):
        self.mixer.seek(seconds)
        sign = "+" if seconds > 0 else ""
        self.status_msg = f"⏩ {sign}{seconds}s" if seconds > 0 else f"⏪ {seconds}s"

    def format_time(self, seconds):
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    def render_ui(self):
        status = self.mixer.get_status()
        track = status.get('track')
        pos = status.get('pos', 0.0)
        dur = status.get('dur', 0.0)
        paused = status.get('paused', False)
        ducking = status.get('ducking', False)

        sys.stdout.write("\033[H\033[J")
        mode_tag = f"{C_GREEN}[100% Offline]{C_RESET}" if self.force_offline else f"{C_CYAN}[Híbrido/Auto]{C_RESET}"
        shuf_tag = f"{C_GREEN}[ALEATORIO ON]{C_RESET}" if self.shuffle_mode else f"{C_GRAY}[ALEATORIO OFF]{C_RESET}"

        print(f"{C_MAGENTA}{C_BOLD}╔══════════════════════════════════════════════════════════════════════════╗{C_RESET}")
        print(f"{C_MAGENTA}{C_BOLD}║                       🎧  O M N I P L A Y E R   D J                      ║{C_RESET}")
        print(f"{C_MAGENTA}{C_BOLD}║              Reproductor con Crossfade Continuo y Mezcla Total           ║{C_RESET}")
        print(f"{C_MAGENTA}{C_BOLD}╚══════════════════════════════════════════════════════════════════════════╝{C_RESET} {mode_tag} {shuf_tag}")
        print()

        if ducking:
            print(f" {C_YELLOW}{C_BOLD}🎙️  LIVI:{C_RESET} {C_YELLOW}{self.status_msg}{C_RESET}")
        elif paused:
            print(f" {C_RED}{C_BOLD}⏸️  EN PAUSA{C_RESET}")
        else:
            print(f" {C_GREEN}{C_BOLD}▶  ESTADO:{C_RESET} {self.status_msg}")

        q_pos = f"{self.queue_index + 1} de {len(self.current_queue)}" if self.current_queue else "0/0"
        print(f" {C_CYAN}Origen:{C_RESET} {C_BOLD}{self.context_name}{C_RESET} (Pista {q_pos} | Total: {len(self.all_tracks)})")
        print()

        if track:
            title = track.get('title') or track.get('filename')
            artist = track.get('artist') or track.get('folder')
            print(f" {C_BOLD}🎶 Pista:{C_RESET}   {C_CYAN}{title}{C_RESET}")
            print(f" {C_BOLD}👤 Artista:{C_RESET} {artist} {C_GRAY}(📁 {track.get('folder')}){C_RESET}")
            
            pct = min(1.0, max(0.0, (pos / dur))) if dur > 0 else 0.0
            bar_len = 35
            filled = int(bar_len * pct)
            bar = f"{C_GREEN}{'━' * filled}{C_GRAY}{'━' * (bar_len - filled)}{C_RESET}"
            time_str = f"{self.format_time(pos)} / {self.format_time(dur)}"
            print(f"    [{bar}] {time_str}")
        else:
            print(f" {C_GRAY}Sin pista activa...{C_RESET}")

        print()
        print(f"{C_GRAY}──────────────────────────────────────────────────────────────────────────{C_RESET}")
        print(f"{C_BOLD}Controles principales:{C_RESET}")
        print(f"  [{C_CYAN}ESPACIO{C_RESET}] Pausa/Play      [{C_CYAN}B / R{C_RESET}] Canción anterior    [{C_CYAN}N{C_RESET}] Siguiente pista (Crossfade)")
        print(f"  [{C_CYAN}, / ◄{C_RESET}] Retroceder 10s   [{C_CYAN}. / ►{C_RESET}] Adelantar 10s       [{C_CYAN}S{C_RESET}] Activar/Desactivar Aleatorio")
        print(f"  [{C_CYAN}T{C_RESET}] Reproducir Todo el dispositivo          [{C_CYAN}Q{C_RESET}] Salir")
        
        folders = list(self.folder_map.keys())
        if folders:
            print(f"\n{C_BOLD}Carpetas disponibles (Presiona el número):{C_RESET}")
            f_str = "  "
            for i, f in enumerate(folders[:8]):
                f_str += f"[{C_YELLOW}{i+1}{C_RESET}] {f} ({len(self.folder_map[f])})   "
            print(f_str)
        print(f"{C_GRAY}──────────────────────────────────────────────────────────────────────────{C_RESET}")

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

                # Crossfade duro automático antes de terminar la canción
                if status['playing'] and dur > 8 and (dur - pos) <= 4.5:
                    if not crossfade_triggered:
                        crossfade_triggered = True
                        self.advance_track()
                else:
                    crossfade_triggered = False

                rlist, _, _ = select.select([sys.stdin], [], [], 0.5)
                if rlist:
                    ch = sys.stdin.read(1)
                    if ch == ' ':
                        self.mixer.toggle_pause()
                    elif ch in ('n', 'N'):
                        self.advance_track()
                    elif ch in ('b', 'B', 'r', 'R'):
                        self.previous_track()
                    elif ch in ('s', 'S'):
                        self.toggle_shuffle()
                    elif ch in ('t', 'T'):
                        self.current_queue = list(self.all_tracks)
                        if self.shuffle_mode:
                            random.shuffle(self.current_queue)
                        self.queue_index = 0
                        self.context_name = "Todo el dispositivo"
                        self.play_current_track(trigger_speech=False)
                    elif ch in ('.', '>'):
                        self.seek_seconds(10)
                    elif ch in (',', '<'):
                        self.seek_seconds(-10)
                    elif ch == '\x1b':
                        r_esc, _, _ = select.select([sys.stdin], [], [], 0.05)
                        if r_esc:
                            seq = sys.stdin.read(2)
                            if seq == '[C':
                                self.seek_seconds(10)
                            elif seq == '[D':
                                self.seek_seconds(-10)
                            elif seq == '[A':
                                self.advance_track()
                            elif seq == '[B':
                                self.previous_track()
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

if __name__ == "__main__":
    offline_mode = "--offline" in sys.argv
    app = DJLiviApp(force_offline=offline_mode)
    app.run()
