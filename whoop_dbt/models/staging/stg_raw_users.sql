-- Staging: raw_users
-- Deduplicated user profile snapshots. The pipeline inserts one row per daily run;
-- this model keeps only the latest snapshot per user_id.
-- Grain: one row per user_id (most recently loaded snapshot).

with source as (
    select * from {{ source('whoop_raw', 'raw_users') }}
),

deduped as (
    select
        user_id,
        email,
        first_name,
        last_name,
        loaded_at
    from source
    qualify row_number() over (
        partition by user_id
        order by loaded_at desc
    ) = 1
)

select * from deduped
