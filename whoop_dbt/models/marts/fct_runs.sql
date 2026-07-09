-- Fact: fct_runs
-- Incremental merge on run_id. Re-processes the last 7 days on each run
-- to pick up any late-arriving WHOOP scores or Strava edits.
-- Grain: one row per Strava run_id.

{{
    config(
        materialized='incremental',
        unique_key='run_id',
        incremental_strategy='merge',
        on_schema_change='sync_all_columns'
    )
}}

with source as (
    select
        *,
        current_timestamp() as dbt_updated_at
    from {{ ref('int_run_recovery') }}
)

select * from source

{% if is_incremental() %}
where run_date >= (
    select date_sub(max(run_date), interval 7 day)
    from {{ this }}
)
{% endif %}
