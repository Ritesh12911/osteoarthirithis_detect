"""
=============================================================
 OA Detection System — Clinical ML Inference Engine
 MDoNER
=============================================================
 Multimodal Clinical Staging grounded in:
   - Radiopaedia Kellgren-Lawrence (KL 0–4) Staging System
   - NIH NDA / OAI (Osteoarthritis Initiative) Cohorts
   - RSNA Multimodal Knee Abnormality Benchmarks
   - Biorad Medisys Indian Knee Implant & Arthroplasty Guidelines
=============================================================
"""

import os
import json
import pickle
import numpy as np

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
KL_MODEL_PATH   = os.path.join(BASE_DIR, "..", "ml", "models", "oa_kl_model.pkl")
BIN_MODEL_PATH  = os.path.join(BASE_DIR, "..", "ml", "models", "oa_model.pkl")
RISK_MODEL_PATH = os.path.join(BASE_DIR, "..", "ml", "models", "oa_risk_regressor.pkl")
SCALER_PATH     = os.path.join(BASE_DIR, "..", "ml", "models", "scaler.pkl")
INFO_PATH       = os.path.join(BASE_DIR, "..", "ml", "models", "model_info.json")

FEATURE_COLS = [
    "audio_rms", "dominant_freq_hz", "crepitus_score",
    "joint_temp_c", "temp_asymmetry",
    "accel_rms_x", "accel_rms_y", "accel_rms_z",
    "gyro_range_deg", "step_symmetry",
    "flex_angle_deg", "flex_stiffness"
]

KL_CLASSES = {
    0: "Grade 0 (Normal)",
    1: "Grade 1 (Doubtful)",
    2: "Grade 2 (Mild OA)",
    3: "Grade 3 (Moderate OA)",
    4: "Grade 4 (Severe OA)"
}

BIORAD_PATHWAYS = {
    0: {
        "candidacy": "Non-Surgical (Healthy Joint)",
        "action": "Routine physical activity, ergonomic education, and joint wellness preservation.",
        "implant_suitable": False
    },
    1: {
        "candidacy": "Preventive / Non-Surgical",
        "action": "Early targeted quadriceps conditioning, low-impact swimming/cycling, weight optimization.",
        "implant_suitable": False
    },
    2: {
        "candidacy": "Joint Preservation Therapy",
        "action": "High-Flex therapeutic rehabilitation, anti-inflammatory dietary protocol, and patellar tracking braces.",
        "implant_suitable": False
    },
    3: {
        "candidacy": "High-Flex UKA / Partial Knee Candidate",
        "action": "Viscosupplementation consult + Biorad Medisys high-flexion Unicompartmental Knee Arthroplasty (UKA) evaluation if single-compartment disease.",
        "implant_suitable": True
    },
    4: {
        "candidacy": "Total Knee Arthroplasty (TKA) Candidate",
        "action": "Orthopedic consultation for Total Knee Arthroplasty (TKA) featuring high-flexion morphometry (>135° deep knee flexion for Indian lifestyle).",
        "implant_suitable": True
    }
}

RISK_THRESHOLDS = {
    "LOW":      (0.00, 0.28),
    "MODERATE": (0.28, 0.55),
    "HIGH":     (0.55, 0.78),
    "CRITICAL": (0.78, 1.00),
}

NORMAL_BASELINE = {
    "audio_rms": 0.016, "dominant_freq_hz": 140.0, "crepitus_score": 0.04,
    "joint_temp_c": 33.1, "temp_asymmetry": 0.08,
    "accel_rms_x": 0.82, "accel_rms_y": 0.88, "accel_rms_z": 9.82,
    "gyro_range_deg": 118.0, "step_symmetry": 0.94,
    "flex_angle_deg": 122.0, "flex_stiffness": 0.10
}


class OAInferenceEngine:
    """Multi-task clinical inference engine combining KL staging, regression, and RSNA abnormality markers."""

    def __init__(self):
        self.kl_model   = None
        self.bin_model  = None
        self.risk_model = None
        self.scaler     = None
        self.info       = {}
        self.use_rules  = True
        self._load()

    def _load(self):
        try:
            if os.path.exists(KL_MODEL_PATH) and os.path.exists(SCALER_PATH):
                with open(KL_MODEL_PATH, 'rb') as f:
                    self.kl_model = pickle.load(f)
                with open(SCALER_PATH, 'rb') as f:
                    self.scaler = pickle.load(f)
                if os.path.exists(BIN_MODEL_PATH):
                    with open(BIN_MODEL_PATH, 'rb') as f:
                        self.bin_model = pickle.load(f)
                if os.path.exists(RISK_MODEL_PATH):
                    with open(RISK_MODEL_PATH, 'rb') as f:
                        self.risk_model = pickle.load(f)
                if os.path.exists(INFO_PATH):
                    with open(INFO_PATH, 'r') as f:
                        self.info = json.load(f)
                print("[INFERENCE] Clinical Multi-Task Models (KL 0–4) loaded successfully.")
                self.use_rules = False
            else:
                print("[INFERENCE] Clinical models not found — using rule-based fallback.")
                self.use_rules = True
        except Exception as e:
            print(f"[INFERENCE] Error loading clinical models: {e}. Using rule-based fallback.")
            self.use_rules = True

    def _get_risk_level(self, score: float) -> str:
        for level, (lo, hi) in RISK_THRESHOLDS.items():
            if lo <= score < hi:
                return level
        return "CRITICAL"

    def _rule_based_predict(self, features: dict) -> dict:
        crep  = features.get("crepitus_score", 0.0)
        temp  = features.get("joint_temp_c", 33.0)
        asym  = features.get("temp_asymmetry", 0.0)
        flex  = features.get("flex_angle_deg", 110.0)
        stiff = features.get("flex_stiffness", 0.1)
        sym   = features.get("step_symmetry", 0.9)

        # Estimate KL grade from physical markers
        if crep > 0.75 or flex < 65 or asym > 1.4 or temp > 36.4:
            kl_grade = 4
            risk_score = 0.88
        elif crep > 0.55 or flex < 85 or asym > 0.9 or temp > 35.5:
            kl_grade = 3
            risk_score = 0.68
        elif crep > 0.35 or flex < 100 or asym > 0.4 or temp > 34.4:
            kl_grade = 2
            risk_score = 0.46
        elif crep > 0.12 or flex < 112 or asym > 0.2:
            kl_grade = 1
            risk_score = 0.24
        else:
            kl_grade = 0
            risk_score = 0.08

        pathway = BIORAD_PATHWAYS[kl_grade]
        label = "Normal" if kl_grade == 0 else ("Early_OA" if kl_grade == 2 else ("Moderate_OA" if kl_grade == 3 else ("Severe_OA" if kl_grade == 4 else "Doubtful_OA")))

        return {
            "kl_grade":               kl_grade,
            "kl_grade_label":         KL_CLASSES[kl_grade],
            "risk_score":             round(risk_score, 3),
            "label":                  label,
            "confidence":             0.85,
            "risk_level":             self._get_risk_level(risk_score),
            "prob_normal":            round(1.0 - risk_score, 3),
            "prob_oa":                round(risk_score, 3),
            "kl_probabilities":       {f"kl{i}": 0.85 if i == kl_grade else 0.0375 for i in range(5)},
            "implant_candidacy":      pathway["candidacy"],
            "treatment_pathway":      pathway["action"],
            "abnormalities": {
                "cartilage_wear_pct":       int(np.clip(risk_score * 100, 5, 98)),
                "synovial_inflammation_pct": int(np.clip((temp - 32.5) / 4.5 * 100, 0, 100)),
                "crepitus_severity_pct":    int(np.clip(crep * 100, 0, 100)),
                "joint_stiffness_pct":      int(np.clip(stiff * 100, 0, 100))
            },
            "feature_contributions":    {},
            "method":                   "rule_based"
        }

    def predict(self, sensor_data: dict) -> dict:
        """Runs multi-task clinical inference on incoming sensor data."""
        if self.use_rules or self.kl_model is None or self.scaler is None:
            return self._rule_based_predict(sensor_data)

        try:
            x = np.array([[sensor_data.get(col, NORMAL_BASELINE[col]) for col in FEATURE_COLS]])
            x_scaled = self.scaler.transform(x)

            # 1. Multi-Class KL Staging
            kl_probs = self.kl_model.predict_proba(x_scaled)[0]
            kl_grade = int(np.argmax(kl_probs))
            confidence = float(np.max(kl_probs))

            # 2. Continuous Progression Score
            if self.risk_model is not None:
                risk_score = float(np.clip(self.risk_model.predict(x_scaled)[0], 0.01, 0.99))
            else:
                # Weighted probability expectation
                risk_score = float(sum(i * kl_probs[i] for i in range(5)) / 4.0)

            # 3. Label & Biorad Medisys Clinical Recommendation
            pathway = BIORAD_PATHWAYS[kl_grade]
            if kl_grade == 0:
                label = "Normal"
            elif kl_grade == 1:
                label = "Doubtful_OA"
            elif kl_grade == 2:
                label = "Early_OA"
            elif kl_grade == 3:
                label = "Moderate_OA"
            else:
                label = "Severe_OA"

            # 4. Multimodal Abnormality Indices (RSNA benchmark inspiration)
            crep  = float(sensor_data.get("crepitus_score", 0.0))
            temp  = float(sensor_data.get("joint_temp_c", 33.2))
            stiff = float(sensor_data.get("flex_stiffness", 0.12))
            flex  = float(sensor_data.get("flex_angle_deg", 112.0))

            cartilage_wear = int(np.clip((kl_grade * 22) + (crep * 20), 4, 98))
            synovial_inf   = int(np.clip(((temp - 32.5) / 4.2) * 100, 2, 98))
            crep_severity  = int(np.clip(crep * 100, 0, 100))
            stiffness_idx  = int(np.clip(stiff * 100 + max(0, (90 - flex) * 0.5), 2, 98))

            # 5. Feature contributions (deviation from OAI healthy baseline)
            contributions = {}
            for col in FEATURE_COLS:
                val = sensor_data.get(col, NORMAL_BASELINE[col])
                base = NORMAL_BASELINE[col]
                dev = abs(val - base) / abs(base) if base != 0 else abs(val)
                contributions[col] = round(float(min(dev, 2.5)), 3)

            prob_normal = float(kl_probs[0] + 0.5 * kl_probs[1])
            prob_oa     = float(1.0 - prob_normal)

            return {
                "kl_grade":               kl_grade,
                "kl_grade_label":         KL_CLASSES[kl_grade],
                "risk_score":             round(risk_score, 3),
                "label":                  label,
                "confidence":             round(confidence, 3),
                "risk_level":             self._get_risk_level(risk_score),
                "prob_normal":            round(prob_normal, 3),
                "prob_oa":                round(prob_oa, 3),
                "kl_probabilities": {
                    "kl0": round(float(kl_probs[0]), 3),
                    "kl1": round(float(kl_probs[1]), 3),
                    "kl2": round(float(kl_probs[2]), 3),
                    "kl3": round(float(kl_probs[3]), 3),
                    "kl4": round(float(kl_probs[4]), 3),
                },
                "implant_candidacy":      pathway["candidacy"],
                "treatment_pathway":      pathway["action"],
                "implant_suitable":       pathway["implant_suitable"],
                "abnormalities": {
                    "cartilage_wear_pct":       cartilage_wear,
                    "synovial_inflammation_pct": synovial_inf,
                    "crepitus_severity_pct":    crep_severity,
                    "joint_stiffness_pct":      stiffness_idx
                },
                "feature_contributions":    contributions,
                "method":                   "clinical_kl_ensemble"
            }

        except Exception as e:
            print(f"[INFERENCE] Clinical prediction error: {e}")
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
