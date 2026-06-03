-- Translate firmographic attributes into interpretable sub-scores (0-100).
-- Weights reflect enterprise deal probability by practice size, EHR maturity,
-- specialty clinical complexity, and patient volume.

with clinicians as (

    select * from {{ ref('stg_clinicians') }}

),

firmographics as (

    select * from {{ ref('stg_firmographic_enrichment') }}

),

joined as (

    select
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

        -- Practice size score: larger practices → higher ACV potential
        case c.practice_size
            when 'Solo'            then  10
            when 'Small (2-10)'    then  30
            when 'Medium (11-50)'  then  55
            when 'Large (51-200)'  then  78
            when 'Enterprise (200+)' then 96
            else 20
        end as practice_size_score,

        -- EHR maturity: established EHR users understand workflow integration value
        case c.ehr_system
            when 'Epic'            then 92
            when 'Cerner'          then 82
            when 'Athenahealth'    then 72
            when 'eClinicalWorks'  then 56
            when 'Allscripts'      then 50
            when 'Practice Fusion' then 40
            when 'DrChrono'        then 44
            when 'Other'           then 32
            when 'None'            then 18
            else 30
        end as ehr_maturity_score,

        -- Specialty need score: reflects clinical complexity and telehealth ROI
        case c.specialty
            when 'Oncology'          then 92
            when 'Psychiatry'        then 88
            when 'Cardiology'        then 82
            when 'Endocrinology'     then 76
            when 'Neurology'         then 72
            when 'Internal Medicine' then 66
            when 'Pediatrics'        then 62
            when 'Primary Care'      then 56
            when 'Gynecology'        then 50
            when 'Urology'           then 50
            when 'Dermatology'       then 38
            when 'Orthopedics'       then 34
            else 48
        end as specialty_need_score

    from clinicians c
    left join firmographics f using (clinician_id)

),

with_volume_score as (

    select
        *,
        -- Patient volume score: log-scaled to prevent outlier dominance
        least(100, ln(greatest(annual_patient_volume, 1)) * 8.5) as patient_volume_score

    from joined

),

final as (

    select
        *,
        -- Composite firmographic score
        round(
            practice_size_score   * 0.32
            + ehr_maturity_score  * 0.22
            + specialty_need_score * 0.26
            + patient_volume_score * 0.20
        , 2) as firmographic_score

    from with_volume_score

)

select * from final
