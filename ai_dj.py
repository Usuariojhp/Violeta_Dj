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
import math
import shutil
import random
import termios
import threading
import unicodedata
from music_scanner import scan_all_device
from dj_commentator import DJCommentator
from dj_mixer import DJMixer
from dj_state import DjState
from dj_brain import get_brain
from set_engine import build_set, next_mood, normalize_mood, DEFAULT_MOOD
from track_intel import enrich_tracks
from voice_command import get_voice

# ------------------------------------------------------------------ color --
# Deteccion automatica de nivel de color:
#   0 = sin color (NO_COLOR / TERM=dumb), 1 = 16 colores, 2 = 256, 3 = truecolor


def _color_level():
    if os.environ.get('NO_COLOR') is not None:
        return 0
    term = os.environ.get('TERM', '').strip().lower()
    if term == 'dumb':
        return 0
    ct = os.environ.get('COLORTERM', '').strip().lower()
    if ct in ('truecolor', '24bit') or 'truecolor' in term or '24bit' in term:
        return 3
    if '256' in term:
        return 2
    if term in ('', 'vt100', 'vt102', 'vt220', 'ansi', 'cons25', 'cons25w'):
        return 1 if term else 0
    if term.startswith(('xterm', 'screen', 'tmux', 'rxvt', 'linux', 'konsole', 'alacritty', 'kitty', 'st-')):
        return 2
    return 1


COLOR_LEVEL = _color_level()


def _rgb_to_256(r, g, b):
    """Mapea RGB al cubo 6x6x6 / rampa gris de la paleta de 256 colores."""
    def q(v):
        return max(0, min(5, int(round(v / 51.0))))
    cr, cg, cb = q(r), q(g), q(b)
    if cr == cg == cb:
        idx = max(0, min(23, int(round((max(r, g, b) - 8) / 10.0))))
        return 232 + idx
    return 16 + 36 * cr + 6 * cg + cb


def _c(rgb, fallback16):
    """Escape de color apropiado al nivel detectado (o vacio si no hay color)."""
    if COLOR_LEVEL <= 0:
        return ''
    if COLOR_LEVEL >= 3:
        return '\033[38;2;%d;%d;%dm' % rgb
    if COLOR_LEVEL == 2:
        return '\033[38;5;%dm' % _rgb_to_256(*rgb)
    return fallback16


def _bg(rgb, fallback16):
    """Escape de color de fondo apropiado al nivel detectado."""
    if COLOR_LEVEL <= 0:
        return ''
    if COLOR_LEVEL >= 3:
        return '\033[48;2;%d;%d;%dm' % rgb
    if COLOR_LEVEL == 2:
        return '\033[48;5;%dm' % _rgb_to_256(*rgb)
    return fallback16


C_RESET = '\033[0m' if COLOR_LEVEL > 0 else ''
C_BOLD = '\033[1m' if COLOR_LEVEL > 0 else ''
C_DIMTXT = '\033[2m' if COLOR_LEVEL > 0 else ''
C_UNDER = '\033[4m' if COLOR_LEVEL > 0 else ''

# Paleta Violeta (truecolor) con fallback razonable a 16 colores.
C_VIOLET = _c((167, 139, 250), '\033[95m')   # titulos
C_ACCENT = _c((139, 92, 246), '\033[95m')    # acento principal
C_PINK = _c((236, 72, 153), '\033[95m')      # calido
C_CYAN = _c((34, 211, 238), '\033[96m')      # frio / detalles
C_GREEN = _c((52, 211, 153), '\033[92m')     # ok / reproduciendo
C_YELLOW = _c((251, 191, 36), '\033[93m')    # aviso / favorito
C_RED = _c((248, 113, 113), '\033[91m')      # error / pausa
C_MAGENTA = _c((217, 70, 239), '\033[95m')
C_GRAY = _c((148, 163, 184), '\033[90m')     # texto secundario
C_LABEL = _c((107, 114, 128), '\033[90m')    # etiquetas
C_TEXT = _c((226, 232, 240), '\033[97m')     # texto principal
C_BORDER = _c((96, 88, 140), '\033[90m')     # bordes de tarjeta
C_BORDER_S = _c((71, 85, 105), '\033[90m')   # bordes suaves / separadores

CROSSFADE_OPTIONS = [0, 3.0, 4.5, 6.0, 8.0]

ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')

_EA_CACHE = {}


def _char_width(ch):
    """Ancho de terminal de un caracter (1, 2 o 0)."""
    w = _EA_CACHE.get(ch)
    if w is None:
        if unicodedata.combining(ch):
            w = 0
        elif unicodedata.east_asian_width(ch) in ('W', 'F'):
            w = 2
        else:
            w = 1
        _EA_CACHE[ch] = w
    return w


def _vis_len(content):
    """Ancho visible ignorando secuencias ANSI."""
    return sum(_char_width(c) for c in ANSI_RE.sub('', content))


def _pad_ansi(content, width):
    """Rellena a ancho fijo ignorando los codigos de color ANSI."""
    pad = width - _vis_len(content)
    return content + ' ' * pad if pad > 0 else content


def _fit_ansi(content, width, ellipsis=True):
    """Trunca a un ancho visible sin romper ni perder los codigos ANSI."""
    total = _vis_len(content)
    if total <= width:
        return content
    if not ellipsis or width < 1:
        target = width
        add_ellipsis = False
    else:
        target = max(0, width - 1)
        add_ellipsis = True
    res = []
    visible = 0
    i = 0
    while i < len(content) and visible < target:
        m = ANSI_RE.match(content, i)
        if m:
            res.append(m.group(0))
            i = m.end()
            continue
        # Secuencia ANSI incompleta al final: ignorar resto
        if content[i] == '\x1b':
            break
        w = _char_width(content[i])
        if visible + w > target:
            break
        res.append(content[i])
        visible += w
        i += 1
    if add_ellipsis:
        res.append('…')
    res.append(C_RESET)
    return ''.join(res)


def _lerp(c1, c2, t):
    """Mezcla dos colores RGB con t en [0,1]."""
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


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
        self.browse_level = 'folders'
        self.browse_sel = 0
        self.browse_folder = None
        self.browse_tracks = []
        self.search_active = False
        self.search_query = ''
        self.search_results = []

        # Estado UI simple
        self.show_help = False
        self.folder_page = 0
        self.browse_page = 0
        self._eq_tick = 0
        self.folder_input = ''

    # ------------------------------------------------------------------ UI --

    BAR_EMPTY = '░'

    # -- helpers simples ----------------------------------------------------

    def _box_top(self, width, title, right=''):
        """Linea superior de caja: ╭─ title ──── right ─╮"""
        inner = max(4, width - 2)
        t = ' ' + C_BOLD + C_VIOLET + title + C_RESET + C_BORDER + ' '
        r = C_BORDER + ' ' + right + ' ' if right else C_BORDER + ' '
        used = _vis_len(t) + _vis_len(r)
        d = max(0, inner - used)
        return C_BORDER + '╭' + t + ('─' * d) + r + '╮' + C_RESET

    def _box_line(self, width, content='', color=C_RESET, right=''):
        """Linea interior: │ content ... right │"""
        cw = max(4, width - 4)
        if right:
            gap = cw - _vis_len(content) - _vis_len(right)
            if gap < 1:
                content = _fit_ansi(content, max(0, cw - _vis_len(right) - 1))
                gap = cw - _vis_len(content) - _vis_len(right)
            content = content + (' ' * max(0, gap)) + right
        inner = _pad_ansi(_fit_ansi(content, cw), cw)
        return C_BORDER + '│' + C_RESET + ' ' + color + inner + C_RESET + ' ' + C_BORDER + '│' + C_RESET

    def _box_bottom(self, width):
        return C_BORDER + '╰' + ('─' * max(4, width - 2)) + '╯' + C_RESET

    @staticmethod
    def _merge_cols(left, right, gap=2):
        if not right:
            return list(left)
        n = max(len(left), len(right))
        out = []
        for i in range(n):
            l = left[i] if i < len(left) else ''
            r = right[i] if i < len(right) else ''
            out.append(l + (' ' * gap) + r)
        return out

    def _layout(self):
        cols = max(40, shutil.get_terminal_size((100, 30)).columns)
        total = min(cols - 1, 110)
        if cols >= 96:
            gap = 2
            left = int(round((total - gap) * 0.62))
            left = max(46, min(left, total - gap - 32))
            right = total - gap - left
            return {'total': total, 'left': left, 'right': right,
                    'two': right >= 30, 'cols': cols}
        return {'total': total, 'left': total, 'right': 0, 'two': False, 'cols': cols}

    # -- piezas visuales ----------------------------------------------------

    def _progress_bar(self, pct, bar_w):
        """Barra con bloques fraccionarios y degradado violeta -> cian."""
        pct = 0.0 if pct < 0 else (1.0 if pct > 1 else pct)
        exact = pct * bar_w
        full = int(exact)
        rem = int(round((exact - full) * 8))
        if rem > 7:
            rem = 7
        add_part = full < bar_w and rem > 0
        filled = '█' * full + ('▏▎▍▌▋▊▉'[rem - 1] if add_part else '')
        empties = max(0, bar_w - full - (1 if add_part else 0))
        n_filled = full + (1 if add_part else 0)
        if COLOR_LEVEL > 0 and n_filled > 0:
            segs = []
            for i, ch in enumerate(filled):
                t = (i / (n_filled - 1)) if n_filled > 1 else 0.0
                segs.append(_c(_lerp((139, 92, 246), (34, 211, 238), t), C_CYAN) + ch)
            head = ''.join(segs) + C_RESET
        else:
            head = (C_VIOLET + filled + C_RESET) if filled else ''
        return head + C_BORDER_S + (self.BAR_EMPTY * empties) + C_RESET

    def _eq(self, playing, bars=8):
        """Mini ecualizador animado (se congela en pausa)."""
        if not playing:
            return C_BORDER_S + ('·' * bars) + C_RESET
        self._eq_tick = getattr(self, '_eq_tick', 0) + 1
        out = []
        blocks = '▁▂▃▄▅▆▇█'
        for i in range(bars):
            v = (math.sin(self._eq_tick * 0.85 + i * 1.15) *
                 math.cos(self._eq_tick * 0.31 + i * 0.55))
            lvl = min(6, int(abs(v) * 7))
            t = i / max(1, bars - 1)
            out.append(_c(_lerp((236, 72, 153), (34, 211, 238), t), C_CYAN) + blocks[lvl])
        return ''.join(out) + C_RESET

    def _chip(self, text, fg, bg_rgb):
        """Pastilla tipo [ chill ] con fondo suave."""
        return ' ' + _bg(bg_rgb, '') + fg + ' ' + text + ' ' + C_RESET + ' '

    def _state_tag(self, status):
        if status.get('ducking'):
            return '● LIVI', C_YELLOW
        if status.get('paused'):
            return '● PAUSA', C_RED
        if status.get('playing'):
            return '● REPRODUCIENDO', C_GREEN
        return '● DETENIDO', C_GRAY

    # -- pantallas --------------------------------------------------------

    def _brand_box(self, width, status):
        state, state_c = self._state_tag(status)
        mode = 'OFFLINE' if self.force_offline else 'ONLINE'
        mode_c = C_RED if self.force_offline else C_GREEN
        stats = (f"{C_BOLD}{len(self.all_tracks)}{C_RESET}{C_LABEL} pistas  "
                 f"{C_BOLD}{len(self.folder_map)}{C_RESET}{C_LABEL} carpetas  "
                 f"{C_YELLOW}★{len(self.favorites)}{C_RESET}")
        right = f"{mode_c}{mode}{C_RESET}  {state_c}{state}{C_RESET}"
        return [self._box_top(width, 'VIOLETA', right),
                self._box_line(width, stats, C_GRAY),
                self._box_bottom(width)]

    def _np_box(self, width):
        status = self.mixer.get_status()
        track = status.get('track')
        pos = float(status.get('pos', 0.0))
        dur = float(status.get('dur', 0.0))
        state, state_c = self._state_tag(status)
        body = []
        if track:
            title = track.get('title') or track.get('filename') or 'Sin pista'
            artist = track.get('artist') or track.get('folder') or ''
            fav = track.get('path') in self.favorites
            star = C_YELLOW + '★ ' + C_RESET if fav else ''
            body.append(star + C_BOLD + C_VIOLET + title + C_RESET)
            body.append(C_CYAN + artist + C_RESET)
            body.append('')
            pct = min(1.0, max(0.0, pos / dur)) if dur > 0 else 0.0
            bar_w = max(10, width - 22)
            body.append('  ' + self._progress_bar(pct, bar_w) + f"  {C_BOLD}{pct * 100:3.0f}%{C_RESET}")
            tail = ''
            if self.mood:
                tail = '  ' + C_PINK + 'mood:' + str(self.mood) + C_RESET
            body.append(f"  {C_CYAN}{self.format_time(pos)}{C_RESET}{C_LABEL} / {self.format_time(dur)}{C_RESET}" + tail)
        else:
            body.append(C_LABEL + 'Sin pista. Pulsa T para reproducir todo.' + C_RESET)
            body += [''] * 4
        while len(body) < 5:
            body.append('')
        return ([self._box_top(width, 'REPRODUCIENDO', f"{state_c}{state}{C_RESET}")]
                + [self._box_line(width, ln, C_TEXT) for ln in body[:5]]
                + [self._box_bottom(width)])

    def _queue_box(self, width):
        n = len(self.current_queue)
        rows = []
        for k in range(1, 4):
            idx = self.queue_index + k
            if idx >= n:
                break
            t = self.current_queue[idx]
            title = t.get('title') or t.get('filename') or ''
            rows.append(f"{C_VIOLET}{k}{C_RESET} {C_GRAY}{title}{C_RESET}")
        while len(rows) < 4:
            rows.append('')
        rows.append(C_LABEL + 'C cola completa' + C_RESET)
        right = f"{self.queue_index + 1}/{n}" if n else '0/0'
        return ([self._box_top(width, 'A CONTINUACIÓN', C_CYAN + right + C_RESET)]
                + [self._box_line(width, ln, C_TEXT) for ln in rows[:5]]
                + [self._box_bottom(width)])

    def _folders_box(self, width, body_rows):
        if not self.folder_names:
            return []
        per_line = 3 if width >= 80 else 1
        body_rows = max(1, body_rows)
        self._folders_body_rows = body_rows
        per_page = body_rows * per_line
        pages = max(1, math.ceil(len(self.folder_names) / per_page))
        page = max(0, min(self.folder_page, pages - 1))
        self.folder_page = page
        start = page * per_page
        chunk = self.folder_names[start:start + per_page]
        cw = max(10, (width - 4 - (per_line - 1) * 2) // per_line)
        rows = []
        for i in range(0, len(chunk), per_line):
            cells = []
            for j, name in enumerate(chunk[i:i + per_line]):
                idx = start + i + j
                count = len(self.folder_map.get(name, []))
                cell = (f"{C_VIOLET}{idx + 1}{C_RESET}{C_LABEL}.{C_RESET} "
                        f"{C_CYAN}{name}{C_RESET} {C_LABEL}({count}){C_RESET}")
                cells.append(_fit_ansi(cell, cw))
            rows.append('  '.join(cells))
        while len(rows) < body_rows:
            rows.append('')
        if self.folder_input:
            right = C_YELLOW + '#' + self.folder_input + C_RESET + C_LABEL + ' Enter' + C_RESET
        else:
            right = C_PINK + f"{page + 1}/{pages}" + C_RESET
        out = [self._box_top(width, 'CARPETAS', right)]
        out += [self._box_line(width, ln, C_TEXT) for ln in rows]
        out.append(self._box_line(width, C_LABEL + 'número + Enter · [ ] página · E explorar · ? ayuda' + C_RESET, C_LABEL))
        out.append(self._box_bottom(width))
        return out

    def _status_bar(self, width):
        bits = []
        bits.append((C_GREEN if not self.force_offline else C_RED) +
                    ('● online' if not self.force_offline else '● offline') + C_RESET)
        bits.append(C_LABEL + 'shuffle ' + (C_GREEN + 'ON' + C_RESET if self.shuffle_mode
                                            else C_GRAY + 'OFF' + C_RESET))
        bits.append(C_LABEL + 'voz ' + (C_GREEN + 'ON' + C_RESET if self.voice_enabled
                                        else C_GRAY + 'OFF' + C_RESET))
        xf = f"{self.crossfade_sec:.1f}s" if self.crossfade_sec > 0 else 'off'
        bits.append(C_LABEL + 'xfade ' + C_CYAN + xf + C_RESET)
        if self.mood:
            bits.append(C_PINK + 'mood:' + str(self.mood) + C_RESET)
        if self.folder_input:
            bits.append(C_YELLOW + 'carpeta #' + self.folder_input + C_RESET)
        bits.append(C_BOLD + '? ayuda' + C_RESET)
        line = '  ' + C_LABEL + ' · '.join(bits) + C_RESET
        return _fit_ansi(line, width, ellipsis=False)

    def _help_screen(self, lay):
        w = lay['total']
        inner = max(10, w - 4)
        half = (inner - 2) // 2
        left = [
            f"{C_BOLD}ESPACIO{C_RESET} pausa / reanudar",
            f"{C_BOLD}N{C_RESET} / {C_BOLD}B{C_RESET} siguiente / anterior",
            f"{C_BOLD}←{C_RESET} / {C_BOLD}→{C_RESET} ±10 segundos",
            f"{C_BOLD}S{C_RESET} shuffle",
            f"{C_BOLD}F{C_RESET} favorito",
            f"{C_BOLD}X{C_RESET} crossfade",
        ]
        right = [
            f"{C_BOLD}E{C_RESET} explorar carpetas",
            f"{C_BOLD}C{C_RESET} / {C_BOLD}H{C_RESET} cola / historial",
            f"{C_BOLD}/{C_RESET} buscar",
            f"{C_BOLD}T{C_RESET} todo el dispositivo",
            f"{C_BOLD}A{C_RESET} auto-dj",
            f"{C_BOLD}M{C_RESET} mood",
        ]
        merged = self._merge_cols(
            [_pad_ansi(_fit_ansi(ln, half), half) for ln in left],
            [_pad_ansi(_fit_ansi(ln, half), half) for ln in right], 2)
        out = [self._box_top(w, 'AYUDA', C_PINK + '? cerrar' + C_RESET)]
        out += [self._box_line(w, ln, C_TEXT) for ln in merged]
        out.append(self._box_line(w, C_LABEL + 'V voz · Z comando de voz · Q salir' + C_RESET, C_LABEL))
        out.append(self._box_bottom(w))
        return out

    def _list_box(self, width, title, items, right='', hint='', rows_avail=12):
        rows_avail = max(3, rows_avail)
        body = list(items)[:rows_avail - 1]
        while len(body) < rows_avail - 1:
            body.append('')
        out = [self._box_top(width, title, right)]
        out += [self._box_line(width, ln, C_TEXT) for ln in body]
        out.append(self._box_line(width, hint or '', C_LABEL))
        out.append(self._box_bottom(width))
        return out

    def _emit(self, lines, footer=''):
        rows = shutil.get_terminal_size((100, 30)).lines
        limit = max(1, rows - (1 if footer else 0))
        out = list(lines)[:limit]
        if footer:
            out.append(footer)
        sys.stdout.write('\033[H\033[J' + '\n'.join(out))
        sys.stdout.flush()

    def render_ui(self):
        lay = self._layout()
        rows = shutil.get_terminal_size((100, 30)).lines
        status = self.mixer.get_status()

        if self.show_help:
            self._emit(self._help_screen(lay), self._status_bar(lay['total']))
            return

        if self.search_active:
            items = []
            for i, t in enumerate(self.search_results[:10]):
                title = t.get('title') or t.get('filename') or ''
                artist = t.get('artist') or t.get('folder') or ''
                mark = C_GREEN + '▸ ' + C_RESET if i == 0 else '  '
                items.append(mark + C_VIOLET + title + C_RESET + '  ' + C_LABEL + '· ' + artist + C_RESET)
            head = C_BOLD + 'Buscar: ' + C_RESET + C_CYAN + self.search_query + C_LABEL + '_' + C_RESET
            box = self._list_box(lay['total'], 'BUSCAR', [head] + items,
                                 C_CYAN + f"{len(self.search_results)}" + C_RESET,
                                 'Enter reproduce el primero · Esc cancela',
                                 rows_avail=max(4, rows - 5))
            self._emit(box, self._status_bar(lay['total']))
            return

        if self.mode != 'main':
            self._emit(self._alt_screen(lay, rows), self._status_bar(lay['total']))
            return

        out = self._brand_box(lay['total'], status) + ['']
        np_box = self._np_box(lay['left'])
        q_box = self._queue_box(lay['right']) if lay['two'] else []
        if lay['two']:
            out += self._merge_cols(np_box, q_box, 2)
        else:
            out += np_box + q_box
        free = rows - len(out) - 3
        if self.folder_names and free >= 4:
            out += [''] + self._folders_box(lay['total'], free - 2)
        self._emit(out, self._status_bar(lay['total']))

    def _alt_screen(self, lay, rows):
        w = lay['total']
        avail = max(3, rows - 4)
        if self.mode == 'browse':
            if self.browse_level == 'folders':
                names = self.folder_names
                per = max(1, avail - 3)
                page = (self.browse_sel // per) if names else 0
                self.browse_page = page
                vis = names[page * per:(page + 1) * per]
                items = []
                for rel, f in enumerate(vis):
                    idx = page * per + rel
                    mark = C_GREEN + '▸ ' + C_RESET if idx == self.browse_sel else '  '
                    count = len(self.folder_map.get(f, []))
                    items.append(mark + C_VIOLET + f + C_RESET + C_LABEL + f' ({count})' + C_RESET)
                pages = max(1, math.ceil(len(names) / per)) if names else 1
                return self._list_box(w, 'EXPLORAR · carpetas', items,
                                      C_PINK + f"{page + 1}/{pages}" + C_RESET,
                                      '↑↓ mover · → abrir · Enter reproducir · Esc volver', avail)
            name = self.browse_folder or ''
            per = max(1, avail - 3)
            page = (self.browse_sel // per) if self.browse_tracks else 0
            self.browse_page = page
            vis = self.browse_tracks[page * per:(page + 1) * per]
            items = []
            for rel, t in enumerate(vis):
                idx = page * per + rel
                title = t.get('title') or t.get('filename') or ''
                mark = C_GREEN + '▸ ' + C_RESET if idx == self.browse_sel else '  '
                items.append(mark + C_VIOLET + title + C_RESET)
            return self._list_box(w, 'EXPLORAR · ' + name, items,
                                  C_CYAN + f"{len(self.browse_tracks)}" + C_RESET,
                                  '← carpeta · Enter reproducir · Esc salir', avail)

        if self.mode == 'queue':
            items = []
            n = len(self.current_queue)
            for k in range(1, 30):
                idx = self.queue_index + k
                if idx >= n:
                    break
                t = self.current_queue[idx]
                items.append(C_VIOLET + f'{k:>2}' + C_RESET + '  ' +
                             (t.get('title') or t.get('filename') or ''))
            if not items:
                items = [C_LABEL + '(sin mas pistas en cola)' + C_RESET]
            return self._list_box(w, 'COLA', items, C_CYAN + f"{n}" + C_RESET,
                                  'Espacio pausa · Esc vuelve', avail)

        if self.mode == 'history':
            items = []
            for i, t in reversed(list(enumerate(self.history[-14:]))):
                title = t.get('title') or t.get('filename') or ''
                items.append(C_VIOLET + f'{i + 1:>2}' + C_RESET + '  ' + C_GRAY + title + C_RESET)
            if not items:
                items = [C_LABEL + '(historial vacio)' + C_RESET]
            return self._list_box(w, 'HISTORIAL', items, C_YELLOW + f"{len(self.history)}" + C_RESET,
                                  'Esc vuelve al inicio', avail)

        return self._list_box(w, 'VIOLETA', [C_LABEL + '...' + C_RESET], '', '', avail)

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
        self.folder_input = ''

    # ---------------------------------------------------------------- run --

    def _read_key(self):
        """Lee UNA tecla sin read-ahead del buffer de Python (soporta UTF-8)."""
        fd = sys.stdin.fileno()
        data = os.read(fd, 1)
        if not data:
            return ''
        lead = data[0]
        extra = 3 if lead >= 0xF0 else 2 if lead >= 0xE0 else 1 if lead >= 0xC0 else 0
        for _ in range(extra):
            r, _, _ = select.select([fd], [], [], 0.02)
            if not r:
                break
            data += os.read(fd, 1)
        return data.decode('utf-8', 'ignore')

    def _read_escape_seq(self):
        """Lee una secuencia de escape completa (p.ej. [A, [5~) y la devuelve."""
        fd = sys.stdin.fileno()
        r, _, _ = select.select([fd], [], [], 0.05)
        if not r:
            return ''
        first = os.read(fd, 1).decode('utf-8', 'ignore')
        if first not in ('[', 'O'):
            return first
        seq = first
        while len(seq) < 8:
            r, _, _ = select.select([fd], [], [], 0.05)
            if not r:
                break
            c = os.read(fd, 1).decode('utf-8', 'ignore')
            seq += c
            if '@' <= c <= '~':
                break
        return seq

    def _page_folders(self, delta):
        if not self.folder_names:
            return
        if not hasattr(self, '_folders_body_rows'):
            rows = shutil.get_terminal_size((100, 30)).lines
            per_line = 3 if self._layout()['total'] >= 80 else 1
            body_rows = max(4, rows - 15) - 2
        else:
            per_line = 3 if self._layout()['total'] >= 80 else 1
            body_rows = self._folders_body_rows
        per_page = max(1, body_rows) * per_line
        pages = max(1, math.ceil(len(self.folder_names) / per_page))
        self.folder_page = max(0, min(self.folder_page + delta, pages - 1))

    def run(self):
        self.setup()
        old_settings = termios.tcgetattr(sys.stdin)
        sys.stdout.write('\033[?1049h')   # buffer alternativo (no ensucia scrollback)
        sys.stdout.write('\033[?25l')     # oculta cursor
        sys.stdout.flush()
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

                rlist, _, _ = select.select([sys.stdin.fileno()], [], [], 0.5)
                if not rlist:
                    continue
                ch = self._read_key()

                # --- Buscador activo ---
                if self.search_active:
                    if ch in ('\x7f', '\x08'):
                        self.search_query = self.search_query[:-1]
                        self.update_search()
                    elif ch in ('\r', '\n'):
                        self.commit_search()
                    elif ch == '\x1b':
                        self._read_escape_seq()
                        self.cancel_transient()
                    elif ch.isprintable():
                        self.search_query += ch
                        self.update_search()
                    continue

                # --- Ayuda (? para alternar) ---
                if ch == '?':
                    self.show_help = not self.show_help
                    self.mode = 'main'
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
                elif ch in ('[', ']'):
                    self._page_folders(-1 if ch == '[' else 1)
                elif ch == '\x1b':
                    seq = self._read_escape_seq()
                    if not seq:
                        self.cancel_transient()
                        continue
                    if self.mode == 'browse':
                        if seq == '[A':
                            self.browse_move(-1)
                        elif seq == '[B':
                            self.browse_move(1)
                        elif seq == '[C':
                            self.browse_expand()
                        elif seq == '[D':
                            self.browse_collapse()
                        elif seq in ('[5~',):
                            self.browse_move(-8)
                        elif seq in ('[6~',):
                            self.browse_move(8)
                    elif self.mode in ('queue', 'history'):
                        if seq in ('[D', 'q', '\x1b'):
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
                        elif seq == '[5~':
                            self._page_folders(-1)
                        elif seq == '[6~':
                            self._page_folders(1)
                elif self.mode == 'browse':
                    if ch in ('\r', '\n'):
                        self.browse_play()
                    elif ch in ('q', 'Q'):
                        self.mode = 'main'
                elif self.mode in ('queue', 'history'):
                    if ch == ' ':
                        self.mixer.toggle_pause()
                    elif ch in ('q', 'Q'):
                        self.mode = 'main'
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
                    elif ch.isdigit():
                        self.folder_input = (self.folder_input + ch)[-3:]
                    elif ch in ('\r', '\n'):
                        if self.folder_input:
                            idx = int(self.folder_input) - 1
                            self.folder_input = ''
                            self.play_folder_by_index(idx)
                    elif ch in ('q', 'Q'):
                        self.running = False
                        break
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            sys.stdout.write('\033[?25h\033[?1049l')
            sys.stdout.flush()
            self.mixer.stop()
            self.save_state()
            print("\nVioleta cerrada. Hasta luego.")


if __name__ == "__main__":
    offline_mode = "--offline" in sys.argv
    rescan_mode = "--rescan" in sys.argv
    app = DJLiviApp(force_offline=offline_mode, rescan=rescan_mode)
    app.run()