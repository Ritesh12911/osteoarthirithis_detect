"""
=============================================================
 OA Detection System — Clinical Multi-Task ML Pipeline
 SIH 2026 | Problem Statement 26004 | MDoNER
=============================================================
 Grounded in:
   - Radiopaedia Kellgren-Lawrence (KL 0–4) Staging
   - NIH NDA / OAI (Osteoarthritis Initiative) Cohorts
   - RSNA Multimodal Knee Abnormality Benchmarks
   - Biorad Medisys Indian Knee Implant & Arthroplasty Guidelines

 Models:
   1. Multi-Class KL Classifier (Random Forest + Extra Trees + Gradient Boosting Soft Ensemble)
   2. Binary Clinical OA Classifier (for backward compatibility)
   3. Continuous OA Progression & Cartilage Wear Regressor

 Outputs:
   - models/oa_kl_model.pkl       ← 5-class KL Staging Ensemble (Grades 0, 1, 2, 3, 4)
   - models/oa_model.pkl          ← Binary Clinical OA Ensemble
   - models/oa_risk_regressor.pkl ← Calibrated Progression Regressor
   - models/scaler.pkl            ← StandardScaler for 12 features
   - models/model_info.json       ← Comprehensive clinical evaluation metrics
   - plots/confusion_matrix.png   ← 5x5 KL confusion matrix
   - plots/roc_curve.png          ← Multiclass ROC curves
   - plots/feature_importance.png ← Sensor contribution breakdown
=============================================================
"""

import os
import sys
import json
import pickle
import warnings

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

try:
    from sklearn.ensemble import (
        RandomForestClassifier,
        GradientBoostingClassifier,
        ExtraTreesClassifier,
        VotingClassifier,
        GradientBoostingRegressor
    )
    from sklearn.svm import SVC
    from sklearn.preprocessing import StandardScaler, label_binarize
    from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
    from sklearn.metrics import (
        accuracy_score, classification_report,
        confusion_matrix, roc_auc_score, roc_curve,
        f1_score, precision_score, recall_score, mean_squared_error, r2_score
    )
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import seaborn as sns
except ImportError as e:
    print(f"[ERR] Missing dependency: {e}")
    sys.exit(1)

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATASET     = os.path.join(BASE_DIR, "oa_dataset.csv")
MODEL_DIR   = os.path.join(BASE_DIR, "models")
PLOTS_DIR   = os.path.join(BASE_DIR, "plots")

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(PLOTS_DIR, exist_ok=True)

FEATURE_COLS = [
    "audio_rms", "dominant_freq_hz", "crepitus_score",
    "joint_temp_c", "temp_asymmetry",
    "accel_rms_x", "accel_rms_y", "accel_rms_z",
    "gyro_range_deg", "step_symmetry",
    "flex_angle_deg", "flex_stiffness"
]

FEATURE_LABELS = {
    "audio_rms":         "Audio RMS (Crepitus Power)",
    "dominant_freq_hz":  "Joint Sound Peak Freq (Hz)",
    "crepitus_score":    "Acoustic Crepitus Score",
    "joint_temp_c":      "Joint Surface Temp (°C)",
    "temp_asymmetry":    "Bilateral Temp Asymmetry (°C)",
    "accel_rms_x":       "Lateral Accel RMS (m/s²)",
    "accel_rms_y":       "Vertical Accel RMS (m/s²)",
    "accel_rms_z":       "A-P Accel RMS (m/s²)",
    "gyro_range_deg":    "Dynamic Flexion ROM (°)",
    "step_symmetry":     "Gait Step Symmetry Index",
    "flex_angle_deg":    "Maximum Flex Angle (°)",
    "flex_stiffness":    "Passive Joint Stiffness"
}

KL_CLASSES = {
    0: "Grade 0 (Normal)",
    1: "Grade 1 (Doubtful)",
    2: "Grade 2 (Mild OA)",
    3: "Grade 3 (Moderate OA)",
    4: "Grade 4 (Severe OA)"
}

plt.rcParams.update({
    'figure.facecolor':  '#0d1117',
    'axes.facecolor':    '#161b22',
    'axes.edgecolor':    '#30363d',
    'axes.labelcolor':   '#e6edf3',
    'xtick.color':       '#8b949e',
    'ytick.color':       '#8b949e',
    'text.color':        '#e6edf3',
    'grid.color':        '#21262d',
    'grid.linestyle':    '--',
    'grid.alpha':        0.6,
    'font.family':       'DejaVu Sans',
    'font.size':         9,
})

def load_data():
    if not os.path.exists(DATASET):
        print("[INFO] Dataset not found. Generating clinical dataset...")
        import subprocess
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "generate_clinical_dataset.py")], check=True)

    df = pd.read_csv(DATASET)
    print(f"[DATA] Loaded {len(df)} clinical samples across 5 KL grades.")

    X = df[FEATURE_COLS].values
    y_kl = df["kl_grade"].values
    y_bin = df["binary_label"].values if "binary_label" in df.columns else (y_kl >= 2).astype(int)
    y_risk = df["progression_risk"].values if "progression_risk" in df.columns else (y_kl / 4.0)

    return X, y_kl, y_bin, y_risk, df

def train_kl_ensemble(X_train, X_test, y_train, y_test):
    print("\n[TRAIN] Training Multi-Class Kellgren-Lawrence (KL 0-4) Classifier...")
    print("-" * 70)

    rf = RandomForestClassifier(
        n_estimators=180,
        max_depth=12,
        min_samples_split=4,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1
    )
    et = ExtraTreesClassifier(
        n_estimators=180,
        max_depth=12,
        min_samples_split=4,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1
    )
    gb = GradientBoostingClassifier(
        n_estimators=140,
        learning_rate=0.08,
        max_depth=4,
        subsample=0.85,
        random_state=42
    )

    ensemble = VotingClassifier(
        estimators=[('rf', rf), ('et', et), ('gb', gb)],
        voting='soft',
        weights=[3, 2, 2]
    )

    ensemble.fit(X_train, y_train)
    y_pred = ensemble.predict(X_test)
    y_prob = ensemble.predict_proba(X_test)

    acc = accuracy_score(y_test, y_pred)
    f1_macro = f1_score(y_test, y_pred, average='macro')
    f1_weighted = f1_score(y_test, y_pred, average='weighted')

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(ensemble, X_train, y_train, cv=skf, scoring='accuracy', n_jobs=-1)

    print(f"  KL Multi-Class Ensemble: Acc={acc*100:.2f}% | F1-Macro={f1_macro*100:.2f}% | 5-Fold CV={cv_scores.mean()*100:.2f}±{cv_scores.std()*100:.2f}%")
    print("\nClassification Report (KL 0–4 Staging):")
    print(classification_report(y_test, y_pred, target_names=[KL_CLASSES[i] for i in range(5)]))

    # Also compute RF feature importance for plotting
    rf.fit(X_train, y_train)
    importances = rf.feature_importances_

    return ensemble, {
        "accuracy": float(acc),
        "f1_macro": float(f1_macro),
        "f1_weighted": float(f1_weighted),
        "cv_mean": float(cv_scores.mean()),
        "cv_std": float(cv_scores.std()),
        "y_pred": y_pred,
        "y_prob": y_prob,
        "feature_importances": {col: float(imp) for col, imp in zip(FEATURE_COLS, importances)}
    }

def train_binary_model(X_train, X_test, y_train, y_test):
    print("\n[TRAIN] Training Binary Clinical OA Classifier (Normal vs Clinical OA)...")
    print("-" * 70)

    rf = RandomForestClassifier(n_estimators=150, max_depth=10, random_state=42, n_jobs=-1)
    gb = GradientBoostingClassifier(n_estimators=100, learning_rate=0.08, max_depth=4, random_state=42)
    ensemble = VotingClassifier(estimators=[('rf', rf), ('gb', gb)], voting='soft', weights=[2, 1])

    ensemble.fit(X_train, y_train)
    y_pred = ensemble.predict(X_test)
    y_prob = ensemble.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_prob)

    print(f"  Binary Ensemble: Acc={acc*100:.2f}% | F1={f1*100:.2f}% | AUC={auc*100:.2f}%")

    return ensemble, {
        "accuracy": float(acc),
        "f1": float(f1),
        "auc": float(auc)
    }

def train_risk_regressor(X_train, X_test, y_train, y_test):
    print("\n[TRAIN] Training OA Progression Risk Regressor (OAI Benchmark)...")
    print("-" * 70)

    gbr = GradientBoostingRegressor(n_estimators=120, learning_rate=0.07, max_depth=4, random_state=42)
    gbr.fit(X_train, y_train)
    y_pred = gbr.predict(X_test)

    r2 = r2_score(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    print(f"  Risk Regressor: R²={r2:.3f} | RMSE={rmse:.3f}")

    return gbr, {"r2": float(r2), "rmse": float(rmse)}

def generate_evaluation_plots(y_test_kl, kl_results, feature_importances):
    print("\n[PLOTS] Generating publication-quality clinical evaluation plots...")

    # 1. 5x5 Kellgren-Lawrence Confusion Matrix
    cm = confusion_matrix(y_test_kl, kl_results["y_pred"])
    cm_pct = cm.astype(float) / cm.sum(axis=1)[:, np.newaxis] * 100

    fig, ax = plt.subplots(figsize=(8, 7), dpi=150)
    sns.heatmap(
        cm, annot=False, fmt='d', ax=ax,
        cmap=sns.color_palette(['#0f172a', '#0369a1', '#06b6d4', '#10b981'], as_cmap=True),
        linewidths=1.5, linecolor='#0d1117'
    )
    for i in range(5):
        for j in range(5):
            count = cm[i, j]
            pct = cm_pct[i, j]
            color = '#ffffff' if count > cm.max() * 0.35 else '#94a3b8'
            ax.text(j + 0.5, i + 0.4, f"{count}", ha='center', va='center',
                    fontsize=12, fontweight='bold', color=color)
            ax.text(j + 0.5, i + 0.65, f"({pct:.1f}%)", ha='center', va='center',
                    fontsize=9, color=color)

    labels = ["KL 0\nNormal", "KL 1\nDoubtful", "KL 2\nMild OA", "KL 3\nModerate", "KL 4\nSevere"]
    ax.set_xticklabels(labels, fontsize=10, fontweight='600')
    ax.set_yticklabels(labels, fontsize=10, fontweight='600', rotation=0)
    ax.set_xlabel("Predicted Clinical Stage", fontsize=11, labelpad=10, color='#e2e8f0', fontweight='bold')
    ax.set_ylabel("Radiographic True Stage (KL)", fontsize=11, labelpad=10, color='#e2e8f0', fontweight='bold')
    ax.set_title("Multi-Modal Osteoarthritis Staging — Confusion Matrix\nRadiopaedia Kellgren-Lawrence (KL 0–4) Standard",
                 fontsize=12, fontweight='bold', pad=15, color='#ffffff')
    plt.tight_layout()
    cm_path = os.path.join(PLOTS_DIR, "confusion_matrix.png")
    plt.savefig(cm_path, dpi=200, facecolor=fig.get_facecolor(), bbox_inches='tight')
    plt.close()
    print(f"  ✓ Saved: {cm_path}")

    # 2. Feature Importance Breakdown
    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
    sorted_features = sorted(feature_importances.items(), key=lambda x: x[1], reverse=True)
    names = [FEATURE_LABELS.get(k, k) for k, _ in sorted_features]
    vals = [v * 100 for _, v in sorted_features]

    # Sensor group coloring: Audio (Cyan), Temp (Orange), Gait/IMU (Purple), Flex (Green)
    bar_colors = []
    for k, _ in sorted_features:
        if 'audio' in k or 'freq' in k or 'crep' in k:
            bar_colors.append('#06b6d4') # Cyan
        elif 'temp' in k:
            bar_colors.append('#f59e0b') # Amber
        elif 'accel' in k or 'gyro' in k or 'step' in k:
            bar_colors.append('#a855f7') # Purple
        else:
            bar_colors.append('#10b981') # Green

    bars = ax.barh(names[::-1], vals[::-1], color=bar_colors[::-1], height=0.65, edgecolor='#334155')
    for bar in bars:
        w = bar.get_width()
        ax.text(w + 0.3, bar.get_y() + bar.get_height()/2, f"{w:.1f}%",
                va='center', ha='left', fontsize=9, color='#e2e8f0', fontweight='600')

    ax.set_xlabel("Relative Importance Contribution (%)", fontsize=11, color='#e2e8f0', labelpad=8)
    ax.set_title("Multi-Sensor Biomarker Importance Ranking (Gini Contribution)\nINMP441 Acoustic + MLX90614 Thermal + MPU6050 IMU + Flex Sensor",
                 fontsize=12, fontweight='bold', pad=14, color='#ffffff')
    ax.set_xlim(0, max(vals) * 1.18)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()
    fi_path = os.path.join(PLOTS_DIR, "feature_importance.png")
    plt.savefig(fi_path, dpi=200, facecolor=fig.get_facecolor(), bbox_inches='tight')
    plt.close()
    print(f"  ✓ Saved: {fi_path}")

    # 3. Multiclass ROC Curves
    fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
    y_test_bin = label_binarize(y_test_kl, classes=[0, 1, 2, 3, 4])
    colors = ['#22d3ee', '#38bdf8', '#fbbf24', '#f97316', '#ef4444']

    for i in range(5):
        fpr, tpr, _ = roc_curve(y_test_bin[:, i], kl_results["y_prob"][:, i])
        roc_auc = roc_auc_score(y_test_bin[:, i], kl_results["y_prob"][:, i])
        ax.plot(fpr, tpr, color=colors[i], lw=2.2, label=f'{KL_CLASSES[i]} (AUC = {roc_auc:.3f})')

    ax.plot([0, 1], [0, 1], 'k--', lw=1.2, color='#64748b')
    ax.set_xlim([0.0, 1.0])
    ax.set_ylim([0.0, 1.05])
    ax.set_xlabel('False Positive Rate', fontsize=10, color='#e2e8f0')
    ax.set_ylabel('True Positive Rate', fontsize=10, color='#e2e8f0')
    ax.set_title('One-vs-Rest ROC Performance Across Kellgren-Lawrence Stages', fontsize=12, fontweight='bold', color='#ffffff', pad=12)
    ax.legend(loc="lower right", facecolor='#161b22', edgecolor='#30363d', fontsize=9)
    plt.tight_layout()
    roc_path = os.path.join(PLOTS_DIR, "roc_curve.png")
    plt.savefig(roc_path, dpi=200, facecolor=fig.get_facecolor(), bbox_inches='tight')
    plt.close()
    print(f"  ✓ Saved: {roc_path}")

def main():
    print("=" * 70)
    print("  Osteoarthritis Multi-Task Clinical ML Pipeline Training")
    print("  SIH 2026 | PS-26004 | MDoNER")
    print("=" * 70)

    X, y_kl, y_bin, y_risk, df = load_data()

    # Split train/test (80/20 stratified)
    X_train, X_test, y_train_kl, y_test_kl, y_train_bin, y_test_bin, y_train_risk, y_test_risk = train_test_split(
        X, y_kl, y_bin, y_risk,
        test_size=0.20,
        random_state=42,
        stratify=y_kl
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled  = scaler.transform(X_test)

    # 1. Train KL Staging Ensemble
    kl_model, kl_metrics = train_kl_ensemble(X_train_scaled, X_test_scaled, y_train_kl, y_test_kl)

    # 2. Train Binary OA Classifier
    bin_model, bin_metrics = train_binary_model(X_train_scaled, X_test_scaled, y_train_bin, y_test_bin)

    # 3. Train Continuous Progression Regressor
    risk_model, risk_metrics = train_risk_regressor(X_train_scaled, X_test_scaled, y_train_risk, y_test_risk)

    # 4. Generate Plots
    generate_evaluation_plots(y_test_kl, kl_metrics, kl_metrics["feature_importances"])

    # 5. Save Model Artifacts
    kl_path = os.path.join(MODEL_DIR, "oa_kl_model.pkl")
    bin_path = os.path.join(MODEL_DIR, "oa_model.pkl")
    risk_path = os.path.join(MODEL_DIR, "oa_risk_regressor.pkl")
    scaler_path = os.path.join(MODEL_DIR, "scaler.pkl")
    info_path = os.path.join(MODEL_DIR, "model_info.json")

    print("\n[EXPORT] Saving serialized model artifacts...")
    with open(kl_path, 'wb') as f:
        pickle.dump(kl_model, f)
    with open(bin_path, 'wb') as f:
        pickle.dump(bin_model, f)
    with open(risk_path, 'wb') as f:
        pickle.dump(risk_model, f)
    with open(scaler_path, 'wb') as f:
        pickle.dump(scaler, f)

    meta = {
        "system": "AI-Assisted Early Osteoarthritis Detection System",
        "sih_code": "SIH2026-PS-26004",
        "version": "3.0.0-clinical",
        "clinical_standards": [
            "Kellgren-Lawrence (KL) Radiographic Staging System (Radiopaedia)",
            "NIH NDA / OAI (Osteoarthritis Initiative) Cohort Benchmarks",
            "RSNA Multimodal Knee Abnormality Benchmarks",
            "Biorad Medisys Indian Knee Morphometry & High-Flex Guidelines"
        ],
        "feature_columns": FEATURE_COLS,
        "kl_classes": KL_CLASSES,
        "metrics": {
            "kl_staging_accuracy": kl_metrics["accuracy"],
            "kl_staging_f1_macro": kl_metrics["f1_macro"],
            "kl_staging_cv_mean": kl_metrics["cv_mean"],
            "kl_staging_cv_std": kl_metrics["cv_std"],
            "binary_oa_accuracy": bin_metrics["accuracy"],
            "binary_oa_f1": bin_metrics["f1"],
            "binary_oa_auc": bin_metrics["auc"],
            "risk_regressor_r2": risk_metrics["r2"],
            "risk_regressor_rmse": risk_metrics["rmse"]
        },
        "feature_importances": kl_metrics["feature_importances"],
        "treatment_pathways": {
            "0": {"stage": "KL 0", "clinical": "Normal / Healthy Joint", "pathway": "Routine Physical Activity & Joint Wellness"},
            "1": {"stage": "KL 1", "clinical": "Doubtful OA / Cartilage Softening", "pathway": "Preventive Low-Impact Exercise & Ergonomics"},
            "2": {"stage": "KL 2", "clinical": "Mild Clinical OA / Definite Osteophytes", "pathway": "High-Flex Physical Therapy, Anti-inflammatory Diet & Quad Strengthening"},
            "3": {"stage": "KL 3", "clinical": "Moderate OA / Definite Joint Space Narrowing", "pathway": "Viscosupplementation & High-Flex UKA Candidate Evaluation"},
            "4": {"stage": "KL 4", "clinical": "Severe OA / Bone-on-Bone Eburnation", "pathway": "Orthopedic Arthroplasty Consultation (High-Flex TKA / UKA Candidate)"}
        }
    }

    with open(info_path, 'w') as f:
        json.dump(meta, f, indent=2)

    print(f"  ✓ Saved KL Model:        {kl_path} ({os.path.getsize(kl_path)/1024:.1f} KB)")
    print(f"  ✓ Saved Binary Model:    {bin_path} ({os.path.getsize(bin_path)/1024:.1f} KB)")
    print(f"  ✓ Saved Risk Regressor:  {risk_path} ({os.path.getsize(risk_path)/1024:.1f} KB)")
    print(f"  ✓ Saved Scaler:          {scaler_path}")
    print(f"  ✓ Saved Model Info:      {info_path}")
    print("\n[SUCCESS] Multi-task clinical model training completed successfully!")

if __name__ == "__main__":
    main()
