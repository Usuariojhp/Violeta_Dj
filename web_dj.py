#!/usr/bin/env python3
"""
web_dj.py - Reproductor Web con Crossfade Real y DJ Livi para Móvil y PC.
Detecta canciones de todo el dispositivo, permite seleccionar carpetas o canciones individuales,
modo aleatorio (shuffle), y mezcla continua con doble deck.
"""
import os
import sys
import json
import time
import random
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from music_scanner import scan_all_device
from dj_commentator import DJCommentator
from dj_mixer import DJMixer

HTML_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
  <title>OmniPlayer DJ - Crossfade Music</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: #0c0d14; color: #fff; display: flex; flex-direction: column; min-height: 100vh; padding: 14px; -webkit-tap-highlight-color: transparent; }
    
    header { text-align: center; margin-bottom: 12px; }
    .top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .badge { background: #1f222e; color: #1db954; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 12px; text-transform: uppercase; letter-spacing: 0.8px; border: 1px solid #2d3142; }
    .stats-tag { font-size: 11px; color: #888ea8; }
    .dj-status { font-size: 13px; color: #ffd166; min-height: 20px; font-weight: 500; transition: color 0.3s; margin-top: 4px; text-align: center; }

    /* Vinilo animado */
    .disc-container { display: flex; justify-content: center; align-items: center; margin: 12px 0; }
    .disc { width: 170px; height: 170px; border-radius: 50%; background: radial-gradient(circle, #333 15%, #111 25%, #222 35%, #050505 60%, #1a1a2e 90%); box-shadow: 0 10px 30px rgba(0,0,0,0.8), 0 0 25px rgba(29, 185, 84, 0.25); display: flex; justify-content: center; align-items: center; border: 4px solid #222; animation: spin 8s linear infinite; animation-play-state: paused; }
    .disc.playing { animation-play-state: running; }
    .disc-center { width: 55px; height: 55px; border-radius: 50%; background: #1db954; display: flex; justify-content: center; align-items: center; font-size: 22px; box-shadow: inset 0 0 10px rgba(0,0,0,0.5); }
    @keyframes spin { 100% { transform: rotate(360deg); } }

    /* Info pista */
    .track-info { text-align: center; margin-bottom: 12px; }
    .track-title { font-size: 17px; font-weight: 700; color: #fff; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 0 8px; }
    .track-artist { font-size: 13px; color: #a0a0b0; }
    .context-tag { font-size: 12px; color: #00d2ff; margin-top: 4px; font-weight: 600; }

    /* Barra progreso */
    .progress-box { margin-bottom: 15px; }
    .progress-bar-bg { width: 100%; height: 7px; background: #252836; border-radius: 4px; overflow: hidden; cursor: pointer; }
    .progress-bar-fill { width: 0%; height: 100%; background: #1db954; border-radius: 4px; transition: width 0.2s linear; }
    .time-labels { display: flex; justify-content: space-between; font-size: 11px; color: #888; margin-top: 5px; }

    /* Controles principales */
    .main-controls { display: flex; justify-content: center; align-items: center; gap: 12px; margin-bottom: 16px; }
    .btn { background: #1f222e; border: none; color: #fff; border-radius: 50%; display: flex; justify-content: center; align-items: center; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.3); transition: transform 0.1s, background 0.2s; }
    .btn:active { transform: scale(0.92); }
    .btn-small { width: 42px; height: 42px; font-size: 15px; }
    .btn-med { width: 50px; height: 50px; font-size: 18px; }
    .btn-large { width: 64px; height: 64px; font-size: 24px; background: #1db954; color: #000; }

    /* Fila de modos y opciones */
    .options-row { display: flex; justify-content: center; gap: 10px; margin-bottom: 16px; }
    .pill-btn { background: #1a1d28; border: 1px solid #2e344a; color: #ccc; padding: 8px 14px; border-radius: 20px; font-size: 12px; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px; }
    .pill-btn.active { background: #1db954; color: #000; border-color: #1db954; font-weight: 700; }
    .pill-btn:active { transform: scale(0.95); }

    /* Pestañas Biblioteca */
    .tabs-nav { display: flex; border-bottom: 1px solid #252836; margin-bottom: 12px; }
    .tab-item { flex: 1; text-align: center; padding: 10px; font-size: 13px; font-weight: 700; color: #888; cursor: pointer; border-bottom: 2px solid transparent; }
    .tab-item.active { color: #1db954; border-bottom-color: #1db954; }

    /* Buscador */
    .search-box { margin-bottom: 12px; }
    .search-input { width: 100%; padding: 10px 14px; background: #161822; border: 1px solid #2e344a; border-radius: 10px; color: #fff; font-size: 13px; outline: none; }
    .search-input:focus { border-color: #1db954; }

    /* Listas de elementos */
    .items-list { max-height: 260px; overflow-y: auto; padding-right: 4px; display: flex; flex-direction: column; gap: 6px; }
    .list-card { background: #161822; border: 1px solid #252836; border-radius: 10px; padding: 10px 12px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; transition: 0.15s; }
    .list-card:active { transform: scale(0.98); background: #252836; }
    .list-card.active-item { border-color: #1db954; background: rgba(29, 185, 84, 0.08); }
    .card-left { flex: 1; min-width: 0; padding-right: 8px; }
    .card-title { font-size: 13px; font-weight: 600; color: #fff; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .card-subtitle { font-size: 11px; color: #888ea8; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .card-badge { font-size: 11px; background: #252836; color: #1db954; padding: 2px 8px; border-radius: 8px; white-space: nowrap; }

    /* Scrollbar personalizada */
    .items-list::-webkit-scrollbar { width: 4px; }
    .items-list::-webkit-scrollbar-thumb { background: #2e344a; border-radius: 4px; }
  </style>
</head>
<body>
  <header>
    <div class="top-bar">
      <div class="badge" id="modeBadge">DJ CROSSFADE</div>
      <div class="stats-tag" id="statsTag">Escaneando canciones...</div>
    </div>
    <div class="dj-status" id="djStatus">Cargando consola de audio...</div>
  </header>

  <div class="disc-container">
    <div class="disc" id="disc">
      <div class="disc-center">🎧</div>
    </div>
  </div>

  <div class="track-info">
    <div class="track-title" id="trackTitle">Selecciona una pista o carpeta</div>
    <div class="track-artist" id="trackArtist">Listo para mezclar</div>
    <div class="context-tag" id="contextTag">Todo el dispositivo</div>
  </div>

  <div class="progress-box">
    <div class="progress-bar-bg" onclick="seekClick(event)">
      <div class="progress-bar-fill" id="progressFill"></div>
    </div>
    <div class="time-labels">
      <span id="currentTime">00:00</span>
      <span id="totalTime">00:00</span>
    </div>
  </div>

  <div class="main-controls">
    <button class="btn btn-small" onclick="apiCall('/api/seek?sec=-10')" title="Retroceder 10s">⏪</button>
    <button class="btn btn-med" onclick="apiCall('/api/prev')" title="Canción anterior">⏮️</button>
    <button class="btn btn-large" id="playPauseBtn" onclick="apiCall('/api/toggle_pause')">▶</button>
    <button class="btn btn-med" onclick="apiCall('/api/next')" title="Siguiente canción (Crossfade)">⏭️</button>
    <button class="btn btn-small" onclick="apiCall('/api/seek?sec=10')" title="Adelantar 10s">⏩</button>
  </div>

  <div class="options-row">
    <button class="pill-btn" id="shuffleBtn" onclick="apiCall('/api/toggle_shuffle')">
      🔀 Aleatorio: <span id="shuffleState">OFF</span>
    </button>
    <button class="pill-btn" onclick="apiCall('/api/play_all')">
      ▶ Reproducir Todo
    </button>
  </div>

  <!-- Pestañas para elegir carpetas o canciones individuales -->
  <div class="tabs-nav">
    <div class="tab-item active" id="tabFolders" onclick="switchTab('folders')">📁 Por Carpetas</div>
    <div class="tab-item" id="tabTracks" onclick="switchTab('tracks')">🎵 Canciones Individuales</div>
  </div>

  <div class="search-box">
    <input type="text" class="search-input" id="searchInput" placeholder="Buscar carpeta o canción..." oninput="filterItems()">
  </div>

  <div class="items-list" id="itemsList">
    <!-- Renderizado dinámico -->
  </div>

  <script>
    let currentTab = 'folders';
    let foldersData = {};
    let tracksData = [];
    let isPlaying = false;

    function formatTime(s) {
      if (!s || isNaN(s)) return "00:00";
      const m = Math.floor(s / 60);
      const sec = Math.floor(s % 60);
      return (m < 10 ? "0" : "") + m + ":" + (sec < 10 ? "0" : "") + sec;
    }

    function apiCall(endpoint) {
      fetch(endpoint, { method: 'POST' }).then(() => updateStatus());
    }

    function switchTab(tab) {
      currentTab = tab;
      document.getElementById('tabFolders').classList.toggle('active', tab === 'folders');
      document.getElementById('tabTracks').classList.toggle('active', tab === 'tracks');
      document.getElementById('searchInput').value = '';
      renderList();
    }

    function filterItems() {
      renderList();
    }

    function playFolder(folderName) {
      fetch('/api/play_folder?folder=' + encodeURIComponent(folderName), { method: 'POST' })
        .then(() => updateStatus());
    }

    function playSingleTrack(trackId) {
      fetch('/api/play_track_id?id=' + trackId, { method: 'POST' })
        .then(() => updateStatus());
    }

    function renderList() {
      const container = document.getElementById('itemsList');
      const query = document.getElementById('searchInput').value.toLowerCase().trim();
      container.innerHTML = '';

      if (currentTab === 'folders') {
        const folderNames = Object.keys(foldersData);
        folderNames.forEach(f => {
          if (!query || f.toLowerCase().includes(query)) {
            const count = foldersData[f].length;
            const div = document.createElement('div');
            div.className = 'list-card';
            div.onclick = () => playFolder(f);
            div.innerHTML = `
              <div class="card-left">
                <div class="card-title">📁 ${f}</div>
                <div class="card-subtitle">${count} canciones encontradas</div>
              </div>
              <div class="card-badge">Reproducir</div>
            `;
            container.appendChild(div);
          }
        });
      } else {
        tracksData.forEach(t => {
          const title = t.title || t.filename;
          const artist = t.artist || t.folder;
          if (!query || title.toLowerCase().includes(query) || artist.toLowerCase().includes(query)) {
            const div = document.createElement('div');
            div.className = 'list-card';
            div.onclick = () => playSingleTrack(t.id);
            div.innerHTML = `
              <div class="card-left">
                <div class="card-title">🎵 ${title}</div>
                <div class="card-subtitle">${artist} &bull; ${t.folder}</div>
              </div>
              <div class="card-badge">▶</div>
            `;
            container.appendChild(div);
          }
        });
      }
    }

    function seekClick(event) {
      const rect = event.currentTarget.getBoundingClientRect();
      const clickX = event.clientX - rect.left;
      const pct = clickX / rect.width;
      fetch('/api/seek_pct?pct=' + pct, { method: 'POST' }).then(() => updateStatus());
    }

    function updateStatus() {
      fetch('/api/status')
        .then(r => r.json())
        .then(data => {
          document.getElementById('djStatus').innerText = data.status_msg;
          document.getElementById('statsTag').innerText = `${data.total_tracks} canciones detectadas`;

          const disc = document.getElementById('disc');
          const btn = document.getElementById('playPauseBtn');

          if (data.playing && !data.paused) {
            disc.classList.add('playing');
            btn.innerText = "⏸";
            isPlaying = true;
          } else {
            disc.classList.remove('playing');
            btn.innerText = "▶";
            isPlaying = false;
          }

          if (data.track) {
            document.getElementById('trackTitle').innerText = data.track.title || data.track.filename;
            document.getElementById('trackArtist').innerText = data.track.artist || "Artista desconocido";
          }
          document.getElementById('contextTag').innerText = `${data.context_name} (${data.queue_pos})`;

          const shuffleBtn = document.getElementById('shuffleBtn');
          const shuffleState = document.getElementById('shuffleState');
          if (data.shuffle) {
            shuffleBtn.classList.add('active');
            shuffleState.innerText = "ON";
          } else {
            shuffleBtn.classList.remove('active');
            shuffleState.innerText = "OFF";
          }

          const pos = data.pos || 0;
          const dur = data.dur || 0;
          const pct = dur > 0 ? Math.min(100, (pos / dur) * 100) : 0;
          document.getElementById('progressFill').style.width = pct + "%";
          document.getElementById('currentTime').innerText = formatTime(pos);
          document.getElementById('totalTime').innerText = formatTime(dur);
        })
        .catch(() => {});
    }

    // Cargar catálogo inicial
    fetch('/api/library')
      .then(r => r.json())
      .then(data => {
        foldersData = data.folders || {};
        tracksData = data.tracks || [];
        renderList();
      });

    setInterval(updateStatus, 600);
    updateStatus();
  </script>
</body>
</html>
"""

class DJLiviController:
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
        self.status_msg = "Escaneando dispositivo..."
        self.lock = threading.Lock()
        
        self.setup()

    def setup(self):
        self.all_tracks, self.folder_map = scan_all_device()
        self.mixer.start()
        
        if self.all_tracks:
            self.current_queue = list(self.all_tracks)
            self.queue_index = 0
            self.context_name = "Todo el dispositivo"
            self.start_playback(trigger_speech=True)
        else:
            self.status_msg = "No se encontraron canciones."

    def start_playback(self, trigger_speech=False):
        with self.lock:
            if not self.current_queue or self.queue_index >= len(self.current_queue):
                return
            first_track = self.current_queue[self.queue_index]

        if trigger_speech:
            script = self.commentator.generate_welcome_script(self.context_name, first_track)
            def intro_play():
                self.status_msg = f"🎙️ Livi: \"{script[:50]}...\""
                try:
                    speech = self.commentator.prepare_speech(script, "livi_intro.mp3")
                    self.mixer.play_track(first_track)
                    time.sleep(0.4)
                    self.mixer.play_voice_with_ducking(speech)
                except Exception:
                    self.mixer.play_track(first_track)
                self.status_msg = "🎵 Reproduciendo"
            threading.Thread(target=intro_play, daemon=True).start()
        else:
            self.mixer.play_track(first_track, crossfade_sec=3.5)
            self.status_msg = "🎵 Reproduciendo"

    def play_folder(self, folder_name):
        with self.lock:
            if folder_name not in self.folder_map:
                return
            tracks = list(self.folder_map[folder_name])
            if not tracks:
                return
            if self.shuffle_mode:
                random.shuffle(tracks)
            self.current_queue = tracks
            self.queue_index = 0
            self.context_name = f"Carpeta: {folder_name}"
            first_track = self.current_queue[0]

        script = self.commentator.generate_folder_switch_script(folder_name, first_track)
        def folder_play():
            self.status_msg = f"🎙️ Livi: \"{script[:50]}...\""
            try:
                speech = self.commentator.prepare_speech(script, "livi_folder.mp3")
                status = self.mixer.get_status()
                if status['playing']:
                    self.mixer.play_voice_with_ducking(speech)
                    self.mixer.play_track(first_track, crossfade_sec=3.5)
                else:
                    self.mixer.play_track(first_track)
                    time.sleep(0.4)
                    self.mixer.play_voice_with_ducking(speech)
            except Exception:
                self.mixer.play_track(first_track, crossfade_sec=3.5)
            self.status_msg = "🎵 Reproduciendo"
        threading.Thread(target=folder_play, daemon=True).start()

    def play_single_track(self, track_id):
        with self.lock:
            target = None
            for idx, t in enumerate(self.all_tracks):
                if t['id'] == track_id:
                    target = t
                    break
            if not target:
                return
            # Se coloca la lista completa a partir de esa canción
            self.current_queue = list(self.all_tracks)
            self.queue_index = track_id
            self.context_name = f"Pista: {target.get('title') or target.get('filename')}"
        
        self.mixer.play_track(target, crossfade_sec=3.0)
        self.status_msg = f"🎵 {target.get('title') or target.get('filename')}"

    def play_all(self):
        with self.lock:
            tracks = list(self.all_tracks)
            if self.shuffle_mode:
                random.shuffle(tracks)
            self.current_queue = tracks
            self.queue_index = 0
            self.context_name = "Todo el dispositivo"
        self.start_playback(trigger_speech=False)

    def toggle_shuffle(self):
        with self.lock:
            self.shuffle_mode = not self.shuffle_mode
            if self.shuffle_mode and self.current_queue:
                current_t = self.current_queue[self.queue_index] if self.queue_index < len(self.current_queue) else None
                rest = [t for t in self.current_queue if t != current_t]
                random.shuffle(rest)
                self.current_queue = ([current_t] if current_t else []) + rest
                self.queue_index = 0
        self.status_msg = f"🔀 Aleatorio {'ACTIVADO' if self.shuffle_mode else 'DESACTIVADO'}"

    def advance_track(self):
        with self.lock:
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

        # Crossfade duro continuo
        self.mixer.play_track(next_track, crossfade_sec=4.5)
        self.status_msg = f"🎵 {next_track.get('title') or next_track.get('filename')}"

    def previous_track(self):
        status = self.mixer.get_status()
        pos = status.get('pos', 0.0)
        if pos > 3.0:
            self.mixer.seek(-99999)
            self.status_msg = "⏮️ Reiniciando pista"
            return

        with self.lock:
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

    def seek(self, sec):
        self.mixer.seek(sec)
        sign = "+" if sec > 0 else ""
        self.status_msg = f"⏩ {sign}{sec}s" if sec > 0 else f"⏪ {sec}s"

    def seek_pct(self, pct):
        status = self.mixer.get_status()
        dur = status.get('dur', 0.0)
        if dur > 0:
            target_pos = max(0.0, min(dur, dur * float(pct)))
            current_pos = status.get('pos', 0.0)
            diff = target_pos - current_pos
            self.mixer.seek(diff)

    def get_info(self):
        status = self.mixer.get_status()
        q_pos = f"{self.queue_index + 1}/{len(self.current_queue)}" if self.current_queue else "0/0"
        return {
            'playing': status.get('playing', False),
            'paused': status.get('paused', False),
            'pos': status.get('pos', 0.0),
            'dur': status.get('dur', 0.0),
            'track': status.get('track'),
            'total_tracks': len(self.all_tracks),
            'context_name': self.context_name,
            'queue_pos': q_pos,
            'shuffle': self.shuffle_mode,
            'status_msg': self.status_msg,
            'offline': self.force_offline
        }

controller = None

class DJRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        elif parsed.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(controller.get_info()).encode('utf-8'))
        elif parsed.path == "/api/library":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                'folders': controller.folder_map,
                'tracks': controller.all_tracks
            }
            self.wfile.write(json.dumps(data).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/api/toggle_pause":
            controller.mixer.toggle_pause()
        elif parsed.path == "/api/next":
            controller.advance_track()
        elif parsed.path == "/api/prev":
            controller.previous_track()
        elif parsed.path == "/api/toggle_shuffle":
            controller.toggle_shuffle()
        elif parsed.path == "/api/play_all":
            controller.play_all()
        elif parsed.path == "/api/seek":
            sec = float(qs.get('sec', [10])[0])
            controller.seek(sec)
        elif parsed.path == "/api/seek_pct":
            pct = float(qs.get('pct', [0])[0])
            controller.seek_pct(pct)
        elif parsed.path == "/api/play_folder":
            f_name = qs.get('folder', [None])[0]
            if f_name:
                controller.play_folder(f_name)
        elif parsed.path == "/api/play_track_id":
            t_id = int(qs.get('id', [-1])[0])
            if t_id >= 0:
                controller.play_single_track(t_id)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"success": true}')

def run_server(port=5000, force_offline=False):
    global controller
    controller = DJLiviController(force_offline=force_offline)
    
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, DJRequestHandler)
    print(f"\n========================================================")
    print(f"🎧 OMNIPLAYER DJ - SERVIDOR WEB INICIADO")
    print(f"   ➔ Canciones detectadas en el dispositivo: {len(controller.all_tracks)}")
    print(f"   ➔ Carpetas detectadas: {len(controller.folder_map)}")
    print(f"   ➔ Abre en tu navegador:")
    print(f"      Local:  http://localhost:{port}")
    print(f"========================================================\n")

    # Detección para crossfade automático continuo
    def auto_dj_loop():
        crossfade_done = False
        while True:
            time.sleep(0.5)
            status = controller.mixer.get_status()
            dur = status.get('dur', 0.0)
            pos = status.get('pos', 0.0)
            if status['playing'] and dur > 8 and (dur - pos) <= 4.5:
                if not crossfade_done:
                    crossfade_done = True
                    controller.advance_track()
            else:
                crossfade_done = False

    threading.Thread(target=auto_dj_loop, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando servidor...")
        controller.mixer.stop()

if __name__ == "__main__":
    offline_mode = "--offline" in sys.argv
    port = 5000
    for arg in sys.argv:
        if arg.startswith("--port="):
            port = int(arg.split("=")[1])
    run_server(port=port, force_offline=offline_mode)
