"""
scoring.py
----------
Pure scoring primitives for the flare model. No database, no Flask, no I/O.

Everything here is a function of its arguments alone, which is what makes it
safe to import from anywhere -- the web app, analysis scripts, or the
summarize.py digest -- without dragging in migrations, a scheduler, or a
request context.

Anything that needs to *fetch* data (UV rows, observations) stays in app.py.
The dividing line is: if it touches db, it doesn't belong here.

Each window metric comes in two forms:

    _<name>_detail(...)   -> (value, recent_avg, baseline_avg)
    _compute_<name>(...)  -> value          (thin wrapper, app.py's contract)

The detail form exists so a caller can *show its work* -- summarize.py prints
the two window averages alongside the deviation so a reader can see where the
number came from. Both forms walk the same windows exactly once, so there is
no second implementation to drift.

Window definitions and thresholds are documented in MODEL.md. When you change
a window here, update MODEL.md in the same commit -- they are meant to describe
the same thing, and MODEL.md has drifted from the code before.
"""

import math
from datetime import datetime, timedelta

# UV protection multipliers — applied to UV dose in scoring.
#
# MODEL.md §1 documents these same values and names this file as their source of
# truth. If you change them here, change them there in the same commit -- the two
# drifted apart once already.
UV_PROTECTION_MULTIPLIERS = {
    "none": 1.0,
    "spf_hat": 0.5,
    "full_cover": 0.3,
    "indoors_only": 0.1,
}

_SYMPTOM_KEYS = [
    'neurological', 'cognitive', 'musculature', 'migraine',
    'pulmonary', 'dermatological', 'rheumatic', 'mucosal', 'gastro',
]

_NONE3 = (None, None, None)


def weighted_uv(uv_row):
    """Compute weighted daily UV from morning/noon/evening readings."""
    if not uv_row:
        return 0.0
    m = float(uv_row.get("uv_morning") or 0)
    n = float(uv_row.get("uv_noon") or 0)
    e = float(uv_row.get("uv_evening") or 0)
    return m * 0.2 + n * 0.6 + e * 0.2


def compute_rmssd(rr_intervals: list) -> float | None:
    """Compute RMSSD from a list of RR intervals in milliseconds.
    RMSSD = sqrt(mean(successive_differences^2))
    Returns None if fewer than 2 intervals.
    """
    if len(rr_intervals) < 2:
        return None
    diffs = [rr_intervals[i + 1] - rr_intervals[i] for i in range(len(rr_intervals) - 1)]
    squared = [d * d for d in diffs]
    return round(math.sqrt(sum(squared) / len(squared)), 2)


def _daily_symptom_count(obs: dict | None) -> int | None:
    """Count binary symptom flags for a single day's observation."""
    if not obs:
        return None
    return sum(1 for sym in _SYMPTOM_KEYS if obs.get(sym))


def _collect(obs_date, obs_by_date, field, start_offset, end_offset):
    """Values of `field` across days -start_offset .. -end_offset, skipping
    missing days and nulls. Shared by the level-based window metrics."""
    target = datetime.strptime(obs_date, "%Y-%m-%d").date()
    out = []
    for offset in range(start_offset, end_offset + 1):
        obs = obs_by_date.get((target - timedelta(days=offset)).isoformat())
        if obs and obs.get(field) is not None:
            out.append(float(obs[field]))
    return out


def _pct_deviation(recent, baseline, min_recent, min_baseline):
    """(deviation_pct, recent_avg, baseline_avg) or _NONE3 if underpowered."""
    if len(recent) < min_recent or len(baseline) < min_baseline:
        return _NONE3
    recent_avg = sum(recent) / len(recent)
    baseline_avg = sum(baseline) / len(baseline)
    if baseline_avg == 0:
        return _NONE3
    return round((recent_avg - baseline_avg) / baseline_avg * 100, 1), recent_avg, baseline_avg


# ------------------------------------------------------------------
# Symptom burden delta
# ------------------------------------------------------------------

def _symptom_burden_detail(obs_date: str, obs_by_date: dict) -> tuple:
    """Symptom burden as deviation from personal rolling baseline.

    Returns (delta, recent_avg, baseline_avg). The delta is the 3-day recent
    average symptom count (days -1..-3) minus the 14-day rolling baseline
    (days -17..-4). Positive = symptoms accelerating above normal.

    The baseline starts at day -4, not -3, so it does not share day -3 with
    the recent window. Overlapping at -3 let the leading edge of the pre-flare
    symptom ramp inflate the baseline and shrink the delta it is meant to
    detect.

    Returns _NONE3 if insufficient baseline data (< 7 days).
    """
    target = datetime.strptime(obs_date, "%Y-%m-%d").date()

    recent = []
    for offset in range(1, 4):
        c = _daily_symptom_count(obs_by_date.get((target - timedelta(days=offset)).isoformat()))
        if c is not None:
            recent.append(c)
    if not recent:
        return _NONE3

    baseline = []
    for offset in range(4, 18):
        c = _daily_symptom_count(obs_by_date.get((target - timedelta(days=offset)).isoformat()))
        if c is not None:
            baseline.append(c)
    if len(baseline) < 7:
        return _NONE3

    recent_avg = sum(recent) / len(recent)
    baseline_avg = sum(baseline) / len(baseline)
    return round(recent_avg - baseline_avg, 2), recent_avg, baseline_avg


def _compute_symptom_burden_delta(obs_date: str, obs_by_date: dict) -> float | None:
    """Delta only. See _symptom_burden_detail."""
    return _symptom_burden_detail(obs_date, obs_by_date)[0]


# ------------------------------------------------------------------
# RMSSD level deviation
# ------------------------------------------------------------------

def _rmssd_deviation_detail(obs_date: str, obs_by_date: dict) -> tuple:
    """Percentage deviation of 7-day RMSSD average from 30-day baseline.

    Recent: days -1..-7. Baseline: days -8..-37 (no overlap).
    Negative values mean recent RMSSD sits below baseline (vagal withdrawal).
    Returns (deviation_pct, recent_avg, baseline_avg), or _NONE3 if either
    window has fewer than 4 values.
    """
    return _pct_deviation(
        _collect(obs_date, obs_by_date, 'hrv_rmssd', 1, 7),
        _collect(obs_date, obs_by_date, 'hrv_rmssd', 8, 37),
        min_recent=4, min_baseline=4)


def _compute_rmssd_deviation(obs_date: str, obs_by_date: dict) -> float | None:
    """Deviation only. See _rmssd_deviation_detail."""
    return _rmssd_deviation_detail(obs_date, obs_by_date)[0]


# ------------------------------------------------------------------
# RMSSD instability (day-to-day |Δ|)
# ------------------------------------------------------------------

def _rmssd_instability_detail(obs_date: str, obs_by_date: dict) -> tuple:
    """Percentage deviation of recent day-to-day |ΔRMSSD| from a longer baseline.

    Captures autonomic *instability* (wild parasympathetic swings) rather than
    level-based withdrawal. Empirically, the author's major flares show their
    cleanest signature in this: day-to-day |ΔRMSSD| in the week before onset
    spikes well above the author's typical range, peaking at the day-1 → day-0
    transition. These thresholds come from n=1 self-tracked data, not a study.
    This is a separate signal from _rmssd_deviation_detail and can fire alongside it.

    Recent: 5-day window (days -1..-5), yields up to 4 adjacent-day deltas.
    Baseline: 30-day window (days -6..-35), yields ~29 deltas — large enough to
    dilute post-flare-steroid oscillation days without skewing.

    Returns (deviation_pct, recent_mean, baseline_mean), or _NONE3 if there are
    fewer than 3 recent deltas or 10 baseline deltas.
    """
    target = datetime.strptime(obs_date, "%Y-%m-%d").date()

    def adjacent_deltas(start_offset: int, end_offset: int) -> list[float]:
        """|RMSSD[d] - RMSSD[d-1]| for days in [start_offset..end_offset] where
        both the day and the previous day have RMSSD values."""
        deltas = []
        for off in range(start_offset, end_offset + 1):
            curr = obs_by_date.get((target - timedelta(days=off)).isoformat())
            prev = obs_by_date.get((target - timedelta(days=off + 1)).isoformat())
            if (curr and prev and curr.get('hrv_rmssd') is not None
                    and prev.get('hrv_rmssd') is not None):
                deltas.append(abs(float(curr['hrv_rmssd']) - float(prev['hrv_rmssd'])))
        return deltas

    return _pct_deviation(adjacent_deltas(1, 5), adjacent_deltas(6, 35),
                          min_recent=3, min_baseline=10)


def _compute_rmssd_instability(obs_date: str, obs_by_date: dict) -> float | None:
    """Deviation only. See _rmssd_instability_detail."""
    return _rmssd_instability_detail(obs_date, obs_by_date)[0]


# ------------------------------------------------------------------
# Respiratory rate deviation
# ------------------------------------------------------------------

def _resp_rate_deviation_detail(obs_date: str, obs_by_date: dict) -> tuple:
    """Percentage deviation of 3-day respiratory rate average from 14-day baseline.

    Recent: days -1..-3 (short, because the hypothesis is a 1-3 day signal).
    Baseline: days -4..-17 (gap avoids pre-event contamination).
    Positive values mean recent respiratory rate is elevated.
    Returns (deviation_pct, recent_avg, baseline_avg), or _NONE3 if fewer than
    2 recent or 4 baseline values.
    """
    return _pct_deviation(
        _collect(obs_date, obs_by_date, 'respiratory_rate', 1, 3),
        _collect(obs_date, obs_by_date, 'respiratory_rate', 4, 17),
        min_recent=2, min_baseline=4)


def _compute_resp_rate_deviation(obs_date: str, obs_by_date: dict) -> float | None:
    """Deviation only. See _resp_rate_deviation_detail."""
    return _resp_rate_deviation_detail(obs_date, obs_by_date)[0]


# ============================================================
# RMSSD ARTIFACT GUARD — per-user calibration
# ============================================================
#
# Why this exists (the short version of a long adventure):
#
# RMSSD is derived from inter-beat intervals, and the derivation is fragile. A
# sync bug that pools intervals across separate overnight recordings, or that
# fails to filter ectopic beats, produces values that are not *impossible* --
# just wrong. Observed here: a run of correct nights around 8-11 ms punctuated
# by junk spikes of 78-120 ms. Because RMSSD feeds the flare model, a silent
# upstream regression silently poisons the forecast.
#
# A fixed universal threshold cannot catch this. "Physiologically impossible"
# is somewhere north of 200 ms, but a person whose real RMSSD sits at 10 ms is
# being handed garbage long before that. Meanwhile a healthy athlete can have a
# genuine RMSSD of 100+ ms, so a tight universal ceiling would reject real data.
# The only threshold that works is one derived from *this user's own history*.
#
# Two design constraints, both learned the hard way:
#
#   1. Calibrate on percentiles, never on min/max or mean/stdev. The history
#      you calibrate from may itself be contaminated -- that is the whole
#      problem -- and a single artifact drags a max or a mean with it.
#
#   2. Use P95, not P99. Measured on 425 real observations containing 4 known
#      artifacts (0.93% contamination): P99 of the RMSSD/SDNN ratio drifted
#      +47% while P95 drifted +2.4%. P99 sits close enough to a ~1% artifact
#      rate to be captured by it. P95 tolerates contamination up to 5%.
#
# The multipliers below are deliberately generous. Rejecting one real night
# costs almost nothing -- that day simply has no RMSSD. Accepting one artifact
# corrupts a rolling baseline for weeks. The asymmetry is the design.

_RMSSD_CALIBRATION_MIN_SAMPLES = 90    # ~3 months of nightly data before trusting a personal bound
_RMSSD_CEILING_P95_MULT = 2.25
_RMSSD_CEILING_FLOOR_MS = 50.0         # never tighter than this, however stable the user
_RMSSD_CEILING_ABSOLUTE_MS = 200.0     # never looser: above this is not physiology
_RMSSD_RATIO_P95_MULT = 2.5
_RMSSD_RATIO_FLOOR = 3.0
_RMSSD_RATIO_ABSOLUTE = 10.0
_SDNN_PLAUSIBLE_FLOOR_MS = 3.0         # SDNN below this is itself broken -- don't judge RMSSD by it

# Bounds used before a user has enough history. These reject only the flatly
# impossible, so a new user is never told their real data is wrong.
UNCALIBRATED_RMSSD_BOUNDS = {
    "ceiling_ms": _RMSSD_CEILING_ABSOLUTE_MS,
    "ratio_max": _RMSSD_RATIO_ABSOLUTE,
    "calibrated": False,
    "n": 0,
}


def _percentile(values: list[float], p: float) -> float:
    """Linear-interpolated percentile. `values` need not be sorted."""
    if not values:
        raise ValueError("percentile of empty sequence")
    v = sorted(values)
    if len(v) == 1:
        return v[0]
    k = (len(v) - 1) * p / 100.0
    lo = int(k)
    if lo + 1 >= len(v):
        return v[-1]
    return v[lo] + (v[lo + 1] - v[lo]) * (k - lo)


def calibrate_rmssd_bounds(history: list) -> dict:
    """Derive per-user RMSSD plausibility bounds from that user's own history.

    Args:
        history: iterable of (rmssd, sdnn) pairs. sdnn may be None. Rows with a
                 missing or non-positive rmssd are ignored.

    Returns:
        {"ceiling_ms", "ratio_max", "calibrated", "n"} -- the bounds to hand to
        rmssd_is_implausible(). Below _RMSSD_CALIBRATION_MIN_SAMPLES usable
        rows this returns UNCALIBRATED_RMSSD_BOUNDS, which reject only the
        physiologically impossible.

    The ratio bound is only computed from rows whose SDNN is itself plausible;
    a broken-low SDNN would inflate the ratio and teach the guard to accept
    genuinely bad RMSSD.
    """
    rmssd_vals = []
    ratios = []
    for pair in history:
        try:
            rmssd, sdnn = pair[0], pair[1]
        except (TypeError, IndexError):
            continue
        if rmssd is None:
            continue
        try:
            rmssd = float(rmssd)
        except (TypeError, ValueError):
            continue
        if rmssd <= 0:
            continue
        rmssd_vals.append(rmssd)
        if sdnn is not None:
            try:
                sdnn = float(sdnn)
            except (TypeError, ValueError):
                continue
            if sdnn >= _SDNN_PLAUSIBLE_FLOOR_MS:
                ratios.append(rmssd / sdnn)

    if len(rmssd_vals) < _RMSSD_CALIBRATION_MIN_SAMPLES:
        return dict(UNCALIBRATED_RMSSD_BOUNDS, n=len(rmssd_vals))

    ceiling = _percentile(rmssd_vals, 95) * _RMSSD_CEILING_P95_MULT
    ceiling = min(max(ceiling, _RMSSD_CEILING_FLOOR_MS), _RMSSD_CEILING_ABSOLUTE_MS)

    # The ratio needs its own sample count -- a user syncing RMSSD without SDNN
    # can clear the RMSSD threshold while having almost no ratio data.
    if len(ratios) >= _RMSSD_CALIBRATION_MIN_SAMPLES // 2:
        ratio_max = _percentile(ratios, 95) * _RMSSD_RATIO_P95_MULT
        ratio_max = min(max(ratio_max, _RMSSD_RATIO_FLOOR), _RMSSD_RATIO_ABSOLUTE)
    else:
        ratio_max = _RMSSD_RATIO_ABSOLUTE

    return {
        "ceiling_ms": round(ceiling, 1),
        "ratio_max": round(ratio_max, 2),
        "calibrated": True,
        "n": len(rmssd_vals),
    }


def rmssd_is_implausible(rmssd: float, sdnn, bounds: dict) -> tuple[bool, str]:
    """Judge one RMSSD reading against calibrated bounds.

    Returns (is_implausible, human_readable_reason). `sdnn` is the same-day
    SDNN if known, else None; the ratio cross-check is skipped when SDNN is
    absent or itself implausibly low.
    """
    ceiling = bounds.get("ceiling_ms", _RMSSD_CEILING_ABSOLUTE_MS)
    ratio_max = bounds.get("ratio_max", _RMSSD_RATIO_ABSOLUTE)
    tag = "personal" if bounds.get("calibrated") else "default"

    if rmssd > ceiling:
        return True, f"RMSSD {rmssd:.1f} ms exceeds {tag} ceiling {ceiling:.1f} ms"
    if sdnn is not None:
        try:
            sdnn = float(sdnn)
        except (TypeError, ValueError):
            return False, ""
        if sdnn >= _SDNN_PLAUSIBLE_FLOOR_MS and rmssd / sdnn > ratio_max:
            return True, (f"RMSSD/SDNN ratio {rmssd / sdnn:.1f} exceeds {tag} "
                          f"maximum {ratio_max:.1f} (artifact signature)")
    return False, ""
