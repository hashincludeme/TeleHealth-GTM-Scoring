-- Fails (returns rows) if any clinician appears more than once in the feature mart.
-- dbt test framework: a passing test returns zero rows.

select
    clinician_id,
    count(*) as row_count
from {{ ref('mart_conversion_features') }}
group by clinician_id
having count(*) > 1
