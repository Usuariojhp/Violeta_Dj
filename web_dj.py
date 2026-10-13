#!/usr/bin/env python3
"""
web_dj.py - Reproductor Web con Crossfade Real para Móvil y PC.
Diseño minimalista con iconos SVG de alta definición.
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
from dj_brain import get_brain
from track_intel import enrich_tracks
from set_engine import build_set, next_mood, normalize_mood, DEFAULT_MOOD
from voice_command import get_voice

HTML_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
  <title>OmniPlayer - Crossfade Studio</title>
  <style>
    :root {
      --bg: #090a0f;
      --surface: #12141c;
      --surface-elevated: #181b26;
      --border: #232738;
      --border-focus: #3b4259;
      --accent: #1db954;
      --accent-dim: rgba(29, 185, 84, 0.12);
      --text-main: #f0f2f8;
      --text-muted: #8b92a5;
      --text-subtle: #565d73;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body {
      background: var(--bg);
      color: var(--text-main);
      display: flex;
      flex-direction: column;
      min-height: 100vh;
      padding: 16px;
      -webkit-tap-highlight-color: transparent;
      max-width: 640px;
      margin: 0 auto;
    }

    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 18px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 1.2px;
      text-transform: uppercase;
      color: var(--text-main);
    }
    .brand-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 8px var(--accent);
    }
    .badge {
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.8px;
      padding: 4px 9px;
      border-radius: 6px;
      background: var(--surface-elevated);
      color: var(--accent);
      border: 1px solid var(--border);
      text-transform: uppercase;
    }

    /* Centro del reproductor: Disco / Tornamesa */
    .player-visual {
      display: flex;
      justify-content: center;
      align-items: center;
      margin: 16px 0 22px 0;
    }
    .turntable {
      position: relative;
      width: 190px;
      height: 190px;
      border-radius: 50%;
      background: radial-gradient(circle, #2a2d3d 12%, #0d0e14 28%, #1c1f2b 45%, #08090d 68%, #141722 92%);
      border: 1px solid var(--border);
      box-shadow: 0 16px 36px rgba(0, 0, 0, 0.7), inset 0 0 20px rgba(0, 0, 0, 0.9);
      display: flex;
      justify-content: center;
      align-items: center;
      animation: rotate-disc 10s linear infinite;
      animation-play-state: paused;
    }
    .turntable.playing {
      animation-play-state: running;
    }
    .disc-groove {
      position: absolute;
      width: 135px;
      height: 135px;
      border-radius: 50%;
      border: 1px dashed rgba(255, 255, 255, 0.05);
    }
    .disc-center {
      position: relative;
      width: 54px;
      height: 54px;
      border-radius: 50%;
      background: var(--accent);
      display: flex;
      justify-content: center;
      align-items: center;
      box-shadow: inset 0 0 10px rgba(0,0,0,0.5);
    }
    .disc-pin {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--bg);
      border: 2px solid #fff;
    }
    @keyframes rotate-disc {
      100% { transform: rotate(360deg); }
    }

    /* Metadatos de la cancion */
    .track-meta {
      text-align: center;
      margin-bottom: 18px;
    }
    .track-title {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.2px;
      color: var(--text-main);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      margin-bottom: 5px;
      padding: 0 10px;
    }
    .track-artist {
      font-size: 13px;
      color: var(--text-muted);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      margin-bottom: 6px;
    }
    .context-tag {
      display: inline-block;
      font-size: 11px;
      font-weight: 600;
      color: var(--accent);
      background: var(--accent-dim);
      padding: 3px 10px;
      border-radius: 12px;
    }

    /* Barra de progreso interactiva */
    .progress-wrapper {
      margin-bottom: 20px;
    }
    .progress-bar-bg {
      width: 100%;
      height: 5px;
      background: var(--surface-elevated);
      border-radius: 3px;
      overflow: hidden;
      cursor: pointer;
    }
    .progress-bar-fill {
      width: 0%;
      height: 100%;
      background: var(--accent);
      border-radius: 3px;
      transition: width 0.2s linear;
    }
    .time-labels {
      display: flex;
      justify-content: space-between;
      font-size: 11px;
      font-variant-numeric: tabular-nums;
      color: var(--text-subtle);
      margin-top: 6px;
    }

    /* Controles de reproduccion */
    .playback-controls {
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 14px;
      margin-bottom: 20px;
    }
    .btn-ctrl {
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text-main);
      border-radius: 50%;
      display: flex;
      justify-content: center;
      align-items: center;
      cursor: pointer;
      transition: transform 0.1s ease, border-color 0.15s, background 0.15s;
    }
    .btn-ctrl:active {
      transform: scale(0.92);
      border-color: var(--accent);
    }
    .btn-sm { width: 42px; height: 42px; }
    .btn-md { width: 50px; height: 50px; }
    .btn-play {
      width: 64px;
      height: 64px;
      background: var(--accent);
      color: #000;
      border: none;
      box-shadow: 0 4px 20px rgba(29, 185, 84, 0.35);
    }
    .btn-play:active {
      background: #17a349;
    }
    .icon {
      width: 18px;
      height: 18px;
      fill: currentColor;
    }
    .icon-lg {
      width: 22px;
      height: 22px;
      fill: currentColor;
    }

    /* Fila de acciones */
    .action-row {
      display: flex;
      justify-content: center;
      gap: 10px;
      margin-bottom: 22px;
    }
    .btn-pill {
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text-muted);
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      padding: 8px 16px;
      border-radius: 20px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: 0.15s;
    }
    .btn-pill.active {
      background: var(--accent-dim);
      border-color: var(--accent);
      color: var(--accent);
      font-weight: 700;
    }
    .btn-pill:active {
      transform: scale(0.96);
    }

    /* Pestañas de navegacion */
    .tabs-nav {
      display: flex;
      border-bottom: 1px solid var(--border);
      margin-bottom: 12px;
    }
    .tab-btn {
      flex: 1;
      text-align: center;
      padding: 11px 0;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: color 0.15s, border-color 0.15s;
    }
    .tab-btn.active {
      color: var(--accent);
      border-bottom-color: var(--accent);
    }

    /* Buscador */
    .search-wrap {
      margin-bottom: 12px;
    }
    .search-input {
      width: 100%;
      padding: 10px 14px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text-main);
      font-size: 13px;
      outline: none;
      transition: border-color 0.15s;
    }
    .search-input:focus {
      border-color: var(--accent);
    }
    .search-input::placeholder {
      color: var(--text-subtle);
    }

    /* Listas de carpetas y pistas */
    .catalog-list {
      max-height: 270px;
      overflow-y: auto;
      padding-right: 4px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .catalog-item {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      cursor: pointer;
      transition: background 0.12s, border-color 0.12s;
    }
    .catalog-item:hover {
      border-color: var(--border-focus);
    }
    .catalog-item:active {
      background: var(--surface-elevated);
      transform: scale(0.99);
    }
    .item-meta {
      flex: 1;
      min-width: 0;
      padding-right: 12px;
    }
    .item-title {
      font-size: 13px;
      font-weight: 600;
      color: var(--text-main);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .item-sub {
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 3px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .item-action {
      font-size: 11px;
      font-weight: 600;
      color: var(--accent);
      background: var(--accent-dim);
      padding: 4px 8px;
      border-radius: 6px;
      white-space: nowrap;
    }

    .catalog-list::-webkit-scrollbar { width: 4px; }
    .catalog-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

    /* Estado secundario discreto */
    .status-note {
      text-align: center;
      font-size: 11px;
      color: var(--text-subtle);
      margin-top: 14px;
      min-height: 16px;
    }

    /* Panel Livi (chat + moods) */
    .livi-panel {
      margin-top: 18px;
      padding: 14px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
    }
    .livi-title {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-muted);
      margin-bottom: 10px;
    }
    .livi-title button {
      background: var(--accent-dim);
      color: var(--accent);
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 5px 12px;
      font-size: 11px;
      cursor: pointer;
    }
    .mood-row { display: flex; gap: 6px; margin-bottom: 10px; }
    .mood-row button {
      flex: 1;
      padding: 8px 0;
      background: var(--surface-elevated);
      color: var(--text-muted);
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 11px;
      cursor: pointer;
    }
    .mood-row button:hover { color: var(--accent); border-color: var(--accent); }
    #liviChat {
      max-height: 130px;
      overflow-y: auto;
      font-size: 12px;
      line-height: 1.5;
      margin-bottom: 10px;
    }
    .chat-msg { padding: 4px 8px; border-radius: 8px; margin-bottom: 4px; }
    .chat-user { color: var(--text-muted); background: var(--bg); }
    .chat-livi { color: var(--text-main); background: var(--accent-dim); }
    .livi-input-row { display: flex; gap: 6px; }
    #liviInput {
      flex: 1;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 9px 12px;
      color: var(--text-main);
      font-size: 13px;
    }
    #liviInput:focus { outline: none; border-color: var(--border-focus); }
    .livi-input-row button {
      background: var(--accent);
      color: #08130c;
      border: none;
      border-radius: 8px;
      padding: 0 16px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <div class="brand-dot"></div>
      <span>OmniPlayer</span>
    </div>
    <div class="badge" id="statsBadge">Cargando...</div>
  </header>

  <div class="player-visual">
    <div class="turntable" id="turntable">
      <div class="disc-groove"></div>
      <div class="disc-center">
        <div class="disc-pin"></div>
      </div>
    </div>
  </div>

  <div class="track-meta">
    <div class="track-title" id="trackTitle">Selecciona una pista o carpeta</div>
    <div class="track-artist" id="trackArtist">Listo</div>
    <div class="context-tag" id="contextTag">Todo el dispositivo</div>
  </div>

  <div class="progress-wrapper">
    <div class="progress-bar-bg" onclick="seekClick(event)">
      <div class="progress-bar-fill" id="progressFill"></div>
    </div>
    <div class="time-labels">
      <span id="currentTime">00:00</span>
      <span id="totalTime">00:00</span>
    </div>
  </div>

  <div class="playback-controls">
    <!-- Retroceder 10s -->
    <button class="btn-ctrl btn-sm" onclick="apiCall('/api/seek?sec=-10')" title="Retroceder 10 segundos">
      <svg class="icon" viewBox="0 0 24 24"><path d="M11 16.07V7.93c0-.81-.91-1.28-1.57-.81L3.7 11.19c-.58.41-.58 1.28 0 1.69l5.73 4.07c.66.47 1.57 0 1.57-.88zm8.5-8.14v8.14c0 .88-.91 1.35-1.57.88l-5.73-4.07c-.58-.41-.58-1.28 0-1.69l5.73-4.07c.66-.47 1.57 0 1.57.81z"/></svg>
    </button>
    <!-- Pista anterior -->
    <button class="btn-ctrl btn-md" onclick="apiCall('/api/prev')" title="Pista anterior">
      <svg class="icon" viewBox="0 0 24 24"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg>
    </button>
    <!-- Play / Pausa -->
    <button class="btn-ctrl btn-play" id="playPauseBtn" onclick="apiCall('/api/toggle_pause')" title="Pausa / Reanudar">
      <svg class="icon-lg" id="playPauseIcon" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
    </button>
    <!-- Siguiente pista con crossfade -->
    <button class="btn-ctrl btn-md" onclick="apiCall('/api/next')" title="Siguiente pista (Crossfade)">
      <svg class="icon" viewBox="0 0 24 24"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
    </button>
    <!-- Adelantar 10s -->
    <button class="btn-ctrl btn-sm" onclick="apiCall('/api/seek?sec=10')" title="Adelantar 10 segundos">
      <svg class="icon" viewBox="0 0 24 24"><path d="M4.5 16.07V7.93c0-.81.91-1.28 1.57-.81l5.73 4.07c.58.41.58 1.28 0 1.69l-5.73 4.07c-.66.47-1.57 0-1.57-.88zm8.5 0V7.93c0-.81.91-1.28 1.57-.81l5.73 4.07c.58.41.58 1.28 0 1.69l-5.73 4.07c-.66.47-1.57 0-1.57-.88z"/></svg>
    </button>
  </div>

  <div class="action-row">
    <button class="btn-pill" id="shuffleBtn" onclick="apiCall('/api/toggle_shuffle')">
      <span>Aleatorio</span>
      <span id="shuffleState">OFF</span>
    </button>
    <button class="btn-pill" onclick="apiCall('/api/play_all')">
      <span>Todo el dispositivo</span>
    </button>
  </div>

  <div class="tabs-nav">
    <div class="tab-btn active" id="tabFolders" onclick="switchTab('folders')">Carpetas</div>
    <div class="tab-btn" id="tabTracks" onclick="switchTab('tracks')">Canciones</div>
  </div>

  <div class="search-wrap">
    <input type="text" class="search-input" id="searchInput" placeholder="Filtrar..." oninput="filterItems()">
  </div>

  <div class="catalog-list" id="itemsList"></div>

  <div class="status-note" id="statusNote">Crossfade continuo activo</div>

  <div class="livi-panel">
    <div class="livi-title">
      <span>Livi DJ <span id="setInfo"></span></span>
      <button onclick="liviListen()">Hablar</button>
    </div>
    <div class="mood-row">
      <button onclick="liviMood('chill')">Chill</button>
      <button onclick="liviMood('energico')">Energico</button>
      <button onclick="liviMood('fiesta')">Fiesta</button>
      <button onclick="liviMood('enfoque')">Enfoque</button>
    </div>
    <div id="liviChat"></div>
    <div class="livi-input-row">
      <input type="text" id="liviInput" placeholder="Pedile algo a Livi: 'pone musica para enfocar'">
      <button onclick="askLivi()">Enviar</button>
    </div>
  </div>

  <script>
    let currentTab = 'folders';
    let foldersData = {};
    let tracksData = [];

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
            div.className = 'catalog-item';
            div.onclick = () => playFolder(f);
            div.innerHTML = `
              <div class="item-meta">
                <div class="item-title">${f}</div>
                <div class="item-sub">${count} pistas</div>
              </div>
              <div class="item-action">Reproducir</div>
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
            div.className = 'catalog-item';
            div.onclick = () => playSingleTrack(t.id);
            div.innerHTML = `
              <div class="item-meta">
                <div class="item-title">${title}</div>
                <div class="item-sub">${artist} &bull; ${t.folder}</div>
              </div>
              <div class="item-action">Iniciar</div>
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
          document.getElementById('statsBadge').innerText = `${data.total_tracks} pistas`;
          document.getElementById('statusNote').innerText = data.status_msg || "Crossfade continuo activo";

          const turntable = document.getElementById('turntable');
          const playIcon = document.getElementById('playPauseIcon');

          if (data.playing && !data.paused) {
            turntable.classList.add('playing');
            playIcon.innerHTML = '<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>';
          } else {
            turntable.classList.remove('playing');
            playIcon.innerHTML = '<path d="M8 5v14l11-7z"/>';
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

    fetch('/api/library')
      .then(r => r.json())
      .then(data => {
        foldersData = data.folders || {};
        tracksData = data.tracks || [];
        renderList();
      });

    setInterval(updateStatus, 600);
    updateStatus();

    function askLivi() {
      const input = document.getElementById('liviInput');
      const text = input.value.trim();
      if (!text) return;
      input.value = '';
      appendChat('user', text);
      fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request: text })
      })
        .then(r => r.json())
        .then(data => {
          if (data && data.reply) appendChat('livi', data.reply);
          if (data && data.set_info) {
            const s = data.set_info;
            document.getElementById('setInfo').innerText =
              'Set ' + (s.mood_label || s.mood) + ' · ' + s.track_count +
              ' pistas · ' + s.minutes + ' min';
          }
          updateStatus();
        })
        .catch(() => appendChat('livi', 'No pude procesar el pedido.'));
    }

    function liviMood(mood) {
      fetch('/api/mood', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mood: mood })
      })
        .then(r => r.json())
        .then(data => {
          if (data && data.reply) appendChat('livi', data.reply);
        });
    }

    function liviListen() {
      fetch('/api/voice_listen', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
          if (data.heard) appendChat('user', '(voz) ' + data.heard);
          if (data.reply) appendChat('livi', data.reply);
          if (data.error || data.reason) {
            appendChat('livi', 'Voz no disponible: ' +
              (data.reason || data.error));
          }
        });
    }

    function appendChat(who, text) {
      const box = document.getElementById('liviChat');
      const div = document.createElement('div');
      div.className = 'chat-msg chat-' + who;
      div.innerText = (who === 'user' ? 'Vos: ' : 'Livi: ') + text;
      box.appendChild(div);
      box.scrollTop = box.scrollHeight;
    }

    document.getElementById('liviInput').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') askLivi();
    });
  </script>
</body>
</html>
"""

class DJLiviController:
    def __init__(self, force_offline=False, enrich_audio=False):
        self.force_offline = force_offline
        self.enrich_audio = enrich_audio
        self.mixer = DJMixer()
        self.commentator = DJCommentator(force_offline=force_offline)
        self.brain = get_brain()
        self.voice = get_voice()
        self.all_tracks = []
        self.folder_map = {}
        
        self.current_queue = []
        self.queue_index = 0
        self.history = []
        self.shuffle_mode = False
        self.context_name = "Todo el dispositivo"
        self.status_msg = "Escaneando dispositivo..."
        self.mood = None
        self.auto_dj = True
        self.set_info = None
        self.chat_log = []
        self.lock = threading.Lock()
        
        self.setup()

    def setup(self):
        self.all_tracks, self.folder_map = scan_all_device()
        if self.all_tracks:
            try:
                self.all_tracks, report = enrich_tracks(
                    self.all_tracks, use_audio=self.enrich_audio)
                self.status_msg = ("Analizadas %d pistas" % report["enriched"])
            except Exception as exc:
                print("[intel] no se pudo enriquecer: %s" % exc)
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
                self.status_msg = f"[Livi] {script[:55]}..."
                try:
                    speech = self.commentator.prepare_speech(script, "livi_intro.mp3")
                    self.mixer.play_track(first_track)
                    time.sleep(0.4)
                    self.mixer.play_voice_with_ducking(speech)
                except Exception:
                    self.mixer.play_track(first_track)
                self.status_msg = "Reproduciendo"
            threading.Thread(target=intro_play, daemon=True).start()
        else:
            self.mixer.play_track(first_track, crossfade_sec=3.5)
            self.status_msg = "Reproduciendo"

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
            self.status_msg = f"[Livi] {script[:55]}..."
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
            self.status_msg = "Reproduciendo"
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
            self.current_queue = list(self.all_tracks)
            self.queue_index = track_id
            self.context_name = f"Pista: {target.get('title') or target.get('filename')}"
        
        self.mixer.play_track(target, crossfade_sec=3.0)
        self.status_msg = f"{target.get('title') or target.get('filename')}"

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
        self.status_msg = f"Aleatorio {'ACTIVADO' if self.shuffle_mode else 'DESACTIVADO'}"

    def advance_track(self):
        with self.lock:
            if not self.current_queue:
                return
            if 0 <= self.queue_index < len(self.current_queue):
                self.history.append(self.current_queue[self.queue_index])

            self.queue_index += 1
            if self.queue_index >= len(self.current_queue):
                if self.auto_dj and self.mood:
                    # Auto-DJ: rearma el set cuando se acaba la cola
                    self.lock.release()
                    try:
                        self.build_auto_queue(
                            minutes=(self.set_info or {}).get('minutes') or 45,
                            mood=self.mood, speech=False)
                    except Exception as exc:
                        print("[auto_dj] no se pudo rearmar: %s" % exc)
                        self.lock.acquire()
                        self.current_queue = list(self.all_tracks)
                        self.queue_index = 0
                    finally:
                        pass
                    return
                if self.shuffle_mode:
                    random.shuffle(self.current_queue)
                self.queue_index = 0
            next_track = self.current_queue[self.queue_index]

        self.mixer.play_track(next_track, crossfade_sec=4.5)
        self.status_msg = f"{next_track.get('title') or next_track.get('filename')}"

    def previous_track(self):
        status = self.mixer.get_status()
        pos = status.get('pos', 0.0)
        if pos > 3.0:
            self.mixer.seek(-99999)
            self.status_msg = "Reiniciando pista"
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
        self.status_msg = f"{prev_track.get('title') or prev_track.get('filename')}"

    def seek(self, sec):
        self.mixer.seek(sec)
        sign = "+" if sec > 0 else ""
        self.status_msg = f"Posicion {sign}{sec}s" if sec > 0 else f"Posicion {sec}s"

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
            'offline': self.force_offline,
            'mood': self.mood,
            'auto_dj': self.auto_dj,
            'set_info': self.set_info,
            'brain': self.brain.status_info(),
            'chat_log': self.chat_log[-10:],
        }

    # ------------------------------------------------------- Auto-DJ / Livi
    def library_summary(self):
        if not self.folder_map:
            return "sin carpetas"
        parts = ["%s (%d)" % (name, len(tr))
                 for name, tr in list(self.folder_map.items())[:12]]
        return "; ".join(parts)

    def build_auto_queue(self, minutes=45, mood=None, terms=None,
                         speech=True, seed=None):
        """Arma la cola con el motor de sets y la pone a sonar."""
        mood = normalize_mood(mood) or normalize_mood(self.mood) or DEFAULT_MOOD
        queue, info = build_set(self.all_tracks, minutes=minutes,
                                mood=mood, terms=terms, seed=seed)
        if not queue:
            return {'success': False, 'error': info.get('error'),
                    'reply': 'No encontre nada para armar el set.'}
        self.mood = mood
        self.set_info = info
        with self.lock:
            self.current_queue = queue
            self.queue_index = 0
            self.history = []
        self.context_name = "Set %s (%d pistas)" % (
            info.get('mood_label', mood), info['track_count'])
        self.start_playback(trigger_speech=bool(speech))
        return {'success': True, 'set_info': info}

    def set_mood(self, mood):
        """Cambia el mood y rearma la cola manteniendo la duracion actual."""
        new_mood = normalize_mood(mood)
        if not new_mood:
            return {'success': False, 'error': 'mood_invalido',
                    'reply': 'No conozco ese estado.'}
        minutes = (self.set_info or {}).get('minutes') or 45
        result = self.build_auto_queue(minutes=minutes, mood=new_mood)
        self.status_msg = "Mood: %s" % new_mood
        return result

    def say(self, text):
        """Hace que Livi diga algo por la mezcla (ducking)."""
        text = (text or "").strip()
        if not text:
            return {'success': False, 'error': 'texto_vacio'}
        try:
            speech = self.commentator.prepare_speech(text, "livi_say.mp3")
        except Exception as exc:
            return {'success': False, 'error': str(exc)}
        status = self.mixer.get_status()
        if status.get('playing'):
            self.mixer.play_voice_with_ducking(speech)
        else:
            self.mixer.play_track(self.mixer.get_status().get('track')
                                  or self.current_queue[0])
            time.sleep(0.3)
            self.mixer.play_voice_with_ducking(speech)
        with self.lock:
            self.chat_log.append({'from': 'livi', 'text': text})
        return {'success': True}

    def ask(self, text):
        """Peticion en lenguaje natural: 'pone algo tranqui para estudiar'."""
        text = (text or "").strip()
        if not text:
            return {'success': False, 'error': 'texto_vacio'}
        reply = None
        if not self.brain.enabled or self.force_offline:
            data = normalize_mood(text) and {
                'action': 'play_mood',
                'mood': normalize_mood(text),
                'query': None, 'minutes': None,
                'reply': 'Modo %s activado.' % normalize_mood(text)}
        else:
            summary = self.library_summary()
            try:
                data = self.brain.parse_request(text, summary)
            except Exception as exc:
                print("[brain] error: %s" % exc)
                data = None
        if not data:
            data = {'action': 'chat', 'reply': None}

        action = data.get('action', 'chat')
        result = {'success': True, 'action': action}
        reply = data.get('reply')

        if action == 'play_mood' or (action == 'unknown' and normalize_mood(text)):
            mood = normalize_mood(data.get('mood')) or normalize_mood(text) or DEFAULT_MOOD
            minutes = data.get('minutes') or 45
            res = self.build_auto_queue(minutes=minutes, mood=mood,
                                        terms=data.get('query'), speech=False)
            result.update(res)
            reply = reply or "Armando una sesion de %d minutos." % minutes
            self.say(reply)
        elif action == 'play_folder':
            folder = data.get('query')
            if folder and folder in self.folder_map:
                self.play_folder(folder)
            else:
                result.update({'success': False, 'reply':
                               'No encontre esa carpeta.'})
                return result
        elif action == 'skip':
            self.advance_track()
        elif action == 'prev':
            self.previous_track()
        elif action == 'pause':
            self.mixer.toggle_pause()
        elif action == 'resume':
            self.mixer.toggle_pause()
        elif action == 'volume_up':
            self.mixer.set_volume(90)
        elif action == 'volume_down':
            self.mixer.set_volume(30)
        else:
            status = self.get_info()
            reply = self.brain.chat_reply(text, status) or \
                "No te entendi bien, pero seguimos sonando."

        reply = reply or "Listo."
        with self.lock:
            self.chat_log.append({'from': 'user', 'text': text})
            self.chat_log.append({'from': 'livi', 'text': reply})
            self.chat_log = self.chat_log[-20:]
        result['reply'] = reply
        return result

    def listen(self):
        """Escucha del microfono y ejecuta lo que se pida."""
        if not self.voice.enabled or self.force_offline:
            return {'success': False, 'reason': self.voice.status().get('reason')}
        try:
            text = self.voice.listen_and_transcribe()
        except Exception as exc:
            return {'success': False, 'error': str(exc)}
        if not text:
            return {'success': False, 'error': 'no_escuche_nada'}
        result = self.ask(text)
        result['heard'] = text
        return result

    def queue_snapshot(self):
        with self.lock:
            items = [{'title': t.get('title') or t.get('filename'),
                      'artist': t.get('artist') or t.get('folder'),
                      'energy': t.get('energy')} for t in self.current_queue]
        return {
            'index': self.queue_index,
            'total': len(items),
            'context': self.context_name,
            'mood': self.mood,
            'set_info': self.set_info,
            'items': items[:50],
        }

controller = None

class DJRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _json(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        elif parsed.path == "/api/status":
            self._json(controller.get_info())
        elif parsed.path == "/api/library":
            data = {
                'folders': controller.folder_map,
                'tracks': controller.all_tracks
            }
            self._json(data)
        elif parsed.path == "/api/queue":
            self._json(controller.queue_snapshot())
        elif parsed.path == "/api/brain":
            self._json(controller.brain.status_info())
        elif parsed.path == "/api/voice_status":
            self._json(controller.voice.status())
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
        elif parsed.path == "/api/ask":
            data = self._read_body()
            self._json(controller.ask(data.get('request') or qs.get('q', [''])[0]))
            return
        elif parsed.path == "/api/mood":
            data = self._read_body()
            self._json(controller.set_mood(data.get('mood')))
            return
        elif parsed.path == "/api/enqueue":
            data = self._read_body()
            self._json(controller.build_auto_queue(
                minutes=float(data.get('minutes') or 45),
                mood=data.get('mood'),
                terms=data.get('terms') or data.get('query')))
            return
        elif parsed.path == "/api/say":
            data = self._read_body()
            self._json(controller.say(data.get('text')))
            return
        elif parsed.path == "/api/voice_listen":
            self._json(controller.listen())
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"success": true}')

def run_server(port=5000, force_offline=False, enrich_audio=False):
    global controller
    controller = DJLiviController(force_offline=force_offline,
                                  enrich_audio=enrich_audio)
    
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, DJRequestHandler)
    print(f"\n========================================================")
    print(f"OMNIPLAYER STUDIO - SERVIDOR WEB INICIADO")
    print(f"   Canciones detectadas: {len(controller.all_tracks)}")
    print(f"   Carpetas detectadas:  {len(controller.folder_map)}")
    print(f"   Cerebro Livi: {controller.brain.status_info()}")
    print(f"   Voz: {controller.voice.status()}")
    print(f"   URL: http://localhost:{port}")
    print(f"========================================================\n")

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
    enrich_audio = "--enrich-audio" in sys.argv
    port = 5000
    for arg in sys.argv:
        if arg.startswith("--port="):
            port = int(arg.split("=")[1])
    run_server(port=port, force_offline=offline_mode, enrich_audio=enrich_audio)
