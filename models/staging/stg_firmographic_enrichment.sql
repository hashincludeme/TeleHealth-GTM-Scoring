-- Cleans external firmographic enrichment data.
-- In production this would come from a Clearbit / ZoomInfo source table.

with source as (

    select * from {{ ref('firmographic_enrichment') }}

),

renamed as (

    select
        clinician_id,
        annual_patient_volume::integer      as annual_patient_volume,
        trim(revenue_band)                   as revenue_band,
        num_locations::integer               as num_locations,
        has_billing_system::boolean          as has_billing_system,
        accepts_insurance::boolean           as accepts_insurance,
        is_group_practice::boolean           as is_group_practice

    from source

)

select * from renamed
