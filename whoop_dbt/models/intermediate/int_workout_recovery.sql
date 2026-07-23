-- Intermediate: int_workout_recovery
-- Joins each WHOOP workout to next-day recovery context from int_daily_metrics.
-- Mirrors the int_run_recovery pattern: the next-day join answers "how did
-- this workout affect my recovery the morning after?"
-- Both joins are LEFT so workouts with no WHOOP daily data still appear.
-- Grain: one row per workout_id.

with workouts as (
    select * from {{ ref('stg_raw_workouts') }}
),

daily as (
    select * from {{ ref('int_daily_metrics') }}
),

next_day as (
    select
        w.workout_id,
        d.cycle_id                  as next_day_cycle_id,
        d.recovery_score            as next_day_recovery,
        d.recovery_bucket           as next_day_recovery_bucket,
        d.hrv_rmssd_milli           as next_day_hrv,
        d.resting_heart_rate        as next_day_resting_hr,
        d.sleep_performance_pct     as next_day_sleep_performance,
        d.total_sleep_hours         as next_day_sleep_hours,
        d.sleep_quality_label       as next_day_sleep_quality
    from workouts w
    left join daily d
        on date_add(w.workout_date, interval 1 day) = d.cycle_date
)

select
    -- Workout identifiers and timing
    w.workout_id,
    w.user_id,
    w.sport_id,
    w.sport_name,
    w.workout_start,
    w.workout_end,
    w.workout_date,
    w.timezone_offset,
    w.score_state,

    -- Workout performance
    w.strain_score,
    w.avg_heart_rate,
    w.max_heart_rate,
    w.kilojoule,
    w.pct_recorded,
    w.distance_meter,
    w.altitude_gain_meter,
    w.altitude_change_meter,

    -- HR zones (minutes)
    w.zone_0_min,
    w.zone_1_min,
    w.zone_2_min,
    w.zone_3_min,
    w.zone_4_min,
    w.zone_5_min,

    -- Derived: high-intensity zone minutes (zones 3 + 4 + 5, above ~70% max HR)
    coalesce(w.zone_3_min, 0)
        + coalesce(w.zone_4_min, 0)
        + coalesce(w.zone_5_min, 0)                                as high_intensity_min,

    -- Next-day recovery context (morning after the workout)
    nd.next_day_cycle_id,
    nd.next_day_recovery,
    nd.next_day_recovery_bucket,
    nd.next_day_hrv,
    nd.next_day_resting_hr,
    nd.next_day_sleep_performance,
    nd.next_day_sleep_hours,
    nd.next_day_sleep_quality,

    w.loaded_at

from workouts w
left join next_day nd using (workout_id)
