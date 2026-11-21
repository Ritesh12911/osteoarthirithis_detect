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

    def aggregate_predict(self, samples: list, patient_meta: dict = None) -> dict:
        """
        Computes clinical multi-task inference over an active movement screening session.
        Aggregates time-series samples across multiple gait & flexion cycles to produce
        an accurate, reproducible, dynamic OA risk score without instantaneous noise bias.
        """
        if not samples or len(samples) == 0:
            return self.predict({})

        # Extract vectors for each feature channel
        crep_vals   = [float(s.get("crepitus_score", s.get("sensors", {}).get("microphone", {}).get("crepitus_score", 0.0))) for s in samples]
        rms_vals    = [float(s.get("audio_rms", s.get("sensors", {}).get("microphone", {}).get("audio_rms", 0.016))) for s in samples]
        temp_vals   = [float(s.get("joint_temp_c", s.get("sensors", {}).get("temperature", {}).get("joint_temp_c", 33.1))) for s in samples if s.get("joint_temp_c") or s.get("sensors", {}).get("temperature", {}).get("joint_temp_c")]
        asym_vals   = [float(s.get("temp_asymmetry", s.get("sensors", {}).get("temperature", {}).get("temp_asymmetry", 0.1))) for s in samples]
        flex_vals   = [float(s.get("knee_angle_deg", s.get("flex_angle_deg", s.get("sensors", {}).get("flex", {}).get("flex_angle_deg", 110.0)))) for s in samples]
        sym_vals    = [float(s.get("step_symmetry", s.get("sensors", {}).get("imu", {}).get("step_symmetry", 0.92))) for s in samples]
        rom_vals    = [float(s.get("rom_deg", s.get("gyro_range_deg", s.get("sensors", {}).get("imu", {}).get("gyro_range_deg", 90.0)))) for s in samples]
        stiff_vals  = [float(s.get("flex_stiffness", s.get("sensors", {}).get("flex", {}).get("flex_stiffness", 0.15))) for s in samples]

        # Robust statistics
        max_flex = max(flex_vals) if flex_vals else 110.0
        min_flex = min(flex_vals) if flex_vals else 20.0
        active_rom = max_flex - min_flex if len(flex_vals) > 5 else (np.mean(rom_vals) if rom_vals else 90.0)

        mean_crep = float(np.mean(crep_vals)) if crep_vals else 0.0
        p90_crep  = float(np.percentile(crep_vals, 90)) if len(crep_vals) >= 10 else (max(crep_vals) if crep_vals else 0.0)
        burst_count = sum(1 for c in crep_vals if c > 0.35)

        mean_temp = float(np.mean(temp_vals)) if temp_vals else 33.2
        mean_asym = float(np.mean(asym_vals)) if asym_vals else 0.1
        mean_sym  = float(np.mean(sym_vals)) if sym_vals else 0.92
        mean_stiff= float(np.mean(stiff_vals)) if stiff_vals else 0.15
        mean_rms  = float(np.mean(rms_vals)) if rms_vals else 0.016

        # Build composite feature dictionary representing the full movement session
        agg_features = {
            "audio_rms":         round(mean_rms, 4),
            "dominant_freq_hz":  float(np.median([s.get("dominant_freq_hz", 150) for s in samples])) if samples else 150.0,
            "crepitus_score":    round(float(0.6 * mean_crep + 0.4 * p90_crep), 3),
            "joint_temp_c":      round(mean_temp, 2),
            "temp_asymmetry":    round(mean_asym, 2),
            "accel_rms_x":       float(np.mean([s.get("accel_rms_x", 0.85) for s in samples])) if samples else 0.85,
            "accel_rms_y":       float(np.mean([s.get("accel_rms_y", 0.90) for s in samples])) if samples else 0.90,
            "accel_rms_z":       float(np.mean([s.get("accel_rms_z", 9.80) for s in samples])) if samples else 9.80,
            "gyro_range_deg":    round(float(active_rom), 1),
            "step_symmetry":     round(mean_sym, 3),
            "flex_angle_deg":    round(float(max_flex), 1),
            "flex_stiffness":    round(mean_stiff, 3),
            "active_rom_deg":    round(float(active_rom), 1),
            "burst_count":       burst_count,
            "sample_count":      len(samples)
        }

        # Run primary prediction on aggregated features
        base_result = self.predict(agg_features)

        # Dynamic continuous risk score calculation based on multi-parameter biomechanics:
        # 1. Acoustic crepitus impact (0-35% weight)
        acoustic_factor = min(1.0, (agg_features["crepitus_score"] * 0.8 + (burst_count / max(1, len(samples))) * 1.5))

        # 2. ROM restriction impact (0-30% weight: <60° = severe restriction, >110° = healthy)
        if active_rom >= 110:
            rom_factor = 0.05
        elif active_rom >= 85:
            rom_factor = 0.05 + 0.35 * (110 - active_rom) / 25.0
        elif active_rom >= 55:
            rom_factor = 0.40 + 0.35 * (85 - active_rom) / 30.0
        else:
            rom_factor = 0.75 + 0.25 * max(0, (55 - active_rom) / 35.0)
        rom_factor = min(1.0, max(0.0, rom_factor))

        # 3. Thermal inflammation impact (0-20% weight: joint temp > 35.0°C and delta > 0.8°C)
        temp_delta = max(0.0, mean_temp - 33.2)
        thermal_factor = min(1.0, max(0.0, (temp_delta / 3.0) * 0.6 + (mean_asym / 1.8) * 0.4))

        # 4. Gait asymmetry & mechanical stiffness impact (0-15% weight)
        sym_penalty = max(0.0, (0.95 - mean_sym) / 0.35)
        stiff_factor = min(1.0, mean_stiff * 0.7 + sym_penalty * 0.3)

        # Multi-modal composite risk score
        computed_risk = (
            0.35 * acoustic_factor +
            0.30 * rom_factor +
            0.20 * thermal_factor +
            0.15 * stiff_factor
        )
        computed_risk = float(np.clip(computed_risk, 0.04, 0.96))

        # Map to KL Stage
        if computed_risk < 0.25:
            final_kl = 0
        elif computed_risk < 0.48:
            final_kl = 1
        elif computed_risk < 0.70:
            final_kl = 2
        elif computed_risk < 0.85:
            final_kl = 3
        else:
            final_kl = 4

        pathway = BIORAD_PATHWAYS[final_kl]
        final_level = self._get_risk_level(computed_risk)

        base_result["risk_score"] = round(computed_risk, 3)
        base_result["risk_level"] = final_level
        base_result["kl_grade"] = final_kl
        base_result["kl_grade_label"] = KL_CLASSES[final_kl]
        base_result["implant_candidacy"] = pathway["candidacy"]
        base_result["treatment_pathway"] = pathway["action"]
        base_result["prob_normal"] = round(1.0 - computed_risk, 3)
        base_result["prob_oa"] = round(computed_risk, 3)
        base_result["aggregated_metrics"] = agg_features
        base_result["session_duration_s"] = round(len(samples) * 0.5, 1)

        return base_result

    def _rule_based_predict(self, features: dict) -> dict:
        crep  = features.get("crepitus_score", 0.0)
        temp  = features.get("joint_temp_c", 33.0)
        asym  = features.get("temp_asymmetry", 0.0)
        flex  = features.get("flex_angle_deg", features.get("knee_angle_deg", 110.0))
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
            feed_data = dict(sensor_data)
            if "knee_angle_deg" in feed_data and "flex_angle_deg" not in feed_data:
                feed_data["flex_angle_deg"] = feed_data["knee_angle_deg"]
            x = np.array([[feed_data.get(col, NORMAL_BASELINE[col]) for col in FEATURE_COLS]])
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

def aggregate_predict(samples: list, patient_meta: dict = None) -> dict:
    return get_engine().aggregate_predict(samples, patient_meta)
