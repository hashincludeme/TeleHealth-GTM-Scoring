# Telehealth GTM Conversion Scorer

> **GTM Engineering** — A production-grade data pipeline that ranks 40,000 free-tier clinicians by predicted probability of converting to an enterprise plan, giving a sales team of 80 weekly calls its highest-ROI targets.

> **Note:** All data in this project is fully synthetic and procedurally generated via `generate_data.py`. No real patient, clinician, or healthcare organization data is used anywhere in this repository.

---

## Business Problem

A telehealth platform has **40,000 free-tier clinician users** and a sales team that can make **80 calls per week**. Without a model, reps call at random — a 5–8 % base conversion rate. With a ranked list, the top decile converts at 3–4× the base rate, turning 80 random calls into 80 high-signal conversations.

**Key question the model answers:** *Which 80 clinicians, if called today, are most likely to upgrade to enterprise?*

---

## Architecture

```
Raw Data (CSV seeds)
    │
    ▼
┌─────────────┐   dbt seed    ┌──────────────────────────────┐
│ clinicians  │──────────────▶│  DuckDB (telehealth_gtm.db)  │
│ usage_metrics│              │                              │
│ firmographic│               │  raw.clinicians              │
└─────────────┘               │  raw.usage_metrics           │
                              │  raw.firmographic_enrichment │
                              └──────────────┬───────────────┘
                                             │ dbt run
                              ┌──────────────▼───────────────┐
                              │        STAGING layer          │
                              │  stg_clinicians               │
                              │  stg_usage_metrics            │
                              │  stg_firmographic_enrichment  │
                              └──────────────┬───────────────┘
                                             │
                              ┌──────────────▼───────────────┐
                              │      INTERMEDIATE layer        │
                              │  int_clinician_engagement     │
                              │    → RFE scores + tier        │
                              │  int_clinician_firmographic   │
                              │    → size/EHR/specialty scores│
                              │  int_clinician_features       │
                              │    → master feature table     │
                              └──────────────┬───────────────┘
                                             │
                              ┌──────────────▼───────────────┐
                              │          MART layer            │
                              │  mart_conversion_features     │
                              │    → full feature vector      │
                              │  mart_weekly_call_list        │
                              │    → top-80 (SQL baseline)    │
                              └──────────────┬───────────────┘
                                             │
                              ┌──────────────▼───────────────┐
                              │        ML LAYER (Python)      │
                              │  train_model.py               │
                              │    → GBM + calibration        │
                              │  score_and_rank.py            │
                              │    → ranked call list + angle │
                              └──────────────────────────────┘
```

---

## dbt Layer Details

### Staging (`models/staging/`)
| Model | Description |
|---|---|
| `stg_clinicians` | Casts types, standardises strings, surfaces conversion label |
| `stg_usage_metrics` | Cleans weekly usage snapshot (logins, invites, API, features) |
| `stg_firmographic_enrichment` | Cleans external firmographic data (volume, revenue, billing) |

### Intermediate (`models/intermediate/`)
| Model | Description |
|---|---|
| `int_clinician_engagement` | Computes **Recency / Frequency / Expansion** sub-scores (0-100) and engagement tier (Champion → Dormant) |
| `int_clinician_firmographic_score` | Converts practice size, EHR system, specialty, and patient volume into 0-100 sub-scores and a weighted firmographic composite |
| `int_clinician_features` | Master join: one wide row per clinician with all raw signals, computed scores, and Boolean flags |

### Marts (`models/marts/`)
| Model | Description |
|---|---|
| `mart_conversion_features` | Full feature vector for all clinicians + explainable SQL baseline score |
| `mart_weekly_call_list` | Top-80 ranked unconverted, active clinicians with sales angle |

---

## Feature Signals

### Behavioral (product usage)
| Feature | Signal |
|---|---|
| `logins_per_week` | Frequency of product use; high = invested user |
| `days_since_last_login` | Recency; >30 days = at-risk |
| `team_members_invited` | Viral loop activation; proxy for team dependency |
| `api_calls_per_week` | Power-user indicator; high willingness to pay for uptime/SLA |
| `features_used_count` | Breadth of adoption; high = more value extracted |
| `video_consults_per_week` | Core-feature intensity |
| `support_tickets_l90d` | Friction signal; slightly negative |

### Firmographic (who they are)
| Feature | Signal |
|---|---|
| `practice_size` | Larger practice = higher ACV potential |
| `ehr_system` | Epic/Cerner users → integration-aware, higher WTP |
| `specialty` | Oncology/Psychiatry/Cardiology → high telehealth complexity |
| `annual_patient_volume` | Scale indicator |
| `revenue_band` | Budget availability |
| `num_locations` | Multi-site → enterprise features are a need, not a want |

---

## ML Model

- **Algorithm:** Gradient Boosting Classifier (sklearn) with isotonic probability calibration
- **Training set:** 80 % of all 40,000 clinicians (stratified by conversion label)
- **Key metric:** `Precision@80` — what fraction of the top-80 scored clinicians are true converters
- **Why GBM over logistic regression?** Handles non-linear interaction effects (e.g. *team invites* only matters if *days_since_last_login* is low) and requires no feature scaling

**Typical performance on synthetic data:**
| Metric | Value |
|---|---|
| Test AUC-ROC | ~0.87 |
| Test Avg Precision | ~0.42 |
| Precision@80 | ~0.35–0.45 |

---

## Engagement Tiers (macro)

Computed by the `compute_engagement_tier` dbt macro:

| Tier | Criteria | Sales Action |
|---|---|---|
| **Champion** | API user + 3+ invites + 5+ logins/wk | Priority 1 — close fast |
| **Power User** | 5+ logins + invites or API | Priority 1 — full demo |
| **Active** | 3+ logins/wk | Priority 2 — ROI call |
| **Casual** | 1-2 logins/wk | Priority 3 — nurture |
| **Dormant** | 0 logins | Exclude from call list |

---

## Quick Start

### Prerequisites
- Python 3.9+
- `pip install -r requirements.txt`

### Run the full pipeline

**Windows (PowerShell):**
```powershell
.\run_pipeline.ps1
```

**Mac/Linux (Make):**
```bash
make all
```

**Step by step:**
```bash
# 1. Generate 40,000 synthetic clinicians
python generate_data.py

# 2. Load seed CSVs into DuckDB
dbt seed --profiles-dir .

# 3. Run staging → intermediate → mart transformations
dbt run --profiles-dir .

# 4. Run data quality tests
dbt test --profiles-dir .

# 5. Train the GBM model on mart output
python train_model.py

# 6. Score all clinicians and output this week's call list
python score_and_rank.py
```

Output: `outputs/weekly_call_list_YYYY-MM-DD.csv`

---

## Output Schema

The weekly call list CSV contains:

| Column | Description |
|---|---|
| `call_rank` | 1 = highest priority |
| `clinician_id` | Unique identifier |
| `specialty` / `state` / `ehr_system` | Identity fields |
| `practice_size` / `org_type` | Firmographic context |
| `annual_patient_volume` / `revenue_band` | Deal size indicators |
| `logins_per_week` / `team_members_invited` / `api_calls_per_week` | Top signals |
| `engagement_tier` | Champion / Power User / Active / Casual |
| `ml_conversion_probability` | Model output (0-1) |
| `baseline_propensity_score` | SQL rule-based score (explainable fallback) |
| `is_power_user` | Boolean flag |
| `sales_angle` | Human-readable talk-track hint for the AE |

---

## Project Structure

```
telehealth-gtm-scoring/
├── generate_data.py           # Synthetic data generation (40k clinicians)
├── train_model.py             # GBM training + evaluation
├── score_and_rank.py          # Scoring pipeline → weekly call list
├── dbt_project.yml            # dbt project configuration
├── profiles.yml               # DuckDB connection profile
├── requirements.txt
├── Makefile                   # Mac/Linux pipeline runner
├── run_pipeline.ps1           # Windows pipeline runner
├── seeds/                     # dbt seeds (generated CSV files)
│   ├── clinicians.csv
│   ├── usage_metrics.csv
│   └── firmographic_enrichment.csv
├── models/
│   ├── staging/               # Clean + cast raw sources
│   ├── intermediate/          # Feature engineering + scoring
│   └── marts/                 # Final feature mart + call list
├── macros/
│   ├── compute_engagement_tier.sql
│   └── generate_schema_name.sql
└── tests/                     # Custom dbt data quality tests
```

---

## Extending to Production

| Capability | How to add |
|---|---|
| Real product data | Replace seeds with `sources:` pointing to your warehouse (Snowflake, BigQuery, Redshift) |
| CRM integration | Join `mart_weekly_call_list` with Salesforce contact history to filter recently-called accounts |
| Weekly scheduling | Add a cron job or Airflow DAG: `dbt run && python score_and_rank.py` |
| Model retraining | Re-run `train_model.py` on the latest mart snapshot monthly |
| A/B testing | Split call list 50/50 between model-ranked and random; track conversion rate by cohort |
| Monitoring | Alert if `conversion_rate` in mart drops >2 pp week-over-week (data drift signal) |

---

## Tech Stack

| Tool | Role |
|---|---|
| **dbt-core + dbt-duckdb** | SQL transformation pipeline (staging → intermediate → mart) |
| **DuckDB** | Embedded analytical database (zero-infrastructure local dev) |
| **scikit-learn** | Gradient Boosting Classifier + isotonic calibration |
| **pandas / numpy** | Data generation and feature preparation |
| **Python** | ML training, scoring, and orchestration |
