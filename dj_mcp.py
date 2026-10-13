#!/usr/bin/env python3
"""
dj_mcp.py - Servidor MCP (stdio) que expone OmniPlayer / AI DJ como
herramientas para agentes (opencode, Claude Code, etc.).

Habla con la API HTTP del reproductor (web_dj.py) en DJ_API_URL.
Requisito: web_dj.py corriendo (python3 web_dj.py). El servidor no depende
de ninguna libreria externa: solo stdlib.
"""
import os
import sys
import json
import urllib.request
import urllib.error

DJ_API_URL = os.environ.get("DJ_API_URL", "http://127.0.0.1:5000").rstrip("/")


def _http(method, path, payload=None):
    url = DJ_API_URL + path
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.URLError as exc:
        return {"error": "no se pudo contactar al reproductor (%s): %s"
                % (url, exc)}
    try:
        return json.loads(body)
    except Exception:
        return {"raw": body}


TOOLS = [
    {
        "name": "dj_status",
        "description": "Estado actual del reproductor: pista sonando, cola, "
                       "mood, si el cerebro Livi esta activo.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "dj_library",
        "description": "Biblioteca: carpetas y pistas disponibles.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "dj_brain",
        "description": "Estado del cerebro LLM (proveedor, modelo, "
                       "habilitado o no).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "dj_queue",
        "description": "Cola actual en orden, con mood e info del set.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "dj_mood",
        "description": "Cambia el mood y rearma la cola automaticamente.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mood": {"type": "string",
                         "enum": ["chill", "energico", "fiesta", "enfoque"]},
            },
            "required": ["mood"],
        },
    },
    {
        "name": "dj_enqueue",
        "description": "Arma un set armónico de N minutos en un mood y "
                       "opcionalmente con terminos de busqueda.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "minutes": {"type": "number", "default": 45},
                "mood": {"type": "string"},
                "terms": {"type": "string",
                          "description": "ej: rock, salsa, nomegusta"},
            },
        },
    },
    {
        "name": "dj_ask",
        "description": "Peticion en lenguaje natural: 'pone algo tranqui "
                       "para estudiar', 'subi el volumen'.",
        "inputSchema": {
            "type": "object",
            "properties": {"request": {"type": "string"}},
            "required": ["request"],
        },
    },
    {
        "name": "dj_say",
        "description": "Hace que Livi diga un texto por la mezcla.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "dj_skip",
        "description": "Pasa a la siguiente pista (con crossfade).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "dj_prev",
        "description": "Vuelve a la pista anterior.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "dj_toggle_pause",
        "description": "Pausa o reanuda la reproduccion.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "dj_play_all",
        "description": "Reproduce toda la biblioteca.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def call_tool(name, arguments):
    args = arguments or {}
    if name == "dj_status":
        return _http("GET", "/api/status")
    if name == "dj_library":
        data = _http("GET", "/api/library")
        folders = data.get("folders") or {}
        tracks = data.get("tracks") or []
        return {"folder_count": len(folders),
                "track_count": len(tracks),
                "folders": list(folders.keys())[:30],
                "sample_tracks": [
                    {"id": t.get("id"),
                     "title": t.get("title") or t.get("filename"),
                     "artist": t.get("artist"),
                     "folder": t.get("folder"),
                     "energy": t.get("energy")}
                    for t in tracks[:25]]}
    if name == "dj_brain":
        return _http("GET", "/api/brain")
    if name == "dj_queue":
        return _http("GET", "/api/queue")
    if name == "dj_mood":
        return _http("POST", "/api/mood", {"mood": args.get("mood")})
    if name == "dj_enqueue":
        return _http("POST", "/api/enqueue", {
            "minutes": args.get("minutes", 45),
            "mood": args.get("mood"),
            "terms": args.get("terms"),
        })
    if name == "dj_ask":
        return _http("POST", "/api/ask", {"request": args.get("request", "")})
    if name == "dj_say":
        return _http("POST", "/api/say", {"text": args.get("text", "")})
    if name == "dj_skip":
        return _http("POST", "/api/next")
    if name == "dj_prev":
        return _http("POST", "/api/prev")
    if name == "dj_toggle_pause":
        return _http("POST", "/api/toggle_pause")
    if name == "dj_play_all":
        return _http("POST", "/api/play_all")
    return {"error": "tool desconocida: %s" % name}


# --------------------------------------------------------------- protocolo MCP
def _send(payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(b"Content-Length: %d\r\n\r\n" % len(body))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def _read_message():
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        if b":" in line:
            key, _, value = line.partition(b":")
            headers[key.strip().lower()] = value.strip()
    length = int(headers.get(b"content-length", b"0"))
    if length <= 0:
        return None
    raw = sys.stdin.buffer.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def handle(message):
    if not isinstance(message, dict):
        return None
    method = message.get("method")
    msg_id = message.get("id")

    if method == "initialize" and msg_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": message.get("params", {}).get(
                    "protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "omniplayer-dj",
                               "version": "1.0.0"},
            },
        }

    if method in ("notifications/initialized", "initialized",
                  "notifications/cancelled"):
        return None

    if method == "ping" and msg_id is not None:
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if method == "tools/list" and msg_id is not None:
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}

    if method == "tools/call" and msg_id is not None:
        params = message.get("params") or {}
        name = params.get("name")
        try:
            result = call_tool(name, params.get("arguments"))
        except Exception as exc:
            result = {"error": str(exc)}
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text",
                             "text": json.dumps(result, ensure_ascii=False,
                                                indent=2)}],
                "isError": "error" in result,
            },
        }

    if method and method.startswith("notifications/"):
        return None

    if msg_id is not None:
        return {"jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32601,
                          "message": "metodo no soportado: %s" % method}}
    return None


def main():
    while True:
        message = _read_message()
        if message is None:
            break
        response = handle(message)
        if response is not None:
            _send(response)


if __name__ == "__main__":
    main()
