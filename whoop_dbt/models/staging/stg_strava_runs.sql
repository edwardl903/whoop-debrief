-- Staging: stg_strava_runs
-- Cast types, compute derived pace and distance metrics, dedup to the latest
-- loaded row per run_id.
-- Grain: one row per run_id (most recently loaded version).

with source as (
    select * from {{ source('whoop_raw', 'raw_strava_runs') }}
),

deduped as (
    select
        id                                                              as run_id,
        name                                                            as run_name,
        sport_type,
        start_date                                                      as run_start,
        date(start_date)                                                as run_date,

        -- Distance
        distance_meter,
        safe_divide(distance_meter, 1000.0)                             as distance_km,

        -- Duration
        moving_time_sec,
        elapsed_time_sec,
        safe_divide(moving_time_sec, 60.0)                              as moving_time_min,

        -- Pace: minutes per km (lower = faster)
        safe_divide(
            safe_divide(moving_time_sec, 60.0),
            safe_divide(distance_meter, 1000.0)
        )                                                               as pace_min_per_km,

        -- Speed: m/s -> km/h for readability
        average_speed_ms,
        max_speed_ms,
        round(average_speed_ms * 3.6, 2)                               as avg_speed_kmh,
        round(max_speed_ms * 3.6, 2)                                   as max_speed_kmh,

        -- Elevation
        total_elevation_gain_meter,

        -- Heart rate
        average_heartrate,
        max_heartrate,

        -- Other metrics
        average_cadence,
        suffer_score,
        summary_polyline,

        loaded_at
    from source
    qualify row_number() over (
        partition by id
        order by loaded_at desc
    ) = 1
)

select * from deduped
