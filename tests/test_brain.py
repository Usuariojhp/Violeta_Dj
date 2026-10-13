"""Tests del cerebro: parseo JSON, cadena de proveedores y fallback."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dj_brain import DJBrain  # noqa: E402


def _brain(**kwargs):
    brain = DJBrain(**kwargs)
    brain.enabled = True
    return brain


def test_extract_json_variants():
    assert DJBrain._extract_json('{"a": 1}') == {"a": 1}
    assert DJBrain._extract_json('```json\n{"a": 2}\n```') == {"a": 2}
    assert DJBrain._extract_json('texto {"b": "x"} mas texto') == {"b": "x"}
    assert DJBrain._extract_json('nada de json') is None
    assert DJBrain._extract_json('{"roto": ') is None
    assert DJBrain._extract_json('') is None
    assert DJBrain._extract_json(None) is None


def test_deshabilitado_sin_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    brain = DJBrain(provider="google")
    assert brain.enabled is False
    assert brain._ask_json("hola") is None
    assert brain.track_intro_line({"path": "x.mp3"}) is None
    assert brain.status_info()["enabled"] is False


def test_track_intro_usa_llm(monkeypatch, tmp_path):
    monkeypatch.setattr("dj_brain.CACHE_DIR", str(tmp_path))
    llamadas = []
    brain = _brain()
    brain._cache_path = str(tmp_path / "livi_lines.json")

    def fake_call(prompt, max_tokens=200):
        llamadas.append(prompt)
        return '{"line": "Arrancamos con todo, esto es puro rock."}'

    brain._call_provider = fake_call
    line = brain.track_intro_line({"path": "p.mp3", "artist": "Soda",
                                   "title": "Musica", "bpm": 120,
                                   "key": "D minor"})
    assert line == "Arrancamos con todo, esto es puro rock."
    assert "Soda" in llamadas[0]

    # segunda llamada con la misma pista: sale del cache, no vuelve al LLM
    brain2 = _brain()
    brain2._cache_path = str(tmp_path / "livi_lines.json")
    assert brain2.track_intro_line({"path": "p.mp3"}) == \
        "Arrancamos con todo, esto es puro rock."


def test_parse_request_valida_acciones():
    brain = _brain()
    brain._call_provider = lambda p, max_tokens=200: json.dumps({
        "action": "play_mood", "mood": "enfoque", "query": None,
        "minutes": 45, "reply": "Modo enfoque activado."})
    data = brain.parse_request("poneme algo para estudiar")
    assert data["action"] == "play_mood"
    assert data["mood"] == "enfoque"
    assert data["minutes"] == 45


def test_parse_request_rechaza_accion_invalida():
    brain = _brain()
    brain._call_provider = lambda p, max_tokens=200: '{"action": "borrar_todo"}'
    assert brain.parse_request("borrar todo") is None


def test_fallback_cuando_el_proveedor_falla():
    brain = _brain()

    def falla(prompt, max_tokens=200):
        raise RuntimeError("sin internet")

    brain._call_provider = falla
    assert brain.track_intro_line({"path": "z.mp3"}) is None
    assert brain.parse_request("pone rock") is None
    assert brain.chat_reply("hola") is None


def test_cache_persistente(monkeypatch, tmp_path):
    cache_file = tmp_path / "livi_lines.json"
    monkeypatch.setattr("dj_brain.CACHE_DIR", str(tmp_path))
    brain = _brain()
    brain._cache_path = str(cache_file)
    brain._call_provider = lambda p, max_tokens=200: '{"line": "Seguimos."}'
    brain.track_intro_line({"path": "final.mp3"})
    assert cache_file.exists()
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    assert data["intro|final.mp3"] == ["Seguimos."]
