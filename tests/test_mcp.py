"""Tests del servidor MCP: protocolo stdio + mapeo de tools."""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dj_mcp  # noqa: E402


def _responde_tools_list():
    resp = dj_mcp.handle({
        "jsonrpc": "2.0", "id": 1, "method": "tools/list",
        "params": {"reason": "test"}})
    assert resp["result"]["tools"]
    names = [t["name"] for t in resp["result"]["tools"]]
    assert "dj_status" in names and "dj_ask" in names


def test_protocolo_initialize():
    resp = dj_mcp.handle({"jsonrpc": "2.0", "id": 1,
                          "method": "initialize",
                          "params": {"protocolVersion": "2024-11-05"}})
    assert resp["result"]["serverInfo"]["name"] == "violeta-dj"
    assert resp["result"]["capabilities"]["tools"] == {}


def test_notificaciones_sin_respuesta():
    assert dj_mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert dj_mcp.handle({"jsonrpc": "2.0", "method": "initialized"}) is None


def test_metodo_desconocido():
    resp = dj_mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "recursos/list"})
    assert resp["error"]["code"] == -32601


def test_tool_desconocida():
    resp = dj_mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                          "params": {"name": "dj_nada", "arguments": {}}})
    assert resp["result"]["isError"] is True
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert "error" in payload


def test_tools_hablan_con_la_api(monkeypatch):
    vistas = []

    def fake_http(method, path, payload=None):
        vistas.append((method, path, payload))
        if path == "/api/status":
            return {"playing": True, "track": {"title": "Musica"}}
        if path == "/api/brain":
            return {"enabled": True, "provider": "google"}
        return {"ok": True}

    monkeypatch.setattr(dj_mcp, "_http", fake_http)

    for method, path, payload in [
        ("POST", "/api/mood", {"mood": "fiesta"}),
        ("POST", "/api/enqueue", {"minutes": 30, "mood": "chill",
                                  "terms": None}),
        ("POST", "/api/ask", {"request": "pone rock"}),
        ("POST", "/api/say", {"text": "hola"}),
        ("POST", "/api/next", None),
        ("GET", "/api/status", None),
    ]:
        resp = dj_mcp.handle({"jsonrpc": "2.0", "id": 9,
                              "method": "tools/call",
                              "params": {"name": _tool_of(path),
                                         "arguments": payload or {}}})
        assert resp["result"]["isError"] is False

    status = dj_mcp.call_tool("dj_status", {})
    assert status["playing"] is True
    brain = dj_mcp.call_tool("dj_brain", {})
    assert brain["provider"] == "google"
    assert ("POST", "/api/mood", {"mood": "fiesta"}) in vistas


def _tool_of(path):
    return {
        "/api/mood": "dj_mood",
        "/api/enqueue": "dj_enqueue",
        "/api/ask": "dj_ask",
        "/api/say": "dj_say",
        "/api/next": "dj_skip",
        "/api/status": "dj_status",
    }[path]


def test_error_de_conexion_se_mapea(monkeypatch):
    def sin_conexion(method, path, payload=None):
        return {"error": "no se pudo contactar"}

    monkeypatch.setattr(dj_mcp, "_http", sin_conexion)
    resp = dj_mcp.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                          "params": {"name": "dj_status", "arguments": {}}})
    assert resp["result"]["isError"] is True
