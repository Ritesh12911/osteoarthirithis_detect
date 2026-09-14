"""
=============================================================
 OA Detection System — SQLite Database Module
 SIH 2026 | Problem Statement 26004 | MDoNER
=============================================================
 Tables:
   sessions          ← sensor readings + ML inference results
   reference_profiles← Normal / OA baseline feature vectors
   patients          ← [NEW] patient profiles (demographics)
   exercises         ← [NEW] generated rehab protocols
   reports           ← [NEW] generated PDF report registry
   chat_history      ← [NEW] LLM conversation history
=============================================================
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oa_sessions.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      TEXT    NOT NULL,
    side            TEXT    DEFAULT 'LEFT',
    timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
    sample_idx      INTEGER DEFAULT 0,

    -- Microphone features
    audio_rms           REAL,
    dominant_freq_hz    REAL,
    crepitus_score      REAL,

    -- Temperature features
    joint_temp_c        REAL,
    ambient_temp_c      REAL,
    temp_asymmetry      REAL,

    -- IMU features
    accel_rms_x         REAL,
    accel_rms_y         REAL,
    accel_rms_z         REAL,
    gyro_range_deg      REAL,
    step_symmetry       REAL,

    -- Flex sensor features
    flex_angle_deg      REAL,
    flex_stiffness      REAL,

    -- ML inference results
    risk_score          REAL,
    risk_level          TEXT,
    label               TEXT,
    confidence          REAL,
    method              TEXT,

    -- Full JSON snapshots
    raw_data            TEXT,
    inference_result    TEXT
);

CREATE TABLE IF NOT EXISTS reference_profiles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_type TEXT NOT NULL,
    features     TEXT NOT NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- [NEW] Patient demographic and clinical profile
CREATE TABLE IF NOT EXISTS patients (
    patient_id      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    age             INTEGER,
    gender          TEXT,
    bmi             REAL,
    comorbidities   TEXT,   -- comma-separated: diabetes,obesity,prior_injury
    notes           TEXT,
    oa_grade        TEXT DEFAULT 'Unknown', -- KL Grade: 0,1,2,3,4 or Unknown
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- [NEW] Generated rehabilitation/exercise protocols
CREATE TABLE IF NOT EXISTS exercises (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      TEXT NOT NULL,
    protocol_json   TEXT NOT NULL,
    oa_grade        TEXT,
    risk_score      REAL,
    generated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- [NEW] Generated PDF clinical reports registry
CREATE TABLE IF NOT EXISTS reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      TEXT NOT NULL,
    pdf_path        TEXT,
    summary_json    TEXT,
    generated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- [NEW] LLM Clinical Insights chat history
CREATE TABLE IF NOT EXISTS chat_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id  TEXT NOT NULL,
    role        TEXT NOT NULL,  -- 'user' or 'assistant'
    message     TEXT NOT NULL,
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_patient_id  ON sessions(patient_id);
CREATE INDEX IF NOT EXISTS idx_timestamp   ON sessions(timestamp);
CREATE INDEX IF NOT EXISTS idx_label       ON sessions(label);
CREATE INDEX IF NOT EXISTS idx_chat_pid    ON chat_history(patient_id);
CREATE INDEX IF NOT EXISTS idx_ex_pid      ON exercises(patient_id);
"""

# ─── CONNECTION ───────────────────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()

    # Seed reference profiles if empty
    cur = conn.execute("SELECT COUNT(*) as cnt FROM reference_profiles")
    if cur.fetchone()["cnt"] == 0:
        _seed_reference_profiles(conn)

    # Seed demo patient profiles if empty
    cur2 = conn.execute("SELECT COUNT(*) as cnt FROM patients")
    if cur2.fetchone()["cnt"] == 0:
        _seed_demo_patients(conn)

    conn.close()
    print(f"[DB] Database initialized at {DB_PATH}")


def _seed_reference_profiles(conn):
    normal_profile = {
        "audio_rms": 0.018, "dominant_freq_hz": 150, "crepitus_score": 0.05,
        "joint_temp_c": 33.2, "temp_asymmetry": 0.1,
        "accel_rms_x": 0.85, "accel_rms_y": 0.90, "accel_rms_z": 9.82,
        "gyro_range_deg": 105, "step_symmetry": 0.92,
        "flex_angle_deg": 112, "flex_stiffness": 0.12
    }
    oa_profile = {
        "audio_rms": 0.09, "dominant_freq_hz": 520, "crepitus_score": 0.65,
        "joint_temp_c": 36.1, "temp_asymmetry": 1.1,
        "accel_rms_x": 1.55, "accel_rms_y": 1.60, "accel_rms_z": 10.0,
        "gyro_range_deg": 52, "step_symmetry": 0.62,
        "flex_angle_deg": 55, "flex_stiffness": 0.67
    }
    conn.execute(
        "INSERT INTO reference_profiles (profile_type, features) VALUES (?,?)",
        ("normal", json.dumps(normal_profile))
    )
    conn.execute(
        "INSERT INTO reference_profiles (profile_type, features) VALUES (?,?)",
        ("oa", json.dumps(oa_profile))
    )
    conn.commit()
    print("[DB] Seeded reference profiles (Normal + OA)")


def _seed_demo_patients(conn):
    demo_patients = [
        ("PATIENT_001", "Anita Sharma",   58, "Female", 26.4, "hypertension",        "Left knee pain for 6 months", "1"),
        ("PATIENT_002", "Rajesh Kumar",   65, "Male",   29.8, "diabetes,obesity",    "Bilateral knee stiffness",    "2"),
        ("PATIENT_003", "Meena Devi",     72, "Female", 31.2, "prior_injury",        "Post-fall right knee injury", "3"),
        ("PATIENT_004", "Suresh Nair",    45, "Male",   24.1, "",                    "Preventive screening",        "0"),
        ("PATIENT_005", "Priya Gogoi",    55, "Female", 27.5, "obesity",             "Morning stiffness complaint", "1"),
    ]
    for p in demo_patients:
        conn.execute("""
            INSERT OR IGNORE INTO patients
              (patient_id, name, age, gender, bmi, comorbidities, notes, oa_grade)
            VALUES (?,?,?,?,?,?,?,?)
        """, p)
    conn.commit()
    print("[DB] Seeded 5 demo patient profiles")


# Auto-initialize database on import so tables and seeds always exist
try:
    init_db()
except Exception as _e:
    print(f"[DB] Notice: Auto-init deferred: {_e}")


# ─── SESSIONS ─────────────────────────────────────────────────────────────────

def insert_session(sensor_data: dict, inference_result: dict) -> int:
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO sessions (
                patient_id, side, sample_idx,
                audio_rms, dominant_freq_hz, crepitus_score,
                joint_temp_c, ambient_temp_c, temp_asymmetry,
                accel_rms_x, accel_rms_y, accel_rms_z,
                gyro_range_deg, step_symmetry,
                flex_angle_deg, flex_stiffness,
                risk_score, risk_level, label, confidence, method,
                raw_data, inference_result
            ) VALUES (
                :patient_id, :side, :sample_idx,
                :audio_rms, :dominant_freq_hz, :crepitus_score,
                :joint_temp_c, :ambient_temp_c, :temp_asymmetry,
                :accel_rms_x, :accel_rms_y, :accel_rms_z,
                :gyro_range_deg, :step_symmetry,
                :flex_angle_deg, :flex_stiffness,
                :risk_score, :risk_level, :label, :confidence, :method,
                :raw_data, :inference_result
            )
        """, {
            **sensor_data,
            "risk_score":        inference_result.get("risk_score", 0),
            "risk_level":        inference_result.get("risk_level", "LOW"),
            "label":             inference_result.get("label", "Unknown"),
            "confidence":        inference_result.get("confidence", 0),
            "method":            inference_result.get("method", "unknown"),
            "raw_data":          json.dumps(sensor_data),
            "inference_result":  json.dumps(inference_result),
        })
        conn.commit()
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return row_id
    finally:
        conn.close()


def get_history(limit: int = 100, patient_id: str = None) -> list:
    conn = get_conn()
    try:
        if patient_id and patient_id != "ALL":
            rows = conn.execute("""
                SELECT * FROM sessions WHERE patient_id=? ORDER BY timestamp DESC LIMIT ?
            """, (patient_id, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM sessions ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_reference_profiles() -> dict:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT profile_type, features FROM reference_profiles").fetchall()
        return {r["profile_type"]: json.loads(r["features"]) for r in rows}
    finally:
        conn.close()


def get_stats() -> dict:
    conn = get_conn()
    try:
        total     = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        normal_ct = conn.execute("SELECT COUNT(*) FROM sessions WHERE label='Normal'").fetchone()[0]
        oa_ct     = conn.execute("SELECT COUNT(*) FROM sessions WHERE label='Early_OA'").fetchone()[0]
        avg_risk  = conn.execute("SELECT AVG(risk_score) FROM sessions").fetchone()[0] or 0.0
        patients  = conn.execute("SELECT COUNT(DISTINCT patient_id) FROM sessions").fetchone()[0]
        return {
            "total_sessions":  total,
            "normal_count":    normal_ct,
            "oa_count":        oa_ct,
            "avg_risk_score":  round(avg_risk, 3),
            "patient_count":   patients,
        }
    finally:
        conn.close()


def get_time_series(patient_id: str, limit: int = 50) -> list:
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT timestamp, risk_score, label, joint_temp_c,
                   crepitus_score, flex_angle_deg, step_symmetry, audio_rms
            FROM sessions WHERE patient_id=?
            ORDER BY timestamp DESC LIMIT ?
        """, (patient_id, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()


# ─── PATIENT PROFILES ─────────────────────────────────────────────────────────

def get_all_patients() -> list:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM patients ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_patient(patient_id: str) -> dict:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM patients WHERE patient_id=?", (patient_id,)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def upsert_patient(data: dict) -> str:
    conn = get_conn()
    try:
        pid = data.get("patient_id", f"PATIENT_{int(datetime.utcnow().timestamp())}")
        conn.execute("""
            INSERT INTO patients (patient_id, name, age, gender, bmi, comorbidities, notes, oa_grade, updated_at)
            VALUES (:patient_id, :name, :age, :gender, :bmi, :comorbidities, :notes, :oa_grade, CURRENT_TIMESTAMP)
            ON CONFLICT(patient_id) DO UPDATE SET
                name=excluded.name, age=excluded.age, gender=excluded.gender,
                bmi=excluded.bmi, comorbidities=excluded.comorbidities,
                notes=excluded.notes, oa_grade=excluded.oa_grade,
                updated_at=CURRENT_TIMESTAMP
        """, {
            "patient_id":    pid,
            "name":          data.get("name", "Unknown"),
            "age":           data.get("age"),
            "gender":        data.get("gender", ""),
            "bmi":           data.get("bmi"),
            "comorbidities": data.get("comorbidities", ""),
            "notes":         data.get("notes", ""),
            "oa_grade":      data.get("oa_grade", "Unknown"),
        })
        conn.commit()
        return pid
    finally:
        conn.close()


def delete_patient(patient_id: str) -> bool:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM patients WHERE patient_id=?", (patient_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# ─── TREND ANALYSIS ───────────────────────────────────────────────────────────

def get_trend_data(patient_id: str, days: int = 30) -> list:
    """Return daily-averaged risk score + key metrics for a patient over the last N days."""
    conn = get_conn()
    try:
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT
                DATE(timestamp) as date,
                AVG(risk_score)     as avg_risk,
                MAX(risk_score)     as max_risk,
                AVG(joint_temp_c)   as avg_temp,
                AVG(crepitus_score) as avg_crep,
                AVG(flex_angle_deg) as avg_rom,
                AVG(step_symmetry)  as avg_sym,
                COUNT(*)            as n_readings
            FROM sessions
            WHERE patient_id=? AND timestamp >= ?
            GROUP BY DATE(timestamp)
            ORDER BY date ASC
        """, (patient_id, since)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["avg_risk"]  = round(d["avg_risk"] or 0, 3)
            d["max_risk"]  = round(d["max_risk"] or 0, 3)
            d["avg_temp"]  = round(d["avg_temp"] or 0, 2)
            d["avg_crep"]  = round(d["avg_crep"] or 0, 3)
            d["avg_rom"]   = round(d["avg_rom"]  or 0, 1)
            d["avg_sym"]   = round(d["avg_sym"]  or 0, 3)
            result.append(d)
        return result
    finally:
        conn.close()


# ─── COHORT / MULTI-PATIENT ───────────────────────────────────────────────────

def get_cohort_stats() -> dict:
    """Aggregate stats across all patients for the cohort dashboard."""
    conn = get_conn()
    try:
        # Query from patients table so all registered patients are included
        patient_rows = conn.execute("""
            SELECT
                p.patient_id,
                p.name,
                p.age,
                p.gender,
                p.bmi,
                p.oa_grade,
                p.comorbidities,
                COALESCE(AVG(s.risk_score), 0.15) as avg_risk,
                COALESCE(MAX(s.risk_score), 0.15) as max_risk,
                COALESCE(MAX(s.timestamp), '')    as last_seen,
                COUNT(s.id)                       as total_readings,
                SUM(CASE WHEN s.label='Early_OA' THEN 1 ELSE 0 END) as oa_readings
            FROM patients p
            LEFT JOIN sessions s ON p.patient_id = s.patient_id
            GROUP BY p.patient_id
            ORDER BY avg_risk DESC
        """).fetchall()

        patients_data = []
        for r in patient_rows:
            d = dict(r)
            d["avg_risk"] = round(d["avg_risk"] or 0.15, 3)
            d["max_risk"] = round(d["max_risk"] or 0.15, 3)
            d["risk_level"] = (
                "CRITICAL" if d["avg_risk"] >= 0.75 else
                "HIGH"     if d["avg_risk"] >= 0.55 else
                "MEDIUM"   if d["avg_risk"] >= 0.35 else
                "LOW"
            )
            patients_data.append(d)

        # Population-level counts
        total        = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        normal_ct    = conn.execute("SELECT COUNT(*) FROM sessions WHERE label='Normal'").fetchone()[0]
        oa_ct        = conn.execute("SELECT COUNT(*) FROM sessions WHERE label='Early_OA'").fetchone()[0]
        pt_count     = len(patients_data)
        high_risk_ct = sum(1 for p in patients_data if p["avg_risk"] >= 0.55)

        return {
            "patients":           patients_data,
            "total_patients":     pt_count,
            "high_risk_patients": [p for p in patients_data if p["avg_risk"] >= 0.55],
            "high_risk_count":    high_risk_ct,
            "total_sessions":     total,
            "oa_readings_count":  oa_ct,
            "distribution": {
                "normal":   max(normal_ct, sum(1 for p in patients_data if p["avg_risk"] < 0.35)),
                "early_oa": max(oa_ct, sum(1 for p in patients_data if 0.35 <= p["avg_risk"] < 0.55)),
                "critical": high_risk_ct
            },
            "population": {
                "total_sessions": total,
                "normal_count":   normal_ct,
                "oa_count":       oa_ct,
                "patient_count":  pt_count,
                "high_risk_count": high_risk_ct,
            }
        }
    finally:
        conn.close()


# ─── EXERCISES ────────────────────────────────────────────────────────────────

def save_exercise_protocol(patient_id: str, protocol: dict, risk_score: float, oa_grade: str) -> int:
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO exercises (patient_id, protocol_json, oa_grade, risk_score)
            VALUES (?,?,?,?)
        """, (patient_id, json.dumps(protocol), oa_grade, risk_score))
        conn.commit()
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return row_id
    finally:
        conn.close()


def get_latest_exercise(patient_id: str) -> dict:
    conn = get_conn()
    try:
        row = conn.execute("""
            SELECT * FROM exercises WHERE patient_id=? ORDER BY generated_at DESC LIMIT 1
        """, (patient_id,)).fetchone()
        if row:
            d = dict(row)
            d["protocol"] = json.loads(d.get("protocol_json", "{}"))
            return d
        return {}
    finally:
        conn.close()


# ─── REPORTS ──────────────────────────────────────────────────────────────────

def save_report(patient_id: str, pdf_path: str, summary: dict) -> int:
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO reports (patient_id, pdf_path, summary_json)
            VALUES (?,?,?)
        """, (patient_id, pdf_path, json.dumps(summary)))
        conn.commit()
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return row_id
    finally:
        conn.close()


def get_reports(patient_id: str) -> list:
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT * FROM reports WHERE patient_id=? ORDER BY generated_at DESC
        """, (patient_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─── CHAT HISTORY ─────────────────────────────────────────────────────────────

def add_chat_message(patient_id: str, role: str, message: str) -> int:
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO chat_history (patient_id, role, message) VALUES (?,?,?)
        """, (patient_id, role, message))
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def get_chat_history(patient_id: str, limit: int = 20) -> list:
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT role, message, timestamp FROM chat_history
            WHERE patient_id=? ORDER BY timestamp DESC LIMIT ?
        """, (patient_id, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()


def clear_chat_history(patient_id: str):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM chat_history WHERE patient_id=?", (patient_id,))
        conn.commit()
    finally:
        conn.close()
