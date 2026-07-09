-- Intermediate: int_daily_metrics
-- Joins cycles, recoveries, and the primary overnight sleep for each cycle.
-- Derives recovery_bucket (peak/optimal/poor) and sleep_quality_label.
-- Grain: one row per cycle_id (one row per day).

with cycles as (
    select * from {{ ref('stg_raw_cycles') }}
),

-- One recovery per cycle (staging already dedups by cycle_id).
recoveries as (
    select * from {{ ref('stg_raw_recoveries') }}
),

-- Exclude naps; when multiple non-nap sleeps share a cycle_id (rare),
-- keep the longest by time in bed.
sleeps as (
    select * from {{ ref('stg_raw_sleeps') }}
    where not is_nap
    qualify row_number() over (
        partition by cycle_id
        order by coalesce(in_bed_hours, 0) desc
    ) = 1
)

select
    -- Identifiers
    c.cycle_id,
    c.user_id,
    c.cycle_date,

    -- Cycle timing
    c.cycle_start,
    c.cycle_end,
    c.score_state                                   as cycle_score_state,

    -- Strain (from cycle)
    c.strain_score,
    c.kilojoule                                     as cycle_kilojoule,
    c.avg_heart_rate                                as cycle_avg_heart_rate,
    c.max_heart_rate                                as cycle_max_heart_rate,

    -- Recovery
    r.recovery_score,
    r.resting_heart_rate,
    r.hrv_rmssd_milli,
    r.spo2_pct,
    r.skin_temp_celsius,
    r.is_calibrating,
    r.score_state                                   as recovery_score_state,

    -- Sleep
    s.sleep_id,
    s.sleep_start,
    s.sleep_end,
    s.in_bed_hours,
    s.awake_hours,
    s.light_sleep_hours,
    s.sws_hours,
    s.rem_hours,
    s.sleep_cycle_count,
    s.disturbance_count,
    s.sleep_needed_baseline_hours,
    s.respiratory_rate,
    s.sleep_performance_pct,
    s.sleep_consistency_pct,
    s.sleep_efficiency_pct,
    s.score_state                                   as sleep_score_state,

    -- Derived: total asleep hours (in bed minus awake)
    round(
        s.in_bed_hours - coalesce(s.awake_hours, 0),
        2
    )                                               as total_sleep_hours,

    -- Derived: recovery bucket (WHOOP green/yellow/red thresholds)
    case
        when r.recovery_score >= 67 then 'peak'
        when r.recovery_score >= 34 then 'optimal'
        when r.recovery_score is not null then 'poor'
        else null
    end                                             as recovery_bucket,

    -- Derived: sleep quality label based on WHOOP performance score
    case
        when s.sleep_performance_pct >= 85 then 'excellent'
        when s.sleep_performance_pct >= 70 then 'good'
        when s.sleep_performance_pct >= 50 then 'fair'
        when s.sleep_performance_pct is not null then 'poor'
        else null
    end                                             as sleep_quality_label,

    -- Watermark
    c.loaded_at

from cycles c
left join recoveries r using (cycle_id)
left join sleeps s using (cycle_id)
