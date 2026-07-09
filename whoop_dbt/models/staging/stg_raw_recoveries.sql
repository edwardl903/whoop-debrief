-- Staging: raw_recoveries
-- Unpack nested score STRUCT, dedup to latest row per cycle_id.
-- Recovery is 1:1 with cycles (one recovery per daily cycle).
-- Grain: one row per cycle_id (most recently loaded version).

with source as (
    select * from {{ source('whoop_raw', 'raw_recoveries') }}
),

deduped as (
    select
        cycle_id,
        sleep_id,
        user_id,
        score_state,
        score.user_calibrating          as is_calibrating,
        score.recovery_score            as recovery_score,
        score.resting_heart_rate        as resting_heart_rate,
        score.hrv_rmssd_milli           as hrv_rmssd_milli,
        score.spo2_percentage           as spo2_pct,
        score.skin_temp_celsius         as skin_temp_celsius,
        created_at,
        updated_at,
        loaded_at,
        date(created_at)                as recovery_date
    from source
    qualify row_number() over (
        partition by cycle_id
        order by loaded_at desc
    ) = 1
)

select * from deduped
