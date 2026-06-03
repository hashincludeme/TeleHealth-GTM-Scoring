-- Top-80 SQL-only call list using the baseline propensity score.
-- In production, replace baseline_propensity_score with ml_conversion_probability
-- written back by score_and_rank.py, or join a scores table produced by the ML step.
--
-- Eligibility filters:
--   • Not already converted
--   • Active within last 60 days (not fully churned)
--   • On platform ≥ 14 days (enough product exposure to pitch)

with scored as (

    select * from {{ ref('mart_conversion_features') }}

),

eligible as (

    select *
    from scored
    where
        converted_to_enterprise = false
        and days_since_last_login <= 60
        and days_on_platform      >= 14

),

ranked as (

    select
        row_number() over (
            order by baseline_propensity_score desc
        )                                   as call_rank,

        clinician_id,
        specialty,
        state,
        ehr_system,
        practice_size,
        org_type,
        annual_patient_volume,
        revenue_band,
        logins_per_week,
        days_since_last_login,
        team_members_invited,
        api_calls_per_week,
        features_used_count,
        is_power_user,
        engagement_tier,
        baseline_propensity_score,

        -- Human-readable sales angle for AE context card
        case
            when api_calls_per_week > 0
                then 'API power user — lead with integrations, SLA, and developer support'
            when team_members_invited >= 5
                then 'Growing team — lead with multi-seat pricing, RBAC, and collaboration'
            when features_used_count >= 8
                then 'Feature explorer — lead with advanced workflows and automation'
            when logins_per_week >= 7
                then 'Daily-active champion — lead with productivity ROI'
            when practice_size in ('Large (51-200)', 'Enterprise (200+)')
                then 'Enterprise account — lead with compliance, SSO, dedicated support'
            else
                'Engaged free user — lead with ROI case study and onboarding offer'
        end as sales_angle,

        current_date as call_list_date

    from eligible

)

select *
from ranked
where call_rank <= 80
order by call_rank
