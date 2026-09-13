"""
=============================================================
 OA Detection System — ML Training Pipeline
 SIH 2026 | Problem Statement 26004 | MDoNER
=============================================================
 Trains an ensemble classifier on sensor features to detect
 early-stage Osteoarthritis vs Normal knee joints.

 Models:
   1. Random Forest (primary)
   2. Gradient Boosting
   3. SVM (RBF kernel)
   4. Voting Ensemble (all three)

 Outputs:
   - models/oa_model.pkl    ← Final trained ensemble model
   - models/scaler.pkl      ← Feature scaler (StandardScaler)
   - models/model_info.json ← Metadata + accuracy metrics
   - plots/confusion_matrix.png
   - plots/roc_curve.png
   - plots/feature_importance.png
   - plots/class_comparison.png
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

# ─── IMPORTS ──────────────────────────────────────────────────────────────────
try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
    from sklearn.svm import SVC
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
    from sklearn.metrics import (accuracy_score, classification_report,
                                  confusion_matrix, roc_auc_score, roc_curve,
                                  f1_score, precision_score, recall_score)
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import seaborn as sns
except ImportError as e:
    print(f"[ERR] Missing dependency: {e}")
    print("Install with: pip install scikit-learn matplotlib seaborn pandas numpy")
    sys.exit(1)

# ─── PATHS ────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATASET     = os.path.join(BASE_DIR, "oa_dataset.csv")
MODEL_DIR   = os.path.join(BASE_DIR, "models")
PLOTS_DIR   = os.path.join(BASE_DIR, "plots")
MODEL_PATH  = os.path.join(MODEL_DIR, "oa_model.pkl")
SCALER_PATH = os.path.join(MODEL_DIR, "scaler.pkl")
INFO_PATH   = os.path.join(MODEL_DIR, "model_info.json")

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(PLOTS_DIR, exist_ok=True)

# ─── FEATURE COLUMNS ──────────────────────────────────────────────────────────
FEATURE_COLS = [
    "audio_rms", "dominant_freq_hz", "crepitus_score",
    "joint_temp_c", "temp_asymmetry",
    "accel_rms_x", "accel_rms_y", "accel_rms_z",
    "gyro_range_deg", "step_symmetry",
    "flex_angle_deg", "flex_stiffness"
]

FEATURE_LABELS = {
    "audio_rms":         "Audio RMS\n(Crepitus Level)",
    "dominant_freq_hz":  "Joint Sound\nFrequency (Hz)",
    "crepitus_score":    "Crepitus\nScore",
    "joint_temp_c":      "Joint Temp\n(°C)",
    "temp_asymmetry":    "Temp\nAsymmetry (°C)",
    "accel_rms_x":       "Accel RMS X\n(m/s²)",
    "accel_rms_y":       "Accel RMS Y\n(m/s²)",
    "accel_rms_z":       "Accel RMS Z\n(m/s²)",
    "gyro_range_deg":    "ROM\n(degrees)",
    "step_symmetry":     "Step\nSymmetry",
    "flex_angle_deg":    "Flex Angle\n(degrees)",
    "flex_stiffness":    "Joint\nStiffness"
}

# ─── STYLING ──────────────────────────────────────────────────────────────────
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
    'font.size':         10,
})

COLORS = {
    'normal':   '#22d3ee',   # Cyan
    'oa':       '#f43f5e',   # Rose
    'accent':   '#a78bfa',   # Purple
    'success':  '#22c55e',   # Green
    'warning':  '#f59e0b',   # Amber
}


# ─── LOAD DATASET ─────────────────────────────────────────────────────────────
def load_data():
    if not os.path.exists(DATASET):
        print(f"[INFO] Dataset not found. Generating it...")
        import subprocess
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "generate_dataset.py")])

    df = pd.read_csv(DATASET)
    print(f"[DATA] Loaded {len(df)} samples ({(df['label']==0).sum()} Normal, "
          f"{(df['label']==1).sum()} OA)")

    X = df[FEATURE_COLS].values
    y = df["label"].values
    return X, y, df


# ─── BUILD MODELS ─────────────────────────────────────────────────────────────
def build_models():
    rf = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        min_samples_split=4,
        min_samples_leaf=2,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1
    )

    gb = GradientBoostingClassifier(
        n_estimators=150,
        learning_rate=0.08,
        max_depth=5,
        subsample=0.85,
        random_state=42
    )

    svm = SVC(
        kernel='rbf',
        C=10.0,
        gamma='scale',
        probability=True,
        class_weight='balanced',
        random_state=42
    )

    ensemble = VotingClassifier(
        estimators=[('rf', rf), ('gb', gb), ('svm', svm)],
        voting='soft',
        weights=[3, 2, 1]   # RF weighted highest
    )

    return {"RandomForest": rf, "GradientBoosting": gb, "SVM": svm, "Ensemble": ensemble}


# ─── TRAIN & EVALUATE ─────────────────────────────────────────────────────────
def train_evaluate(X_train, X_test, y_train, y_test, models):
    results = {}
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    print("\n[TRAIN] Training all models...")
    print("-" * 60)

    for name, model in models.items():
        model.fit(X_train, y_train)
        y_pred      = model.predict(X_test)
        y_proba     = model.predict_proba(X_test)[:, 1]
        cv_scores   = cross_val_score(model, X_train, y_train, cv=skf,
                                       scoring='f1', n_jobs=-1)

        results[name] = {
            "accuracy":  accuracy_score(y_test, y_pred),
            "f1":        f1_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred),
            "recall":    recall_score(y_test, y_pred),
            "auc":       roc_auc_score(y_test, y_proba),
            "cv_mean":   cv_scores.mean(),
            "cv_std":    cv_scores.std(),
            "y_pred":    y_pred,
            "y_proba":   y_proba,
        }

        print(f"  {name:20s}: Acc={results[name]['accuracy']:.3f} | "
              f"F1={results[name]['f1']:.3f} | "
              f"AUC={results[name]['auc']:.3f} | "
              f"CV={cv_scores.mean():.3f}±{cv_scores.std():.3f}")

    return results


# ─── PLOT CONFUSION MATRIX ────────────────────────────────────────────────────
def plot_confusion_matrix(y_test, y_pred, name, ax):
    cm = confusion_matrix(y_test, y_pred)
    cm_pct = cm.astype(float) / cm.sum(axis=1)[:, np.newaxis] * 100

    sns.heatmap(
        cm, annot=False, fmt='d', ax=ax,
        cmap=sns.color_palette(['#1e2937', '#0e4f6e', '#22d3ee'], as_cmap=True),
        linewidths=2, linecolor='#0d1117',
        cbar_kws={'shrink': 0.7}
    )

    for i in range(2):
        for j in range(2):
            ax.text(j + 0.5, i + 0.35, f"{cm[i,j]}",
                    ha='center', va='center', fontsize=18, fontweight='bold',
                    color='white')
            ax.text(j + 0.5, i + 0.65, f"({cm_pct[i,j]:.1f}%)",
                    ha='center', va='center', fontsize=10, color='#8b949e')

    ax.set_xlabel('Predicted', fontsize=11, labelpad=8)
    ax.set_ylabel('Actual', fontsize=11, labelpad=8)
    ax.set_title(f'{name}', fontsize=12, pad=10, color=COLORS['accent'])
    ax.set_xticklabels(['Normal', 'Early OA'], fontsize=10)
    ax.set_yticklabels(['Normal', 'Early OA'], fontsize=10, rotation=0)


def plot_all_confusion_matrices(y_test, results):
    fig, axes = plt.subplots(1, 4, figsize=(22, 5.5))
    fig.suptitle('Confusion Matrices — All Models', fontsize=16, y=1.02,
                 color='white', fontweight='bold')
    fig.patch.set_facecolor('#0d1117')

    for ax, (name, res) in zip(axes, results.items()):
        plot_confusion_matrix(y_test, res['y_pred'], name, ax)

    plt.tight_layout()
    path = os.path.join(PLOTS_DIR, "confusion_matrix.png")
    plt.savefig(path, dpi=150, bbox_inches='tight', facecolor='#0d1117')
    plt.close()
    print(f"[PLOT] Confusion matrices saved → {path}")


# ─── PLOT ROC CURVES ─────────────────────────────────────────────────────────
def plot_roc_curves(y_test, results):
    fig, ax = plt.subplots(figsize=(8, 7))
    fig.patch.set_facecolor('#0d1117')

    model_colors = {
        'RandomForest':    '#22d3ee',
        'GradientBoosting':'#a78bfa',
        'SVM':             '#f59e0b',
        'Ensemble':        '#22c55e',
    }

    for name, res in results.items():
        fpr, tpr, _ = roc_curve(y_test, res['y_proba'])
        ax.plot(fpr, tpr, linewidth=2.5, label=f"{name}  (AUC={res['auc']:.3f})",
                color=model_colors.get(name, 'white'), alpha=0.9)

    ax.plot([0, 1], [0, 1], 'w--', alpha=0.3, linewidth=1, label='Random Classifier')
    ax.fill_between([0, 1], [0, 1], alpha=0.05, color='white')

    ax.set_xlabel('False Positive Rate (1 - Specificity)', fontsize=12, labelpad=10)
    ax.set_ylabel('True Positive Rate (Sensitivity)', fontsize=12, labelpad=10)
    ax.set_title('ROC Curves — OA Detection Models', fontsize=14, pad=15, fontweight='bold')
    ax.legend(loc='lower right', fontsize=10, framealpha=0.2)
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1.02])
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = os.path.join(PLOTS_DIR, "roc_curve.png")
    plt.savefig(path, dpi=150, bbox_inches='tight', facecolor='#0d1117')
    plt.close()
    print(f"[PLOT] ROC curves saved → {path}")


# ─── PLOT FEATURE IMPORTANCE ─────────────────────────────────────────────────
def plot_feature_importance(rf_model):
    importance = rf_model.feature_importances_
    indices    = np.argsort(importance)[::-1]
    sorted_features = [FEATURE_LABELS.get(FEATURE_COLS[i], FEATURE_COLS[i]) for i in indices]

    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor('#0d1117')

    bars = ax.bar(range(len(importance)), importance[indices],
                   color=COLORS['accent'], alpha=0.85, edgecolor='#7c3aed', linewidth=0.8)

    # Color top-3 differently
    for i, bar in enumerate(bars[:3]):
        bar.set_color(COLORS['success'])
        bar.set_alpha(1.0)

    ax.set_xticks(range(len(importance)))
    ax.set_xticklabels(sorted_features, rotation=30, ha='right', fontsize=9)
    ax.set_ylabel('Feature Importance Score', fontsize=12, labelpad=10)
    ax.set_title('Feature Importance — Random Forest\n(Higher = More Predictive for OA Detection)',
                 fontsize=13, pad=15, fontweight='bold')
    ax.grid(True, axis='y', alpha=0.3)

    # Add value labels
    for bar, imp in zip(bars, importance[indices]):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.002,
                f"{imp:.3f}", ha='center', va='bottom', fontsize=8, color='#8b949e')

    plt.tight_layout()
    path = os.path.join(PLOTS_DIR, "feature_importance.png")
    plt.savefig(path, dpi=150, bbox_inches='tight', facecolor='#0d1117')
    plt.close()
    print(f"[PLOT] Feature importance saved → {path}")


# ─── PLOT CLASS COMPARISON ───────────────────────────────────────────────────
def plot_class_comparison(df):
    """Radar + violin chart comparing Normal vs OA across all features."""
    fig, axes = plt.subplots(2, 6, figsize=(24, 10))
    fig.patch.set_facecolor('#0d1117')
    fig.suptitle('Sensor Feature Distribution: Normal vs Early OA',
                 fontsize=16, fontweight='bold', color='white', y=1.01)

    axes_flat = axes.flatten()
    df_normal = df[df['label'] == 0]
    df_oa     = df[df['label'] == 1]

    for i, col in enumerate(FEATURE_COLS):
        ax = axes_flat[i]
        label = FEATURE_LABELS.get(col, col)

        parts_normal = ax.violinplot([df_normal[col].values], positions=[0.8],
                                      widths=0.5, showmedians=True)
        parts_oa     = ax.violinplot([df_oa[col].values],     positions=[1.8],
                                      widths=0.5, showmedians=True)

        for pc in parts_normal['bodies']:
            pc.set_facecolor(COLORS['normal'])
            pc.set_alpha(0.6)
        parts_normal['cmedians'].set_color(COLORS['normal'])
        parts_normal['cmedians'].set_linewidth(2)

        for pc in parts_oa['bodies']:
            pc.set_facecolor(COLORS['oa'])
            pc.set_alpha(0.6)
        parts_oa['cmedians'].set_color(COLORS['oa'])
        parts_oa['cmedians'].set_linewidth(2)

        ax.set_xticks([0.8, 1.8])
        ax.set_xticklabels(['Normal', 'OA'], fontsize=9)
        ax.set_title(label, fontsize=9, pad=5)
        ax.grid(True, axis='y', alpha=0.3)

    # Legend
    legend_patches = [
        mpatches.Patch(color=COLORS['normal'], alpha=0.7, label='Normal'),
        mpatches.Patch(color=COLORS['oa'],     alpha=0.7, label='Early OA'),
    ]
    fig.legend(handles=legend_patches, loc='upper right', fontsize=12, framealpha=0.2)

    plt.tight_layout()
    path = os.path.join(PLOTS_DIR, "class_comparison.png")
    plt.savefig(path, dpi=150, bbox_inches='tight', facecolor='#0d1117')
    plt.close()
    print(f"[PLOT] Class comparison chart saved → {path}")


# ─── PRINT RESULTS TABLE ─────────────────────────────────────────────────────
def print_results_table(results):
    print("\n" + "=" * 70)
    print("  MODEL PERFORMANCE COMPARISON")
    print("=" * 70)
    print(f"  {'Model':<20} {'Acc':>6} {'F1':>6} {'Prec':>6} {'Recall':>6} {'AUC':>6}")
    print("-" * 70)
    for name, res in results.items():
        marker = " <<< BEST" if name == "Ensemble" else ""
        print(f"  {name:<20} {res['accuracy']:>6.3f} {res['f1']:>6.3f} "
              f"{res['precision']:>6.3f} {res['recall']:>6.3f} {res['auc']:>6.3f}{marker}")
    print("=" * 70)


# ─── SAVE MODEL ──────────────────────────────────────────────────────────────
def save_model(ensemble, scaler, results):
    with open(MODEL_PATH, 'wb') as f:
        pickle.dump(ensemble, f)
    with open(SCALER_PATH, 'wb') as f:
        pickle.dump(scaler, f)

    info = {
        "model_type": "VotingClassifier (RF + GB + SVM)",
        "feature_columns": FEATURE_COLS,
        "classes": {0: "Normal", 1: "Early_OA"},
        "metrics": {
            name: {k: float(v) for k, v in res.items()
                   if k not in ['y_pred', 'y_proba']}
            for name, res in results.items()
        },
        "version": "1.0.0",
        "sih": "2026-PS-26004"
    }
    with open(INFO_PATH, 'w') as f:
        json.dump(info, f, indent=2)

    print(f"\n[SAVE] Model    → {MODEL_PATH}")
    print(f"[SAVE] Scaler   → {SCALER_PATH}")
    print(f"[SAVE] Metadata → {INFO_PATH}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  OA Detection ML Training Pipeline")
    print("  SIH 2026 | PS-26004 | MDoNER")
    print("=" * 60)

    # 1. Load data
    X, y, df = load_data()

    # 2. Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )
    print(f"[SPLIT] Train: {len(X_train)} | Test: {len(X_test)}")

    # 3. Scale
    scaler  = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test  = scaler.transform(X_test)

    # 4. Train all models
    models  = build_models()
    results = train_evaluate(X_train, X_test, y_train, y_test, models)

    # 5. Print comparison table
    print_results_table(results)

    # 6. Generate all plots
    print("\n[PLOT] Generating evaluation plots...")
    plot_all_confusion_matrices(y_test, results)
    plot_roc_curves(y_test, results)
    plot_feature_importance(models["RandomForest"])
    plot_class_comparison(df)

    # 7. Print best model report
    ens_pred = results["Ensemble"]["y_pred"]
    print("\n[REPORT] Ensemble Model — Classification Report:")
    print(classification_report(y_test, ens_pred,
                                 target_names=['Normal (0)', 'Early OA (1)']))

    # 8. Save model + metadata
    save_model(models["Ensemble"], scaler, results)

    best_acc = results["Ensemble"]["accuracy"]
    print(f"\n[DONE] Training complete! Ensemble accuracy: {best_acc*100:.2f}%")
    if best_acc >= 0.85:
        print("[PASS] ✓ Target accuracy ≥85% achieved!")
    else:
        print("[WARN] Accuracy below 85% — consider tuning hyperparameters or collecting more data.")

    print("\n[OUTPUT] Files generated:")
    print(f"  Model:       {MODEL_PATH}")
    print(f"  Scaler:      {SCALER_PATH}")
    print(f"  CM Plot:     {os.path.join(PLOTS_DIR, 'confusion_matrix.png')}")
    print(f"  ROC Plot:    {os.path.join(PLOTS_DIR, 'roc_curve.png')}")
    print(f"  Importance:  {os.path.join(PLOTS_DIR, 'feature_importance.png')}")
    print(f"  Comparison:  {os.path.join(PLOTS_DIR, 'class_comparison.png')}")


if __name__ == "__main__":
    main()
