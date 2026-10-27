#!/usr/bin/env python3
"""
music_scanner.py - Escáner de música para todo el dispositivo, por carpetas y canciones individuales.
Soporta Linux y Android (Termux).
Mejoras: caché del índice, metadatos reales (mutagen si está instalado) y
carpetas sin colisión de nombres.
"""
import os
import re
import json
import time
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(SCRIPT_DIR, '.library_cache.json')
CACHE_TTL = 600  # 10 minutos; usa --rescan para forzar un escaneo completo

AUDIO_EXTENSIONS = ('.opus', '.m4a', '.mp3', '.flac', '.wav', '.ogg', '.aac', '.wma')

# Carpetas de sistema que se deben ignorar al escanear
EXCLUDED_DIRS = {
    'android/data', 'android/obb', '.thumbnails', '.trash', '.trashbin',
    '.trash-storage', '.git', 'node_modules', '.cache', '__pycache__', '.l2s'
}

def clean_title_for_speech(raw_name):
    """Limpia el nombre del archivo para mostrar y anunciar de forma limpia."""
    name = re.sub(r'\.(opus|m4a|mp3|wav|flac|ogg|aac|wma)$', '', raw_name, flags=re.IGNORECASE)
    tags_to_remove = [
        r'\(Official (Music )?Video\)', r'\[Official (Music )?Video\]',
        r'\(Official Audio\)', r'\[Official Audio\]',
        r'\(Lyric Video\)', r'\[Lyric Video\]',
        r'\(Letra[^)]*\)', r'\[Letra[^\]]*\]',
        r'\(Traducida[^)]*\)', r'\[Traducida[^\]]*\]',
        r'\(Audio\)', r'\[Audio\]',
        r'\[4K[^\]]*\]', r'\(4K[^)]*\)',
        r'\[HD[^\]]*\]', r'\(HD[^)]*\)',
        r'\[MV\]', r'M/V', r'M⧸V',
        r'~use headphones~',
        r'\(remastered \d+\)',
        r'#\w+'
    ]
    for tag in tags_to_remove:
        name = re.sub(tag, '', name, flags=re.IGNORECASE)

    if ' - ' in name:
        parts = name.split(' - ', 1)
        artist = parts[0].strip()
        title = parts[1].strip()
        title = re.sub(r'\s+', ' ', title).strip(' -_')
        artist = re.sub(r'\s+', ' ', artist).strip(' -_')
        return artist, title
    else:
        name = re.sub(r'\s+', ' ', name).strip(' -_')
        return None, name

def _read_real_tags(path, artist, title):
    """Si mutagen está instalado, mejora artista/título con los metadatos reales."""
    if artist and title:
        return artist, title
    try:
        from mutagen import File as MFile
        f = MFile(path, easy=True)
        if f:
            a = f.get('artist') if artist is None else None
            t = f.get('title') if title is None else None
            if a and a[0]:
                artist = a[0]
            if t and t[0]:
                title = t[0]
    except Exception:
        pass
    return artist, title

def get_search_roots():
    """Obtiene las rutas raíz para escanear según si es Android o PC."""
    roots = []
    # Android almacenamiento interno
    if os.path.exists('/sdcard'):
        roots.append('/sdcard')
    elif os.path.exists('/storage/emulated/0'):
        roots.append('/storage/emulated/0')

    # PC / Linux rutas estándar
    home_dirs = ['~/Música', '~/Music', '~/Descargas', '~/Downloads', '~/Audio']
    for d in home_dirs:
        expanded = os.path.expanduser(d)
        if os.path.exists(expanded) and expanded not in roots:
            roots.append(expanded)

    # USB / discos extraíbles montados en Linux
    for base in ('/media', '/mnt', '/run/media'):
        if os.path.isdir(base):
            try:
                for user_dir in os.listdir(base):
                    user_path = os.path.join(base, user_dir)
                    if os.path.isdir(user_path):
                        for mount in os.listdir(user_path):
                            mount_path = os.path.join(user_path, mount)
                            if os.path.ismount(mount_path) and mount_path not in roots:
                                roots.append(mount_path)
            except Exception:
                pass

    if not roots:
        roots.append(os.path.expanduser('~'))
    return roots

def _load_cache():
    try:
        if time.time() - os.path.getmtime(CACHE_FILE) > CACHE_TTL:
            return None
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if data and 'tracks' in data and 'folders' in data:
            return data['tracks'], data['folders']
    except Exception:
        pass
    return None

def _save_cache(all_tracks, folder_map):
    try:
        tmp = CACHE_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'tracks': all_tracks, 'folders': folder_map}, f, ensure_ascii=False)
        os.replace(tmp, CACHE_FILE)
    except Exception:
        pass

def scan_all_device(roots=None, use_cache=True):
    """
    Escanea todo el almacenamiento buscando canciones.
    Retorna:
      - all_tracks: lista completa de canciones con metadatos.
      - folder_map: diccionario {nombre_carpeta: [tracks]} (sin colisiones).
    Si use_cache=True y el caché es reciente, carga el índice sin volver a recorrer el disco.
    """
    if use_cache:
        cached = _load_cache()
        if cached:
            return cached

    if roots is None:
        roots = get_search_roots()
    elif isinstance(roots, str):
        roots = [roots]

    all_tracks = []
    folder_map = defaultdict(list)
    folder_keys = {}  # display -> folder_path real
    seen_paths = set()

    def folder_display_name(path):
        """Nombre a mostrar para una carpeta, desambiguando nombres duplicados."""
        name = os.path.basename(path) or "Raíz"
        if name not in folder_keys or folder_keys[name] == path:
            folder_keys[name] = path
            return name
        parent = os.path.basename(os.path.dirname(path)) or "raiz"
        alt = f"{name} ({parent})"
        folder_keys[alt] = path
        return alt

    def build_track(full_path, folder_name, folder_path, idx):
        fname = os.path.basename(full_path)
        artist, title = clean_title_for_speech(fname)
        artist, title = _read_real_tags(full_path, artist, title)
        return {
            'id': idx,
            'path': full_path,
            'filename': fname,
            'artist': artist,
            'title': title,
            'folder': folder_name,
            'folder_path': folder_path
        }

    for base in roots:
        if not os.path.exists(base):
            continue

        # Si la ruta es un archivo directo
        if os.path.isfile(base):
            if base.lower().endswith(AUDIO_EXTENSIONS):
                folder_path = os.path.dirname(base)
                folder_name = folder_display_name(folder_path)
                track = build_track(base, folder_name, folder_path, len(all_tracks))
                all_tracks.append(track)
                folder_map[folder_name].append(track)
            continue

        for root, dirs, files in os.walk(base):
            # Omitir carpetas de sistema o caché
            root_lower = root.lower()
            if any(ex in root_lower for ex in EXCLUDED_DIRS):
                dirs.clear()
                continue

            for f in sorted(files):
                if f.lower().endswith(AUDIO_EXTENSIONS) and not f.startswith('.'):
                    full_path = os.path.join(root, f)
                    if full_path in seen_paths:
                        continue
                    try:
                        if os.path.getsize(full_path) < 50000:  # omitir archivos dañados < 50KB
                            continue
                    except OSError:
                        continue

                    seen_paths.add(full_path)
                    folder_name = folder_display_name(root)
                    track = build_track(full_path, folder_name, root, len(all_tracks))
                    all_tracks.append(track)
                    folder_map[folder_name].append(track)

    result = all_tracks, dict(folder_map)
    _save_cache(*result)
    return result

if __name__ == '__main__':
    tracks, folders = scan_all_device(use_cache=False)
    print(f"{len(tracks)} canciones en {len(folders)} carpetas")
    for name, items in list(folders.items())[:10]:
        print(f"  * {name}: {len(items)}")
