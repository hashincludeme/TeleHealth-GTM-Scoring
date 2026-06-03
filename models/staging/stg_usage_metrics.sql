-- Cleans and casts the weekly usage snapshot per clinician.
-- One row per clinician; snapshot_date marks when the metrics were captured.

with source as (

    select * from {{ ref('usage_metrics') }}

),

renamed as (

    select
        clinician_id,
        try_cast(snapshot_date as date)     as snapshot_date,
        logins_per_week::integer            as logins_per_week,
        days_since_last_login::integer      as days_since_last_login,
        team_members_invited::integer       as team_members_invited,
        api_calls_per_week::integer         as api_calls_per_week,
        features_used_count::integer        as features_used_count,
        support_tickets_l90d::integer       as support_tickets_l90d,
        video_consults_per_week::integer    as video_consults_per_week,
        async_messages_per_week::integer    as async_messages_per_week,
        days_on_platform::integer           as days_on_platform

    from source

)

select * from renamed
