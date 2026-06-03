-- Standardises the raw clinicians seed: casts types, strips whitespace, and
-- surfaces the ground-truth conversion label for model training.

with source as (

    select * from {{ ref('clinicians') }}

),

renamed as (

    select
        clinician_id,
        try_cast(signup_date as date)       as signup_date,
        trim(specialty)                      as specialty,
        upper(trim(state))                   as state,
        trim(ehr_system)                     as ehr_system,
        trim(practice_size)                  as practice_size,
        trim(org_type)                       as org_type,
        annual_patient_volume::integer       as annual_patient_volume,
        converted_to_enterprise::boolean     as converted_to_enterprise,
        try_cast(conversion_date as date)    as conversion_date

    from source

)

select * from renamed
