{% macro compute_engagement_tier(logins_col, invites_col, api_col) %}
    case
        when {{ api_col }} > 0
             and {{ invites_col }} >= 3
             and {{ logins_col }}  >= 5  then 'Champion'
        when {{ logins_col }} >= 5
             and ({{ invites_col }} >= 2 or {{ api_col }} > 0)
                                         then 'Power User'
        when {{ logins_col }} >= 3       then 'Active'
        when {{ logins_col }} >= 1       then 'Casual'
        else                                  'Dormant'
    end
{% endmacro %}
