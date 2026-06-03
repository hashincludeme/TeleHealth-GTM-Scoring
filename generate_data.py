"""
Synthetic data generator for telehealth GTM conversion scoring.
Produces 40,000 clinician records with realistic behavioral and firmographic signals.

Run: python generate_data.py
Outputs: seeds/clinicians.csv, seeds/usage_metrics.csv, seeds/firmographic_enrichment.csv
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random
import os

np.random.seed(42)
random.seed(42)

N = 40_000
REF_DATE = datetime(2026, 6, 3)

# ── Categorical dimensions ────────────────────────────────────────────────────

SPECIALTIES = [
    "Primary Care", "Psychiatry", "Cardiology", "Dermatology",
    "Pediatrics", "Oncology", "Neurology", "Orthopedics",
    "Endocrinology", "Internal Medicine", "Gynecology", "Urology",
]
SPECIALTY_WEIGHTS = [0.20, 0.12, 0.10, 0.06, 0.10, 0.05, 0.07, 0.06, 0.07, 0.08, 0.05, 0.04]

# Enterprise conversion base rate by specialty (oncology & psych have highest need)
SPECIALTY_CONV = {
    "Primary Care": 0.055, "Psychiatry": 0.100, "Cardiology": 0.090,
    "Dermatology": 0.035, "Pediatrics": 0.065, "Oncology": 0.110,
    "Neurology": 0.075, "Orthopedics": 0.035, "Endocrinology": 0.085,
    "Internal Medicine": 0.065, "Gynecology": 0.045, "Urology": 0.045,
}

STATES = [
    "CA", "TX", "NY", "FL", "IL", "PA", "OH", "GA", "NC", "MI",
    "NJ", "VA", "WA", "AZ", "MA", "TN", "IN", "MO", "MD", "WI",
    "CO", "MN", "SC", "AL", "LA", "KY", "OR", "OK", "CT", "UT",
]

EHR_SYSTEMS = ["Epic", "Cerner", "Athenahealth", "eClinicalWorks",
               "Allscripts", "Practice Fusion", "DrChrono", "Other", "None"]
EHR_WEIGHTS  = [0.25, 0.15, 0.12, 0.10, 0.08, 0.07, 0.05, 0.10, 0.08]
EHR_CONV_BOOST = {
    "Epic": 0.025, "Cerner": 0.018, "Athenahealth": 0.012,
    "eClinicalWorks": 0.006, "Allscripts": 0.005, "Practice Fusion": 0.000,
    "DrChrono": 0.006, "Other": 0.000, "None": -0.015,
}

PRACTICE_SIZES   = ["Solo", "Small (2-10)", "Medium (11-50)", "Large (51-200)", "Enterprise (200+)"]
SIZE_WEIGHTS     = [0.28, 0.34, 0.22, 0.11, 0.05]
SIZE_CONV_MULT   = {"Solo": 0.45, "Small (2-10)": 0.75, "Medium (11-50)": 1.20,
                    "Large (51-200)": 1.90, "Enterprise (200+)": 2.60}
SIZE_PT_VOL_MEAN = {"Solo": 220, "Small (2-10)": 1_200, "Medium (11-50)": 6_000,
                    "Large (51-200)": 25_000, "Enterprise (200+)": 90_000}

ORG_TYPES = [
    "Private Practice", "Hospital System", "FQHC",
    "Urgent Care Chain", "Telehealth-Native", "Academic Medical Center",
    "Multi-Specialty Group",
]

REVENUE_BANDS   = ["<$1M", "$1M-$5M", "$5M-$20M", "$20M-$100M", "$100M+"]
REVENUE_WEIGHTS = [0.28, 0.30, 0.24, 0.13, 0.05]

N_FEATURES = 12   # breadth of product features available

# ── Categorical draws ─────────────────────────────────────────────────────────

specialties   = random.choices(SPECIALTIES, weights=SPECIALTY_WEIGHTS, k=N)
states        = random.choices(STATES, k=N)
ehr_systems   = random.choices(EHR_SYSTEMS, weights=EHR_WEIGHTS, k=N)
practice_sizes = random.choices(PRACTICE_SIZES, weights=SIZE_WEIGHTS, k=N)
org_types     = random.choices(ORG_TYPES, k=N)
revenue_bands = random.choices(REVENUE_BANDS, weights=REVENUE_WEIGHTS, k=N)

# ── Signup dates: spread over past 2.5 years ──────────────────────────────────

signup_dates = [REF_DATE - timedelta(days=random.randint(30, 900)) for _ in range(N)]
days_on_platform = np.array([(REF_DATE - sd).days for sd in signup_dates])

# ── Engagement factor tied to practice size ───────────────────────────────────

eng_factor = np.array([
    {"Solo": 0.55, "Small (2-10)": 0.80, "Medium (11-50)": 1.05,
     "Large (51-200)": 1.40, "Enterprise (200+)": 1.75}[ps]
    for ps in practice_sizes
])

# ── Usage metrics ─────────────────────────────────────────────────────────────

logins_per_week = np.round(
    np.random.lognormal(np.log(3.5), 0.85, N) * eng_factor
).astype(int)
logins_per_week = np.clip(logins_per_week, 0, 120)

# Recency: 30 % of users are "at risk" (haven't logged in recently)
is_at_risk_user = np.random.random(N) < 0.30
days_since_last_login = np.where(
    is_at_risk_user,
    np.random.randint(15, 185, N),
    np.random.randint(0, 15, N),
)

# Team invites — key viral/expansion signal for group practices
is_group = np.array([ps != "Solo" for ps in practice_sizes])
team_members_invited = np.round(
    np.where(
        is_group,
        np.random.negative_binomial(1.5, 0.4, N) * eng_factor,
        np.random.negative_binomial(1, 0.7, N),
    )
).astype(int)
team_members_invited = np.clip(team_members_invited, 0, 120)

# API calls — strong power-user signal
api_penetration = 0.04 + 0.18 * (eng_factor - 0.55) / 1.20
has_api = np.random.random(N) < api_penetration
api_calls_per_week = np.where(has_api, np.random.poisson(180, N), 0)

# Feature breadth (1–12)
features_used_count = np.round(
    np.random.beta(2.2, 3.5, N) * N_FEATURES * eng_factor / 1.75
).astype(int)
features_used_count = np.clip(features_used_count, 1, N_FEATURES)

# Support tickets (slightly negative signal — friction, not commitment)
support_tickets_l90d = np.random.poisson(0.4, N)

# Video consults and async messages
video_consults_per_week = np.round(
    np.random.lognormal(1.2, 1.1, N) * eng_factor
).astype(int)
video_consults_per_week = np.clip(video_consults_per_week, 0, 600)

async_messages_per_week = np.round(
    np.random.lognormal(2.3, 1.0, N) * eng_factor
).astype(int)

# Patient volume by practice size
patient_volumes = np.array([
    int(np.clip(np.random.lognormal(np.log(SIZE_PT_VOL_MEAN[ps]), 0.55), 50, 500_000))
    for ps in practice_sizes
])

# ── Conversion label (ground truth) ──────────────────────────────────────────
# Logistic model targeting ~7% overall conversion with realistic lift curves.
# Base intercept = log(0.07/0.93) ≈ -2.59 for an average-signal clinician.

specialty_score = np.array([
    {"Primary Care": 0.0, "Psychiatry": 0.6, "Cardiology": 0.5,
     "Dermatology": -0.4, "Pediatrics": 0.1, "Oncology": 0.7,
     "Neurology": 0.3, "Orthopedics": -0.4, "Endocrinology": 0.4,
     "Internal Medicine": 0.1, "Gynecology": -0.1, "Urology": -0.1}[s]
    for s in specialties
])
size_score = np.array([
    {"Solo": -0.8, "Small (2-10)": -0.2, "Medium (11-50)": 0.4,
     "Large (51-200)": 1.0, "Enterprise (200+)": 1.8}[ps]
    for ps in practice_sizes
])
ehr_score = np.array([
    {"Epic": 0.5, "Cerner": 0.4, "Athenahealth": 0.2, "eClinicalWorks": 0.0,
     "Allscripts": -0.1, "Practice Fusion": -0.2, "DrChrono": -0.1,
     "Other": -0.2, "None": -0.6}[e]
    for e in ehr_systems
])

# Linear combination anchored at -2.59 base
logit = (
    -3.60                                        # base rate ~7% after signal contributions
    + specialty_score
    + size_score
    + ehr_score
    + 0.12 * np.log1p(logins_per_week)
    + 0.22 * np.log1p(team_members_invited)
    + 0.04 * np.log1p(api_calls_per_week)
    + 0.08 * features_used_count
    - 0.012 * days_since_last_login
    - 0.30 * support_tickets_l90d
    + 0.008 * np.log1p(video_consults_per_week) * 4
    + 0.002 * np.log1p(days_on_platform)
    + np.random.normal(0, 0.90, N)               # noise keeps AUC realistic
)

prob = 1 / (1 + np.exp(-logit))
prob = np.clip(prob, 0.003, 0.96)
converted = (np.random.random(N) < prob).astype(int)

conversion_dates = [
    (sd + timedelta(days=random.randint(21, 400))).strftime("%Y-%m-%d") if c else None
    for sd, c in zip(signup_dates, converted)
]

print(f"Clinicians generated : {N:,}")
print(f"Conversion rate      : {converted.mean():.2%}  ({converted.sum():,} converted)")

# ── Build DataFrames ──────────────────────────────────────────────────────────

clinicians_df = pd.DataFrame({
    "clinician_id":            [f"CLN_{i:05d}" for i in range(1, N + 1)],
    "signup_date":             [d.strftime("%Y-%m-%d") for d in signup_dates],
    "specialty":               specialties,
    "state":                   states,
    "ehr_system":              ehr_systems,
    "practice_size":           practice_sizes,
    "org_type":                org_types,
    "annual_patient_volume":   patient_volumes,
    "converted_to_enterprise": converted,
    "conversion_date":         conversion_dates,
})

usage_metrics_df = pd.DataFrame({
    "clinician_id":               clinicians_df["clinician_id"],
    "snapshot_date":              REF_DATE.strftime("%Y-%m-%d"),
    "logins_per_week":            logins_per_week,
    "days_since_last_login":      days_since_last_login,
    "team_members_invited":       team_members_invited,
    "api_calls_per_week":         api_calls_per_week,
    "features_used_count":        features_used_count,
    "support_tickets_l90d":       support_tickets_l90d,
    "video_consults_per_week":    video_consults_per_week,
    "async_messages_per_week":    async_messages_per_week,
    "days_on_platform":           days_on_platform,
})

num_locs = np.where(
    np.array(practice_sizes) == "Solo", 1,
    np.clip(np.random.negative_binomial(1, 0.3, N), 1, 60),
)

firmographic_df = pd.DataFrame({
    "clinician_id":       clinicians_df["clinician_id"],
    "annual_patient_volume": patient_volumes,
    "revenue_band":       revenue_bands,
    "num_locations":      num_locs,
    "has_billing_system": (np.random.random(N) > 0.28).astype(int),
    "accepts_insurance":  (np.random.random(N) > 0.18).astype(int),
    "is_group_practice":  is_group.astype(int),
})

# ── Save seeds ────────────────────────────────────────────────────────────────

os.makedirs("seeds", exist_ok=True)
clinicians_df.to_csv("seeds/clinicians.csv", index=False)
usage_metrics_df.to_csv("seeds/usage_metrics.csv", index=False)
firmographic_df.to_csv("seeds/firmographic_enrichment.csv", index=False)

print(f"\nSaved seeds/")
print(f"  clinicians.csv              : {len(clinicians_df):,} rows")
print(f"  usage_metrics.csv           : {len(usage_metrics_df):,} rows")
print(f"  firmographic_enrichment.csv : {len(firmographic_df):,} rows")
