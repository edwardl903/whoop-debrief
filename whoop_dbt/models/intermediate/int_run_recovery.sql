-- Intermediate: int_run_recovery
-- Joins each Strava run to WHOOP daily metrics for two time windows:
--   same_day:  cycle_date == run_date  (strain context for the run day)
--   next_day:  cycle_date == run_date + 1  (recovery impact the morning after)
--
-- Also matches each Strava run to the closest WHOOP-tracked running workout
-- on the same day by start-time proximity (QUALIFY ROW_NUMBER). The match
-- surfaces WHOOP's own HR zones and strain for the same activity, bridging
-- Strava GPS data with WHOOP physiological data.
--
-- All joins are LEFT so runs with no WHOOP data still appear.
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
),

-- Match each Strava run to the closest WHOOP running workout on the same day.
-- When multiple running workouts exist on the same day, QUALIFY picks the one
-- whose start time is nearest to the Strava run start (smallest minute diff).
-- When no WHOOP workout matches, all whoop_workout_* columns are null.
whoop_workout as (
    select
        r.run_id,
        w.workout_id                                                as whoop_workout_id,
        w.sport_name                                                as whoop_sport_name,
        w.strain_score                                              as whoop_workout_strain,
        w.avg_heart_rate                                            as whoop_workout_avg_hr,
        w.max_heart_rate                                            as whoop_workout_max_hr,
        w.distance_meter                                            as whoop_workout_distance_meter,
        w.zone_3_min                                                as whoop_zone_3_min,
        w.zone_4_min                                                as whoop_zone_4_min,
        w.zone_5_min                                                as whoop_zone_5_min,
        coalesce(w.zone_3_min, 0)
            + coalesce(w.zone_4_min, 0)
            + coalesce(w.zone_5_min, 0)                            as whoop_high_intensity_min
    from runs r
    left join {{ ref('stg_raw_workouts') }} w
        on r.run_date = w.workout_date
        and lower(w.sport_name) like '%run%'
    qualify row_number() over (
        partition by r.run_id
        order by abs(timestamp_diff(r.run_start, w.workout_start, minute))
    ) = 1
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

    -- Matched WHOOP workout (same-day running activity by start-time proximity)
    ww.whoop_workout_id,
    ww.whoop_sport_name,
    ww.whoop_workout_strain,
    ww.whoop_workout_avg_hr,
    ww.whoop_workout_max_hr,
    ww.whoop_workout_distance_meter,
    ww.whoop_high_intensity_min,

    r.loaded_at

from runs r
left join same_day sd using (run_id)
left join next_day nd using (run_id)
left join whoop_workout ww using (run_id)
