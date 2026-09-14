#!/usr/bin/env python3
"""
dj_mixer.py - Motor de mezcla en tiempo real con doble deck (Deck A / Deck B),
ducking para la voz del DJ y crossfade fluido usando MPV IPC.
"""
import os
import time
import json
import socket
import subprocess
import threading

class MPVDeck:
    def __init__(self, name, socket_path):
        self.name = name
        self.socket_path = socket_path
        self.proc = None
        self.sock = None
        self.lock = threading.Lock()
        self.current_file = None
        self.target_volume = 100

    def start(self):
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except OSError:
                pass

        cmd = [
            'mpv',
            '--idle=yes',
            '--no-video',
            '--no-terminal',
            '--volume=100',
            f'--input-ipc-server={self.socket_path}'
        ]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Conectar al socket
        for _ in range(25):
            time.sleep(0.1)
            if os.path.exists(self.socket_path):
                try:
                    self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    self.sock.connect(self.socket_path)
                    self.sock.settimeout(2.0)
                    return True
                except (socket.error, OSError):
                    pass
        raise RuntimeError(f"No se pudo conectar al IPC de {self.name} en {self.socket_path}")

    def send_command(self, cmd_list):
        with self.lock:
            if not self.sock:
                return None
            try:
                msg = (json.dumps({"command": cmd_list}) + "\n").encode('utf-8')
                self.sock.sendall(msg)
                
                # Leer respuesta
                data = b""
                while b"\n" not in data:
                    chunk = self.sock.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                line = data.decode('utf-8', errors='ignore').split('\n')[0]
                if line:
                    return json.loads(line)
            except Exception:
                return None
        return None

    def get_property(self, prop_name):
        res = self.send_command(["get_property", prop_name])
        if res and isinstance(res, dict) and "data" in res:
            return res["data"]
        return None

    def set_property(self, prop_name, value):
        return self.send_command(["set_property", prop_name, value])

    def load(self, filepath, start_paused=False):
        self.current_file = filepath
        if start_paused:
            self.send_command(["loadfile", filepath, "replace", "pause=yes"])
        else:
            self.send_command(["loadfile", filepath, "replace"])

    def stop(self):
        self.send_command(["stop"])
        self.current_file = None

    def pause(self, state=True):
        self.set_property("pause", state)

    def is_paused(self):
        return bool(self.get_property("pause"))

    def is_idle(self):
        return bool(self.get_property("idle-active"))

    def get_time_pos(self):
        val = self.get_property("time-pos")
        return float(val) if val is not None else 0.0

    def get_duration(self):
        val = self.get_property("duration")
        return float(val) if val is not None else 0.0

    def seek(self, seconds):
        """Adelanta o retrocede la posición actual en segundos."""
        self.send_command(["seek", seconds, "relative"])

    def set_volume(self, vol):
        vol = max(0.0, min(100.0, float(vol)))
        self.set_property("volume", vol)

    def ramp_volume(self, target_vol, duration_sec=1.5, steps=15):
        """Sube o baja suavemente el volumen."""
        current_vol = self.get_property("volume")
        if current_vol is None:
            current_vol = 100.0
        else:
            current_vol = float(current_vol)

        step_delay = duration_sec / steps
        vol_diff = target_vol - current_vol

        for i in range(1, steps + 1):
            new_v = current_vol + (vol_diff * (i / steps))
            self.set_volume(new_v)
            time.sleep(step_delay)

    def quit(self):
        try:
            self.send_command(["quit"])
        except Exception:
            pass
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=1.0)
            except Exception:
                pass


import tempfile

class DJMixer:
    def __init__(self):
        tmp = tempfile.gettempdir()
        self.deck_a = MPVDeck("Deck A", os.path.join(tmp, "livi_deck_a.sock"))
        self.deck_b = MPVDeck("Deck B", os.path.join(tmp, "livi_deck_b.sock"))
        self.deck_voice = MPVDeck("Voice Deck", os.path.join(tmp, "livi_voice.sock"))
        self.active_deck = None
        self.current_track = None
        self.ducking_active = False

    def start(self):
        self.deck_a.start()
        self.deck_b.start()
        self.deck_voice.start()
        self.active_deck = self.deck_a

    def stop(self):
        self.deck_a.quit()
        self.deck_b.quit()
        self.deck_voice.quit()

    def get_next_deck(self):
        return self.deck_b if self.active_deck == self.deck_a else self.deck_a

    def play_track(self, track_info, crossfade_sec=4.0):
        """Reproduce una pista. Si ya hay una sonando, hace crossfade suave."""
        filepath = track_info['path']
        self.current_track = track_info

        # Si no hay música sonando, arrancar directo
        if not self.active_deck or self.active_deck.is_idle():
            self.active_deck = self.deck_a
            self.active_deck.set_volume(100)
            self.active_deck.load(filepath)
            return

        old_deck = self.active_deck
        new_deck = self.get_next_deck()

        # Iniciar nueva pista con volumen 0
        new_deck.set_volume(0)
        new_deck.load(filepath)
        self.active_deck = new_deck

        # Crossfade en hilo para no bloquear el loop principal
        def do_crossfade():
            steps = 20
            delay = crossfade_sec / steps
            for i in range(1, steps + 1):
                fade_out = 100.0 * (1.0 - (i / steps))
                fade_in = 100.0 * (i / steps)
                old_deck.set_volume(fade_out)
                new_deck.set_volume(fade_in)
                time.sleep(delay)
            old_deck.stop()

        t = threading.Thread(target=do_crossfade, daemon=True)
        t.start()

    def play_voice_with_ducking(self, voice_audio_path, duck_volume=20, duck_time=0.4):
        """Baja la música suavemente (ducking), habla Livi, y restaura la música."""
        self.ducking_active = True
        active = self.active_deck

        # 1. Ducking suave de la música activa
        if active and not active.is_idle():
            active.ramp_volume(duck_volume, duration_sec=duck_time, steps=8)

        # 2. Reproducir voz en el Voice Deck
        self.deck_voice.set_volume(100)
        self.deck_voice.load(voice_audio_path)

        # Esperar a que comience la voz
        time.sleep(0.2)

        # Esperar hasta que termine de hablar
        while not self.deck_voice.is_idle():
            time.sleep(0.1)

        # 3. Restaurar música activa a volumen 100%
        if active and not active.is_idle():
            active.ramp_volume(100, duration_sec=duck_time, steps=8)

        self.ducking_active = False

    def seek(self, seconds):
        """Adelanta o retrocede segundos en la pista activa."""
        if self.active_deck and not self.active_deck.is_idle():
            self.active_deck.seek(seconds)

    def toggle_pause(self):
        if self.active_deck:
            new_state = not self.active_deck.is_paused()
            self.active_deck.pause(new_state)
            return new_state
        return False

    def get_status(self):
        if not self.active_deck or self.active_deck.is_idle():
            return {
                'playing': False,
                'track': None,
                'pos': 0.0,
                'dur': 0.0,
                'paused': False,
                'ducking': self.ducking_active
            }
        
        pos = self.active_deck.get_time_pos()
        dur = self.active_deck.get_duration()
        paused = self.active_deck.is_paused()

        return {
            'playing': True,
            'track': self.current_track,
            'pos': pos,
            'dur': dur,
            'paused': paused,
            'ducking': self.ducking_active
        }
