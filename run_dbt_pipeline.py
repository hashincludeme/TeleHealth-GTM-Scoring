"""
dbt-equivalent pipeline runner using DuckDB Python API directly.
Executes the same SQL as the dbt models in the correct dependency order:
  seeds → staging views → intermediate tables → mart tables

Use this if dbt CLI is not available (e.g., Python 3.9/3.14 compatibility issues).
On a modern Python 3.10–3.12 environment, use: dbt seed && dbt run instead.
"""

import duckdb
import os
import re
import csv

DB_PATH = "telehealth_gtm.duckdb"

con = duckdb.connect(DB_PATH)


# ── Schema setup ─────────────────────────────────────────────────────────────

def setup_schemas() -> None:
    for schema in ("raw", "staging", "intermediate", "marts"):
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    print("Schemas ready: raw, staging, intermediate, marts")


# ── Seed loader ──────────────────────────────────────────────────────────────

def load_seeds() -> None:
    seeds = {
        "raw.clinicians":               "seeds/clinicians.csv",
        "raw.usage_metrics":            "seeds/usage_metrics.csv",
        "raw.firmographic_enrichment":  "seeds/firmographic_enrichment.csv",
    }
    for table, csv_path in seeds.items():
        con.execute(f"DROP TABLE IF EXISTS {table}")
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM read_csv_auto('{csv_path}')")
        count = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        print(f"  Loaded {table:<40} {count:>7,} rows")


# ── Macro: compute_engagement_tier ───────────────────────────────────────────

def engagement_tier_expr(logins: str, invites: str, api: str) -> str:
    return f"""
        CASE
            WHEN {api} > 0 AND {invites} >= 3 AND {logins} >= 5 THEN 'Champion'
            WHEN {logins} >= 5 AND ({invites} >= 2 OR {api} > 0)  THEN 'Power User'
            WHEN {logins} >= 3                                      THEN 'Active'
            WHEN {logins} >= 1                                      THEN 'Casual'
            ELSE 'Dormant'
        END
    """


# ── Staging views ─────────────────────────────────────────────────────────────

def run_staging() -> None:
    con.execute("DROP VIEW IF EXISTS staging.stg_clinicians")
    con.execute("""
        CREATE VIEW staging.stg_clinicians AS
        SELECT
            clinician_id,
            TRY_CAST(signup_date AS DATE)           AS signup_date,
            TRIM(specialty)                          AS specialty,
            UPPER(TRIM(state))                       AS state,
            TRIM(ehr_system)                         AS ehr_system,
            TRIM(practice_size)                      AS practice_size,
            TRIM(org_type)                           AS org_type,
            annual_patient_volume::INTEGER           AS annual_patient_volume,
            CAST(converted_to_enterprise AS BOOLEAN) AS converted_to_enterprise,
            TRY_CAST(conversion_date AS DATE)        AS conversion_date
        FROM raw.clinicians
    """)

    con.execute("DROP VIEW IF EXISTS staging.stg_usage_metrics")
    con.execute("""
        CREATE VIEW staging.stg_usage_metrics AS
        SELECT
            clinician_id,
            TRY_CAST(snapshot_date AS DATE)  AS snapshot_date,
            logins_per_week::INTEGER          AS logins_per_week,
            days_since_last_login::INTEGER    AS days_since_last_login,
            team_members_invited::INTEGER     AS team_members_invited,
            api_calls_per_week::INTEGER       AS api_calls_per_week,
            features_used_count::INTEGER      AS features_used_count,
            support_tickets_l90d::INTEGER     AS support_tickets_l90d,
            video_consults_per_week::INTEGER  AS video_consults_per_week,
            async_messages_per_week::INTEGER  AS async_messages_per_week,
            days_on_platform::INTEGER         AS days_on_platform
        FROM raw.usage_metrics
    """)

    con.execute("DROP VIEW IF EXISTS staging.stg_firmographic_enrichment")
    con.execute("""
        CREATE VIEW staging.stg_firmographic_enrichment AS
        SELECT
            clinician_id,
            annual_patient_volume::INTEGER    AS annual_patient_volume,
            TRIM(revenue_band)                AS revenue_band,
            num_locations::INTEGER            AS num_locations,
            CAST(has_billing_system AS BOOLEAN) AS has_billing_system,
            CAST(accepts_insurance  AS BOOLEAN) AS accepts_insurance,
            CAST(is_group_practice  AS BOOLEAN) AS is_group_practice
        FROM raw.firmographic_enrichment
    """)
    print("  Staging views created (3)")


# ── Intermediate tables ───────────────────────────────────────────────────────

def run_intermediate() -> None:
    tier_expr = engagement_tier_expr(
        "logins_per_week", "team_members_invited", "api_calls_per_week"
    )

    con.execute("DROP TABLE IF EXISTS intermediate.int_clinician_engagement")
    con.execute(f"""
        CREATE TABLE intermediate.int_clinician_engagement AS
        SELECT
            clinician_id,
            snapshot_date,
            logins_per_week,
            days_since_last_login,
            team_members_invited,
            api_calls_per_week,
            features_used_count,
            support_tickets_l90d,
            video_consults_per_week,
            async_messages_per_week,
            days_on_platform,

            CASE
                WHEN days_since_last_login <= 2  THEN 100
                WHEN days_since_last_login <= 7  THEN  85
                WHEN days_since_last_login <= 14 THEN  65
                WHEN days_since_last_login <= 30 THEN  40
                WHEN days_since_last_login <= 60 THEN  20
                ELSE 0
            END AS recency_score,

            LEAST(100, logins_per_week * 10) AS frequency_score,

            LEAST(100,
                team_members_invited * 12
                + CASE WHEN api_calls_per_week > 0 THEN 28 ELSE 0 END
                + (features_used_count - 1) * 5
            ) AS expansion_score,

            {tier_expr} AS engagement_tier

        FROM staging.stg_usage_metrics
    """)

    con.execute("DROP TABLE IF EXISTS intermediate.int_clinician_firmographic_score")
    con.execute("""
        CREATE TABLE intermediate.int_clinician_firmographic_score AS
        WITH joined AS (
            SELECT
                c.clinician_id,
                c.specialty,
                c.state,
                c.ehr_system,
                c.practice_size,
                c.org_type,
                c.signup_date,
                c.converted_to_enterprise,
                c.conversion_date,
                f.annual_patient_volume,
                f.revenue_band,
                f.num_locations,
                f.has_billing_system,
                f.accepts_insurance,
                f.is_group_practice,

                CASE c.practice_size
                    WHEN 'Solo'              THEN  10
                    WHEN 'Small (2-10)'      THEN  30
                    WHEN 'Medium (11-50)'    THEN  55
                    WHEN 'Large (51-200)'    THEN  78
                    WHEN 'Enterprise (200+)' THEN  96
                    ELSE 20
                END AS practice_size_score,

                CASE c.ehr_system
                    WHEN 'Epic'            THEN 92
                    WHEN 'Cerner'          THEN 82
                    WHEN 'Athenahealth'    THEN 72
                    WHEN 'eClinicalWorks'  THEN 56
                    WHEN 'Allscripts'      THEN 50
                    WHEN 'Practice Fusion' THEN 40
                    WHEN 'DrChrono'        THEN 44
                    WHEN 'Other'           THEN 32
                    WHEN 'None'            THEN 18
                    ELSE 30
                END AS ehr_maturity_score,

                CASE c.specialty
                    WHEN 'Oncology'          THEN 92
                    WHEN 'Psychiatry'        THEN 88
                    WHEN 'Cardiology'        THEN 82
                    WHEN 'Endocrinology'     THEN 76
                    WHEN 'Neurology'         THEN 72
                    WHEN 'Internal Medicine' THEN 66
                    WHEN 'Pediatrics'        THEN 62
                    WHEN 'Primary Care'      THEN 56
                    WHEN 'Gynecology'        THEN 50
                    WHEN 'Urology'           THEN 50
                    WHEN 'Dermatology'       THEN 38
                    WHEN 'Orthopedics'       THEN 34
                    ELSE 48
                END AS specialty_need_score

            FROM staging.stg_clinicians c
            LEFT JOIN staging.stg_firmographic_enrichment f USING (clinician_id)
        ),
        with_vol AS (
            SELECT *, LEAST(100, LN(GREATEST(annual_patient_volume, 1)) * 8.5) AS patient_volume_score
            FROM joined
        )
        SELECT *,
            ROUND(
                practice_size_score    * 0.32
                + ehr_maturity_score   * 0.22
                + specialty_need_score * 0.26
                + patient_volume_score * 0.20
            , 2) AS firmographic_score
        FROM with_vol
    """)

    con.execute("DROP TABLE IF EXISTS intermediate.int_clinician_features")
    con.execute("""
        CREATE TABLE intermediate.int_clinician_features AS
        SELECT
            f.clinician_id,
            f.signup_date,
            f.specialty,
            f.state,
            f.ehr_system,
            f.practice_size,
            f.org_type,
            f.annual_patient_volume,
            f.num_locations,
            f.revenue_band,
            f.converted_to_enterprise,
            f.has_billing_system,
            f.accepts_insurance,
            f.is_group_practice,

            e.logins_per_week,
            e.days_since_last_login,
            e.team_members_invited,
            e.api_calls_per_week,
            e.features_used_count,
            e.support_tickets_l90d,
            e.video_consults_per_week,
            e.async_messages_per_week,
            e.days_on_platform,
            e.engagement_tier,

            e.recency_score,
            e.frequency_score,
            e.expansion_score,
            f.practice_size_score,
            f.ehr_maturity_score,
            f.specialty_need_score,
            f.firmographic_score,

            ROUND(
                e.expansion_score * 0.42
                + e.frequency_score * 0.30
                + e.recency_score   * 0.28
            , 2) AS behavioral_score,

            CASE WHEN e.team_members_invited >= 3 AND e.api_calls_per_week > 0
                 THEN true ELSE false END AS is_power_user,

            CASE WHEN e.days_since_last_login > 30
                 THEN true ELSE false END AS is_at_risk

        FROM intermediate.int_clinician_firmographic_score f
        LEFT JOIN intermediate.int_clinician_engagement e USING (clinician_id)
    """)
    print("  Intermediate tables created (3)")


# ── Mart tables ───────────────────────────────────────────────────────────────

def run_marts() -> None:
    con.execute("DROP TABLE IF EXISTS marts.mart_conversion_features")
    con.execute("""
        CREATE TABLE marts.mart_conversion_features AS
        SELECT
            clinician_id, signup_date, specialty, state, ehr_system,
            practice_size, org_type, annual_patient_volume, num_locations,
            revenue_band, converted_to_enterprise,
            logins_per_week, days_since_last_login, team_members_invited,
            api_calls_per_week, features_used_count, support_tickets_l90d,
            video_consults_per_week, async_messages_per_week, days_on_platform,
            recency_score, frequency_score, expansion_score, behavioral_score,
            firmographic_score, practice_size_score, ehr_maturity_score,
            specialty_need_score, is_power_user, is_at_risk,
            has_billing_system, accepts_insurance, is_group_practice,
            engagement_tier,
            ROUND(
                behavioral_score   * 0.45
                + firmographic_score * 0.42
                + CASE WHEN is_power_user THEN 13.0 ELSE 0.0 END
                - CASE WHEN is_at_risk    THEN  8.0 ELSE 0.0 END
            , 2) AS baseline_propensity_score,
            NOW() AS scored_at
        FROM intermediate.int_clinician_features
        ORDER BY baseline_propensity_score DESC
    """)

    con.execute("DROP TABLE IF EXISTS marts.mart_weekly_call_list")
    con.execute("""
        CREATE TABLE marts.mart_weekly_call_list AS
        WITH eligible AS (
            SELECT * FROM marts.mart_conversion_features
            WHERE converted_to_enterprise = false
              AND days_since_last_login <= 60
              AND days_on_platform      >= 14
        ),
        ranked AS (
            SELECT
                ROW_NUMBER() OVER (ORDER BY baseline_propensity_score DESC) AS call_rank,
                clinician_id, specialty, state, ehr_system, practice_size, org_type,
                annual_patient_volume, revenue_band, logins_per_week,
                days_since_last_login, team_members_invited, api_calls_per_week,
                features_used_count, is_power_user, engagement_tier,
                baseline_propensity_score,
                CASE
                    WHEN api_calls_per_week > 0
                        THEN 'API power user — lead with integrations, SLA, and developer support'
                    WHEN team_members_invited >= 5
                        THEN 'Growing team — lead with multi-seat pricing, RBAC, and collaboration'
                    WHEN features_used_count >= 8
                        THEN 'Feature explorer — lead with advanced workflows and automation'
                    WHEN logins_per_week >= 7
                        THEN 'Daily-active champion — lead with productivity ROI'
                    WHEN practice_size IN ('Large (51-200)', 'Enterprise (200+)')
                        THEN 'Enterprise account — lead with compliance, SSO, dedicated support'
                    ELSE 'Engaged free user — lead with ROI case study and onboarding offer'
                END AS sales_angle,
                CURRENT_DATE AS call_list_date
            FROM eligible
        )
        SELECT * FROM ranked WHERE call_rank <= 80
    """)
    print("  Mart tables created (2)")


# ── Validation ────────────────────────────────────────────────────────────────

def run_tests() -> None:
    dupes = con.execute("""
        SELECT clinician_id, count(*) AS n
        FROM marts.mart_conversion_features
        GROUP BY clinician_id HAVING count(*) > 1
    """).fetchall()
    assert len(dupes) == 0, f"Duplicate clinicians found: {dupes[:5]}"

    call_list_count = con.execute(
        "SELECT count(*) FROM marts.mart_weekly_call_list"
    ).fetchone()[0]
    assert call_list_count == 80, f"Expected 80 calls, got {call_list_count}"

    bad_scores = con.execute("""
        SELECT count(*) FROM marts.mart_conversion_features
        WHERE baseline_propensity_score < 0 OR baseline_propensity_score > 128
    """).fetchone()[0]
    assert bad_scores == 0, f"{bad_scores} scores out of range"

    print(f"  All tests passed (deduplication, call_list=80, score range)")


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary() -> None:
    stats = con.execute("""
        SELECT
            count(*)                           AS total,
            sum(converted_to_enterprise::int)  AS converted,
            avg(baseline_propensity_score)     AS avg_score,
            avg(CASE WHEN is_power_user THEN 1 ELSE 0 END) AS pct_power_users
        FROM marts.mart_conversion_features
    """).fetchone()
    print(f"\n=== Mart Summary ===")
    print(f"  Total clinicians       : {stats[0]:,}")
    print(f"  Converted (train label): {stats[1]:,}  ({stats[1]/stats[0]:.1%})")
    print(f"  Avg propensity score   : {stats[2]:.1f} / 128")
    print(f"  Power users            : {stats[3]:.1%}")

    top5 = con.execute("""
        SELECT call_rank, clinician_id, specialty, practice_size,
               engagement_tier, ROUND(baseline_propensity_score, 1) AS score, sales_angle
        FROM marts.mart_weekly_call_list
        ORDER BY call_rank
        LIMIT 5
    """).fetchdf()
    print(f"\n=== Top 5 calls this week ===")
    print(top5.to_string(index=False))


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Running dbt-equivalent pipeline via DuckDB Python API\n")
    setup_schemas()
    print("\nLoading seeds …")
    load_seeds()
    print("\nRunning staging layer …")
    run_staging()
    print("\nRunning intermediate layer …")
    run_intermediate()
    print("\nRunning mart layer …")
    run_marts()
    print("\nRunning data quality tests …")
    run_tests()
    print_summary()
    print(f"\nDuckDB written to: {DB_PATH}")
    con.close()
