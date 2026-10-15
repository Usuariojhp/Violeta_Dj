#!/data/data/com.termux/files/usr/bin/bash
# install_termux.sh - Instalador automatizado para Termux en Android

echo "================================================="
echo "🎧 INSTALANDO VIOLETA EN TU TELÉFONO"
echo "================================================="

# 1. Permisos de almacenamiento
echo "[1/4] Verificando acceso al almacenamiento..."
if [ ! -d "$HOME/storage/shared" ]; then
    echo "Por favor concede permiso de almacenamiento en el mensaje emergente..."
    termux-setup-storage
    sleep 3
fi

# 2. Actualizar paquetes e instalar python y mpv
echo "[2/4] Instalando Python y MPV..."
pkg update -y
pkg install -y python mpv

# 3. Instalar librerías de voz
echo "[3/4] Instalando Edge-TTS..."
pip install --upgrade pip
pip install edge-tts

# 4. Copiar carpeta y crear comandos binarios en el PATH
echo "[4/4] Creando comandos directos..."
mkdir -p "$HOME/violeta"
if [ -d "/sdcard/violeta" ]; then
    cp -r /sdcard/violeta/* "$HOME/violeta/"
fi

# Crear scripts ejecutables en $PREFIX/bin para que funcionen siempre sin reiniciar la terminal
cat << 'EOF' > "$PREFIX/bin/violeta"
#!/data/data/com.termux/files/usr/bin/bash
python "$HOME/violeta/ai_dj.py" "$@"
EOF
chmod +x "$PREFIX/bin/violeta"

cat << 'EOF' > "$PREFIX/bin/violeta-web"
#!/data/data/com.termux/files/usr/bin/bash
python "$HOME/violeta/web_dj.py" "$@"
EOF
chmod +x "$PREFIX/bin/violeta-web"

echo ""
echo "================================================="
echo "✔ ¡INSTALACIÓN COMPLETADA!"
echo "================================================="
echo "Puedes ejecutar directamente:"
echo "  ➔ violeta-web    (Abre http://localhost:5000 con botones táctiles)"
echo "  ➔ violeta        (Modo terminal interactivo)"
echo "================================================="