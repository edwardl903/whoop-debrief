-- Mart: my_trends
-- Full table rebuild on every run. Pre-aggregated rolling averages (7-day and
-- 28-day) for recovery, strain, sleep, and HRV. Designed for consumption by
-- a dashboard or portfolio serve layer.
-- Grain: one row per (cycle_date, user_id).

{{
    config(materialized='table')
}}

with daily as (
    select
        cycle_date,
        user_id,
        strain_score,
        recovery_score,
        sleep_performance_pct,
        total_sleep_hours,
        hrv_rmssd_milli,
        recovery_bucket,
        sleep_quality_label,
        resting_heart_rate,
        sws_hours,
        rem_hours
    from {{ ref('int_daily_metrics') }}
    where cycle_date is not null
),

with_rolling as (
    select
        cycle_date,
        user_id,

        -- Raw daily metrics
        strain_score,
        recovery_score,
        sleep_performance_pct,
        total_sleep_hours,
        hrv_rmssd_milli,
        resting_heart_rate,
        sws_hours,
        rem_hours,
        recovery_bucket,
        sleep_quality_label,

        -- 7-day rolling averages (ordered by date, rows-based window)
        round(avg(recovery_score) over (
            partition by user_id
            order by cycle_date
            rows between 6 preceding and current row
        ), 1)                                               as recovery_score_7d_avg,

        round(avg(strain_score) over (
            partition by user_id
            order by cycle_date
            rows between 6 preceding and current row
        ), 1)                                               as strain_score_7d_avg,

        round(avg(sleep_performance_pct) over (
            partition by user_id
            order by cycle_date
            rows between 6 preceding and current row
        ), 1)                                               as sleep_performance_7d_avg,

        round(avg(total_sleep_hours) over (
            partition by user_id
            order by cycle_date
            rows between 6 preceding and current row
        ), 2)                                               as sleep_hours_7d_avg,

        round(avg(hrv_rmssd_milli) over (
            partition by user_id
            order by cycle_date
            rows between 6 preceding and current row
        ), 1)                                               as hrv_7d_avg,

        round(avg(resting_heart_rate) over (
            partition by user_id
            order by cycle_date
            rows between 6 preceding and current row
        ), 1)                                               as resting_hr_7d_avg,

        -- 28-day rolling averages
        round(avg(recovery_score) over (
            partition by user_id
            order by cycle_date
            rows between 27 preceding and current row
        ), 1)                                               as recovery_score_28d_avg,

        round(avg(strain_score) over (
            partition by user_id
            order by cycle_date
            rows between 27 preceding and current row
        ), 1)                                               as strain_score_28d_avg,

        round(avg(sleep_performance_pct) over (
            partition by user_id
            order by cycle_date
            rows between 27 preceding and current row
        ), 1)                                               as sleep_performance_28d_avg,

        round(avg(hrv_rmssd_milli) over (
            partition by user_id
            order by cycle_date
            rows between 27 preceding and current row
        ), 1)                                               as hrv_28d_avg,

        -- Day-over-day deltas (useful for trend arrows in dashboards)
        recovery_score - lag(recovery_score) over (
            partition by user_id order by cycle_date
        )                                                   as recovery_score_dod,

        strain_score - lag(strain_score) over (
            partition by user_id order by cycle_date
        )                                                   as strain_score_dod,

        hrv_rmssd_milli - lag(hrv_rmssd_milli) over (
            partition by user_id order by cycle_date
        )                                                   as hrv_dod

    from daily
)

select * from with_rolling
