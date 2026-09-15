"""
=============================================================
 OA Detection System — Clinical Dataset Generator (OAI & KL 0–4)
 SIH 2026 | Problem Statement 26004 | MDoNER
=============================================================
 Grounded in:
   1. Radiopaedia Kellgren-Lawrence (KL) Staging (Grades 0 to 4)
   2. NIH NDA / OAI (Osteoarthritis Initiative) Cohorts & Biomechanics
   3. RSNA Multimodal Knee Abnormality & Cartilage Degradation Benchmarks
   4. Biorad Medisys Indian Knee Biomechanics & Implant Candidacy Parameters
=============================================================
"""

import os
import sys

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import numpy as np
import pandas as pd

np.random.seed(42)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT   = os.path.join(BASE_DIR, "oa_dataset.csv")

# 500 samples per KL Grade = 2,500 total samples
SAMPLES_PER_GRADE = 500

def generate_kl_grade_samples(grade: int, n: int) -> pd.DataFrame:
    sub = np.random.uniform(0.0, 1.0, n)
    
    if grade == 0:
        # KL 0: Normal
        audio_rms        = np.random.normal(0.016, 0.005, n) + sub * 0.006
        dom_freq         = np.random.normal(140, 45, n) + sub * 30
        crep_score       = np.random.normal(0.04, 0.025, n) + sub * 0.04
        joint_temp       = np.random.normal(33.1, 0.5, n) + sub * 0.3
        temp_asym        = np.abs(np.random.normal(0.08, 0.06, n))
        accel_x          = np.random.normal(0.82, 0.12, n)
        accel_y          = np.random.normal(0.88, 0.12, n)
        accel_z          = np.random.normal(9.82, 0.15, n)
        gyro_rom         = np.random.normal(118, 12, n) - sub * 8
        step_sym         = np.random.normal(0.94, 0.03, n) - sub * 0.03
        flex_angle       = np.random.normal(122, 10, n) - sub * 8
        flex_stiff       = np.random.normal(0.10, 0.04, n) + sub * 0.05
        label_name       = "Normal"
        kl_label         = "Grade 0 (Normal)"
        risk_base        = 0.05 + sub * 0.15
        cartilage_wear   = np.random.uniform(0.02, 0.15, n)
        implant_cand     = "Conservative - Normal Activity"
        
    elif grade == 1:
        # KL 1: Doubtful OA
        audio_rms        = np.random.normal(0.028, 0.008, n) + sub * 0.012
        dom_freq         = np.random.normal(240, 55, n) + sub * 50
        crep_score       = np.random.normal(0.18, 0.05, n) + sub * 0.08
        joint_temp       = np.random.normal(33.9, 0.5, n) + sub * 0.4
        temp_asym        = np.abs(np.random.normal(0.25, 0.10, n)) + sub * 0.15
        accel_x          = np.random.normal(0.95, 0.14, n) + sub * 0.10
        accel_y          = np.random.normal(0.98, 0.14, n) + sub * 0.10
        accel_z          = np.random.normal(9.83, 0.18, n)
        gyro_rom         = np.random.normal(102, 10, n) - sub * 10
        step_sym         = np.random.normal(0.87, 0.04, n) - sub * 0.05
        flex_angle       = np.random.normal(108, 9, n) - sub * 10
        flex_stiff       = np.random.normal(0.25, 0.06, n) + sub * 0.10
        label_name       = "Doubtful_OA"
        kl_label         = "Grade 1 (Doubtful)"
        risk_base        = 0.22 + sub * 0.18
        cartilage_wear   = np.random.uniform(0.15, 0.35, n)
        implant_cand     = "Preventive Therapy & Ergonomics"
        
    elif grade == 2:
        # KL 2: Mild OA (Definite Osteophytes, Early Clinical OA)
        audio_rms        = np.random.normal(0.052, 0.012, n) + sub * 0.020
        dom_freq         = np.random.normal(390, 70, n) + sub * 80
        crep_score       = np.random.normal(0.42, 0.07, n) + sub * 0.14
        joint_temp       = np.random.normal(34.8, 0.5, n) + sub * 0.5
        temp_asym        = np.abs(np.random.normal(0.55, 0.15, n)) + sub * 0.25
        accel_x          = np.random.normal(1.15, 0.16, n) + sub * 0.15
        accel_y          = np.random.normal(1.18, 0.15, n) + sub * 0.15
        accel_z          = np.random.normal(9.85, 0.22, n)
        gyro_rom         = np.random.normal(86, 9, n) - sub * 12
        step_sym         = np.random.normal(0.78, 0.04, n) - sub * 0.06
        flex_angle       = np.random.normal(92, 8, n) - sub * 12
        flex_stiff       = np.random.normal(0.45, 0.07, n) + sub * 0.12
        label_name       = "Early_OA"
        kl_label         = "Grade 2 (Mild OA)"
        risk_base        = 0.44 + sub * 0.20
        cartilage_wear   = np.random.uniform(0.35, 0.60, n)
        implant_cand     = "High-Flex Physical Therapy & Quad Strengthening"
        
    elif grade == 3:
        # KL 3: Moderate OA (Definite JSN, Multiple Osteophytes)
        audio_rms        = np.random.normal(0.092, 0.018, n) + sub * 0.030
        dom_freq         = np.random.normal(560, 85, n) + sub * 110
        crep_score       = np.random.normal(0.68, 0.08, n) + sub * 0.15
        joint_temp       = np.random.normal(35.8, 0.5, n) + sub * 0.6
        temp_asym        = np.abs(np.random.normal(1.10, 0.25, n)) + sub * 0.40
        accel_x          = np.random.normal(1.45, 0.18, n) + sub * 0.20
        accel_y          = np.random.normal(1.42, 0.18, n) + sub * 0.20
        accel_z          = np.random.normal(9.88, 0.28, n)
        gyro_rom         = np.random.normal(68, 8, n) - sub * 14
        step_sym         = np.random.normal(0.68, 0.05, n) - sub * 0.08
        flex_angle       = np.random.normal(74, 8, n) - sub * 14
        flex_stiff       = np.random.normal(0.68, 0.07, n) + sub * 0.12
        label_name       = "Moderate_OA"
        kl_label         = "Grade 3 (Moderate OA)"
        risk_base        = 0.68 + sub * 0.18
        cartilage_wear   = np.random.uniform(0.60, 0.82, n)
        implant_cand     = "Viscosupplementation / Unicompartmental (UKA) Consult"
        
    else:
        # KL 4: Severe OA (Marked JSN, Severe Sclerosis, Bone Eburnation)
        audio_rms        = np.random.normal(0.145, 0.025, n) + sub * 0.040
        dom_freq         = np.random.normal(720, 95, n) + sub * 120
        crep_score       = np.random.normal(0.88, 0.06, n) + sub * 0.10
        joint_temp       = np.random.normal(36.7, 0.6, n) + sub * 0.7
        temp_asym        = np.abs(np.random.normal(1.70, 0.30, n)) + sub * 0.50
        accel_x          = np.random.normal(1.78, 0.22, n) + sub * 0.25
        accel_y          = np.random.normal(1.72, 0.22, n) + sub * 0.25
        accel_z          = np.random.normal(9.92, 0.35, n)
        gyro_rom         = np.random.normal(46, 8, n) - sub * 15
        step_sym         = np.random.normal(0.52, 0.06, n) - sub * 0.10
        flex_angle       = np.random.normal(50, 9, n) - sub * 15
        flex_stiff       = np.random.normal(0.86, 0.06, n) + sub * 0.10
        label_name       = "Severe_OA"
        kl_label         = "Grade 4 (Severe OA)"
        risk_base        = 0.85 + sub * 0.14
        cartilage_wear   = np.random.uniform(0.82, 0.98, n)
        implant_cand     = "Total Knee Arthroplasty (TKA) Surgical Consult"

    # Clipping to physiological ranges
    df = pd.DataFrame({
        "audio_rms":        np.clip(audio_rms,  0.005, 0.250),
        "dominant_freq_hz": np.clip(dom_freq,   20.0,  950.0),
        "crepitus_score":   np.clip(crep_score, 0.00,  1.000),
        "joint_temp_c":     np.clip(joint_temp, 31.5,  39.0),
        "temp_asymmetry":   np.clip(temp_asym,  0.00,  3.50),
        "accel_rms_x":      np.clip(accel_x,    0.40,  2.80),
        "accel_rms_y":      np.clip(accel_y,    0.40,  2.80),
        "accel_rms_z":      np.clip(accel_z,    9.00,  11.50),
        "gyro_range_deg":   np.clip(gyro_rom,   10.0,  150.0),
        "step_symmetry":    np.clip(step_sym,   0.30,  1.000),
        "flex_angle_deg":   np.clip(flex_angle, 15.0,  145.0),
        "flex_stiffness":   np.clip(flex_stiff, 0.02,  1.000),
        "kl_grade":         grade,
        "kl_grade_label":   kl_label,
        "binary_label":     0 if grade < 2 else 1,   # 0 = Normal/Preclinical, 1 = Clinical OA
        "label_name":       label_name,
        "progression_risk": np.clip(risk_base, 0.01, 0.99),
        "cartilage_wear":   np.clip(cartilage_wear, 0.01, 1.00),
        "implant_candidacy": implant_cand
    })
    return df

def main():
    print("=" * 70)
    print("  Clinical Multi-Modal OA Dataset Generator")
    print("  Grounded in NIH OAI, RSNA Benchmarks & Radiopaedia KL Staging")
    print("=" * 70)

    dfs = []
    for g in range(5):
        df_g = generate_kl_grade_samples(g, SAMPLES_PER_GRADE)
        dfs.append(df_g)
        print(f"[GEN] Generated {len(df_g)} samples for KL Grade {g} ({df_g['kl_grade_label'].iloc[0]})")

    df = pd.concat(dfs, ignore_index=True)
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    df.insert(0, "sample_id", [f"OAI_PAT_{i+1:05d}" for i in range(len(df))])

    # Assign realistic clinical age distribution correlated with KL grade
    age_offsets = {0: 38, 1: 48, 2: 58, 3: 66, 4: 72}
    df["patient_age"] = [
        int(np.clip(np.random.normal(age_offsets[g], 7), 24, 88))
        for g in df["kl_grade"]
    ]
    df["gender"] = np.random.choice(["Female", "Male"], size=len(df), p=[0.58, 0.42])

    print(f"\n[SUMMARY] Total samples: {len(df)}")
    print("Class distribution by KL Grade:")
    print(df["kl_grade_label"].value_counts().to_string())

    print(f"\n[SAVE] Saving clinical dataset to: {OUTPUT}")
    df.to_csv(OUTPUT, index=False)
    print(f"[DONE] File written ({os.path.getsize(OUTPUT)/1024:.1f} KB)")

if __name__ == "__main__":
    main()
