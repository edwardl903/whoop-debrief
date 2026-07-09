-- Fact: fct_daily
-- Incremental merge on cycle_id. On each run, re-processes the last 7 days
-- to capture any WHOOP rescores, then merges into the existing table.
-- Grain: one row per cycle_id (day).

{{
    config(
        materialized='incremental',
        unique_key='cycle_id',
        incremental_strategy='merge',
        on_schema_change='sync_all_columns'
    )
}}

with source as (
    select
        *,
        current_timestamp() as dbt_updated_at
    from {{ ref('int_daily_metrics') }}
)

select * from source

{% if is_incremental() %}
-- Re-check the last 7 days on every run to catch WHOOP rescores.
where cycle_date >= (
    select date_sub(max(cycle_date), interval 7 day)
    from {{ this }}
)
{% endif %}
