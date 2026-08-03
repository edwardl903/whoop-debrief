-- fct_weekly_training_summary.sql
--
-- Weekly aggregate of training load and WHOOP wellness metrics.
-- Grain: one row per user_id + ISO week (Monday-anchored).
--
-- Designed to answer: am I building fitness week over week?
-- Is my weekly load sustainable given my recovery?
--
-- Sources: int_training_load (CTL/ATL/TSB), fct_runs (weekly mileage + pace).

{{
    config(
        materialized='table',
        description='Weekly training summary: total load, CTL trend, mileage, avg recovery.'
    )
}}

with

training_load as (
    select * from {{ ref('int_training_load') }}
),

runs as (
    select
        run_date,
        distance_km,
        moving_time_min,
        pace_min_per_km,
        run_avg_hr
    from {{ ref('fct_runs') }}
    where run_date is not null
),

-- Weekly aggregates from training load
weekly_load as (
    select
        date_trunc(cycle_date, week(monday))  as week_start,
        date_add(
            date_trunc(cycle_date, week(monday)), interval 6 day
        )                                      as week_end,
        user_id,
        count(*)                               as tracked_days,
        round(sum(daily_tss), 1)               as total_weekly_tss,
        round(avg(daily_tss), 1)               as avg_daily_tss,

        -- CTL and ATL: end-of-week snapshot (last day of the week in the data)
        round(
            max_by(ctl, cycle_date),
            1
        )                                      as week_end_ctl,
        round(
            max_by(atl, cycle_date),
            1
        )                                      as week_end_atl,
        round(
            max_by(tsb, cycle_date),
            1
        )                                      as week_end_tsb,
        max_by(form_label, cycle_date)         as week_end_form,
        max_by(fitness_phase, cycle_date)      as fitness_phase,

        -- Recovery and HRV
        round(avg(recovery_score), 1)          as avg_recovery,
        round(avg(hrv_rmssd_milli), 1)         as avg_hrv_rmssd,
        round(avg(resting_heart_rate), 1)      as avg_rhr,

        -- Training monotony: high (>2) signals insufficient variation
        round(avg(training_monotony_7d), 2)    as avg_monotony,

        -- Strain days vs rest days
        countif(strain_score >= 10)            as hard_days,
        countif(strain_score < 5 or strain_score is null) as easy_or_rest_days

    from training_load
    group by 1, 2, 3
),

-- Weekly run aggregates
-- fct_runs does not surface user_id, so join to weekly_load on week_start only.
-- Single-user pipeline: no fan-out risk from this cartesian-free join.
weekly_runs as (
    select
        date_trunc(run_date, week(monday))  as week_start,
        count(*)                            as run_count,
        round(sum(distance_km), 2)          as total_distance_km,
        round(sum(moving_time_min), 1)      as total_run_minutes,
        round(avg(pace_min_per_km), 2)      as avg_pace_min_per_km,
        round(avg(run_avg_hr), 1)           as avg_run_hr
    from runs
    group by 1
),

final as (
    select
        wl.week_start,
        wl.week_end,
        wl.user_id,
        wl.tracked_days,
        wl.total_weekly_tss,
        wl.avg_daily_tss,
        wl.week_end_ctl,
        wl.week_end_atl,
        wl.week_end_tsb,
        wl.week_end_form,
        wl.fitness_phase,
        wl.avg_recovery,
        wl.avg_hrv_rmssd,
        wl.avg_rhr,
        wl.avg_monotony,
        wl.hard_days,
        wl.easy_or_rest_days,

        -- Run metrics (null if no runs that week)
        coalesce(wr.run_count, 0)           as run_count,
        wr.total_distance_km,
        wr.total_run_minutes,
        wr.avg_pace_min_per_km,
        wr.avg_run_hr,

        -- Week-over-week CTL delta
        round(
            wl.week_end_ctl
            - lag(wl.week_end_ctl) over (partition by wl.user_id order by wl.week_start),
            1
        )                                   as ctl_wow_delta,

        -- Week-over-week TSS delta (training load progression)
        round(
            wl.total_weekly_tss
            - lag(wl.total_weekly_tss) over (partition by wl.user_id order by wl.week_start),
            1
        )                                   as tss_wow_delta,

        -- Week-over-week distance delta
        round(
            coalesce(wr.total_distance_km, 0)
            - coalesce(
                lag(wr.total_distance_km) over (partition by wl.user_id order by wl.week_start),
                0
            ),
            2
        )                                   as distance_wow_delta_km,

        -- Sustainable load flag: ATL > 1.5 * CTL signals spike risk
        case
            when wl.week_end_atl > 1.5 * nullif(wl.week_end_ctl, 0)
            then true
            else false
        end                                 as load_spike_flag

    from weekly_load as wl
    left join weekly_runs as wr
        on wr.week_start = wl.week_start
)

select * from final
order by user_id, week_start
