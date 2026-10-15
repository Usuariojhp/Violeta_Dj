#!/data/data/com.termux/files/usr/bin/bash
# =============================================================================
#  🎧 VIOLETA / AI DJ — Launcher unificado (web + bot) en tmux
#  Uso:
#    bash start_violeta.sh start        → arranca DJ web + asegura el bot
#    bash start_violeta.sh stop         → detiene el DJ web (el bot queda)
#    bash start_violeta.sh restart      → reinicia todo
#    bash start_violeta.sh status       → estado de sesiones
#    bash start_violeta.sh logs         → logs del DJ en vivo (Ctrl+C para salir)
#    bash start_violeta.sh attach       → consola del DJ (Ctrl+B luego D para salir)
#    bash start_violeta.sh ip           → IP local y URL del reproductor
# =============================================================================

TMUX_SESSION="violeta"
BOT_SESSION="tg_bot"
VIOLETA_DIR="$(cd "$(dirname "$0")" && pwd)"
DJ_SCRIPT="$VIOLETA_DIR/web_dj.py"
DJ_LOG="$VIOLETA_DIR/web.log"
BOT_CTRL="/data/data/com.termux/files/home/telegram_bot/bot_control.sh"

# Python de Termux (con mutagen + syncedlyrics + mpv); si no existe, cualquiera
PY_TERMUX="/data/data/com.termux/files/usr/bin/python3"
if [ -x "$PY_TERMUX" ]; then PY="$PY_TERMUX"; else PY="$(command -v python3)"; fi

PORT="${VIOLETA_PORT:-8000}"

enable_wakelock() {
    if command -v termux-wake-lock >/dev/null 2>&1; then
        termux-wake-lock
    fi
}

get_lan_ip() {
    if command -v ip >/dev/null 2>&1; then
        ip -4 addr show scope global 2>/dev/null | awk '/inet /{sub(/\/.*/,"",$2); print $2}' | grep -v '^127\.' | head -1
    fi
}

start() {
    if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        echo "🎧 Violeta ya está corriendo (sesión tmux '$TMUX_SESSION')."
        echo "   Ver en vivo: bash start_violeta.sh attach"
        status
        return
    fi

    echo "🔋 Activando Wake-Lock de Termux..."
    enable_wakelock

    echo "🔄 Generando iconos PWA (si hace falta)..."
    "$PY" - "$VIOLETA_DIR" <<'PYEOF'
import os, sys
sys.path.insert(0, sys.argv[1])
from pwa_assets import ensure_pwa_assets
ensure_pwa_assets(sys.argv[1])
print("   ✓ Iconos listos en", os.path.join(sys.argv[1], "pwa_icons"))
PYEOF

    echo "🚀 Iniciando Violeta en sesión independiente de tmux ($TMUX_SESSION)..."
    tmux new-session -d -s "$TMUX_SESSION" "bash -c 'while true; do \"$PY\" -u \"$DJ_SCRIPT\" --port=$PORT >> \"$DJ_LOG\" 2>&1; echo \"[$(date '+%Y-%m-%d %H:%M:%S')] Violeta se detuvo. Reiniciando en 3s...\" >> \"$DJ_LOG\"; sleep 3; done'"

    sleep 4

    if ! tmux has-session -t "$BOT_SESSION" 2>/dev/null; then
        echo "🤖 El bot no estaba activo, arrancándolo..."
        bash "$BOT_CTRL" start 2>&1 | sed 's/^/   /'
    fi

    echo ""
    echo "✅ ¡Violeta iniciada con éxito!"
    print_urls
    echo ""
    echo "   📄 Logs:   bash start_violeta.sh logs"
    echo "   🖥️  Consola: bash start_violeta.sh attach   (salir: Ctrl+B luego D)"
}

stop() {
    echo "🛑 Deteniendo Violeta (el bot queda activo)..."
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null
    pkill -9 -f "web_dj.py" 2>/dev/null
    pkill -9 -f "mpv --idle=yes" 2>/dev/null
    sleep 1
    echo "✅ Violeta detenida."
}

restart() {
    stop
    sleep 1
    start
}

status() {
    echo "── Estados ─────────────────────────────"
    if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        PID=$(pgrep -f "web_dj.py" | head -1)
        echo "✅ Violeta ACTIVA (sesión: $TMUX_SESSION | PID: ${PID:-iniciando})"
        print_urls
    else
        echo "⛔ Violeta DETENIDA — inicia con: bash start_violeta.sh start"
    fi
    if tmux has-session -t "$BOT_SESSION" 2>/dev/null; then
        echo "✅ Bot de Telegram ACTIVO (sesión: $BOT_SESSION)"
    else
        echo "⛔ Bot de Telegram DETENIDO — bash bot_control.sh start"
    fi
}

print_urls() {
    IP=$(get_lan_ip)
    if [ -n "$IP" ]; then
        echo "   📱 Desde tu celular (misma red WiFi):"
        echo "      http://$IP:$PORT"
    fi
    echo "   💻 En el mismo equipo:"
    echo "      http://localhost:$PORT"
}

show_logs() {
    [ -f "$DJ_LOG" ] || { echo "⚠️  No existe $DJ_LOG aún."; return; }
    echo "📄 Logs de Violeta en vivo (Ctrl+C para salir):"
    echo "──────────────────────────────────────────────────"
    tail -f "$DJ_LOG"
}

attach_tmux() {
    if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        echo "💡 Salir sin cerrar: Ctrl+B y luego D"
        sleep 1
        tmux attach-session -t "$TMUX_SESSION"
    else
        echo "⚠️  No hay sesión activa. bash start_violeta.sh start"
    fi
}

show_ip() {
    echo "🌐 IP local: $(get_lan_ip)"
    echo "🎧 URL del reproductor: http://$(get_lan_ip):$PORT (en el celular lista la web DJ)"
}

case "$1" in
    start)    start ;;
    stop)     stop ;;
    restart)  restart ;;
    status)   status ;;
    logs)     show_logs ;;
    attach)   attach_tmux ;;
    ip)       show_ip ;;
    *)
        echo ""
        echo "  🎧 Violeta — Comandos:"
        echo "  ────────────────────────────────────────────"
        echo "  bash start_violeta.sh start    → Arrancar DJ web + asegurar bot"
        echo "  bash start_violeta.sh stop     → Detener DJ web (bot sigue)"
        echo "  bash start_violeta.sh restart  → Reiniciar todo"
        echo "  bash start_violeta.sh status   → Estado"
        echo "  bash start_violeta.sh logs     → Logs en vivo (Ctrl+C)"
        echo "  bash start_violeta.sh attach   → Consola (Ctrl+B luego D)"
        echo "  bash start_violeta.sh ip       → IP y URL"
        echo "  ────────────────────────────────────────────"
        echo ""
        ;;
esac