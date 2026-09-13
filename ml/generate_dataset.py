"""
=============================================================
 OA Detection System — Synthetic Dataset Generator
 SIH 2026 | Problem Statement 26004 | MDoNER
=============================================================
 Generates clinically-inspired synthetic data for:
   - Class 0: Normal (healthy knee joint)
   - Class 1: Early Osteoarthritis

 Feature distributions are derived from published OA biomarker
 research (Berenbaum 2013, Kraus 2015, Felson 2009).
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

# ─── CONFIG ───────────────────────────────────────────────────────────────────
N_NORMAL = 600    # Number of normal samples
N_OA     = 600    # Number of OA samples
OUTPUT   = os.path.join(os.path.dirname(__file__), "oa_dataset.csv")


# ─── FEATURE DISTRIBUTIONS ────────────────────────────────────────────────────
#
# Normal Person:
#   - Quiet joint sounds (low RMS, low freq)
#   - Normal joint temperature ~32–34°C
#   - Regular gait pattern (high symmetry)
#   - Full range of motion ~90–130°
#   - Low flex stiffness
#
# Early OA Person:
#   - Crepitus: audible crackling (higher RMS, 300–800 Hz)
#   - Slightly elevated joint temp ~35–37.5°C (synovial inflammation)
#   - Irregular gait (asymmetric loading, pain avoidance)
#   - Reduced ROM ~30–80° (morning stiffness, restricted movement)
#   - Higher flex stiffness
#
# Reference ranges from:
#  - Kawchuk GN et al., "Real-time visualization of joint cavitation"
#  - Peat G et al., "Clinical classification criteria for knee OA"
#  - Neogi T et al., "Epidemiology of OA"

def generate_normal(n):
    """Generate sensor feature data for a healthy person."""
    data = {
        # Microphone / acoustic features
        "audio_rms":          np.random.normal(0.018, 0.006, n).clip(0.005, 0.045),
        "dominant_freq_hz":   np.random.normal(150,   50,    n).clip(20,    299),
        "crepitus_score":     np.random.normal(0.05,  0.04,  n).clip(0.0,   0.18),

        # Temperature features
        "joint_temp_c":       np.random.normal(33.2,  0.6,   n).clip(31.5,  34.8),
        "temp_asymmetry":     np.abs(np.random.normal(0.1,   0.08,  n)).clip(0.0, 0.35),

        # IMU / gait features
        "accel_rms_x":        np.random.normal(0.85,  0.15,  n).clip(0.4,   1.3),
        "accel_rms_y":        np.random.normal(0.90,  0.12,  n).clip(0.5,   1.2),
        "accel_rms_z":        np.random.normal(9.82,  0.20,  n).clip(9.2,   10.4),
        "gyro_range_deg":     np.random.normal(105,   15,    n).clip(70,    140),
        "step_symmetry":      np.random.normal(0.92,  0.04,  n).clip(0.80,  1.0),

        # Flex sensor features
        "flex_angle_deg":     np.random.normal(112,   12,    n).clip(80,    140),
        "flex_stiffness":     np.random.normal(0.12,  0.05,  n).clip(0.02,  0.28),

        # Label
        "label": np.zeros(n, dtype=int),
        "label_name": ["Normal"] * n
    }
    return pd.DataFrame(data)


def generate_oa(n):
    """Generate sensor feature data for a person with early-stage OA."""
    # Add some heterogeneity — not all OA patients have identical severity
    severity = np.random.uniform(0.3, 1.0, n)  # OA severity scalar

    data = {
        # Microphone / acoustic features (elevated)
        "audio_rms":          (0.055 + severity * 0.08  + np.random.normal(0, 0.012, n)).clip(0.03, 0.20),
        "dominant_freq_hz":   (320   + severity * 350   + np.random.normal(0, 40,    n)).clip(280,   850),
        "crepitus_score":     (0.40  + severity * 0.50  + np.random.normal(0, 0.05,  n)).clip(0.25,  1.0),

        # Temperature features (synovial inflammation → warmer)
        "joint_temp_c":       (35.5  + severity * 1.8   + np.random.normal(0, 0.4,   n)).clip(34.5,  38.5),
        "temp_asymmetry":     (0.6   + severity * 1.4   + np.abs(np.random.normal(0, 0.15, n))).clip(0.3, 2.5),

        # IMU / gait features (irregular, antalgic gait)
        "accel_rms_x":        (1.25  + severity * 0.60  + np.random.normal(0, 0.15,  n)).clip(0.8,   2.5),
        "accel_rms_y":        (1.30  + severity * 0.55  + np.random.normal(0, 0.15,  n)).clip(0.8,   2.4),
        "accel_rms_z":        (9.82  + severity * 0.40  + np.random.normal(0, 0.30,  n)).clip(9.0,   11.0),
        "gyro_range_deg":     (75    - severity * 45    + np.random.normal(0, 10,    n)).clip(15,    100),
        "step_symmetry":      (0.72  - severity * 0.20  + np.random.normal(0, 0.05,  n)).clip(0.35,  0.85),

        # Flex sensor features (restricted ROM, stiffer)
        "flex_angle_deg":     (75    - severity * 40    + np.random.normal(0, 8,     n)).clip(20,    95),
        "flex_stiffness":     (0.50  + severity * 0.35  + np.random.normal(0, 0.04,  n)).clip(0.30,  0.95),

        # Label
        "label": np.ones(n, dtype=int),
        "label_name": ["Early_OA"] * n
    }
    return pd.DataFrame(data)


# ─── GENERATE & SAVE DATASET ──────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  OA Detection Dataset Generator")
    print("  SIH 2026 | PS-26004 | MDoNER")
    print("=" * 60)

    print(f"\n[GEN] Generating {N_NORMAL} Normal samples...")
    df_normal = generate_normal(N_NORMAL)

    print(f"[GEN] Generating {N_OA} Early-OA samples...")
    df_oa = generate_oa(N_OA)

    # Combine and shuffle
    df = pd.concat([df_normal, df_oa], ignore_index=True)
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)

    # Add metadata columns
    df.insert(0, "sample_id", range(len(df)))
    df["age_group"] = np.where(
        df["label"] == 0,
        np.random.choice(["<40", "40-55"], size=len(df)),
        np.random.choice(["40-55", "55-70", "70+"], size=len(df))
    )

    print(f"\n[STATS] Dataset Summary:")
    print(f"  Total samples : {len(df)}")
    print(f"  Normal (0)    : {(df['label']==0).sum()}")
    print(f"  Early OA (1)  : {(df['label']==1).sum()}")
    print(f"  Features      : {len(df.columns) - 3}")

    print(f"\n[STATS] Feature ranges:")
    numeric_cols = df.select_dtypes(include=np.number).columns.tolist()
    numeric_cols = [c for c in numeric_cols if c not in ['sample_id', 'label']]
    for col in numeric_cols:
        print(f"  {col:22s}: [{df[col].min():.3f}, {df[col].max():.3f}]  "
              f"(mean={df[col].mean():.3f}, std={df[col].std():.3f})")

    print(f"\n[SAVE] Saving to: {OUTPUT}")
    df.to_csv(OUTPUT, index=False)
    print(f"[DONE] Dataset saved ({os.path.getsize(OUTPUT)/1024:.1f} KB)")

    # Class-wise statistics
    print("\n[STATS] Class-wise mean comparison:")
    print("-" * 70)
    feature_cols = [c for c in numeric_cols if c != 'label']
    comparison = df.groupby("label_name")[feature_cols].mean().T
    comparison.columns.name = None
    with pd.option_context('display.float_format', '{:.3f}'.format,
                            'display.max_rows', 20):
        print(comparison.to_string())

    return df


if __name__ == "__main__":
    df = main()
