-- Master feature table: joins engagement and firmographic scores into a single
-- wide record per clinician. This is the input to the ML model training step.

with firmographic as (

    select * from {{ ref('int_clinician_firmographic_score') }}

),

engagement as (

    select * from {{ ref('int_clinician_engagement') }}

),

combined as (

    select
        -- Identity
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

        -- Raw usage signals
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

        -- Scored sub-components
        e.recency_score,
        e.frequency_score,
        e.expansion_score,
        f.practice_size_score,
        f.ehr_maturity_score,
        f.specialty_need_score,
        f.firmographic_score,

        -- Composite behavioral score (weights tuned on historical conversions)
        round(
            e.expansion_score * 0.42
            + e.frequency_score * 0.30
            + e.recency_score   * 0.28
        , 2) as behavioral_score,

        -- Derived flags for sales routing
        case
            when e.team_members_invited >= 3 and e.api_calls_per_week > 0 then true
            else false
        end as is_power_user,

        case
            when e.days_since_last_login > 30 then true
            else false
        end as is_at_risk

    from firmographic f
    left join engagement e using (clinician_id)

)

select * from combined
