"""
Train a gradient boosting classifier on features produced by the dbt mart.
Reads mart_conversion_features from DuckDB, trains, evaluates, saves artifacts.

Run after: dbt seed && dbt run
Output: artifacts/gbm_model.pkl, artifacts/feature_importance.csv, artifacts/model_metrics.json
"""

import duckdb
import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.metrics import roc_auc_score, average_precision_score, classification_report
from sklearn.calibration import CalibratedClassifierCV
import joblib
import json
import os

DB_PATH = "telehealth_gtm.duckdb"

FEATURE_COLS = [
    # Raw usage signals
    "logins_per_week",
    "days_since_last_login",
    "team_members_invited",
    "api_calls_per_week",
    "features_used_count",
    "support_tickets_l90d",
    "video_consults_per_week",
    "async_messages_per_week",
    "days_on_platform",
    # dbt-computed scores
    "recency_score",
    "frequency_score",
    "expansion_score",
    "behavioral_score",
    "firmographic_score",
    "practice_size_score",
    "ehr_maturity_score",
    "specialty_need_score",
    # Boolean flags
    "is_power_user",
    "is_at_risk",
    "has_billing_system",
    "accepts_insurance",
    "is_group_practice",
    "num_locations",
]

TARGET_COL = "converted_to_enterprise"


def load_data() -> pd.DataFrame:
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute("SELECT * FROM marts.mart_conversion_features").fetchdf()
    con.close()
    return df


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    X = df[FEATURE_COLS].copy()
    bool_cols = ["is_power_user", "is_at_risk", "has_billing_system",
                 "accepts_insurance", "is_group_practice"]
    for col in bool_cols:
        X[col] = X[col].astype(int)
    return X.fillna(0)


def train() -> GradientBoostingClassifier:
    print("Loading mart_conversion_features from DuckDB …")
    df = load_data()
    print(f"  Clinicians loaded : {len(df):,}")
    print(f"  Conversion rate   : {df[TARGET_COL].mean():.2%}")

    X = prepare_features(df)
    y = df[TARGET_COL].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    model = GradientBoostingClassifier(
        n_estimators=300,
        learning_rate=0.04,
        max_depth=4,
        min_samples_leaf=60,
        subsample=0.80,
        max_features="sqrt",
        random_state=42,
        validation_fraction=0.10,
        n_iter_no_change=25,
        tol=1e-4,
    )

    print("\nTraining GBM …")
    model.fit(X_train, y_train)

    # Isotonic calibration for well-calibrated probabilities (prefit=True in sklearn >=1.2)
    calibrated = CalibratedClassifierCV(model, method="isotonic")
    calibrated.fit(X_test, y_test)

    train_proba = calibrated.predict_proba(X_train)[:, 1]
    test_proba  = calibrated.predict_proba(X_test)[:, 1]

    train_auc = roc_auc_score(y_train, train_proba)
    test_auc  = roc_auc_score(y_test,  test_proba)
    test_ap   = average_precision_score(y_test, test_proba)

    # Precision in top-80 (the operational metric that matters most)
    n_top80 = 80
    top80_idx = np.argsort(test_proba)[::-1][:n_top80]
    precision_at_80 = y_test.values[top80_idx].mean()

    print(f"\n=== Model Performance ===")
    print(f"  Train AUC-ROC      : {train_auc:.4f}")
    print(f"  Test  AUC-ROC      : {test_auc:.4f}")
    print(f"  Test  Avg Precision: {test_ap:.4f}")
    print(f"  Precision@80       : {precision_at_80:.4f}")

    importance_df = (
        pd.DataFrame({"feature": FEATURE_COLS, "importance": model.feature_importances_})
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )
    print(f"\n=== Top 10 Features ===")
    print(importance_df.head(10).to_string(index=False))

    os.makedirs("artifacts", exist_ok=True)
    joblib.dump(calibrated, "artifacts/gbm_model.pkl")
    importance_df.to_csv("artifacts/feature_importance.csv", index=False)

    metrics = {
        "train_auc_roc":       float(train_auc),
        "test_auc_roc":        float(test_auc),
        "test_avg_precision":  float(test_ap),
        "precision_at_top_80": float(precision_at_80),
        "n_train":             int(len(X_train)),
        "n_test":              int(len(X_test)),
        "conversion_rate":     float(y.mean()),
        "features":            FEATURE_COLS,
    }
    with open("artifacts/model_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"\nArtifacts written to artifacts/")
    return calibrated


if __name__ == "__main__":
    train()
