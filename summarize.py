#!/usr/bin/env python3
"""
summarize.py — deterministic daily digest for LLM narration.

Produces a compact, factual summary of one day's flare context: the model's
input features, the windows they were computed over, and which scoring tier
each one lands in. Everything numeric is computed here, in Python, from the
database. Nothing is left for a language model to derive.

That split is the whole point. An LLM asked to reason over raw observation
rows will do arithmetic, and it will sometimes do it wrong and confidently.
Feed it this digest instead and its only job is to put the numbers into
sentences -- which is the part it is actually good at.

Read-only by construction: the database is opened with mode=ro, so this
cannot corrupt biotracking.db no matter what goes wrong.

Usage:
    python3 summarize.py                       # newest date in the default db
    python3 summarize.py --date 2026-07-01
    python3 summarize.py --db ~/backups/pi-biotracking/biotracking-2026-07-10.db
    python3 summarize.py --json                # machine-readable

The window functions come from scoring.py, which app.py also imports -- so the
digest and the app's own scores cannot drift apart. scoring.py is pure (no db,
no Flask), which is why it can be imported here without running migrations or
starting a scheduler the way `import app` would.
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta

from scoring import (
    UV_PROTECTION_MULTIPLIERS,
    _SYMPTOM_KEYS,
    _resp_rate_deviation_detail,
    _rmssd_deviation_detail,
    _rmssd_instability_detail,
    _symptom_burden_detail,
    weighted_uv,
)

DEFAULT_DB = os.path.expanduser("~/projects/private-track/biotracking.db")


# ============================================================
# TIER LOOKUP — thresholds from MODEL.md, reported not applied
# ============================================================
# These name which scoring band a value falls into. Deliberately no weights
# and no total: the app owns the score. The digest's job is to say "this
# feature is in its high band", not to recompute what /timeline already shows.

def _tier(value, bands):
    """bands: list of (threshold, label, comparison) in priority order."""
    if value is None:
        return None
    for thresh, label, cmp in bands:
        if (cmp == 'gte' and value >= thresh) or (cmp == 'lte' and value <= thresh):
            return label
    return None


TIERS = {
    'symptom_burden': [(3.0, 'HIGH (>=3.0)', 'gte'), (2.0, 'MID (>=2.0)', 'gte'),
                       (1.0, 'LOW (>=1.0)', 'gte')],
    'rmssd_deviation': [(-25.0, 'HIGH (<=-25%)', 'lte'), (-15.0, 'LOW (<=-15%)', 'lte')],
    'rmssd_instability': [(50.0, 'HIGH (>=50%)', 'gte'), (25.0, 'LOW (>=25%)', 'gte')],
    'resp_rate': [(15.0, 'HIGH (>=15%)', 'gte'), (10.0, 'LOW (>=10%)', 'gte')],
    'uv_dose': [(800.0, 'HIGH (>=800)', 'gte'), (400.0, 'MID (>=400)', 'gte')],
    'uv_cumulative': [(2500.0, 'HIGH (>=2500)', 'gte'), (1500.0, 'MID (>=1500)', 'gte')],
    'pain': [(7.0, 'HIGH (>=7)', 'gte'), (6.0, 'MID (>=6)', 'gte'),
             (5.0, 'LOW (>=5)', 'gte'), (4.0, 'MINIMAL (>=4)', 'gte')],
    'fatigue': [(7.0, 'HIGH (>=7)', 'gte'), (6.0, 'MID (>=6)', 'gte'),
                (5.0, 'LOW (>=5)', 'gte'), (4.0, 'MINIMAL (>=4)', 'gte')],
}


# ============================================================
# DATA ACCESS — read-only
# ============================================================

def load(db_path):
    if not os.path.exists(db_path):
        sys.exit(f"error: no database at {db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_observations(conn):
    rows = conn.execute("SELECT * FROM daily_observations ORDER BY date").fetchall()
    obs_by_date = {r['date']: dict(r) for r in rows}
    return obs_by_date


def fetch_uv(conn, location_key=None):
    if location_key is None:
        row = conn.execute(
            "SELECT location_key FROM uv_data GROUP BY location_key "
            "ORDER BY COUNT(*) DESC LIMIT 1").fetchone()
        location_key = row['location_key'] if row else None
    rows = conn.execute(
        "SELECT * FROM uv_data WHERE location_key = ?", (location_key,)).fetchall()
    return {r['date']: dict(r) for r in rows}, location_key


def uv_dose_for(date_str, obs_by_date, uv_by_date):
    """Same-day UV dose: (weighted_uv ** 1.5) * sun_minutes * protection."""
    uv_row = uv_by_date.get(date_str)
    obs = obs_by_date.get(date_str, {})
    w_uv = weighted_uv(uv_row)
    sun_min = float(obs.get('sun_exposure_min') or 0)
    protection = UV_PROTECTION_MULTIPLIERS.get(obs.get('uv_protection_level') or 'none', 1.0)
    return (w_uv ** 1.5) * sun_min * protection, w_uv, sun_min, protection


def cumulative_uv(date_str, obs_by_date, uv_by_date):
    """Mirrors app.py's _compute_cumulative_uv, with db.get_uv_data() swapped
    for the local dict. That one stays in app.py because it hits the database,
    so it is the single piece of scoring logic still duplicated here."""
    decay = [(1, 0.8), (2, 0.6), (3, 0.4), (4, 0.2)]
    target = datetime.strptime(date_str, "%Y-%m-%d").date()
    total = 0.0
    for offset, w in decay:
        d = (target - timedelta(days=offset)).isoformat()
        dose, _, _, _ = uv_dose_for(d, obs_by_date, uv_by_date)
        total += dose * w
    return total


def flare_history(conn, date_str):
    """Counts by severity in trailing windows, plus days since last flare."""
    out = {}
    for label, days in (('30d', 30), ('90d', 90)):
        rows = conn.execute(
            "SELECT COALESCE(flare_severity,'unspecified') AS sev, COUNT(*) AS n "
            "FROM daily_observations WHERE flare_occurred = 1 "
            "AND date <= ? AND date > date(?, ?) GROUP BY sev",
            (date_str, date_str, f'-{days} day')).fetchall()
        out[label] = {r['sev']: r['n'] for r in rows}

    last = conn.execute(
        "SELECT date, COALESCE(flare_severity,'unspecified') AS sev "
        "FROM daily_observations WHERE flare_occurred = 1 AND date <= ? "
        "ORDER BY date DESC LIMIT 1", (date_str,)).fetchone()
    if last:
        delta = (datetime.strptime(date_str, "%Y-%m-%d").date()
                 - datetime.strptime(last['date'], "%Y-%m-%d").date()).days
        out['last'] = {'date': last['date'], 'severity': last['sev'], 'days_ago': delta}
    return out


def recent_labs(conn, date_str, days=90, limit=8):
    rows = conn.execute(
        "SELECT date, test_name, numeric_value, unit, qualitative_result, "
        "reference_range, flag FROM lab_results "
        "WHERE date <= ? AND date > date(?, ?) "
        "AND flag IS NOT NULL AND flag != '' AND UPPER(flag) NOT IN ('N','NORMAL') "
        "ORDER BY date DESC LIMIT ?",
        (date_str, date_str, f'-{days} day', limit)).fetchall()
    return [dict(r) for r in rows]


def data_gaps(date_str, obs_by_date, uv_by_date, window=14):
    """What's missing in the trailing window. Stated plainly so the narrator
    can say 'I don't know' instead of quietly reasoning from absent data."""
    target = datetime.strptime(date_str, "%Y-%m-%d").date()
    gaps = []
    for field in ('hrv_rmssd', 'respiratory_rate', 'pain_scale', 'fatigue_scale'):
        missing = sum(
            1 for off in range(0, window)
            if (obs_by_date.get((target - timedelta(days=off)).isoformat()) or {}).get(field) is None
        )
        if missing:
            gaps.append(f"{field} missing {missing} of last {window} days")
    no_obs = sum(1 for off in range(0, window)
                 if (target - timedelta(days=off)).isoformat() not in obs_by_date)
    if no_obs:
        gaps.append(f"no observation row on {no_obs} of last {window} days")
    no_uv = sum(1 for off in range(0, 5)
                if (target - timedelta(days=off)).isoformat() not in uv_by_date)
    if no_uv:
        gaps.append(f"no UV row on {no_uv} of last 5 days")
    return gaps


# ============================================================
# DIGEST
# ============================================================

def build(conn, date_str, location_key=None):
    obs_by_date = fetch_observations(conn)
    uv_by_date, loc = fetch_uv(conn, location_key)
    today = obs_by_date.get(date_str)

    burden, burden_recent, burden_base = _symptom_burden_detail(date_str, obs_by_date)
    rdev, rdev_recent, rdev_base = _rmssd_deviation_detail(date_str, obs_by_date)
    rinst, rinst_recent, rinst_base = _rmssd_instability_detail(date_str, obs_by_date)
    resp, resp_recent, resp_base = _resp_rate_deviation_detail(date_str, obs_by_date)
    dose, w_uv, sun_min, protection = uv_dose_for(date_str, obs_by_date, uv_by_date)
    cum = cumulative_uv(date_str, obs_by_date, uv_by_date)

    active = [s for s in _SYMPTOM_KEYS if today and today.get(s)] if today else []

    span = conn.execute(
        "SELECT MIN(date) a, MAX(date) b, COUNT(*) n FROM daily_observations").fetchone()

    return {
        'date': date_str,
        'db_span': {'first': span['a'], 'last': span['b'], 'observations': span['n']},
        'uv_location': loc,
        'today': {
            'pain': today.get('pain_scale') if today else None,
            'pain_tier': _tier(today.get('pain_scale') if today else None, TIERS['pain']),
            'fatigue': today.get('fatigue_scale') if today else None,
            'fatigue_tier': _tier(today.get('fatigue_scale') if today else None, TIERS['fatigue']),
            'emotional_state': today.get('emotional_state') if today else None,
            'active_symptoms': active,
            'symptom_count': len(active),
            'hours_slept': today.get('hours_slept') if today else None,
            'steps': today.get('steps') if today else None,
            'resting_heart_rate': today.get('resting_heart_rate') if today else None,
            'flare_occurred': bool(today.get('flare_occurred')) if today else None,
            'flare_severity': today.get('flare_severity') if today else None,
        } if today else None,
        'symptom_burden': {
            'recent_3d_mean': round(burden_recent, 2) if burden_recent is not None else None,
            'baseline_14d_mean': round(burden_base, 2) if burden_base is not None else None,
            'delta': burden, 'tier': _tier(burden, TIERS['symptom_burden'])},
        'rmssd_deviation': {
            'recent_7d_ms': round(rdev_recent, 1) if rdev_recent is not None else None,
            'baseline_30d_ms': round(rdev_base, 1) if rdev_base is not None else None,
            'deviation_pct': rdev, 'tier': _tier(rdev, TIERS['rmssd_deviation'])},
        'rmssd_instability': {
            'recent_mean_abs_delta_ms': round(rinst_recent, 1) if rinst_recent is not None else None,
            'baseline_mean_abs_delta_ms': round(rinst_base, 1) if rinst_base is not None else None,
            'deviation_pct': rinst, 'tier': _tier(rinst, TIERS['rmssd_instability'])},
        'respiratory_rate': {
            'recent_3d': round(resp_recent, 1) if resp_recent is not None else None,
            'baseline_14d': round(resp_base, 1) if resp_base is not None else None,
            'deviation_pct': resp, 'tier': _tier(resp, TIERS['resp_rate'])},
        'uv': {
            'weighted_index': round(w_uv, 2), 'sun_minutes': sun_min,
            'protection_multiplier': protection,
            'dose': round(dose, 1), 'dose_tier': _tier(dose, TIERS['uv_dose']),
            'cumulative_4d': round(cum, 1),
            'cumulative_tier': _tier(cum, TIERS['uv_cumulative'])},
        'flare_history': flare_history(conn, date_str),
        'recent_abnormal_labs': recent_labs(conn, date_str),
        'data_gaps': data_gaps(date_str, obs_by_date, uv_by_date),
    }


def render(d):
    L = []
    n = lambda v, unit='': '--' if v is None else f"{v}{unit}"
    tier = lambda t: f"  -> {t}" if t else ""

    L.append(f"FLARE CONTEXT DIGEST -- {d['date']}")
    s = d['db_span']
    L.append(f"source: {s['observations']} observations, {s['first']} to {s['last']}"
             f" | uv location: {d['uv_location']}")
    L.append("")

    t = d['today']
    if t:
        L.append("TODAY")
        L.append(f"  pain {n(t['pain'])}{tier(t['pain_tier'])}")
        L.append(f"  fatigue {n(t['fatigue'])}{tier(t['fatigue_tier'])}")
        L.append(f"  emotional state {n(t['emotional_state'])}"
                 f"{'  -> LOW (<=4)' if t['emotional_state'] is not None and t['emotional_state'] <= 4 else ''}")
        L.append(f"  active symptoms ({t['symptom_count']}/9): "
                 f"{', '.join(t['active_symptoms']) if t['active_symptoms'] else 'none'}")
        L.append(f"  sleep {n(t['hours_slept'],' h')} | steps {n(t['steps'])} "
                 f"| resting HR {n(t['resting_heart_rate'])}")
        if t['flare_occurred']:
            L.append(f"  ** FLARE LOGGED THIS DAY: {t['flare_severity'] or 'unspecified'} **")
    else:
        L.append("TODAY\n  no observation row for this date")
    L.append("")

    b = d['symptom_burden']
    L.append("SYMPTOM BURDEN DELTA  [strongest predictor per MODEL.md]")
    L.append(f"  recent 3d mean {n(b['recent_3d_mean'])} | baseline 14d mean {n(b['baseline_14d_mean'])}"
             f" | delta {n(b['delta'])}{tier(b['tier'])}")
    L.append("")

    r = d['rmssd_deviation']
    i = d['rmssd_instability']
    L.append("AUTONOMIC (RMSSD)")
    L.append(f"  level: recent 7d {n(r['recent_7d_ms'],' ms')} | baseline 30d {n(r['baseline_30d_ms'],' ms')}"
             f" | {n(r['deviation_pct'],'%')}{tier(r['tier'])}")
    L.append(f"  instability: recent {n(i['recent_mean_abs_delta_ms'],' ms')} | baseline "
             f"{n(i['baseline_mean_abs_delta_ms'],' ms')} | {n(i['deviation_pct'],'%')}{tier(i['tier'])}")
    L.append("")

    rr = d['respiratory_rate']
    L.append("RESPIRATORY RATE")
    L.append(f"  recent 3d {n(rr['recent_3d'])} | baseline 14d {n(rr['baseline_14d'])}"
             f" | {n(rr['deviation_pct'],'%')}{tier(rr['tier'])}")
    L.append("")

    u = d['uv']
    L.append("UV")
    L.append(f"  today: weighted index {u['weighted_index']} x {u['sun_minutes']} min "
             f"x protection {u['protection_multiplier']} = dose {u['dose']}{tier(u['dose_tier'])}")
    L.append(f"  4-day cumulative (decay-weighted): {u['cumulative_4d']}{tier(u['cumulative_tier'])}")
    L.append("")

    f = d['flare_history']
    L.append("FLARE HISTORY")
    if f.get('last'):
        l = f['last']
        L.append(f"  last flare {l['date']} ({l['severity']}), {l['days_ago']} days ago")
    else:
        L.append("  no prior flare on record")
    for label in ('30d', '90d'):
        counts = f.get(label, {})
        total = sum(counts.values())
        detail = ', '.join(f"{v} {k}" for k, v in sorted(counts.items())) or 'none'
        L.append(f"  last {label}: {total} flare-days ({detail})")
    L.append("")

    labs = d['recent_abnormal_labs']
    if labs:
        L.append("ABNORMAL LABS (last 90d)")
        for lab in labs:
            val = lab['numeric_value'] if lab['numeric_value'] is not None else lab['qualitative_result']
            L.append(f"  {lab['date']}  {lab['test_name']}: {val} {lab['unit'] or ''}"
                     f" [{lab['flag']}] ref {lab['reference_range'] or '--'}")
        L.append("")

    if d['data_gaps']:
        L.append("DATA GAPS -- do not infer across these")
        for g in d['data_gaps']:
            L.append(f"  {g}")
        L.append("")

    return "\n".join(L)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--db', default=DEFAULT_DB, help='path to biotracking.db')
    p.add_argument('--date', help='YYYY-MM-DD (default: newest date in db)')
    p.add_argument('--location', help='uv_data location_key (default: most common)')
    p.add_argument('--json', action='store_true', help='emit JSON instead of text')
    args = p.parse_args()

    conn = load(os.path.expanduser(args.db))
    date_str = args.date
    if not date_str:
        row = conn.execute("SELECT MAX(date) AS d FROM daily_observations").fetchone()
        date_str = row['d']
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        sys.exit(f"error: bad date {date_str!r}, expected YYYY-MM-DD")

    digest = build(conn, date_str, args.location)
    print(json.dumps(digest, indent=2) if args.json else render(digest))


if __name__ == '__main__':
    main()
