-- Compute Recency-Frequency-Expansion (RFE) scores and engagement tier from
-- raw usage metrics. All scores are normalized to 0-100 for interpretability.

with usage as (

    select * from {{ ref('stg_usage_metrics') }}

),

scored as (

    select
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

        -- Recency score (0-100): recent login → high score
        case
            when days_since_last_login <= 2  then 100
            when days_since_last_login <= 7  then  85
            when days_since_last_login <= 14 then  65
            when days_since_last_login <= 30 then  40
            when days_since_last_login <= 60 then  20
            else 0
        end as recency_score,

        -- Frequency score (0-100): capped at 10 logins/week
        least(100, logins_per_week * 10) as frequency_score,

        -- Expansion score (0-100): team growth + API adoption + feature breadth
        least(100,
            team_members_invited * 12
            + case when api_calls_per_week > 0 then 28 else 0 end
            + (features_used_count - 1) * 5
        ) as expansion_score,

        -- Engagement tier used for sales routing and talk-track selection
        {{ compute_engagement_tier(
            'logins_per_week',
            'team_members_invited',
            'api_calls_per_week'
        ) }} as engagement_tier

    from usage

)

select * from scored
