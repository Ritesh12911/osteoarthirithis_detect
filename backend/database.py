"""
=============================================================
 OA Detection System — SQLite Database Module
 SIH 2026 | PS-26004 | MDoNER
=============================================================
"""

import sqlite3
import json
import os
from datetime import datetime

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
    profile_type TEXT NOT NULL,  -- 'normal' or 'oa'
    features     TEXT NOT NULL,  -- JSON
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_patient_id ON sessions(patient_id);
CREATE INDEX IF NOT EXISTS idx_timestamp  ON sessions(timestamp);
CREATE INDEX IF NOT EXISTS idx_label      ON sessions(label);
"""


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

    conn.close()
    print(f"[DB] Database initialized at {DB_PATH}")


def _seed_reference_profiles(conn):
    """Insert reference Normal and OA mean feature profiles."""
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
        if patient_id:
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
        return {
            "total_sessions": total,
            "normal_count":   normal_ct,
            "oa_count":       oa_ct,
            "avg_risk_score": round(avg_risk, 3)
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
