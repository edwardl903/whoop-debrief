-- Staging: raw_sleeps
-- Unpack nested score STRUCT, convert millisecond durations to hours,
-- and dedup to the latest loaded row per sleep ID.
-- Grain: one row per sleep_id (most recently loaded version).

with source as (
    select * from {{ source('whoop_raw', 'raw_sleeps') }}
),

deduped as (
    select
        id                                                                          as sleep_id,
        cycle_id,
        user_id,
        nap                                                                         as is_nap,
        start                                                                       as sleep_start,
        `end`                                                                       as sleep_end,
        timezone_offset,
        score_state,

        -- Stage durations: milliseconds → hours
        safe_divide(score.stage_summary.total_in_bed_time_milli, 3600000.0)         as in_bed_hours,
        safe_divide(score.stage_summary.total_awake_time_milli, 3600000.0)          as awake_hours,
        safe_divide(score.stage_summary.total_light_sleep_time_milli, 3600000.0)    as light_sleep_hours,
        safe_divide(score.stage_summary.total_slow_wave_sleep_time_milli, 3600000.0) as sws_hours,
        safe_divide(score.stage_summary.total_rem_sleep_time_milli, 3600000.0)      as rem_hours,
        score.stage_summary.sleep_cycle_count                                       as sleep_cycle_count,
        score.stage_summary.disturbance_count                                       as disturbance_count,

        -- Sleep need: milliseconds → hours
        safe_divide(score.sleep_needed.baseline_milli, 3600000.0)                  as sleep_needed_baseline_hours,
        safe_divide(score.sleep_needed.need_from_sleep_debt_milli, 3600000.0)      as sleep_need_from_debt_hours,

        -- Quality metrics (already percentages 0-100)
        score.respiratory_rate                                                      as respiratory_rate,
        score.sleep_performance_percentage                                          as sleep_performance_pct,
        score.sleep_consistency_percentage                                          as sleep_consistency_pct,
        score.sleep_efficiency_percentage                                           as sleep_efficiency_pct,

        loaded_at,
        date(`end`)                                                                 as sleep_date
    from source
    qualify row_number() over (
        partition by id
        order by loaded_at desc
    ) = 1
)

select * from deduped
