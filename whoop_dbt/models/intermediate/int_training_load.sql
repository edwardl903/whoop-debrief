-- int_training_load.sql
--
-- Daily training load metrics using exponentially weighted moving averages (EWMA).
--
-- CTL (Chronic Training Load) = fitness.   42-day time constant.
-- ATL (Acute Training Load)   = fatigue.    7-day time constant.
-- TSB (Training Stress Balance) = form.     TSB = CTL - ATL.
--
-- Daily Training Stress Score (TSS) proxy: WHOOP day strain, normalized from
-- the 0-21 WHOOP scale to a 0-100 scale so the numbers are comparable to
-- standard TrainingPeaks / Golden Cheetah conventions.
--
-- EWMA formula:
--   CTL(d) = sum over all prior days of: TSS(d_i) * (1 - alpha_ctl) * alpha_ctl^(d - d_i)
--   where alpha_ctl = exp(-1/42), alpha_atl = exp(-1/7)
--
-- Implemented as a self-join (O(n * lookback)) rather than recursion.
-- Lookback capped at 180 days -- captures >99.9% of weight for the 42-day kernel.
--
-- Grain: one row per user_id + cycle_date.
-- Materialized as a full table rebuild; personal-scale data makes this cheap.

{{
    config(
        materialized='table',
        description='Daily CTL/ATL/TSB training load model using WHOOP strain as TSS proxy.'
    )
}}

with

daily_strain as (
    select
        cycle_date,
        user_id,
        strain_score,
        recovery_score,
        hrv_rmssd_milli,
        resting_heart_rate,
        -- Normalize WHOOP strain (0-21) to 0-100 TSS scale.
        -- A strain of 21 (max) maps to TSS 100; rest days (strain ~0) map near 0.
        round(coalesce(strain_score, 0) * (100.0 / 21.0), 2) as daily_tss
    from {{ ref('fct_daily') }}
    where cycle_date is not null
),

-- Weighted sums via self-join.
-- For each target date, sum TSS of every historical date weighted by
-- the exponential decay since that date.
weighted as (
    select
        target.cycle_date,
        target.user_id,
        target.daily_tss,
        target.strain_score,
        target.recovery_score,
        target.hrv_rmssd_milli,
        target.resting_heart_rate,

        -- CTL: 42-day exponential kernel
        round(
            sum(
                hist.daily_tss
                * (1.0 - exp(-1.0 / 42.0))
                * pow(exp(-1.0 / 42.0), date_diff(target.cycle_date, hist.cycle_date, day))
            ),
            1
        ) as ctl,

        -- ATL: 7-day exponential kernel
        round(
            sum(
                hist.daily_tss
                * (1.0 - exp(-1.0 / 7.0))
                * pow(exp(-1.0 / 7.0), date_diff(target.cycle_date, hist.cycle_date, day))
            ),
            1
        ) as atl

    from daily_strain as target
    left join daily_strain as hist
        on  hist.user_id    = target.user_id
        and hist.cycle_date <= target.cycle_date
        -- Cap lookback: exp(-180/42) < 0.014; negligible contribution beyond this.
        and date_diff(target.cycle_date, hist.cycle_date, day) <= 180
    group by 1, 2, 3, 4, 5, 6, 7
),

with_tsb as (
    select
        cycle_date,
        user_id,
        daily_tss,
        strain_score,
        recovery_score,
        hrv_rmssd_milli,
        resting_heart_rate,
        ctl,
        atl,
        round(ctl - atl, 1) as tsb,

        -- Form label based on TSB conventions from Coggan / Friel
        case
            when ctl - atl  >  25 then 'very_fresh'    -- possibly under-trained
            when ctl - atl  >   5 then 'peak_form'     -- race-ready window
            when ctl - atl  >= -10 then 'neutral'      -- building base
            when ctl - atl  >= -30 then 'fatigued'     -- normal hard training
            else                       'overtrained'   -- high injury/illness risk
        end as form_label,

        -- Training phase: is fitness (CTL) building or declining?
        case
            when ctl > lag(ctl, 7) over (partition by user_id order by cycle_date) then 'building'
            when ctl < lag(ctl, 7) over (partition by user_id order by cycle_date) then 'declining'
            else 'maintaining'
        end as fitness_phase,

        -- 7-day CTL delta: positive = gaining fitness, negative = losing it
        round(
            ctl - lag(ctl, 7) over (partition by user_id order by cycle_date),
            1
        ) as ctl_7d_delta,

        -- Monotony: ratio of avg daily TSS to std dev (high = not enough variation)
        round(
            avg(daily_tss) over (
                partition by user_id
                order by cycle_date
                rows between 6 preceding and current row
            )
            / nullif(
                stddev(daily_tss) over (
                    partition by user_id
                    order by cycle_date
                    rows between 6 preceding and current row
                ),
                0
            ),
            2
        ) as training_monotony_7d

    from weighted
)

select * from with_tsb
order by user_id, cycle_date
