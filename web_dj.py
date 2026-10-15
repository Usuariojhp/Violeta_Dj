#!/usr/bin/env python3
"""
web_dj.py - Reproductor Web con Crossfade Real para Móvil y PC.
Diseño: glassmorphism oscuro con acentos degradados, vinilo girando con
caratula real, ecualizador animado y micro-interacciones.
Detecta canciones de todo el dispositivo, favoritos, volumen maestro,
crossfade configurable, busqueda con resaltado, persistencia y reanudacion.
"""
import os
import sys
import json
import time
import random
import hashlib
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

from music_scanner import scan_all_device
from dj_commentator import DJCommentator
from dj_mixer import DJMixer
from dj_state import DjState
from pwa_assets import ensure_pwa_assets
from dj_brain import get_brain
from set_engine import build_set, next_mood, normalize_mood, DEFAULT_MOOD
from track_intel import enrich_tracks
from voice_command import get_voice

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COVERS_DIR = os.path.join(SCRIPT_DIR, 'covers')
LYRICS_DIR = os.path.join(SCRIPT_DIR, 'lyrics')
CROSSFADE_OPTIONS = [0, 3.0, 4.5, 6.0, 8.0]

MANIFEST = {
    "name": "Violeta - Crossfade Studio",
    "short_name": "Violeta",
    "description": "Reproductor con crossfade, IA y DJ automático",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "background_color": "#0a0c14",
    "theme_color": "#0a0c14",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
    ],
}

PWA_ICON_DIR = os.path.join(SCRIPT_DIR, 'pwa_icons')
ensure_pwa_assets(SCRIPT_DIR)


def _lyrics_for(artist, title):
    """Busca y cachea letras (LRC sincronizado o texto plano) con syncedlyrics."""
    if not title:
        return None
    term = f"{artist} - {title}" if artist else title
    key = hashlib.md5(term.encode('utf-8', errors='ignore')).hexdigest()[:16]
    try:
        if not os.path.isdir(LYRICS_DIR):
            os.makedirs(LYRICS_DIR, exist_ok=True)
        cache_path = os.path.join(LYRICS_DIR, key + '.json')
        if os.path.exists(cache_path):
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        cache_path = None

    data = None
    try:
        import syncedlyrics
        lrc = syncedlyrics.search(term, synced_only=True)
        if lrc:
            data = {'synced': True, 'lyrics': lrc}
        else:
            plain = syncedlyrics.search(term, plain_only=True)
            data = {'synced': False, 'lyrics': plain or None}
    except Exception:
        data = None

    if data and data.get('lyrics'):
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass
    return data

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
  <title>Violeta - Crossfade Studio</title>
  <link rel="manifest" href="/manifest.json">
  <meta name="theme-color" content="#0a0c14">
  <link rel="icon" type="image/png" href="/icon-192.png">
  <link rel="apple-touch-icon" href="/icon-192.png">
  <style>
    :root {
      --bg: #07080d;
      --surface-glass: rgba(18, 20, 28, 0.72);
      --surface-solid: #12141c;
      --surface-elevated: #181b26;
      --border-glass: rgba(255, 255, 255, 0.08);
      --accent: #1db954;
      --accent-2: #00d4ff;
      --accent-grad: linear-gradient(135deg, #1db954, #00d4ff);
      --accent-dim: rgba(29, 185, 84, 0.12);
      --text-main: #f0f2f8;
      --text-muted: #8b92a5;
      --text-subtle: #565d73;
      --fav: #f5b301;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif; }

    body {
      background:
        radial-gradient(1100px 600px at 15% -10%, rgba(29, 185, 84, 0.10), transparent 60%),
        radial-gradient(900px 520px at 115% 15%, rgba(0, 212, 255, 0.07), transparent 60%),
        radial-gradient(800px 600px at 50% 115%, rgba(29, 185, 84, 0.05), transparent 60%),
        var(--bg);
      background-attachment: fixed;
      color: var(--text-main);
      display: flex;
      flex-direction: column;
      min-height: 100vh;
      padding: 18px 16px;
      -webkit-tap-highlight-color: transparent;
      max-width: 660px;
      margin: 0 auto;
    }

    /* Marcos de vidrio */
    .glass {
      background: var(--surface-glass);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--border-glass);
    }

    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 16px;
      border-radius: 16px;
      margin-bottom: 18px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 13px;
      font-weight: 800;
      letter-spacing: 1.4px;
      text-transform: uppercase;
      color: var(--text-main);
    }
    .brand-dot {
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: var(--accent-grad);
      box-shadow: 0 0 10px var(--accent), 0 0 22px rgba(29, 185, 84, 0.5);
      animation: pulse 2.4s ease-in-out infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.55; }
    }
    .badge {
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.9px;
      padding: 5px 11px;
      border-radius: 10px;
      color: var(--accent);
      border: 1px solid rgba(29, 185, 84, 0.35);
      background: var(--accent-dim);
      text-transform: uppercase;
    }

    /* Centro del reproductor: tornamesa con vinilo y neón */
    .player-visual {
      display: flex;
      justify-content: center;
      align-items: center;
      margin: 4px 0 10px 0;
    }
    .turntable {
      position: relative;
      width: 196px;
      height: 196px;
      border-radius: 50%;
      background:
        radial-gradient(circle at 30% 30%, rgba(255,255,255,0.05), transparent 40%),
        radial-gradient(circle, #262a3a 10%, #0c0d13 30%, #1a1d29 46%, #08090d 68%, #13161f 92%);
      border: 1px solid var(--border-glass);
      box-shadow: inset 0 0 26px rgba(0, 0, 0, 0.85);
      display: flex;
      justify-content: center;
      align-items: center;
      animation: rotate-disc 9s linear infinite;
      animation-play-state: paused;
      overflow: hidden;
      transition: box-shadow 0.5s ease, border-color 0.5s ease;
    }
    .turntable.playing {
      animation-play-state: running;
      border-color: rgba(29, 185, 84, 0.55);
      box-shadow:
        0 0 24px rgba(29, 185, 84, 0.4),
        0 0 70px rgba(29, 185, 84, 0.16),
        0 14px 34px rgba(0, 0, 0, 0.75),
        inset 0 0 26px rgba(0, 0, 0, 0.85);
    }
    .disc-groove {
      position: absolute;
      width: 138px;
      height: 138px;
      border-radius: 50%;
      border: 1px dashed rgba(255, 255, 255, 0.06);
    }
    .cover-img {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      opacity: 0.88;
    }
    .disc-center {
      position: relative;
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: var(--accent-grad);
      display: flex;
      justify-content: center;
      align-items: center;
      box-shadow: inset 0 0 12px rgba(0, 0, 0, 0.45), 0 0 12px rgba(0, 212, 255, 0.35);
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

    /* Ecualizador */
    .eq {
      display: flex;
      align-items: flex-end;
      justify-content: center;
      gap: 4px;
      height: 24px;
      margin: 6px 0 16px 0;
    }
    .eq span {
      width: 3px;
      height: 4px;
      border-radius: 2px;
      background: var(--accent-grad);
      opacity: 0.3;
    }
    .eq.playing span {
      opacity: 1;
      animation: eqb 0.8s ease-in-out infinite alternate;
    }
    .eq.playing span:nth-child(2n) { animation-duration: 0.55s; }
    .eq.playing span:nth-child(3n) { animation-duration: 1.15s; }
    .eq.playing span:nth-child(5n) { animation-duration: 0.7s; }
    @keyframes eqb {
      from { height: 4px; }
      to { height: 24px; }
    }

    /* Metadatos de la cancion */
    .track-meta {
      text-align: center;
      margin-bottom: 18px;
    }
    .track-title-row {
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 8px;
    }
    .btn-fav {
      background: transparent;
      border: none;
      color: var(--text-subtle);
      font-size: 21px;
      cursor: pointer;
      line-height: 1;
      padding: 0 2px;
      transition: transform 0.1s, color 0.15s;
    }
    .btn-fav:active { transform: scale(0.8); }
    .btn-fav.on {
      color: var(--fav);
      text-shadow: 0 0 12px rgba(245, 179, 1, 0.6);
    }
    .track-title {
      font-size: 19px;
      font-weight: 800;
      letter-spacing: -0.3px;
      color: var(--text-main);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      margin-bottom: 5px;
      padding: 0 10px;
    }
    .track-title::after {
      content: '';
      display: block;
      height: 2px;
      width: 42%;
      margin: 5px auto 0;
      background: var(--accent-grad);
      border-radius: 2px;
    }
    .track-artist {
      font-size: 13px;
      color: var(--text-muted);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      margin-bottom: 8px;
    }
    .context-tag {
      display: inline-block;
      font-size: 11px;
      font-weight: 600;
      color: var(--accent);
      background: var(--accent-dim);
      border: 1px solid rgba(29, 185, 84, 0.25);
      padding: 3px 12px;
      border-radius: 20px;
    }

    /* Barra de progreso interactiva */
    .progress-wrapper {
      margin-bottom: 20px;
    }
    .progress-bar-bg {
      width: 100%;
      height: 6px;
      background: rgba(255, 255, 255, 0.07);
      border-radius: 3px;
      overflow: hidden;
      cursor: pointer;
      border: 1px solid var(--border-glass);
    }
    .progress-bar-fill {
      width: 0%;
      height: 100%;
      background: var(--accent-grad);
      border-radius: 3px;
      box-shadow: 0 0 10px rgba(29, 185, 84, 0.6);
      transition: width 0.2s linear;
    }
    .time-labels {
      display: flex;
      justify-content: space-between;
      font-size: 11px;
      font-variant-numeric: tabular-nums;
      color: var(--text-subtle);
      margin-top: 7px;
      padding: 0 2px;
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
      background: var(--surface-glass);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      border: 1px solid var(--border-glass);
      color: var(--text-main);
      border-radius: 50%;
      display: flex;
      justify-content: center;
      align-items: center;
      cursor: pointer;
      transition: transform 0.12s ease, border-color 0.18s, box-shadow 0.18s, background 0.18s;
    }
    .btn-ctrl:hover {
      border-color: rgba(29, 185, 84, 0.5);
      box-shadow: 0 0 14px rgba(29, 185, 84, 0.25);
    }
    .btn-ctrl:active {
      transform: scale(0.9);
    }
    .btn-sm { width: 42px; height: 42px; }
    .btn-md { width: 50px; height: 50px; }
    .btn-play {
      width: 66px;
      height: 66px;
      background: var(--accent-grad);
      color: #000;
      border: none;
      box-shadow: 0 6px 26px rgba(29, 185, 84, 0.45), 0 0 16px rgba(0, 212, 255, 0.3);
    }
    .btn-play:hover {
      box-shadow: 0 6px 32px rgba(29, 185, 84, 0.6), 0 0 24px rgba(0, 212, 255, 0.45);
    }
    .icon { width: 18px; height: 18px; fill: currentColor; }
    .icon-lg { width: 24px; height: 24px; fill: currentColor; }

    /* Fila de acciones */
    .action-row {
      display: flex;
      justify-content: center;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 16px;
    }
    .btn-pill {
      background: var(--surface-glass);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      border: 1px solid var(--border-glass);
      color: var(--text-muted);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      padding: 9px 16px;
      border-radius: 24px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: 0.15s;
    }
    .btn-pill:hover {
      color: var(--text-main);
      border-color: rgba(29, 185, 84, 0.4);
    }
    .btn-pill.active {
      background: var(--accent-dim);
      border-color: var(--accent);
      color: var(--accent);
      font-weight: 800;
      box-shadow: 0 0 12px rgba(29, 185, 84, 0.2);
    }
    .btn-pill:active { transform: scale(0.95); }
    .btn-fav-pill.active {
      background: rgba(245, 179, 1, 0.12);
      border-color: var(--fav);
      color: var(--fav);
      box-shadow: 0 0 12px rgba(245, 179, 1, 0.2);
    }

    /* Controles extra: volumen y crossfade */
    .extra-controls {
      border-radius: 16px;
      padding: 14px 16px;
      margin-bottom: 18px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .control-row {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .control-label {
      font-size: 10px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: var(--text-muted);
      min-width: 74px;
    }
    .control-value {
      font-size: 12px;
      font-variant-numeric: tabular-nums;
      color: var(--text-main);
      min-width: 46px;
      text-align: right;
      font-weight: 700;
    }
    input[type="range"] {
      -webkit-appearance: none;
      appearance: none;
      flex: 1;
      height: 5px;
      border-radius: 3px;
      background: rgba(255, 255, 255, 0.08);
      outline: none;
    }
    input[type="range"]::-webkit-slider-thumb {
      -webkit-appearance: none;
      appearance: none;
      width: 17px;
      height: 17px;
      border-radius: 50%;
      background: var(--accent-grad);
      border: none;
      cursor: pointer;
      box-shadow: 0 0 12px rgba(29, 185, 84, 0.55);
    }
    input[type="range"]::-webkit-slider-thumb:active {
      transform: scale(1.2);
    }
    .crossfade-opts {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .opt-chip {
      font-size: 11px;
      font-weight: 700;
      padding: 5px 10px;
      border-radius: 14px;
      background: var(--surface-elevated);
      border: 1px solid var(--border-glass);
      color: var(--text-muted);
      cursor: pointer;
      transition: 0.12s;
    }
    .opt-chip:hover {
      color: var(--text-main);
      border-color: rgba(29, 185, 84, 0.4);
    }
    .opt-chip.active {
      background: var(--accent-dim);
      border-color: var(--accent);
      color: var(--accent);
      font-weight: 800;
    }

    /* Pestañas de navegacion */
    .tabs-nav {
      display: flex;
      gap: 6px;
      margin-bottom: 12px;
      background: var(--surface-glass);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      border: 1px solid var(--border-glass);
      border-radius: 12px;
      padding: 4px;
    }
    .tab-btn {
      flex: 1;
      text-align: center;
      padding: 9px 0;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      cursor: pointer;
      border-radius: 9px;
      transition: color 0.15s, background 0.15s;
    }
    .tab-btn.active {
      color: var(--accent);
      background: var(--accent-dim);
    }

    /* Buscador */
    .search-wrap {
      margin-bottom: 12px;
    }
    .search-input {
      width: 100%;
      padding: 11px 15px;
      background: var(--surface-glass);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      border: 1px solid var(--border-glass);
      border-radius: 12px;
      color: var(--text-main);
      font-size: 13px;
      outline: none;
      transition: border-color 0.15s, box-shadow 0.15s;
    }
    .search-input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(29, 185, 84, 0.12);
    }
    .search-input::placeholder { color: var(--text-subtle); }

    /* Listas de carpetas y pistas */
    .catalog-list {
      max-height: 272px;
      overflow-y: auto;
      padding-right: 4px;
      display: flex;
      flex-direction: column;
      gap: 7px;
      scrollbar-width: thin;
      scrollbar-color: var(--border) transparent;
    }
    .catalog-item {
      background: var(--surface-glass);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      border: 1px solid var(--border-glass);
      border-radius: 13px;
      padding: 11px 15px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      cursor: pointer;
      transition: background 0.15s, border-color 0.15s, transform 0.1s;
    }
    .catalog-item:hover {
      border-color: rgba(29, 185, 84, 0.45);
    }
    .catalog-item:active {
      background: var(--surface-elevated);
      transform: scale(0.985);
    }
    .item-meta { flex: 1; min-width: 0; padding-right: 12px; }
    .item-title {
      font-size: 13px;
      font-weight: 700;
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
    .item-fav {
      color: var(--text-subtle);
      font-size: 15px;
      margin-right: 11px;
      cursor: pointer;
    }
    .item-fav.on {
      color: var(--fav);
      text-shadow: 0 0 8px rgba(245, 179, 1, 0.6);
    }
    .item-action {
      font-size: 11px;
      font-weight: 800;
      color: var(--accent);
      background: var(--accent-dim);
      border: 1px solid rgba(29, 185, 84, 0.25);
      padding: 5px 9px;
      border-radius: 8px;
      white-space: nowrap;
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }

    mark {
      background: rgba(245, 179, 1, 0.35);
      color: var(--text-main);
      border-radius: 2px;
      padding: 0 1px;
    }

    .catalog-list::-webkit-scrollbar { width: 4px; }
    .catalog-list::-webkit-scrollbar-thumb {
      background: rgba(255, 255, 255, 0.14);
      border-radius: 2px;
    }

    /* Estado secundario discreto */
    .status-note {
      text-align: center;
      font-size: 11px;
      color: var(--text-subtle);
      margin-top: 16px;
      min-height: 16px;
      letter-spacing: 0.3px;
    }

    /* Modal de letras */
    .lyrics-modal {
      position: fixed;
      inset: 0;
      background: rgba(4, 5, 9, 0.62);
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
      z-index: 50;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 16px;
    }
    .lyrics-modal.open { display: flex; }
    .lyrics-box {
      width: 100%;
      max-width: 560px;
      max-height: 82vh;
      border-radius: 18px;
      padding: 16px;
      display: flex;
      flex-direction: column;
    }
    .lyrics-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
    }
    .lyrics-song {
      font-size: 14px;
      font-weight: 800;
      color: var(--text-main);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .lyrics-scroll {
      overflow-y: auto;
      max-height: 62vh;
      padding-right: 6px;
      scrollbar-width: thin;
      scrollbar-color: var(--border) transparent;
    }
    .lrcline {
      padding: 6px 10px;
      border-radius: 8px;
      color: var(--text-muted);
      font-size: 14px;
      line-height: 1.45;
      transition: background 0.2s, color 0.2s;
      border-left: 3px solid transparent;
    }
    .lrcline.active {
      color: var(--text-main);
      background: var(--accent-dim);
      font-weight: 700;
      border-left-color: var(--accent);
    }
    .lrcline.timezero { text-align: center; color: var(--text-subtle); }
    .lyrics-scroll::-webkit-scrollbar { width: 4px; }
    .lyrics-scroll::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.16); border-radius: 2px; }

    /* Responsivo */
    @media (max-width: 400px) {
      body { padding: 14px 12px; }
      .turntable { width: 160px; height: 160px; }
      .btn-md { width: 46px; height: 46px; }
      .btn-play { width: 60px; height: 60px; }
      .control-label { min-width: 64px; }
    }
  </style>
</head>
<body>

  <header class="glass">
    <div class="brand">
      <div class="brand-dot"></div>
      <span>Violeta</span>
    </div>
    <div class="badge" id="statsBadge">Cargando...</div>
  </header>

  <div class="player-visual">
    <div class="turntable" id="turntable">
      <div class="disc-groove"></div>
      <img class="cover-img" id="coverImg" alt="" style="display:none">
      <div class="disc-center">
        <div class="disc-pin"></div>
      </div>
    </div>
  </div>

  <div class="eq" id="eq">
    <span></span><span></span><span></span><span></span><span></span><span></span>
  </div>

  <div class="track-meta">
    <div class="track-title-row">
      <span class="track-title" id="trackTitle">Selecciona una pista o carpeta</span>
    </div>
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

  <div class="extra-controls glass">
    <!-- Volumen maestro -->
    <div class="control-row">
      <div class="control-label">Volumen</div>
      <input type="range" id="volumeSlider" min="0" max="150" value="100" oninput="setVolume(this.value)">
      <div class="control-value" id="volumeValue">100</div>
    </div>
    <!-- Crossfade configurable -->
    <div class="control-row">
      <div class="control-label">Crossfade</div>
      <div class="crossfade-opts" id="crossfadeOpts"></div>
      <div class="control-value" id="crossfadeValue"></div>
    </div>
  </div>

  <div class="action-row">
    <button class="btn-pill" id="shuffleBtn" onclick="apiCall('/api/toggle_shuffle')">
      <span>Aleatorio</span>
      <span id="shuffleState">OFF</span>
    </button>
    <button class="btn-pill" onclick="apiCall('/api/play_all')">
      <span>Todo el dispositivo</span>
    </button>
    <button class="btn-pill btn-fav-pill" id="favFilterBtn" onclick="toggleFavFilter()">
      <span id="favFilterStar">&#9734;</span>
      <span>Favoritos</span>
      <span id="favCount">0</span>
    </button>
    <button class="btn-pill" id="voiceBtn" onclick="apiCall('/api/toggle_voice')">
      <span>Voz</span>
      <span id="voiceState">ON</span>
    </button>
    <button class="btn-pill" id="lyricsBtn" onclick="openLyrics()">
      <span>Letra</span>
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

  <div class="lyrics-modal" id="lyricsModal" onclick="if(event.target===this)closeLyrics()">
    <div class="lyrics-box glass">
      <div class="lyrics-head">
        <span class="lyrics-song" id="lyricsSongTitle">Letra</span>
        <button class="btn-pill" onclick="closeLyrics()">
          <span>Cerrar</span>
        </button>
      </div>
      <div class="lyrics-scroll" id="lyricsScroll">
        <div id="lyricsText"></div>
      </div>
    </div>
  </div>

  <script>
    let currentTab = 'folders';
    let foldersData = {};
    let tracksData = [];
    let favoritesSet = new Set();
    let favoritosFiltro = false;

    let lastLyricsPath = null;
    let lyricsLines = [];
    let lyricsSynced = false;
    let lastKnownPos = 0;

    const CROSS_OPTS = [0, 3.0, 4.5, 6.0, 8.0];

    function formatTime(s) {
      if (!s || isNaN(s)) return "00:00";
      const m = Math.floor(s / 60);
      const sec = Math.floor(s % 60);
      return (m < 10 ? "0" : "") + m + ":" + (sec < 10 ? "0" : "") + sec;
    }

    // Parsea un LRC "[mm:ss.xx]texto" a [{t: segundos, txt}]
    function parseLRC(lrc) {
      return lrc.split(/\r?\n/).map(l => {
        const m = l.match(/\[(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?\](.*)/);
        if (!m) return { t: null, txt: l.trim() };
        const min = +m[1], sec = +m[2];
        let ms = m[3] ? +m[3] : 0;
        if (m[3] && m[3].length === 2) ms = ms / 100;
        if (m[3] && m[3].length === 3) ms = ms / 1000;
        return { t: min * 60 + sec + ms, txt: (m[4] || '').trim() };
      }).filter(l => l.txt);
    }

    function openLyrics() {
      document.getElementById('lyricsModal').classList.add('open');
      renderLyrics();
    }
    function closeLyrics() {
      document.getElementById('lyricsModal').classList.remove('open');
    }
    function renderLyrics() {
      const box = document.getElementById('lyricsText');
      box.innerHTML = '';
      let activeIdx = -1;
      if (lyricsSynced) {
        for (let i = 0; i < lyricsLines.length; i++) {
          if (lyricsLines[i].t != null && lyricsLines[i].t <= lastKnownPos) activeIdx = i;
        }
      }
      lyricsLines.forEach((l, i) => {
        const d = document.createElement('div');
        d.className = 'lrcline' + (i === activeIdx ? ' active' : '');
        if (l.t == null) d.classList.add('timezero');
        d.textContent = l.txt || '\u00a0';
        box.appendChild(d);
      });
      if (activeIdx >= 0) {
        const el = box.children[activeIdx];
        const wrap = document.getElementById('lyricsScroll');
        wrap.scrollTop = Math.max(0, el.offsetTop - wrap.clientHeight / 2);
      }
    }

    // Escapa una cadena para texto plano (proteccion contra XSS)
    function esc(s) {
      if (s == null) return "";
      return String(s);
    }

    // Construye el titulo con resaltado seguro para el query
    function buildHighlighted(text, query) {
      const node = document.createElement('span');
      text = esc(text);
      if (!query) {
        node.textContent = text;
        return node;
      }
      const lower = text.toLowerCase();
      const ql = query.toLowerCase();
      let i = 0;
      while (true) {
        const idx = lower.indexOf(ql, i);
        if (idx === -1) {
          node.appendChild(document.createTextNode(text.slice(i)));
          break;
        }
        if (idx > i) {
          node.appendChild(document.createTextNode(text.slice(i, idx)));
        }
        const mark = document.createElement('mark');
        mark.textContent = text.slice(idx, idx + ql.length);
        node.appendChild(mark);
        i = idx + ql.length;
      }
      return node;
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

    function toggleFavFilter() {
      favoritosFiltro = !favoritosFiltro;
      const btn = document.getElementById('favFilterBtn');
      btn.classList.toggle('active', favoritosFiltro);
      document.getElementById('favFilterStar').innerHTML = favoritosFiltro ? '&#9733;' : '&#9734;';
      renderList();
    }

    function toggleFavTrack(id) {
      fetch('/api/toggle_fav?id=' + id, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
          favoritesSet = new Set(data.favorites);
          document.getElementById('favCount').innerText = favoritesSet.size;
          renderList();
        });
    }

    function playFolder(folderName) {
      fetch('/api/play_folder?folder=' + encodeURIComponent(folderName), { method: 'POST' })
        .then(() => updateStatus());
    }

    function playSingleTrack(trackId) {
      fetch('/api/play_track_id?id=' + trackId, { method: 'POST' })
        .then(() => updateStatus());
    }

    function setVolume(val) {
      document.getElementById('volumeValue').innerText = val;
      fetch('/api/set_volume?vol=' + val, { method: 'POST' });
    }

    function setCrossfade(val) {
      fetch('/api/set_crossfade?sec=' + val, { method: 'POST' })
        .then(() => updateStatus());
      document.querySelectorAll('.opt-chip').forEach(c => {
        c.classList.toggle('active', parseFloat(c.dataset.sec) === val);
      });
      const label = val > 0 ? val.toFixed(1) + 's' : 'OFF';
      document.getElementById('crossfadeValue').innerText = label;
    }

    function renderList() {
      const container = document.getElementById('itemsList');
      const queryBox = document.getElementById('searchInput');
      const query = queryBox.value.toLowerCase().trim();
      container.innerHTML = '';

      if (currentTab === 'folders') {
        const folderNames = Object.keys(foldersData);
        folderNames.forEach(f => {
          if (favoritosFiltro) return;
          if (!query || f.toLowerCase().includes(query)) {
            const count = foldersData[f].length;
            const div = document.createElement('div');
            div.className = 'catalog-item';
            div.onclick = () => playFolder(f);
            const meta = document.createElement('div');
            meta.className = 'item-meta';
            const t1 = document.createElement('div');
            t1.className = 'item-title';
            t1.appendChild(buildHighlighted(f, query));
            const t2 = document.createElement('div');
            t2.className = 'item-sub';
            t2.textContent = count + ' pistas';
            meta.appendChild(t1);
            meta.appendChild(t2);
            const action = document.createElement('div');
            action.className = 'item-action';
            action.textContent = 'Reproducir';
            div.appendChild(meta);
            div.appendChild(action);
            container.appendChild(div);
          }
        });
      } else {
        tracksData.forEach(t => {
          const title = t.title || t.filename;
          const artist = t.artist || t.folder;
          const isFav = favoritesSet.has(t.path);
          if (favoritosFiltro && !isFav) return;
          if (query && !(title.toLowerCase().includes(query) || artist.toLowerCase().includes(query))) return;

          const div = document.createElement('div');
          div.className = 'catalog-item';
          div.onclick = () => playSingleTrack(t.id);

          // Estrella de favorito (no propaga el click)
          const favBtn = document.createElement('span');
          favBtn.className = 'item-fav' + (isFav ? ' on' : '');
          favBtn.innerHTML = isFav ? '&#9733;' : '&#9734;';
          favBtn.onclick = (e) => { e.stopPropagation(); toggleFavTrack(t.id); };

          const meta = document.createElement('div');
          meta.className = 'item-meta';
          const t1 = document.createElement('div');
          t1.className = 'item-title';
          t1.appendChild(buildHighlighted(title, query));
          const t2 = document.createElement('div');
          t2.className = 'item-sub';
          t2.textContent = artist + '  \u2022  ' + t.folder;
          meta.appendChild(t1);
          meta.appendChild(t2);

          const action = document.createElement('div');
          action.className = 'item-action';
          action.textContent = 'Iniciar';

          div.appendChild(favBtn);
          div.appendChild(meta);
          div.appendChild(action);
          container.appendChild(div);
        });
      }
      if (container.children.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'item-title';
        empty.textContent = 'Sin resultados';
        container.appendChild(empty);
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
          document.getElementById('statsBadge').innerText = (data.total_tracks || 0) + ' pistas';
          document.getElementById('statusNote').innerText = data.status_msg || "Crossfade continuo activo";

          const turntable = document.getElementById('turntable');
          const eqEl = document.getElementById('eq');
          const playIcon = document.getElementById('playPauseIcon');
          const playing = data.playing && !data.paused;

          if (playing) {
            turntable.classList.add('playing');
            eqEl.classList.add('playing');
            playIcon.innerHTML = '<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>';
          } else {
            turntable.classList.remove('playing');
            eqEl.classList.remove('playing');
            playIcon.innerHTML = '<path d="M8 5v14l11-7z"/>';
          }

          if (data.track) {
            document.getElementById('trackTitle').textContent = data.track.title || data.track.filename;
            document.getElementById('trackArtist').textContent = data.track.artist || "Artista desconocido";
            // Caratula
            const cover = document.getElementById('coverImg');
            if (data.cover_url) {
              cover.src = data.cover_url + '&t=' + Date.now();
              cover.style.display = 'block';
            } else {
              cover.style.display = 'none';
            }
            // Letras (solo pedir cuando cambia la cancion)
            const path = data.track.path;
            if (path && path !== lastLyricsPath) {
              lastLyricsPath = path;
              lyricsLines = [];
              lyricsSynced = false;
              document.getElementById('lyricsSongTitle').textContent = data.track.title || data.track.filename;
              fetch('/api/lyrics?path=' + encodeURIComponent(path))
                .then(r => r.json())
                .then(d => {
                  if (d && d.lyrics) {
                    lyricsSynced = !!d.synced;
                    lyricsLines = parseLRC(d.lyrics);
                  } else {
                    lyricsSynced = false;
                    lyricsLines = [{ t: null, txt: 'Sin letra disponible para esta cancion' }];
                  }
                  if (document.getElementById('lyricsModal').classList.contains('open')) renderLyrics();
                })
                .catch(() => {});
            }
          }
          document.getElementById('contextTag').textContent = (data.context_name || '') + ' (' + (data.queue_pos || '0/0') + ')';

          const shuffleBtn = document.getElementById('shuffleBtn');
          const shuffleState = document.getElementById('shuffleState');
          if (data.shuffle) {
            shuffleBtn.classList.add('active');
            shuffleState.innerText = 'ON';
          } else {
            shuffleBtn.classList.remove('active');
            shuffleState.innerText = 'OFF';
          }

          const voiceBtn = document.getElementById('voiceBtn');
          const voiceState = document.getElementById('voiceState');
          if (data.voice_enabled) {
            voiceBtn.classList.add('active');
            voiceState.innerText = 'ON';
          } else {
            voiceBtn.classList.remove('active');
            voiceState.innerText = 'OFF';
          }

          // Volumen maestro (no sobreescribir mientras se arrastra el slider)
          if (data.volume != null && document.activeElement !== document.getElementById('volumeSlider')) {
            document.getElementById('volumeSlider').value = data.volume;
            document.getElementById('volumeValue').innerText = data.volume;
          }

          // Crossfade
          if (data.crossfade_sec != null) {
            setCrossfadeUI(data.crossfade_sec);
          }

          // Favoritos
          if (data.favorites) {
            favoritesSet = new Set(data.favorites);
            document.getElementById('favCount').innerText = favoritesSet.size;
          }

          const pos = data.pos || 0;
          const dur = data.dur || 0;
          lastKnownPos = pos;
          const pct = dur > 0 ? Math.min(100, (pos / dur) * 100) : 0;
          document.getElementById('progressFill').style.width = pct + '%';
          document.getElementById('currentTime').innerText = formatTime(pos);
          document.getElementById('totalTime').innerText = formatTime(dur);

          if (lyricsSynced && document.getElementById('lyricsModal').classList.contains('open')) renderLyrics();
        })
        .catch(() => {});
    }

    function setCrossfadeUI(val) {
      const container = document.getElementById('crossfadeOpts');
      if (container.dataset.built) {
        document.querySelectorAll('.opt-chip').forEach(c => {
          c.classList.toggle('active', parseFloat(c.dataset.sec) === val);
        });
      } else {
        container.dataset.built = '1';
        CROSS_OPTS.forEach(c => {
          const chip = document.createElement('div');
          chip.className = 'opt-chip';
          chip.dataset.sec = c;
          chip.textContent = c > 0 ? c + 's' : 'OFF';
          chip.onclick = () => setCrossfade(c);
          container.appendChild(chip);
        });
        document.querySelectorAll('.opt-chip').forEach(c => {
          c.classList.toggle('active', parseFloat(c.dataset.sec) === val);
        });
      }
      const label = val > 0 ? val.toFixed(1) + 's' : 'OFF';
      document.getElementById('crossfadeValue').innerText = label;
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
      div.innerText = (who === 'user' ? 'Vos: ' : 'Violeta: ') + text;
      box.appendChild(div);
      box.scrollTop = box.scrollHeight;
    }

    document.getElementById('liviInput').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') askLivi();
    });
  </script>

  <div class="livi-panel glass">
    <div class="livi-title">
      <span>Violeta DJ <span id="setInfo"></span></span>
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
      <input type="text" id="liviInput" placeholder="Pedile algo a Violeta: 'pone algo tranqui para estudiar'">
      <button onclick="askLivi()">Enviar</button>
    </div>
  </div>

  <style>
    .livi-panel {
      margin-top: 18px;
      padding: 14px;
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
      border: 1px solid var(--border-glass);
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
      border: 1px solid var(--border-glass);
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
      border: 1px solid var(--border-glass);
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

  </script>
</body>
</html>
"""


class DJLiviController:
    def __init__(self, force_offline=False, rescan=False):
        self.force_offline = force_offline
        self.rescan = rescan
        self.state = DjState()
        self.mixer = DJMixer()
        self.commentator = DJCommentator(force_offline=force_offline)
        self.brain = get_brain()
        self.voice = get_voice()
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
        self.status_msg = "Escaneando dispositivo..."
        self.lock = threading.Lock()

        # IA
        self.brain = get_brain()
        self.voice = get_voice()
        self.mood = None
        self.auto_dj = True
        self.set_info = None
        self.chat_log = []

        if not os.path.isdir(COVERS_DIR):
            try:
                os.makedirs(COVERS_DIR, exist_ok=True)
            except Exception:
                pass

        self.setup()
        self._start_autosave()

    def _start_autosave(self):
        def loop():
            while True:
                time.sleep(6)
                self._save_state()
        threading.Thread(target=loop, daemon=True).start()

    def _save_state(self):
        try:
            self.state['shuffle'] = self.shuffle_mode
            self.state['voice_enabled'] = self.voice_enabled
            self.state['crossfade_sec'] = self.crossfade_sec
            self.state['favorites'] = sorted(self.favorites)
            self.state['last_context'] = self.context_name
            status = self.mixer.get_status()
            if status.get('track'):
                self.state['last_track_path'] = status['track'].get('path')
                self.state['last_pos'] = status.get('pos', 0.0)
            elif self.current_queue:
                track = self.current_queue[self.queue_index]
                self.state['last_track_path'] = track.get('path')
            self.state['last_index'] = self.queue_index
            self.state.save()
        except Exception:
            pass

    def setup(self):
        os.environ.setdefault('PYTHONUNBUFFERED', '1')
        self.all_tracks, self.folder_map = scan_all_device(use_cache=not self.rescan)
        try:
            self.all_tracks, report = enrich_tracks(self.all_tracks)
            print(f"[OK] {report['enriched']} pistas enriquecidas con BPM/key.")
        except Exception as exc:
            print(f"[!] No se pudo enriquecer con BPM/key: {exc}")
        self.mixer.start()
        self.mixer.set_master_volume(float(self.state['volume'] or 100))

        if not self.all_tracks:
            self.status_msg = "No se encontraron canciones."
            return

        # Reanudar sesion si hay una pista guardada
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
        self.context_name = self.state['last_context'] or "Todo el dispositivo"
        saved_pos = float(self.state['last_pos'] or 0.0)
        self.start_playback(trigger_speech=True, resume_pos=saved_pos)

    def start_playback(self, trigger_speech=False, resume_pos=0.0):
        with self.lock:
            if not self.current_queue or self.queue_index >= len(self.current_queue):
                return
            first_track = self.current_queue[self.queue_index]

        if trigger_speech and self.voice_enabled:
            script = self.commentator.generate_welcome_script(self.context_name, first_track)

            def intro_play():
                self.status_msg = f"[Livi] {script[:55]}..."
                try:
                    speech = self.commentator.prepare_speech(script, "livi_intro.mp3")
                    self.mixer.play_track(first_track, crossfade_sec=self.crossfade_sec)
                    time.sleep(0.4)
                    if resume_pos > 5.0:
                        self.mixer.seek(resume_pos)
                    self.mixer.play_voice_with_ducking(speech)
                except Exception:
                    self.mixer.play_track(first_track, crossfade_sec=self.crossfade_sec)
                    if resume_pos > 5.0:
                        self.mixer.seek(resume_pos)
                self.status_msg = "Reproduciendo"
            threading.Thread(target=intro_play, daemon=True).start()
        else:
            self.mixer.play_track(first_track, crossfade_sec=self.crossfade_sec)
            if resume_pos > 5.0:
                self.mixer.seek(resume_pos)
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

        def folder_play():
            try:
                speech = None
                if self.voice_enabled:
                    script = self.commentator.generate_folder_switch_script(folder_name, first_track)
                    speech = self.commentator.prepare_speech(script, "livi_folder.mp3")
                self.mixer.play_track(first_track, crossfade_sec=self.crossfade_sec)
                if speech:
                    self.status_msg = "[Livi] " + folder_name
                    time.sleep(0.4)
                    self.mixer.play_voice_with_ducking(speech)
            except Exception:
                self.mixer.play_track(first_track, crossfade_sec=self.crossfade_sec)
            self.status_msg = "Reproduciendo"
        threading.Thread(target=folder_play, daemon=True).start()

    def play_single_track(self, track_id):
        with self.lock:
            target = None
            target_idx = -1
            for idx, t in enumerate(self.all_tracks):
                if t['id'] == track_id:
                    target = t
                    target_idx = idx
                    break
            if not target:
                return
            self.current_queue = list(self.all_tracks)
            self.queue_index = target_idx
            self.context_name = f"Pista: {target.get('title') or target.get('filename')}"

        self.mixer.play_track(target, crossfade_sec=self.crossfade_sec)
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

    def toggle_voice(self):
        with self.lock:
            self.voice_enabled = not self.voice_enabled
        self.status_msg = f"Voz del DJ: {'ON' if self.voice_enabled else 'SILENCIADA'}"

    def toggle_favorite(self, track_id):
        with self.lock:
            path = None
            for t in self.all_tracks:
                if t['id'] == track_id:
                    path = t['path']
                    break
            if not path:
                return self.get_favorites()
            if path in self.favorites:
                self.favorites.discard(path)
                self.status_msg = "Quitado de Favoritos"
            else:
                self.favorites.add(path)
                self.status_msg = "Agregado a Favoritos"
        self._save_state()
        return self.get_favorites()

    def get_favorites(self):
        with self.lock:
            return sorted(self.favorites)

    def advance_track(self, quick=False):
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

        crossfade = min(self.crossfade_sec, 3.0) if quick else self.crossfade_sec
        self.mixer.play_track(next_track, crossfade_sec=crossfade)
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

        self.mixer.play_track(prev_track, crossfade_sec=self.crossfade_sec)
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

    def set_crossfade(self, sec):
        sec = float(sec)
        if sec in CROSSFADE_OPTIONS:
            with self.lock:
                self.crossfade_sec = sec
            label = f"{sec:.1f}s" if sec > 0 else "OFF"
            self.status_msg = f"Crossfade: {label}"

    def get_cover(self, track_path):
        """Extrae y cache la caratula real de la pista. Devuelve ruta abs o None."""
        if not track_path or not os.path.exists(track_path):
            return None
        h = hashlib.md5(track_path.encode('utf-8', errors='ignore')).hexdigest()[:16]
        cached = os.path.join(COVERS_DIR, h + '.jpg')
        if os.path.exists(cached):
            return cached

        data = None
        try:
            from mutagen import File as MFile
            f = MFile(track_path)
            if f is None:
                return None
            if f.tags:
                pic = None
                try:
                    from mutagen.id3 import APIC
                    apics = f.tags.getall('APIC')
                    if apics:
                        pic = (apics[0].data, apics[0].mime)
                except Exception:
                    pass
                if pic is None:
                    try:
                        v = f.tags.get('metadata_block_picture')
                        if v:
                            import base64
                            from mutagen.flac import Picture
                            p = Picture(base64.b64decode(v[0]))
                            pic = (p.data, 'image/jpeg')
                    except Exception:
                        pass
                if pic is None:
                    try:
                        if 'covr' in f.tags:
                            covr = f.tags['covr']
                            if covr:
                                pic = (bytes(covr[0]), None)
                    except Exception:
                        pass
                if pic is None:
                    try:
                        if f.tags.get('pictures'):
                            p = f.tags['pictures'][0]
                            pic = (p.data, p.mime)
                    except Exception:
                        pass
                if pic and pic[0]:
                    data = pic[0]
        except Exception:
            data = None

        if not data:
            return None
        try:
            with open(cached, 'wb') as fh:
                fh.write(data)
            return cached
        except Exception:
            return None

    def get_lyrics_by_path(self, path):
        """Devuelve la letra (LRC sincronizada o texto) de una pista por su ruta."""
        if not path:
            return {'synced': False, 'lyrics': None}
        track = None
        for t in self.all_tracks:
            if t.get('path') == path:
                track = t
                break
        if not track:
            return {'synced': False, 'lyrics': None}
        data = _lyrics_for(track.get('artist'), track.get('title'))
        return data or {'synced': False, 'lyrics': None}

    def get_info(self):
        status = self.mixer.get_status()
        q_pos = f"{self.queue_index + 1}/{len(self.current_queue)}" if self.current_queue else "0/0"
        track = status.get('track')
        cover_url = None
        if track and track.get('path'):
            cover_path = self.get_cover(track['path'])
            if cover_path:
                cover_url = '/api/cover?path=' + cover_path
        return {
            'playing': status.get('playing', False),
            'paused': status.get('paused', False),
            'pos': status.get('pos', 0.0),
            'dur': status.get('dur', 0.0),
            'track': track,
            'cover_url': cover_url,
            'total_tracks': len(self.all_tracks),
            'context_name': self.context_name,
            'queue_pos': q_pos,
            'shuffle': self.shuffle_mode,
            'voice_enabled': self.voice_enabled,
            'volume': int(self.mixer.master_volume),
            'crossfade_sec': self.crossfade_sec,
            'favorites': self.get_favorites(),
            'status_msg': self.status_msg,
            'offline': self.force_offline
        }

    # --------------------------------------------------- IA / Auto-DJ --
    def library_summary(self):
        if not self.folder_map:
            return "sin carpetas"
        parts = ["%s (%d)" % (name, len(tr))
                 for name, tr in list(self.folder_map.items())[:12]]
        return "; ".join(parts)

    def build_auto_queue(self, minutes=45, mood=None, terms=None,
                         speech=True, seed=None):
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
        self.start_playback(trigger_speech=speech)
        return {'success': True, 'set_info': info}

    def set_mood(self, mood):
        new_mood = normalize_mood(mood)
        if not new_mood:
            return {'success': False, 'error': 'mood_invalido',
                    'reply': 'No conozco ese estado.'}
        minutes = (self.set_info or {}).get('minutes') or 45
        result = self.build_auto_queue(minutes=minutes, mood=new_mood)
        self.status_msg = "Mood: %s" % new_mood
        return result

    def say(self, text):
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
        text = (text or "").strip()
        if not text:
            return {'success': False, 'error': 'texto_vacio'}
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


controller = None


class DJRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

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

        elif parsed.path == "/api/lyrics":
            qs = parse_qs(parsed.query)
            path = None
            if qs.get('path'):
                path = unquote(qs['path'][0])
            lyrics = controller.get_lyrics_by_path(path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(lyrics).encode('utf-8'))

        elif parsed.path == "/api/cover":
            qs = parse_qs(parsed.query)
            path = qs.get('path', [None])[0]
            if path:
                path = unquote(path)
                if os.path.exists(path) and os.path.dirname(path) == COVERS_DIR:
                    with open(path, 'rb') as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Cache-Control", "max-age=3600")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
            self.send_response(404)
            self.end_headers()
        elif parsed.path == "/manifest.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json")
            self.end_headers()
            self.wfile.write(json.dumps(MANIFEST).encode('utf-8'))

        elif parsed.path in ("/icon-192.png", "/icon-512.png", "/favicon.ico"):
            p = parsed.path.lstrip("/")
            size = "icon-192.png" if p == "favicon.ico" else p
            icon = os.path.join(PWA_ICON_DIR, size)
            if not os.path.exists(icon):
                icon = os.path.join(PWA_ICON_DIR, "icon-192.png")
            if os.path.exists(icon):
                with open(icon, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "max-age=86400")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            self.send_response(404)
            self.end_headers()
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
        elif parsed.path == "/api/toggle_voice":
            controller.toggle_voice()
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
        elif parsed.path == "/api/toggle_fav":
            t_id = int(qs.get('id', [-1])[0])
            favs = controller.toggle_favorite(t_id)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'favorites': favs}).encode('utf-8'))
            return
        elif parsed.path == "/api/set_volume":
            vol = float(qs.get('vol', [100])[0])
            controller.mixer.set_master_volume(vol)
            controller.state['volume'] = vol
            controller.state.save()
        elif parsed.path == "/api/set_crossfade":
            sec = float(qs.get('sec', [4.5])[0])
            controller.set_crossfade(sec)
        elif parsed.path == "/api/ask":
            data = self._read_body()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(controller.ask(data.get('request') or qs.get('q', [''])[0])).encode('utf-8'))
            return
        elif parsed.path == "/api/mood":
            data = self._read_body()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(controller.set_mood(data.get('mood'))).encode('utf-8'))
            return
        elif parsed.path == "/api/say":
            data = self._read_body()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(controller.say(data.get('text'))).encode('utf-8'))
            return
        elif parsed.path == "/api/enqueue":
            data = self._read_body()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(controller.build_auto_queue(
                minutes=float(data.get('minutes') or 45),
                mood=data.get('mood'),
                terms=data.get('terms') or data.get('query'))).encode('utf-8'))
            return
        elif parsed.path == "/api/say":
            data = self._read_body()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(controller.say(data.get('text'))).encode('utf-8'))
            return
        elif parsed.path == "/api/voice_listen":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(controller.listen()).encode('utf-8'))
            return
        elif parsed.path == "/api/voice_status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(controller.voice.status()).encode('utf-8'))
            return
        elif parsed.path == "/api/queue":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(controller.queue_snapshot()).encode('utf-8'))
            return
        elif parsed.path == "/api/brain":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(controller.brain.status_info()).encode('utf-8'))
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"success": true}')


def run_server(port=5000, force_offline=False, rescan=False):
    global controller
    controller = DJLiviController(force_offline=force_offline, rescan=rescan)

    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, DJRequestHandler)
    print(f"\n========================================================")
    print(f"VIOLETA STUDIO - SERVIDOR WEB INICIADO")
    print(f"   Canciones detectadas: {len(controller.all_tracks)}")
    print(f"   Carpetas detectadas:  {len(controller.folder_map)}")
    print(f"   Favoritos:            {len(controller.favorites)}")
    print(f"   URL: http://localhost:{port}")
    print(f"========================================================\n")

    def auto_dj_loop():
        crossfade_done = False
        while True:
            time.sleep(0.5)
            try:
                status = controller.mixer.get_status()
                dur = status.get('dur', 0.0)
                pos = status.get('pos', 0.0)
                xf_quick = min(controller.crossfade_sec, 3.0)
                lookahead = min(xf_quick + 1.0, 5.0)
                if status['playing'] and dur > 8 and (dur - pos) <= lookahead:
                    if not crossfade_done:
                        crossfade_done = True
                        controller.advance_track(quick=True)
                else:
                    crossfade_done = False
            except Exception:
                pass

    threading.Thread(target=auto_dj_loop, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando servidor...")
        controller.mixer.stop()
        controller._save_state()


if __name__ == "__main__":
    offline_mode = "--offline" in sys.argv
    rescan_mode = "--rescan" in sys.argv
    port = 5000
    args = sys.argv
    if "--port" in args:
        i = args.index("--port")
        if i + 1 < len(args):
            port = int(args[i + 1])
    for arg in args:
        if arg.startswith("--port="):
            port = int(arg.split("=")[1])
    run_server(port=port, force_offline=offline_mode, rescan=rescan_mode)