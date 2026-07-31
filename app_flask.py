"""app_flask.py
Servidor Flask que sirve el visor Leaflet y expone alerts.geojson
como una API REST. Rutas absolutas para funcionar desde cualquier
directorio de ejecución.
"""

import os
import json
import re

import requests
from flask import Flask, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
GEOJSON_PATH = os.path.join(BASE_DIR, "alerts.geojson")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

app = Flask(
    __name__,
    template_folder=TEMPLATES_DIR,
    static_folder=STATIC_DIR,
    static_url_path="/static",
)


def _extract_geojson_from_text(text: str):
    """Intenta extraer un bloque GeoJSON válido del texto devuelto por Ollama."""
    if not text:
        return None

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        candidate = match.group(1)
    else:
        candidate = text.strip()

    if not candidate.startswith("{"):
        return None

    try:
        data = json.loads(candidate)
        if isinstance(data, dict) and "type" in data:
            return data
    except Exception:
        pass

    return None


@app.route("/")
def index():
    try:
        return render_template("index.html")
    except Exception as e:
        return (
            "<h1>Plantilla no encontrada</h1>"
            "<p>Verifica que exista <code>templates/index.html</code></p>"
            f"<p>Detalle: {e}</p>"
        ), 500


@app.route("/ollama")
def ollama_page():
    return render_template("ollama.html")


@app.route("/api/geojson")
def geojson():
    if not os.path.exists(GEOJSON_PATH):
        return jsonify({
            "error": f"No se encontró {os.path.basename(GEOJSON_PATH)}",
            "type": "FeatureCollection",
            "features": [],
        }), 404
    try:
        with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except json.JSONDecodeError as e:
        return jsonify({"error": f"GeoJSON inválido: {e}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/geolocate", methods=["POST"])
def geolocate():
    """Endpoint que usa el modelo GeoBERT para geolocalizar un texto."""
    from ai_geolocator import GeoLocator  # import lazy
    body = request.get_json(silent=True) or {}
    text = body.get("text", "")
    if not text:
        return jsonify({"error": "Falta el campo 'text'"}), 400

    locator = GeoLocator(model_dir=os.path.join(BASE_DIR, "models", "geobert"))
    result = locator.predict(text)
    return jsonify(result)


@app.route("/api/stats")
def stats():
    """Estadísticas básicas del GeoJSON actual."""
    if not os.path.exists(GEOJSON_PATH):
        return jsonify({"error": "alerts.geojson no existe", "count": 0}), 404
    try:
        with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        features = data.get("features", []) or []
        sevs = []
        for feat in features:
            try:
                sevs.append(int(feat.get("properties", {}).get("severity", 0)))
            except Exception:
                pass
        return jsonify({
            "count": len(features),
            "avg_severity": (sum(sevs) / len(sevs)) if sevs else 0,
            "max_severity": max(sevs) if sevs else 0,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ollama", methods=["POST"])
def ollama_generate():
    """Usa Ollama para convertir un batch GeoJSON + prompt en un GeoJSON resultante."""
    if "file" not in request.files and "files" not in request.files:
        return jsonify({"error": "Debes adjuntar al menos un archivo GeoJSON."}), 400

    prompt = request.form.get("prompt", "").strip()
    model = request.form.get("model", "llama3.1").strip() or "llama3.1"

    files = request.files.getlist("files") or [request.files["file"]]
    valid_files = [f for f in files if f and f.filename]

    if not valid_files:
        return jsonify({"error": "No se encontró ningún archivo válido."}), 400

    geojson_batches = []
    for uploaded in valid_files:
        try:
            raw = uploaded.read()
            if not raw:
                continue
            data = json.loads(raw.decode("utf-8"))
            if isinstance(data, dict) and "features" in data:
                geojson_batches.append(data)
            else:
                return jsonify({"error": f"El archivo {uploaded.filename} no parece un GeoJSON válido."}), 400
        except Exception as e:
            return jsonify({"error": f"No se pudo leer {uploaded.filename}: {e}"}), 400

    if not geojson_batches:
        return jsonify({"error": "No se pudo extraer ningún FeatureCollection válido."}), 400

    combined_features = []
    for batch in geojson_batches:
        for feature in batch.get("features", []) or []:
            combined_features.append(feature)

    base_geojson = {"type": "FeatureCollection", "features": combined_features}
    base_json = json.dumps(base_geojson, ensure_ascii=False, indent=2)

    if not prompt:
        prompt = (
            "Analiza este GeoJSON de alertas. Identifica los sitios geográficos relevantes "
            "y devuelve únicamente un GeoJSON válido FeatureCollection con features de tipo Point "
            "y propiedades con 'name', 'country', 'lat', 'lon', 'source' y 'confidence'. "
            "No agregues texto fuera del GeoJSON."
        )

    request_payload = {
        "model": model,
        "prompt": f"{prompt}\n\nGEOJSON DE ENTRADA:\n{base_json}",
        "stream": False,
        "options": {"temperature": 0.2},
    }

    try:
        response = requests.post(f"{OLLAMA_URL}/api/generate", json=request_payload, timeout=120)
        response.raise_for_status()
        payload = response.json()
        result_text = (payload.get("response") or "").strip()
    except Exception as e:
        return jsonify({"error": f"No se pudo contactar a Ollama en {OLLAMA_URL}: {e}"}), 502

    parsed = _extract_geojson_from_text(result_text)
    if parsed is None:
        return jsonify({
            "error": "Ollama respondió, pero no devolvió un GeoJSON válido.",
            "raw_response": result_text,
            "model": model,
        }), 400

    if not isinstance(parsed, dict) or parsed.get("type") != "FeatureCollection":
        return jsonify({
            "error": "La respuesta no cumple con el formato FeatureCollection de GeoJSON.",
            "raw_response": result_text,
            "model": model,
        }), 400

    return jsonify({
        "model": model,
        "result": parsed,
        "feature_count": len(parsed.get("features", [])),
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
