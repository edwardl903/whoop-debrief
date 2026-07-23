-- Staging: raw_workouts
-- Unpack nested score STRUCT (including HR zone_duration sub-struct),
-- convert zone durations from milliseconds to minutes, dedup per workout ID.
-- Grain: one row per workout_id (most recently loaded version).

with source as (
    select * from {{ source('whoop_raw', 'raw_workouts') }}
),

deduped as (
    select
        id                                                          as workout_id,
        user_id,
        sport_id,
        sport_name,
        start                                                       as workout_start,
        `end`                                                       as workout_end,
        timezone_offset,
        score_state,
        score.strain                                                as strain_score,
        score.average_heart_rate                                    as avg_heart_rate,
        score.max_heart_rate                                        as max_heart_rate,
        score.kilojoule                                             as kilojoule,
        safe_divide(score.percent_recorded, 100.0)                  as pct_recorded,
        score.distance_meter                                        as distance_meter,
        score.altitude_gain_meter                                   as altitude_gain_meter,
        score.altitude_change_meter                                 as altitude_change_meter,

        -- HR zone durations: milliseconds → minutes
        safe_divide(score.zone_duration.zone_zero_milli, 60000.0)   as zone_0_min,
        safe_divide(score.zone_duration.zone_one_milli, 60000.0)    as zone_1_min,
        safe_divide(score.zone_duration.zone_two_milli, 60000.0)    as zone_2_min,
        safe_divide(score.zone_duration.zone_three_milli, 60000.0)  as zone_3_min,
        safe_divide(score.zone_duration.zone_four_milli, 60000.0)   as zone_4_min,
        safe_divide(score.zone_duration.zone_five_milli, 60000.0)   as zone_5_min,

        loaded_at,
        date(start)                                                 as workout_date
    from source
    qualify row_number() over (
        partition by id
        order by loaded_at desc
    ) = 1
)

select * from deduped
