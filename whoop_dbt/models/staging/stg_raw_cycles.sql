-- Staging: raw_cycles
-- Cast types, rename columns, and dedup to latest loaded row per cycle.
-- Score fields are unpacked from the nested STRUCT.
-- Grain: one row per cycle_id (most recently loaded version).

with source as (
    select * from {{ source('whoop_raw', 'raw_cycles') }}
),

deduped as (
    select
        id                              as cycle_id,
        user_id,
        start                           as cycle_start,
        `end`                           as cycle_end,
        timezone_offset,
        score_state,
        score.strain                    as strain_score,
        score.kilojoule                 as kilojoule,
        score.average_heart_rate        as avg_heart_rate,
        score.max_heart_rate            as max_heart_rate,
        loaded_at,
        date(start)                     as cycle_date
    from source
    qualify row_number() over (
        partition by id
        order by loaded_at desc
    ) = 1
)

select * from deduped
