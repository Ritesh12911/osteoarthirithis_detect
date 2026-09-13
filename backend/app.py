"""
=============================================================
 OA Detection System — Flask Backend Server
 SIH 2026 | Problem Statement 26004 | MDoNER
=============================================================

 Endpoints:
   POST /api/data          ← ESP32 sends sensor readings
   GET  /api/history       ← Dashboard fetches past sessions
   GET  /api/reference     ← Normal + OA reference profiles
   GET  /api/stats         ← Summary stats
   GET  /api/timeseries    ← Time-series for a patient
   GET  /api/compare       ← Side-by-side comparison data
   GET  /api/model_info    ← ML model metadata
   POST /api/simulate      ← Simulate sensor data (demo mode)

 WebSocket Events:
   Server → Client  : 'live_data'  (every new reading)
   Server → Client  : 'alert'      (high OA risk detected)
   Client → Server  : 'subscribe'  (patient_id to watch)

 Run:
   pip install flask flask-socketio flask-cors
   python app.py
=============================================================
"""

import os
import sys

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import time
import random
import threading
import numpy as np
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS

# ─── LOCAL IMPORTS ────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database as db
import inference as inf

# ─── APP SETUP ────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=None)
app.config['SECRET_KEY'] = 'sih2026-oa-detection-secret'
CORS(app, origins="*")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard")

# Broadcast last N readings per session for dashboard charts
_live_buffer = {}   # patient_id → deque of readings (max 50)
_subscribers  = {}  # socket_id → patient_id

# ─── STARTUP ──────────────────────────────────────────────────────────────────
@app.before_request
def startup():
    pass  # init_db() called once at bottom


# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the dashboard."""
    return send_from_directory(DASHBOARD_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(DASHBOARD_DIR, filename)


@app.route("/api/data", methods=["POST"])
def receive_data():
    """
    ESP32 posts sensor JSON here every 500ms.
    Runs ML inference, stores in DB, broadcasts via WebSocket.
    """
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "No JSON received"}), 400

        # Defaults for optional fields
        data.setdefault("patient_id",      "PATIENT_001")
        data.setdefault("side",            "LEFT")
        data.setdefault("sample_idx",       0)
        data.setdefault("ambient_temp_c",  28.0)

        # Run ML inference
        result = inf.predict(data)

        # Store in database
        row_id = db.insert_session(data, result)

        # Build broadcast payload
        payload = {
            "row_id":         row_id,
            "patient_id":     data["patient_id"],
            "side":           data["side"],
            "timestamp":      datetime.utcnow().isoformat() + "Z",
            "sensors": {
                "microphone": {
                    "audio_rms":        data.get("audio_rms", 0),
                    "dominant_freq_hz": data.get("dominant_freq_hz", 0),
                    "crepitus_score":   data.get("crepitus_score", 0),
                },
                "temperature": {
                    "joint_temp_c":   data.get("joint_temp_c", 0),
                    "ambient_temp_c": data.get("ambient_temp_c", 0),
                    "temp_asymmetry": data.get("temp_asymmetry", 0),
                },
                "imu": {
                    "accel_rms_x":    data.get("accel_rms_x", 0),
                    "accel_rms_y":    data.get("accel_rms_y", 0),
                    "accel_rms_z":    data.get("accel_rms_z", 0),
                    "gyro_range_deg": data.get("gyro_range_deg", 0),
                    "step_symmetry":  data.get("step_symmetry", 0),
                },
                "flex": {
                    "flex_angle_deg": data.get("flex_angle_deg", 0),
                    "flex_stiffness": data.get("flex_stiffness", 0),
                }
            },
            "inference": result
        }

        # Broadcast to dashboard
        socketio.emit("live_data", payload)

        # Emit alert if high risk
        if result.get("risk_level") in ("HIGH", "CRITICAL"):
            socketio.emit("alert", {
                "patient_id": data["patient_id"],
                "risk_score": result["risk_score"],
                "risk_level": result["risk_level"],
                "message":    f"⚠️ OA Risk Alert for {data['patient_id']}: "
                              f"{result['risk_level']} ({result['risk_score']*100:.0f}%)"
            })

        return jsonify({
            "status":     "ok",
            "row_id":     row_id,
            "risk_score": result["risk_score"],
            "risk_level": result["risk_level"],
            "label":      result["label"],
            "confidence": result["confidence"]
        }), 200

    except Exception as e:
        print(f"[ERR] /api/data: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/history")
def get_history():
    limit      = int(request.args.get("limit", 100))
    patient_id = request.args.get("patient_id")
    rows       = db.get_history(limit=limit, patient_id=patient_id)
    return jsonify({"status": "ok", "data": rows, "count": len(rows)})


@app.route("/api/reference")
def get_reference():
    profiles = db.get_reference_profiles()
    return jsonify({"status": "ok", "data": profiles})


@app.route("/api/stats")
def get_stats():
    stats = db.get_stats()
    return jsonify({"status": "ok", "data": stats})


@app.route("/api/timeseries")
def get_timeseries():
    patient_id = request.args.get("patient_id", "PATIENT_001")
    limit      = int(request.args.get("limit", 50))
    rows       = db.get_time_series(patient_id=patient_id, limit=limit)
    return jsonify({"status": "ok", "data": rows})


@app.route("/api/compare")
def get_compare():
    """Returns current patient's latest reading vs Normal vs OA reference profiles."""
    patient_id = request.args.get("patient_id", "PATIENT_001")
    history    = db.get_history(limit=1, patient_id=patient_id)
    references = db.get_reference_profiles()

    current = {}
    if history:
        current = {
            "audio_rms":        history[0].get("audio_rms", 0),
            "dominant_freq_hz": history[0].get("dominant_freq_hz", 0),
            "crepitus_score":   history[0].get("crepitus_score", 0),
            "joint_temp_c":     history[0].get("joint_temp_c", 0),
            "temp_asymmetry":   history[0].get("temp_asymmetry", 0),
            "accel_rms_x":      history[0].get("accel_rms_x", 0),
            "gyro_range_deg":   history[0].get("gyro_range_deg", 0),
            "step_symmetry":    history[0].get("step_symmetry", 0),
            "flex_angle_deg":   history[0].get("flex_angle_deg", 0),
            "flex_stiffness":   history[0].get("flex_stiffness", 0),
            "risk_score":       history[0].get("risk_score", 0),
            "label":            history[0].get("label", "Unknown"),
        }

    return jsonify({
        "status": "ok",
        "data": {
            "current":  current,
            "normal":   references.get("normal", {}),
            "oa":       references.get("oa", {}),
        }
    })


@app.route("/api/model_info")
def get_model_info():
    info = inf.get_engine().get_model_info()
    return jsonify({"status": "ok", "data": info})


@app.route("/api/simulate", methods=["POST"])
def simulate():
    """
    Generate simulated sensor data for demo/testing.
    Body: {"mode": "normal"|"oa"|"random", "patient_id": "..."}
    """
    body    = request.get_json(force=True) or {}
    mode    = body.get("mode", "random")
    patient = body.get("patient_id", "DEMO_PATIENT")

    if mode == "normal":
        data = _generate_normal_sample(patient)
    elif mode == "oa":
        data = _generate_oa_sample(patient)
    else:
        data = _generate_normal_sample(patient) if random.random() > 0.5 \
               else _generate_oa_sample(patient)

    # Route through the same pipeline
    with app.test_client() as c:
        resp = c.post("/api/data",
                      data=json.dumps(data),
                      content_type="application/json")
        return resp.data, resp.status_code, resp.headers


# ─── DEMO MODE (auto-simulate when no ESP32 is connected) ─────────────────────
_demo_mode = False
_demo_thread = None

def _demo_loop():
    """Automatically simulates sensor readings when in demo mode."""
    print("[DEMO] Demo mode started — simulating sensor data every 1s")
    patients = ["PATIENT_001", "PATIENT_002"]
    modes    = ["normal", "normal", "normal", "oa", "oa"]  # 60% normal, 40% OA
    while _demo_mode:
        for patient in patients:
            mode = random.choice(modes)
            data = _generate_oa_sample(patient) if mode == "oa" \
                   else _generate_normal_sample(patient)
            result = inf.predict(data)
            db.insert_session(data, result)

            payload = {
                "patient_id":  patient,
                "timestamp":   datetime.utcnow().isoformat() + "Z",
                "sensors": {
                    "microphone":  {"audio_rms": data["audio_rms"],
                                    "dominant_freq_hz": data["dominant_freq_hz"],
                                    "crepitus_score": data["crepitus_score"]},
                    "temperature": {"joint_temp_c": data["joint_temp_c"],
                                    "temp_asymmetry": data["temp_asymmetry"]},
                    "imu":         {"gyro_range_deg": data["gyro_range_deg"],
                                    "step_symmetry":  data["step_symmetry"]},
                    "flex":        {"flex_angle_deg": data["flex_angle_deg"],
                                    "flex_stiffness": data["flex_stiffness"]}
                },
                "inference": result,
                "demo": True
            }
            socketio.emit("live_data", payload)
        time.sleep(1.0)


@app.route("/api/demo/start", methods=["POST"])
def start_demo():
    global _demo_mode, _demo_thread
    _demo_mode   = True
    _demo_thread = threading.Thread(target=_demo_loop, daemon=True)
    _demo_thread.start()
    return jsonify({"status": "ok", "message": "Demo mode started"})


@app.route("/api/demo/stop", methods=["POST"])
def stop_demo():
    global _demo_mode
    _demo_mode = False
    return jsonify({"status": "ok", "message": "Demo mode stopped"})


# ─── SAMPLE GENERATORS ────────────────────────────────────────────────────────
def _generate_normal_sample(patient_id: str) -> dict:
    return {
        "patient_id":       patient_id,
        "side":             "LEFT",
        "sample_idx":       int(time.time()),
        "audio_rms":        round(random.gauss(0.018, 0.005), 4),
        "dominant_freq_hz": round(random.gauss(150, 40), 1),
        "crepitus_score":   round(max(0, random.gauss(0.05, 0.03)), 3),
        "joint_temp_c":     round(random.gauss(33.2, 0.5), 2),
        "ambient_temp_c":   round(random.gauss(28.0, 1.0), 2),
        "temp_asymmetry":   round(abs(random.gauss(0.1, 0.07)), 3),
        "accel_rms_x":      round(random.gauss(0.85, 0.12), 3),
        "accel_rms_y":      round(random.gauss(0.90, 0.10), 3),
        "accel_rms_z":      round(random.gauss(9.82, 0.18), 3),
        "gyro_range_deg":   round(random.gauss(105, 12), 1),
        "step_symmetry":    round(min(1.0, max(0, random.gauss(0.92, 0.04))), 3),
        "flex_angle_deg":   round(random.gauss(112, 10), 1),
        "flex_stiffness":   round(max(0, random.gauss(0.12, 0.04)), 3),
    }


def _generate_oa_sample(patient_id: str) -> dict:
    sev = random.uniform(0.4, 1.0)
    return {
        "patient_id":       patient_id,
        "side":             "LEFT",
        "sample_idx":       int(time.time()),
        "audio_rms":        round(max(0.03, 0.06 + sev*0.08 + random.gauss(0, 0.01)), 4),
        "dominant_freq_hz": round(max(280, 350 + sev*300 + random.gauss(0, 30)), 1),
        "crepitus_score":   round(min(1.0, 0.45 + sev*0.45 + random.gauss(0, 0.04)), 3),
        "joint_temp_c":     round(35.5 + sev*1.5 + random.gauss(0, 0.3), 2),
        "ambient_temp_c":   round(random.gauss(28.0, 1.0), 2),
        "temp_asymmetry":   round(max(0.3, 0.7 + sev*1.2 + random.gauss(0, 0.1)), 3),
        "accel_rms_x":      round(1.3 + sev*0.6 + random.gauss(0, 0.12), 3),
        "accel_rms_y":      round(1.35 + sev*0.5 + random.gauss(0, 0.12), 3),
        "accel_rms_z":      round(9.82 + sev*0.35 + random.gauss(0, 0.25), 3),
        "gyro_range_deg":   round(max(15, 75 - sev*40 + random.gauss(0, 8)), 1),
        "step_symmetry":    round(min(1.0, max(0, 0.72 - sev*0.20 + random.gauss(0, 0.04))), 3),
        "flex_angle_deg":   round(max(15, 75 - sev*38 + random.gauss(0, 7)), 1),
        "flex_stiffness":   round(min(1.0, 0.52 + sev*0.35 + random.gauss(0, 0.04)), 3),
    }


# ─── WEBSOCKET EVENTS ─────────────────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    print(f"[WS] Client connected: {request.sid}")
    emit("connected", {"message": "OA Detection System — Connected", "version": "1.0.0"})


@socketio.on("disconnect")
def on_disconnect():
    print(f"[WS] Client disconnected: {request.sid}")


@socketio.on("subscribe")
def on_subscribe(data):
    patient_id = data.get("patient_id", "PATIENT_001")
    print(f"[WS] {request.sid} subscribed to patient {patient_id}")
    emit("subscribed", {"patient_id": patient_id})


# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  OA Detection System — Backend Server")
    print("  SIH 2026 | PS-26004 | MDoNER")
    print("=" * 60)

    db.init_db()

    host = "0.0.0.0"
    port = 5000
    print(f"\n[SRV] Starting Flask-SocketIO server on http://{host}:{port}")
    print(f"[SRV] Dashboard: http://localhost:{port}")
    print(f"[SRV] API docs:  http://localhost:{port}/api/stats")
    print(f"[SRV] Demo mode: POST http://localhost:{port}/api/demo/start\n")

    socketio.run(app, host=host, port=port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
