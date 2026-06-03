"""
Score all eligible clinicians with the trained model and output the top-80 call list.

Run after: python train_model.py
Output: outputs/weekly_call_list_YYYY-MM-DD.csv
"""

import duckdb
import pandas as pd
import joblib
from datetime import date
import os

DB_PATH    = "telehealth_gtm.duckdb"
MODEL_PATH = "artifacts/gbm_model.pkl"

FEATURE_COLS = [
    "logins_per_week", "days_since_last_login", "team_members_invited",
    "api_calls_per_week", "features_used_count", "support_tickets_l90d",
    "video_consults_per_week", "async_messages_per_week", "days_on_platform",
    "recency_score", "frequency_score", "expansion_score", "behavioral_score",
    "firmographic_score", "practice_size_score", "ehr_maturity_score",
    "specialty_need_score", "is_power_user", "is_at_risk",
    "has_billing_system", "accepts_insurance", "is_group_practice", "num_locations",
]

BOOL_COLS = ["is_power_user", "is_at_risk", "has_billing_system",
             "accepts_insurance", "is_group_practice"]


def get_sales_angle(row: pd.Series) -> str:
    """Return an AE talk-track hint based on the clinician's dominant signal."""
    if row["api_calls_per_week"] > 0:
        return "API power user — lead with integrations, SLA, and developer support"
    if row["team_members_invited"] >= 5:
        return "Growing team — lead with multi-seat pricing, RBAC, and collaboration"
    if row["features_used_count"] >= 8:
        return "Feature explorer — lead with advanced workflows and automation"
    if row["logins_per_week"] >= 7:
        return "Daily-active champion — lead with productivity and time savings"
    if row["practice_size"] in ("Large (51-200)", "Enterprise (200+)"):
        return "Enterprise account — lead with compliance, SSO, and dedicated support"
    return "Engaged free-tier user — lead with ROI case study and onboarding offer"


def main() -> None:
    """Load model, score eligible clinicians, write top-80 call list CSV."""
    print("Loading model ...")
    model = joblib.load(MODEL_PATH)

    print("Querying eligible clinicians from DuckDB ...")
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute("""
        SELECT *
        FROM   marts.mart_conversion_features
        WHERE  converted_to_enterprise = false
          AND  days_since_last_login   <= 60
          AND  days_on_platform        >= 14
    """).fetchdf()
    con.close()
    print(f"  Eligible pool : {len(df):,} clinicians")

    features = df[FEATURE_COLS].copy()
    for col in BOOL_COLS:
        features[col] = features[col].astype(int)
    features = features.fillna(0)

    df["ml_conversion_probability"] = model.predict_proba(features)[:, 1]

    top80 = (
        df.sort_values("ml_conversion_probability", ascending=False)
        .head(80)
        .reset_index(drop=True)
    )
    top80["call_rank"]      = top80.index + 1
    top80["sales_angle"]    = top80.apply(get_sales_angle, axis=1)
    top80["call_list_date"] = date.today().isoformat()

    output_cols = [
        "call_rank", "clinician_id", "specialty", "state", "ehr_system",
        "practice_size", "org_type", "annual_patient_volume", "revenue_band",
        "logins_per_week", "days_since_last_login", "team_members_invited",
        "api_calls_per_week", "features_used_count", "engagement_tier",
        "ml_conversion_probability", "baseline_propensity_score",
        "is_power_user", "sales_angle", "call_list_date",
    ]
    output = top80[output_cols]

    os.makedirs("outputs", exist_ok=True)
    out_path = f"outputs/weekly_call_list_{date.today().isoformat()}.csv"
    output.to_csv(out_path, index=False)

    print("\n=== Top 10 This Week ===")
    print(output.head(10)[
        ["call_rank", "clinician_id", "specialty", "practice_size",
         "ml_conversion_probability", "sales_angle"]
    ].to_string(index=False))
    print(f"\nFull call list -> {out_path}")


if __name__ == "__main__":
    main()
