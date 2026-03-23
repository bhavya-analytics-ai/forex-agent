"""
ml/trainer.py — Train scoring model from your signal history

After 50+ labeled signals:
  → trains a simple model on your actual outcomes
  → re-weights the scorer to match what actually works for YOU
  → saves weights to ml/weights.json

The model learns:
  - Which components (zone, tf, pattern, session) actually predict wins
  - Which setups you personally take (taken=True) — those get extra weight
  - Re-weights SCORING.weights in config automatically

Usage:
  python -m ml.trainer           # train and save weights
  python -m ml.trainer report    # just show performance report, no training
"""

import os
import sys
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import LOG_CONFIG

logger   = logging.getLogger(__name__)
LOG_PATH = LOG_CONFIG["signal_log_path"]
WEIGHTS_PATH = "ml/weights.json"
MIN_SIGNALS  = 50


FEATURE_COLS = [
    "score_zone",
    "score_tf",
    "score_pattern",
    "score_session",
    "score_news",
    "score_quality_bonus",
    "score_fvg",
]


def load_training_data() -> pd.DataFrame:
    if not os.path.exists(LOG_PATH):
        return pd.DataFrame()

    df = pd.read_csv(LOG_PATH)

    # Only use WIN/LOSS labeled signals
    df = df[df["outcome"].isin(["WIN", "LOSS"])].copy()

    # Binary target: 1 = WIN, 0 = LOSS
    df["target"] = (df["outcome"] == "WIN").astype(int)

    # Fill missing features with 0
    for col in FEATURE_COLS:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def train_model(df: pd.DataFrame) -> dict:
    """
    Simple logistic regression to find which features predict wins.
    Returns dict of feature → importance weight (0–1 normalized).
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import cross_val_score

    X = df[FEATURE_COLS].values
    y = df["target"].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = LogisticRegression(max_iter=1000, random_state=42)
    model.fit(X_scaled, y)

    # Cross-validation accuracy
    cv_scores = cross_val_score(model, X_scaled, y, cv=min(5, len(df)//10 or 2))
    cv_acc    = round(cv_scores.mean() * 100, 1)

    # Feature importances (absolute coefficients, normalized)
    coefs      = np.abs(model.coef_[0])
    normalized = coefs / coefs.sum() if coefs.sum() > 0 else coefs

    weights = {col: round(float(w), 4) for col, w in zip(FEATURE_COLS, normalized)}

    return {
        "weights":       weights,
        "cv_accuracy":   cv_acc,
        "n_signals":     len(df),
        "win_rate":      round(y.mean() * 100, 1),
        "trained_at":    datetime.utcnow().isoformat(),
    }


def apply_weights_to_config(weights: dict):
    """
    Write learned weights to ml/weights.json.
    Scorer will pick these up on next run.
    """
    os.makedirs("ml", exist_ok=True)

    # Map feature columns back to scorer weight names
    weight_map = {
        "score_zone":          "zone_strength",
        "score_tf":            "tf_confluence",
        "score_pattern":       "candle_pattern",
        "score_session":       "session_context",
        "score_news":          "news_clearance",
        "score_quality_bonus": "quality_bonus",
        "score_fvg":           "fvg_bonus",
    }

    # Scale to max_points (zone=25, tf=25, etc.)
    max_points = {
        "zone_strength":   25,
        "tf_confluence":   25,
        "candle_pattern":  20,
        "session_context": 15,
        "news_clearance":  10,
        "quality_bonus":   15,
        "fvg_bonus":       10,
    }

    scaled = {}
    for feat_col, weight_name in weight_map.items():
        importance = weights.get(feat_col, 0)
        max_p      = max_points.get(weight_name, 10)
        # Scale: if importance is high, allow full max_points
        # if low, reduce max_points proportionally
        # floor at 50% of original to avoid zeroing out anything
        scale    = max(0.5, min(importance * 7, 1.0))
        scaled[weight_name] = round(max_p * scale)

    result = {
        "weights":     scaled,
        "raw_weights": weights,
        "updated_at":  datetime.utcnow().isoformat(),
    }

    with open(WEIGHTS_PATH, "w") as f:
        json.dump(result, f, indent=2)

    logger.info(f"Saved weights to {WEIGHTS_PATH}")
    return scaled


def print_report(df: pd.DataFrame):
    print(f"\n{'='*50}")
    print(f"  ML TRAINING REPORT")
    print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*50}")
    print(f"\n  Signals with outcomes: {len(df)}")
    print(f"  Win rate overall:      {round(df['target'].mean()*100,1)}%")

    if "grade" in df.columns:
        print(f"\n  Win rate by grade:")
        for grade in ["A+", "A", "B", "C"]:
            g = df[df["grade"] == grade] if "grade" in df.columns else pd.DataFrame()
            if len(g) >= 3:
                wr = round(g["target"].mean() * 100, 1)
                print(f"    {grade}: {wr}% ({len(g)} signals)")

    if "taken" in df.columns:
        taken = df[df["taken"] == True]
        if len(taken) >= 3:
            print(f"\n  Setups you TOOK:")
            print(f"    Count:    {len(taken)}")
            print(f"    Win rate: {round(taken['target'].mean()*100,1)}%")
            print(f"    (vs {round(df['target'].mean()*100,1)}% overall)")

    if "pair" in df.columns:
        print(f"\n  Win rate by pair:")
        for pair in df["pair"].unique():
            p = df[df["pair"] == pair]
            if len(p) >= 3:
                wr = round(p["target"].mean() * 100, 1)
                print(f"    {pair}: {wr}% ({len(p)} signals)")

    print(f"\n{'='*50}\n")


def run_training():
    df = load_training_data()

    if len(df) < MIN_SIGNALS:
        print(f"\n⏳ Not enough signals to train yet.")
        print(f"   Have: {len(df)} labeled signals")
        print(f"   Need: {MIN_SIGNALS}")
        print(f"   Keep running the scanner — model trains automatically once you hit {MIN_SIGNALS}.\n")
        return

    print_report(df)

    try:
        result = train_model(df)
        scaled = apply_weights_to_config(result["weights"])

        print(f"\n✅ Model trained successfully!")
        print(f"   CV accuracy:   {result['cv_accuracy']}%")
        print(f"   Win rate:      {result['win_rate']}%")
        print(f"   Signals used:  {result['n_signals']}")
        print(f"\n   New weights saved to {WEIGHTS_PATH}")
        print(f"   Scanner will use these weights on next run.\n")

    except ImportError:
        print("\n⚠️  sklearn not installed. Run: pip install scikit-learn")
        print("   Report shown above — manual weight adjustment available.\n")
    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        print(f"\n❌ Training failed: {e}\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "train"

    if cmd == "report":
        df = load_training_data()
        print_report(df)
    else:
        run_training()