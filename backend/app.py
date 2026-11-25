"""
Flask backend for the Network Fault Prediction / Root Cause Analysis
dashboard. Exposes the live simulation (see backend/simulation.py) and the
reconstructed topology (rca/topology.py) as a small JSON API; frontend/ is
served as static files.

Run with:  python backend/app.py
(requires a trained model -- see README "Instructions to train the LSTM")
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

import config
from rca import topology as T
from backend.serialize import to_native

FRONTEND_DIR = os.path.join(config.PROJECT_ROOT, "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)

_engine = None
_engine_error = None


def get_engine():
    global _engine, _engine_error
    if _engine is None and _engine_error is None:
        try:
            from backend.simulation import SimulationEngine
            _engine = SimulationEngine()
        except Exception as e:  # noqa: BLE001 - surface any startup failure to the API
            _engine_error = str(e)
    return _engine, _engine_error


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/api/health")
def health():
    engine, err = get_engine()
    if err:
        return jsonify({"ready": False, "error": err}), 503
    return jsonify({"ready": True})


@app.route("/api/devices")
def devices():
    engine, err = get_engine()
    if err:
        return jsonify({"error": err}), 503
    return jsonify({"devices": engine.available_devices, "current_device": engine.device})


@app.route("/api/topology")
def topology():
    g = T.build_topology_graph()
    nodes = [{"id": n, **{k: v for k, v in attrs.items()}} for n, attrs in g.nodes(data=True)]
    edges = [{"source": u, "target": v} for u, v in g.edges()]
    return jsonify(to_native({"nodes": nodes, "edges": edges}))


@app.route("/api/state")
def state():
    engine, err = get_engine()
    if err:
        return jsonify({"error": err}), 503
    return jsonify(engine.state())


@app.route("/api/tick", methods=["POST"])
def tick():
    engine, err = get_engine()
    if err:
        return jsonify({"error": err}), 503
    n = int(request.json.get("steps", 1)) if request.is_json else 1
    result = engine.state()
    for _ in range(max(1, n)):
        result = engine.step()
        if result.get("finished"):
            break
    return jsonify(result)


@app.route("/api/reset", methods=["POST"])
def reset():
    engine, err = get_engine()
    if err:
        return jsonify({"error": err}), 503
    device = None
    if request.is_json:
        device = request.json.get("device")
    return jsonify(engine.reset(device))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
