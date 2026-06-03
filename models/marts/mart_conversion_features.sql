-- Final feature mart used for both ML model training and the rule-based
-- baseline score. Ordered by baseline score descending so the first rows
-- are the best prospects without running the ML layer.
--
-- baseline_propensity_score is a weighted SQL score used:
--   1. As a fallback if the ML model artifact is unavailable
--   2. As a feature in the ML model itself (meta-feature)
--   3. For stakeholder-explainable scoring without a black-box model

with features as (

    select * from {{ ref('int_clinician_features') }}

),

final as (

    select
        -- Identity & firmographic
        clinician_id,
        signup_date,
        specialty,
        state,
        ehr_system,
        practice_size,
        org_type,
        annual_patient_volume,
        num_locations,
        revenue_band,
        converted_to_enterprise,

        -- Raw usage features (ML model inputs)
        logins_per_week,
        days_since_last_login,
        team_members_invited,
        api_calls_per_week,
        features_used_count,
        support_tickets_l90d,
        video_consults_per_week,
        async_messages_per_week,
        days_on_platform,

        -- dbt-computed scores (also ML model inputs)
        recency_score,
        frequency_score,
        expansion_score,
        behavioral_score,
        firmographic_score,
        practice_size_score,
        ehr_maturity_score,
        specialty_need_score,

        -- Boolean flags
        is_power_user,
        is_at_risk,
        has_billing_system,
        accepts_insurance,
        is_group_practice,

        -- Engagement tier label
        engagement_tier,

        -- Rule-based baseline propensity (0-100, explainable to leadership)
        round(
            behavioral_score  * 0.45
            + firmographic_score * 0.42
            + case when is_power_user then 13.0 else 0.0 end
            - case when is_at_risk    then  8.0 else 0.0 end
        , 2) as baseline_propensity_score,

        current_timestamp as scored_at

    from features

)

select * from final
order by baseline_propensity_score desc
