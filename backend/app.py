"""
=============================================================
 OA Detection System — Flask Backend Server
 SIH 2026 | Problem Statement 26004 | MDoNER
=============================================================

 Core Endpoints:
   POST /api/data            ← ESP32 sends sensor readings
   GET  /api/history         ← Dashboard fetches past sessions
   GET  /api/reference       ← Normal + OA reference profiles
   GET  /api/stats           ← Summary stats
   GET  /api/timeseries      ← Time-series for a patient
   GET  /api/compare         ← Side-by-side comparison data
   GET  /api/model_info      ← ML model metadata
   POST /api/simulate        ← Simulate sensor data (demo mode)

 NEW Endpoints (Feature Expansion):
   GET/POST /api/patients            ← Patient profile CRUD
   GET/PUT  /api/patients/<id>       ← Single patient detail / update
   DELETE   /api/patients/<id>       ← Delete patient
   GET      /api/trend               ← Risk trend over time
   GET      /api/cohort              ← Multi-patient cohort stats
   POST     /api/report/generate     ← Generate PDF clinical report
   GET      /api/report/<report_id>  ← Download generated PDF
   POST     /api/chat                ← LLM Clinical Insights Q&A
   GET      /api/chat/history        ← Chat conversation history
   DELETE   /api/chat/clear          ← Clear chat history
   GET      /api/exercises           ← Get exercise protocol
   POST     /api/exercises/generate  ← Generate new exercise plan
   GET      /api/diet                ← Get diet plan
   GET      /api/llm/status          ← LLM service status

 WebSocket Events:
   Server → Client: 'live_data'   (every new reading)
   Server → Client: 'alert'       (high OA risk detected)
   Client → Server: 'subscribe'   (patient_id to watch)

 Run:
   pip install -r requirements.txt
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
from datetime import datetime

import numpy as np
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_socketio import SocketIO, emit
from flask_cors import CORS

# ─── LOCAL IMPORTS ────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database as db
import inference as inf
import llm_service as llm
import report_generator as rpt

# ─── APP SETUP ────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=None)
app.config['SECRET_KEY'] = 'sih2026-oa-detection-secret'
CORS(app, origins="*")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard")

# ─── LIVE BUFFER ──────────────────────────────────────────────────────────────
_live_buffer = {}   # patient_id → list of recent readings
_subscribers  = {}  # socket_id → patient_id


# ─── STATIC SERVING ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(DASHBOARD_DIR, "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(DASHBOARD_DIR, filename)

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "oa-detection-backend",
        "version": "2.1.0",
        "timestamp": datetime.now().isoformat()
    })


# ─── SENSOR DATA ──────────────────────────────────────────────────────────────

@app.route("/api/data", methods=["POST"])
def receive_data():
    """ESP32 posts sensor JSON here every 500ms."""
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "No JSON received"}), 400

        data.setdefault("patient_id",     "PATIENT_001")
        data.setdefault("side",           "LEFT")
        data.setdefault("sample_idx",      0)
        data.setdefault("ambient_temp_c", 28.0)

        result = inf.predict(data)
        row_id = db.insert_session(data, result)

        payload = _build_payload(row_id, data, result)
        socketio.emit("live_data", payload)

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


def _build_payload(row_id, data, result):
    return {
        "row_id":     row_id,
        "patient_id": data["patient_id"],
        "side":       data["side"],
        "timestamp":  datetime.utcnow().isoformat() + "Z",
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


# ─── EXISTING ENDPOINTS ───────────────────────────────────────────────────────

@app.route("/api/history")
def get_history():
    limit      = int(request.args.get("limit", 100))
    patient_id = request.args.get("patient_id")
    rows       = db.get_history(limit=limit, patient_id=patient_id)
    return jsonify({"status": "ok", "data": rows, "count": len(rows)})


@app.route("/api/reference")
def get_reference():
    return jsonify({"status": "ok", "data": db.get_reference_profiles()})


@app.route("/api/stats")
def get_stats():
    return jsonify({"status": "ok", "data": db.get_stats()})


@app.route("/api/timeseries")
def get_timeseries():
    patient_id = request.args.get("patient_id", "PATIENT_001")
    limit      = int(request.args.get("limit", 50))
    rows       = db.get_time_series(patient_id=patient_id, limit=limit)
    return jsonify({"status": "ok", "data": rows})


@app.route("/api/compare")
def get_compare():
    patient_id = request.args.get("patient_id", "PATIENT_001")
    history    = db.get_history(limit=1, patient_id=patient_id)
    references = db.get_reference_profiles()
    current = {}
    if history:
        current = {k: history[0].get(k, 0) for k in [
            "audio_rms","dominant_freq_hz","crepitus_score","joint_temp_c",
            "temp_asymmetry","accel_rms_x","gyro_range_deg","step_symmetry",
            "flex_angle_deg","flex_stiffness","risk_score","label"
        ]}
    return jsonify({"status": "ok", "data": {
        "current": current,
        "normal":  references.get("normal", {}),
        "oa":      references.get("oa", {}),
    }})


@app.route("/api/model_info")
def get_model_info():
    info = inf.get_engine().get_model_info()
    return jsonify({"status": "ok", "data": info})


# ─── PATIENT PROFILES ─────────────────────────────────────────────────────────

@app.route("/api/patients", methods=["GET", "POST"])
def patients():
    if request.method == "GET":
        patients_list = db.get_all_patients()
        # Enrich with latest risk score from sessions
        for p in patients_list:
            hist = db.get_history(limit=1, patient_id=p["patient_id"])
            if hist:
                p["latest_risk"]  = hist[0].get("risk_score", 0)
                p["latest_level"] = hist[0].get("risk_level", "UNKNOWN")
                p["last_seen"]    = hist[0].get("timestamp", "")
            else:
                p["latest_risk"]  = None
                p["latest_level"] = "NO_DATA"
                p["last_seen"]    = ""
        return jsonify({"status": "ok", "patients": patients_list, "data": patients_list, "count": len(patients_list)})

    elif request.method == "POST":
        data = request.get_json(force=True) or {}
        pid  = db.upsert_patient(data)
        return jsonify({"status": "ok", "patient_id": pid, "message": "Patient saved"})


@app.route("/api/patients/<patient_id>", methods=["GET", "PUT", "DELETE"])
def patient_detail(patient_id):
    if request.method == "GET":
        p = db.get_patient(patient_id)
        if not p:
            return jsonify({"error": "Patient not found"}), 404
        hist = db.get_history(limit=5, patient_id=patient_id)
        p["recent_sessions"] = hist
        return jsonify({"status": "ok", "data": p})

    elif request.method == "PUT":
        data = request.get_json(force=True) or {}
        data["patient_id"] = patient_id
        db.upsert_patient(data)
        return jsonify({"status": "ok", "message": "Patient updated"})

    elif request.method == "DELETE":
        db.delete_patient(patient_id)
        return jsonify({"status": "ok", "message": f"Patient {patient_id} deleted"})


# ─── TREND ANALYSIS ───────────────────────────────────────────────────────────

@app.route("/api/trend")
def get_trend():
    patient_id = request.args.get("patient_id", "PATIENT_001")
    days       = int(request.args.get("days", 30))
    trend_data = db.get_trend_data(patient_id=patient_id, days=days)

    # Compute trend direction from linear regression slope
    direction = "stable"
    slope     = 0.0
    if len(trend_data) >= 3:
        risks = [d["avg_risk"] for d in trend_data]
        n     = len(risks)
        xs    = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(risks) / n
        num = sum((xs[i] - mean_x) * (risks[i] - mean_y) for i in range(n))
        den = sum((xs[i] - mean_x) ** 2 for i in range(n))
        slope = num / den if den != 0 else 0
        if slope > 0.005:
            direction = "worsening"
        elif slope < -0.005:
            direction = "improving"
        else:
            direction = "stable"

    return jsonify({
        "status": "ok",
        "data": trend_data,
        "trend": {
            "direction": direction,
            "slope":     round(slope, 6),
            "days":      days,
            "patient_id": patient_id,
        }
    })


# ─── COHORT DASHBOARD ─────────────────────────────────────────────────────────

@app.route("/api/cohort")
def get_cohort():
    data = db.get_cohort_stats()
    return jsonify({"status": "ok", "data": data, **data})


# ─── PDF REPORT GENERATION ────────────────────────────────────────────────────

@app.route("/api/report/generate", methods=["POST"])
def generate_report():
    """Generate a PDF clinical report for a patient."""
    body       = request.get_json(force=True) or {}
    patient_id = body.get("patient_id", "PATIENT_001")

    patient  = db.get_patient(patient_id) or {"patient_id": patient_id, "name": patient_id}
    readings = db.get_history(limit=50, patient_id=patient_id)
    trend    = db.get_trend_data(patient_id=patient_id, days=30)

    latest_reading = readings[0] if readings else {}
    exercise_row   = db.get_latest_exercise(patient_id)
    exercises      = exercise_row.get("protocol", []) if exercise_row else []

    # Generate diet plan
    diet_plan = llm.generate_diet_plan({
        **patient,
        "risk_score": latest_reading.get("risk_score", 0),
        "risk_level": latest_reading.get("risk_level", "LOW"),
    })

    # Generate exercises if not cached
    if not exercises:
        exercises = llm.generate_exercise_protocol(
            risk_score     = latest_reading.get("risk_score", 0),
            rom_deg        = latest_reading.get("flex_angle_deg", 90),
            gait_symmetry  = latest_reading.get("step_symmetry", 0.9),
        )

    # Compute trend summary
    trend_dir  = "stable"
    trend_slope= 0.0
    if len(trend) >= 3:
        risks = [d["avg_risk"] for d in trend]
        n, xs = len(risks), list(range(len(risks)))
        mx, my = sum(xs)/n, sum(risks)/n
        num = sum((xs[i]-mx)*(risks[i]-my) for i in range(n))
        den = sum((xs[i]-mx)**2 for i in range(n))
        trend_slope = num/den if den else 0
        trend_dir = "worsening" if trend_slope > 0.005 else "improving" if trend_slope < -0.005 else "stable"

    # Generate clinical summary
    clinical_summary = llm.get_clinical_summary(
        patient_id     = patient_id,
        patient_data   = patient,
        latest_reading = latest_reading,
        trend          = {"direction": trend_dir, "slope": trend_slope}
    )

    # Generate PDF
    try:
        pdf_path = rpt.generate_report(
            patient_id       = patient_id,
            patient          = patient,
            readings         = readings,
            trend            = trend,
            clinical_summary = clinical_summary,
            diet_plan        = diet_plan,
            exercises        = exercises,
        )

        summary = {
            "patient_id":   patient_id,
            "risk_score":   latest_reading.get("risk_score", 0),
            "total_readings": len(readings),
            "trend":        trend_dir,
        }
        report_id = db.save_report(patient_id, pdf_path, summary)

        return jsonify({
            "status":    "ok",
            "report_id": report_id,
            "filename":  os.path.basename(pdf_path),
            "message":   "Report generated successfully"
        })
    except Exception as e:
        print(f"[ERR] Report generation: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/report/<int:report_id>")
def download_report(report_id):
    """Download a generated PDF report."""
    conn_reports = db.get_conn()
    try:
        row = conn_reports.execute(
            "SELECT pdf_path FROM reports WHERE id=?", (report_id,)
        ).fetchone()
    finally:
        conn_reports.close()

    if not row or not row["pdf_path"]:
        return jsonify({"error": "Report not found"}), 404

    pdf_path = row["pdf_path"]
    if not os.path.exists(pdf_path):
        return jsonify({"error": "Report file not found on disk"}), 404

    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=os.path.basename(pdf_path),
        mimetype="application/pdf"
    )


@app.route("/api/report/download_latest")
def download_latest_report():
    """Download the latest report for a patient — returns the file directly."""
    patient_id = request.args.get("patient_id", "PATIENT_001")
    reports    = db.get_reports(patient_id)
    if not reports:
        return jsonify({"error": "No reports found for this patient"}), 404
    latest = reports[0]
    pdf_path = latest.get("pdf_path", "")
    if not pdf_path or not os.path.exists(pdf_path):
        return jsonify({"error": "Report file missing — please regenerate"}), 404
    return send_file(
        pdf_path, as_attachment=True,
        download_name=os.path.basename(pdf_path),
        mimetype="application/pdf"
    )


# ─── LLM CLINICAL INSIGHTS ────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def chat():
    """LLM-powered clinical Q&A."""
    body       = request.get_json(force=True) or {}
    patient_id = body.get("patient_id", "PATIENT_001")
    message    = body.get("message", "")

    if not message.strip():
        return jsonify({"error": "Empty message"}), 400

    # Build patient context
    patient        = db.get_patient(patient_id) or {}
    latest_reading = (db.get_history(limit=1, patient_id=patient_id) or [{}])[0]
    trend_data     = db.get_trend_data(patient_id=patient_id, days=7)

    trend_dir, trend_slope = "stable", 0.0
    if len(trend_data) >= 3:
        risks = [d["avg_risk"] for d in trend_data]
        n, xs = len(risks), list(range(len(risks)))
        mx, my = sum(xs)/n, sum(risks)/n
        num = sum((xs[i]-mx)*(risks[i]-my) for i in range(n))
        den = sum((xs[i]-mx)**2 for i in range(n))
        trend_slope = num/den if den else 0
        trend_dir = "worsening" if trend_slope > 0.005 else "improving" if trend_slope < -0.005 else "stable"

    patient_context = {
        "patient":        patient,
        "latest_reading": latest_reading,
        "trend_summary":  {"direction": trend_dir, "slope": trend_slope},
    }

    # Save user message
    db.add_chat_message(patient_id, "user", message)

    # Get AI response
    response_text = llm.chat(patient_id, message, patient_context)

    # Save assistant response
    db.add_chat_message(patient_id, "assistant", response_text)

    return jsonify({
        "status":   "ok",
        "response": response_text,
        "mode":     llm.is_available()["mode"],
    })


@app.route("/api/chat/history")
def get_chat_history():
    patient_id = request.args.get("patient_id", "PATIENT_001")
    limit      = int(request.args.get("limit", 20))
    history    = db.get_chat_history(patient_id=patient_id, limit=limit)
    return jsonify({"status": "ok", "data": history})


@app.route("/api/chat/clear", methods=["DELETE"])
def clear_chat():
    patient_id = request.args.get("patient_id", "PATIENT_001")
    db.clear_chat_history(patient_id)
    return jsonify({"status": "ok", "message": "Chat history cleared"})


# ─── EXERCISES ────────────────────────────────────────────────────────────────

@app.route("/api/exercises")
def get_exercises():
    patient_id = request.args.get("patient_id", "PATIENT_001")
    row        = db.get_latest_exercise(patient_id)
    if not row:
        return jsonify({"status": "ok", "exercises": [], "data": [], "message": "No exercise protocol yet. Generate one."})
    return jsonify({"status": "ok", "exercises": row.get("protocol", []), "data": row.get("protocol", []), "meta": {
        "generated_at": row.get("generated_at", ""),
        "risk_score":   row.get("risk_score", 0),
        "oa_grade":     row.get("oa_grade", "Unknown"),
    }})


@app.route("/api/exercises/generate", methods=["POST"])
def generate_exercises():
    body       = request.get_json(force=True) or {}
    patient_id = body.get("patient_id", "PATIENT_001")
    patient    = db.get_patient(patient_id) or {}
    latest     = (db.get_history(limit=1, patient_id=patient_id) or [{}])[0]

    risk_score = latest.get("risk_score", 0)
    rom_deg    = latest.get("flex_angle_deg", 90)
    gait_sym   = latest.get("step_symmetry", 0.9)

    protocol = llm.generate_exercise_protocol(risk_score, rom_deg, gait_sym)

    row_id = db.save_exercise_protocol(
        patient_id = patient_id,
        protocol   = {"exercises": protocol},
        risk_score = risk_score,
        oa_grade   = patient.get("oa_grade", "Unknown"),
    )

    return jsonify({
        "status":      "ok",
        "exercises":   protocol,
        "data":        protocol,
        "protocol_id": row_id,
        "message":     f"Generated {len(protocol)} exercises for {patient_id}",
    })


# ─── DIET PLAN ────────────────────────────────────────────────────────────────

@app.route("/api/diet")
def get_diet():
    patient_id = request.args.get("patient_id", "PATIENT_001")
    patient    = db.get_patient(patient_id) or {}
    latest     = (db.get_history(limit=1, patient_id=patient_id) or [{}])[0]

    diet = llm.generate_diet_plan({
        **patient,
        "risk_score": latest.get("risk_score", 0),
        "risk_level": latest.get("risk_level", "LOW"),
    })
    return jsonify({"status": "ok", "diet": diet, "data": diet})


# ─── LLM STATUS ───────────────────────────────────────────────────────────────

@app.route("/api/llm/status")
def llm_status():
    return jsonify({"status": "ok", "data": llm.is_available()})


# ─── SIMULATE ─────────────────────────────────────────────────────────────────

@app.route("/api/simulate", methods=["POST"])
def simulate():
    body    = request.get_json(force=True) or {}
    mode    = body.get("mode", "random")
    patient = body.get("patient_id", "DEMO_PATIENT")
    data    = (_generate_oa_sample(patient) if mode == "oa"
               else _generate_normal_sample(patient) if mode == "normal"
               else random.choice([_generate_normal_sample, _generate_oa_sample])(patient))
    with app.test_client() as c:
        resp = c.post("/api/data", data=json.dumps(data), content_type="application/json")
        return resp.data, resp.status_code, resp.headers


# ─── DEMO MODE ────────────────────────────────────────────────────────────────
_demo_mode   = False
_demo_thread = None


def _demo_loop():
    print("[DEMO] Demo mode started — simulating sensor data every 1s")
    patients = ["PATIENT_001", "PATIENT_002"]
    modes    = ["normal", "normal", "normal", "oa", "oa"]
    while _demo_mode:
        for patient in patients:
            mode = random.choice(modes)
            data = _generate_oa_sample(patient) if mode == "oa" else _generate_normal_sample(patient)
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
                                    "temp_asymmetry": data["temp_asymmetry"],
                                    "ambient_temp_c": data.get("ambient_temp_c", 28.0)},
                    "imu":         {"gyro_range_deg": data["gyro_range_deg"],
                                    "step_symmetry":  data["step_symmetry"],
                                    "accel_rms_x":    data.get("accel_rms_x", 0)},
                    "flex":        {"flex_angle_deg": data["flex_angle_deg"],
                                    "flex_stiffness": data["flex_stiffness"]}
                },
                "inference": result,
                "demo": True,
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
        "patient_id":       patient_id, "side": "LEFT", "sample_idx": int(time.time()),
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
        "patient_id":       patient_id, "side": "LEFT", "sample_idx": int(time.time()),
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
    emit("connected", {"message": "OA Detection System — Connected", "version": "2.0.0"})


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
    print("  OA Detection System — Backend Server v2.0")
    print("  SIH 2026 | PS-26004 | MDoNER")
    print("=" * 60)

    db.init_db()

    llm_info = llm.is_available()
    print(f"\n[LLM] Mode: {llm_info['mode']} | Model: {llm_info['model']}")
    if not llm_info['gemini_available']:
        print("[LLM] Set GEMINI_API_KEY env var to enable Gemini AI features")

    host, port = "0.0.0.0", 5000
    print(f"\n[SRV] Starting on http://{host}:{port}")
    print(f"[SRV] Dashboard:  http://localhost:{port}")
    print(f"[SRV] API stats:  http://localhost:{port}/api/stats")
    print(f"[SRV] Cohort:     http://localhost:{port}/api/cohort")
    print(f"[SRV] Demo:       POST http://localhost:{port}/api/demo/start\n")

    socketio.run(app, host=host, port=port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
