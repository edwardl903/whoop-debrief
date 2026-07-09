-- Intermediate: int_run_recovery
-- Joins each Strava run to WHOOP daily metrics for two time windows:
--   same_day:  cycle_date == run_date  (strain context for the run day)
--   next_day:  cycle_date == run_date + 1  (recovery impact the morning after)
--
-- Both joins are LEFT so runs with no WHOOP data still appear.
-- Grain: one row per run_id.

with runs as (
    select * from {{ ref('stg_strava_runs') }}
),

daily as (
    select * from {{ ref('int_daily_metrics') }}
),

same_day as (
    select
        run_id,
        -- WHOOP same-day context (strain during the run day)
        cycle_id                    as same_day_cycle_id,
        strain_score                as same_day_strain,
        cycle_avg_heart_rate        as same_day_avg_hr,
        recovery_score              as same_day_recovery,
        recovery_bucket             as same_day_recovery_bucket,
        hrv_rmssd_milli             as same_day_hrv
    from runs
    left join daily
        on runs.run_date = daily.cycle_date
),

next_day as (
    select
        run_id,
        -- WHOOP next-day recovery (morning after the run)
        cycle_id                    as next_day_cycle_id,
        recovery_score              as next_day_recovery,
        recovery_bucket             as next_day_recovery_bucket,
        hrv_rmssd_milli             as next_day_hrv,
        resting_heart_rate          as next_day_resting_hr,
        sleep_performance_pct       as next_day_sleep_performance,
        total_sleep_hours           as next_day_sleep_hours,
        sleep_quality_label         as next_day_sleep_quality
    from runs
    left join daily
        on date_add(runs.run_date, interval 1 day) = daily.cycle_date
)

select
    -- Run identifiers
    r.run_id,
    r.run_name,
    r.sport_type,
    r.run_start,
    r.run_date,

    -- Run performance
    r.distance_km,
    r.moving_time_min,
    r.pace_min_per_km,
    r.avg_speed_kmh,
    r.total_elevation_gain_meter,
    r.average_heartrate                                     as run_avg_hr,
    r.max_heartrate                                         as run_max_hr,
    r.average_cadence,
    r.suffer_score,
    r.summary_polyline,

    -- WHOOP context for run day
    sd.same_day_cycle_id,
    sd.same_day_strain,
    sd.same_day_avg_hr,
    sd.same_day_recovery,
    sd.same_day_recovery_bucket,
    sd.same_day_hrv,

    -- WHOOP recovery the morning after
    nd.next_day_cycle_id,
    nd.next_day_recovery,
    nd.next_day_recovery_bucket,
    nd.next_day_hrv,
    nd.next_day_resting_hr,
    nd.next_day_sleep_performance,
    nd.next_day_sleep_hours,
    nd.next_day_sleep_quality,

    -- Derived: did recovery go up or down after this run?
    nd.next_day_recovery - sd.same_day_recovery             as recovery_delta,

    r.loaded_at

from runs r
left join same_day sd using (run_id)
left join next_day nd using (run_id)
