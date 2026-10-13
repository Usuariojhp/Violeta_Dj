#!/usr/bin/env python3
"""
music_scanner.py - Escáner de música para todo el dispositivo, por carpetas y canciones individuales.
Soporta Linux y Android (Termux).
"""
import os
import re
from collections import defaultdict

AUDIO_EXTENSIONS = ('.opus', '.m4a', '.mp3', '.flac', '.wav', '.ogg', '.aac', '.wma')

# Carpetas de sistema que se deben ignorar al escanear
EXCLUDED_DIRS = {
    'android/data', 'android/obb', '.thumbnails', '.trash', '.trashbin',
    '.trash-storage', '.git', 'node_modules', '.cache', '__pycache__'
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

def get_search_roots():
    """Obtiene las rutas raíz para escanear según si es Android o PC.

    Se puede forzar con DJ_SCAN_ROOTS (rutas separadas por ':' o ','): util
    para limitar el escaneo o para pruebas.
    """
    forced = os.environ.get("DJ_SCAN_ROOTS", "").strip()
    if forced:
        parts = [p for p in forced.replace(",", ":").split(":") if p]
        roots = [os.path.expanduser(p) for p in parts]
        if roots:
            return roots

    roots = []
    # Android almacenamiento interno
    if os.path.exists('/sdcard'):
        roots.append('/sdcard')
    elif os.path.exists('/storage/emulated/0'):
        roots.append('/storage/emulated/0')
    
    # PC / Linux rutas estándar
    home_dirs = ['~/Música', '~/Music', '~/Descargas', '~/Downloads', '~/Audio', '~/videos of galery/Music', '~/videos of galery/musicas1', '~/run/media/josehp/Android SD']
    for d in home_dirs:
        expanded = os.path.expanduser(d)
        if os.path.exists(expanded) and expanded not in roots:
            roots.append(expanded)
            
    if not roots:
        roots.append(os.path.expanduser('~'))
    return roots

def scan_all_device(roots=None):
    """
    Escanea todo el almacenamiento buscando canciones.
    Retorna:
      - all_tracks: lista completa de canciones con metadatos.
      - folder_map: diccionario {nombre_carpeta: [tracks]}
    """
    if roots is None:
        roots = get_search_roots()
    elif isinstance(roots, str):
        roots = [roots]

    all_tracks = []
    folder_map = defaultdict(list)
    seen_paths = set()

    for base in roots:
        if not os.path.exists(base):
            continue
            
        # Si la ruta es un archivo directo
        if os.path.isfile(base):
            if base.lower().endswith(AUDIO_EXTENSIONS):
                fname = os.path.basename(base)
                artist, title = clean_title_for_speech(fname)
                folder_name = os.path.basename(os.path.dirname(base)) or "Raíz"
                track = {
                    'id': 0,
                    'path': base,
                    'filename': fname,
                    'artist': artist,
                    'title': title,
                    'folder': folder_name,
                    'folder_path': os.path.dirname(base)
                }
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
                        if os.path.getsize(full_path) < 50000: # omitir archivos dañados < 50KB
                            continue
                    except OSError:
                        continue

                    seen_paths.add(full_path)
                    artist, title = clean_title_for_speech(f)
                    folder_name = os.path.basename(root) or "Raíz"
                    track_info = {
                        'id': len(all_tracks),
                        'path': full_path,
                        'filename': f,
                        'artist': artist,
                        'title': title,
                        'folder': folder_name,
                        'folder_path': root
                    }
                    all_tracks.append(track_info)
                    folder_map[folder_name].append(track_info)

    return all_tracks, dict(folder_map)
