-- Dimension: dim_user
-- Full table rebuild on every run. One row per user with lifetime aggregates,
-- peak scores, and basic profile info (name, email from raw_users).
-- Grain: one row per user_id.

{{
    config(materialized='table')
}}

with base as (
    select
        user_id,
        cycle_date,
        strain_score,
        recovery_score,
        sleep_performance_pct,
        total_sleep_hours,
        hrv_rmssd_milli
    from {{ ref('int_daily_metrics') }}
    where recovery_score is not null
        and cycle_date is not null
),

aggregated as (
    select
        user_id,
        count(distinct cycle_date)              as total_tracked_days,
        min(cycle_date)                         as first_tracked_date,
        max(cycle_date)                         as latest_tracked_date,

        -- Recovery
        round(avg(recovery_score), 1)           as avg_recovery_score,
        round(max(recovery_score), 1)           as peak_recovery_score,

        -- Strain
        round(avg(strain_score), 1)             as avg_strain_score,
        round(max(strain_score), 1)             as peak_strain_score,

        -- Sleep
        round(avg(sleep_performance_pct), 1)    as avg_sleep_performance_pct,
        round(avg(total_sleep_hours), 2)        as avg_sleep_hours,

        -- HRV
        round(avg(hrv_rmssd_milli), 1)          as avg_hrv_rmssd_milli,
        round(max(hrv_rmssd_milli), 1)          as peak_hrv_rmssd_milli
    from base
    group by 1
),

profile as (
    select
        user_id,
        first_name,
        last_name,
        email
    from {{ ref('stg_raw_users') }}
)

select
    a.*,
    p.first_name,
    p.last_name,
    p.email,
    current_timestamp()     as dbt_updated_at
from aggregated a
left join profile p using (user_id)
