-- Fails if any baseline_propensity_score falls outside [0, 128].
-- Upper bound > 100 is possible because power_user bonus can push it slightly above.

select clinician_id, baseline_propensity_score
from {{ ref('mart_conversion_features') }}
where baseline_propensity_score < 0
   or baseline_propensity_score > 128
