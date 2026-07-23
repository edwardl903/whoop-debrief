-- Fact: fct_workouts
-- Incremental merge on workout_id. Re-processes the last 7 days on each run
-- to catch WHOOP rescores and late-arriving next-day recovery values.
-- Grain: one row per workout_id.

{{
    config(
        materialized='incremental',
        unique_key='workout_id',
        incremental_strategy='merge',
        on_schema_change='sync_all_columns'
    )
}}

with source as (
    select
        *,
        current_timestamp() as dbt_updated_at
    from {{ ref('int_workout_recovery') }}
)

select * from source

{% if is_incremental() %}
where workout_date >= (
    select date_sub(max(workout_date), interval 7 day)
    from {{ this }}
)
{% endif %}
