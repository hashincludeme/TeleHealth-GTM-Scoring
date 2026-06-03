-- Override dbt's default schema-naming convention so that
-- +schema: staging produces schema "staging" (not "<target>_staging").
-- This keeps local DuckDB schema names clean and predictable.

{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
