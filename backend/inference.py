"""
=============================================================
 OA Detection System — ML Inference Module
 SIH 2026 | PS-26004 | MDoNER
=============================================================
"""

import os
import json
import pickle
import numpy as np

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH  = os.path.join(BASE_DIR, "..", "ml", "models", "oa_model.pkl")
SCALER_PATH = os.path.join(BASE_DIR, "..", "ml", "models", "scaler.pkl")
INFO_PATH   = os.path.join(BASE_DIR, "..", "ml", "models", "model_info.json")

FEATURE_COLS = [
    "audio_rms", "dominant_freq_hz", "crepitus_score",
    "joint_temp_c", "temp_asymmetry",
    "accel_rms_x", "accel_rms_y", "accel_rms_z",
    "gyro_range_deg", "step_symmetry",
    "flex_angle_deg", "flex_stiffness"
]

RISK_THRESHOLDS = {
    "LOW":      (0.00, 0.30),
    "MODERATE": (0.30, 0.60),
    "HIGH":     (0.60, 0.80),
    "CRITICAL": (0.80, 1.00),
}


class OAInferenceEngine:
    """Loads the trained model and runs real-time inference on sensor data."""

    def __init__(self):
        self.model  = None
        self.scaler = None
        self.info   = {}
        self._load()

    def _load(self):
        """Load model + scaler from disk. Falls back to rule-based if model missing."""
        try:
            if os.path.exists(MODEL_PATH) and os.path.exists(SCALER_PATH):
                with open(MODEL_PATH, 'rb') as f:
                    self.model = pickle.load(f)
                with open(SCALER_PATH, 'rb') as f:
                    self.scaler = pickle.load(f)
                if os.path.exists(INFO_PATH):
                    with open(INFO_PATH, 'r') as f:
                        self.info = json.load(f)
                print("[INFERENCE] Model loaded successfully.")
                self.use_rules = False
            else:
                print("[INFERENCE] Model files not found — using rule-based fallback.")
                print("[INFERENCE] Run: python ml/train_model.py to train the model.")
                self.use_rules = True
        except Exception as e:
            print(f"[INFERENCE] Error loading model: {e}. Using rule-based fallback.")
            self.use_rules = True

    def _rule_based_predict(self, features: dict) -> dict:
        """Simple rule-based OA risk scorer (fallback when model not trained)."""
        score = 0.0
        reasons = []

        # Crepitus
        if features.get("crepitus_score", 0) > 0.4:
            score += 0.25
            reasons.append("Elevated crepitus")
        # Temperature
        if features.get("joint_temp_c", 33) > 35.0:
            score += 0.20
            reasons.append("Joint hyperthermia")
        if features.get("temp_asymmetry", 0) > 0.8:
            score += 0.10
            reasons.append("Temperature asymmetry")
        # ROM
        if features.get("flex_angle_deg", 110) < 80:
            score += 0.20
            reasons.append("Reduced ROM")
        if features.get("flex_stiffness", 0) > 0.5:
            score += 0.10
            reasons.append("Joint stiffness")
        # Gait
        if features.get("step_symmetry", 0.9) < 0.7:
            score += 0.15
            reasons.append("Gait asymmetry")

        score = min(score, 1.0)
        label = "Early_OA" if score >= 0.5 else "Normal"

        return {
            "risk_score": round(score, 3),
            "label": label,
            "confidence": round(0.65, 3),
            "risk_level": self._get_risk_level(score),
            "reasons": reasons,
            "method": "rule_based"
        }

    def _get_risk_level(self, score: float) -> str:
        for level, (lo, hi) in RISK_THRESHOLDS.items():
            if lo <= score < hi:
                return level
        return "CRITICAL"

    def predict(self, sensor_data: dict) -> dict:
        """
        Run inference on incoming sensor data dict.

        Args:
            sensor_data: dict with keys matching FEATURE_COLS

        Returns:
            dict with risk_score, label, confidence, risk_level, feature_contributions
        """
        if self.use_rules:
            return self._rule_based_predict(sensor_data)

        try:
            # Extract features in correct order
            x = np.array([[sensor_data.get(col, 0.0) for col in FEATURE_COLS]])
            x_scaled = self.scaler.transform(x)

            # Predict
            prob       = self.model.predict_proba(x_scaled)[0]
            risk_score = float(prob[1])
            label      = "Early_OA" if risk_score >= 0.5 else "Normal"
            confidence = float(max(prob))

            # Rough feature contributions (deviation from normal baseline)
            normal_baseline = {
                "audio_rms": 0.018, "dominant_freq_hz": 150, "crepitus_score": 0.05,
                "joint_temp_c": 33.2, "temp_asymmetry": 0.1,
                "accel_rms_x": 0.85, "accel_rms_y": 0.9, "accel_rms_z": 9.82,
                "gyro_range_deg": 105, "step_symmetry": 0.92,
                "flex_angle_deg": 112, "flex_stiffness": 0.12
            }
            contributions = {}
            for col in FEATURE_COLS:
                val      = sensor_data.get(col, 0)
                baseline = normal_baseline.get(col, 0)
                if baseline != 0:
                    dev = abs(val - baseline) / abs(baseline)
                else:
                    dev = abs(val)
                contributions[col] = round(min(dev, 2.0), 3)

            return {
                "risk_score":           round(risk_score, 3),
                "label":                label,
                "confidence":           round(confidence, 3),
                "risk_level":           self._get_risk_level(risk_score),
                "prob_normal":          round(float(prob[0]), 3),
                "prob_oa":              round(float(prob[1]), 3),
                "feature_contributions": contributions,
                "method":               "ml_model"
            }

        except Exception as e:
            print(f"[INFERENCE] Prediction error: {e}")
            return self._rule_based_predict(sensor_data)

    def get_model_info(self) -> dict:
        return self.info


# Singleton engine
_engine = None

def get_engine() -> OAInferenceEngine:
    global _engine
    if _engine is None:
        _engine = OAInferenceEngine()
    return _engine


def predict(sensor_data: dict) -> dict:
    return get_engine().predict(sensor_data)
