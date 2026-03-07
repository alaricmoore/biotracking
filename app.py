"""
biotracking app.py
------------------
Flask routes only. No database logic, no API calls.
All data access goes through db.py.
All UV fetching goes through uv_fetcher.py.

Run with:
    python app.py

Access locally:    http://localhost:5000
Access from phone: http://<your-mac-ip>:5000
"""

import calendar
import json
import os
from datetime import date, datetime, timedelta

from flask import Flask, jsonify, render_template, request, redirect, url_for, Response

import db
import uv_fetcher
import zipfile
import shutil
from pathlib import Path
from flask import send_file

from typing import Optional, Dict, List, Any
from collections import Counter

from apscheduler.schedulers.background import BackgroundScheduler


app = Flask(__name__)

import os
import json

# ============================================================
# LAB ADJUSTMENTS
# ============================================================

# Default symptom weights (factory settings)
DEFAULT_WEIGHTS = {
    'neurological': 1.5,
    'cognitive': 1.0,
    'musculature': 1.5,
    'migraine': 1.0,
    'pulmonary': 1.0,
    'dermatological': 0.75,
    'mucosal': 0.25,
    'rheumatic': 0.5,
    'cycle_phase': 1.0,
}

# Path to custom weights config
CUSTOM_WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), 'config', 'custom_weights.json')

def get_current_weights():
    """
    Load weights from config file if exists, otherwise return defaults.
    """
    if os.path.exists(CUSTOM_WEIGHTS_PATH):
        try:
            with open(CUSTOM_WEIGHTS_PATH, 'r') as f:
                custom = json.load(f)
                # Merge with defaults in case new symptoms added
                weights = DEFAULT_WEIGHTS.copy()
                weights.update(custom)
                return weights
        except Exception as e:
            print(f"Error loading custom weights: {e}")
            return DEFAULT_WEIGHTS.copy()
    return DEFAULT_WEIGHTS.copy()

def save_custom_weights(weights):
    """
    Save custom weights to config file.
    """
    # Create config directory if it doesn't exist
    config_dir = os.path.dirname(CUSTOM_WEIGHTS_PATH)
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    
    # Save weights
    with open(CUSTOM_WEIGHTS_PATH, 'w') as f:
        json.dump(weights, f, indent=2)

def reset_to_default_weights():
    """
    Delete custom weights config to revert to defaults.
    """
    if os.path.exists(CUSTOM_WEIGHTS_PATH):
        os.remove(CUSTOM_WEIGHTS_PATH)
        
def calculate_flare_score_with_weights(obs, weights):
    """Calculate score using custom symptom weights."""
    score = 0.0

    # UV, overexertion, temp - unchanged from calculate_flare_prime_score
    sun_min = obs.get('sun_exposure_min') or 0
    if sun_min >= 100:
        score += 3
    elif sun_min >= 70:
        score += 1.25

    # Apply custom weights
    for symptom, weight in weights.items():
        if symptom == 'cycle_phase':
            if obs.get('cycle_in_high_risk_phase'):
                score += weight
        else:
            score += obs.get(symptom, 0) * weight

    return score
    

# ============================================================
# FORECAST LAB MANUAL TEXT
# ============================================================

FORECAST_LAB_MANUAL ="""╔═══════════════════════════════════════════════════════════════════════════╗
║                    FLARE PREDICTION MODEL — USER MANUAL                   ║
╚═══════════════════════════════════════════════════════════════════════════╝

WHAT THIS IS
────────────
A transparent, statistical model for predicting lupus flare risk based on 
daily observations. Unlike black-box AI, you can see exactly how it works 
and tune it yourself.

CURRENT WEIGHTS (as of 2026-03-05)
───────────────────────────────────
These weights were adjusted based on accuracy analysis:

  Symptom Weights:
  • Neurological: 1.5 (numbness, tingling, vision changes)
  • Cognitive: 1.0 (brain fog, memory, word recall)
  • Musculature: 1.5 (muscle pain, cramping, weakness)
  • Migraine: 1.0 (headaches, light sensitivity)
  • Pulmonary: 1.0 (air hunger, chest discomfort)
  • Dermatological: 0.75 (rash, photosensitivity)
  • Mucosal: 0.25 (dry mouth, dry eyes)
  • Rheumatic (base): 0.5 (joint pain without specificity)
    └─ Major joints: 2.0 (hip, knee, shoulder, elbow, ankle, wrist, jaw)
    └─ Minor joints: 1.0 (finger, toe, hand)

  Environmental Factors:
  • High UV (100+ min): 3.0
  • Moderate UV (70-99 min): 1.25
  • High temperature (0.8°F+): 3.0
  • Moderate temperature (0.5-0.8°F): 2.0
  • Mild temperature (0.3-0.5°F): 1.0

  Physical Load:
  • Severe overexertion (2000+ steps/hr slept): 2.0
  • Moderate overexertion (1500-2000 steps/hr slept): 1.5

  Other:
  • Severe fatigue (7+): 3.0
  • Moderate fatigue (5-7): 1.0
  • Mild fatigue (3-5): 0.5
  • High pain (7+): 1.0
  • Low emotional state (≤4): 2.0

  Threshold: 8.0 points = flare risk
  (Lowered from 10.0 to improve recall from 20.9% to 65.7%)

WHY THESE WEIGHTS
─────────────────
Analysis of 60 days of data with known flare outcomes showed:
  - Neurological symptoms appeared in 51 missed flares
  - Cognitive symptoms appeared in 34 missed flares  
  - Musculature symptoms appeared in 44 missed flares

Weights were increased to catch more true flares (recall) while maintaining
accuracy. Current model: 85.8% accuracy, 65.7% recall, 79.2% precision.

UV LAG ANALYSIS — HOW IT WORKS
───────────────────────────────
UV exposure doesn't cause immediate flares. The effect is delayed.

The model tests different lag periods:
  • Same-day UV (no lag)
  • 24-hour lag (yesterday's UV affects today)
  • 48-hour lag (UV from 2 days ago)
  • 72-hour lag (UV from 3 days ago)

For each lag period, it:
  1. Pairs UV data with flare days
  2. Runs statistical tests (t-test, Cohen's d)
  3. Measures correlation strength
  4. Requires 30+ days of data for reliability

Currently, 24-hour lag shows the strongest correlation for this dataset.

Plain English: If you get too much sun today, you're more likely to feel it
tomorrow. The model learns your specific lag pattern from your own data.

USING THE LAB
─────────────
Commands:
  [1] weights   — View current symptom weights
  [2] adjust    — Adjust weights with sliders
  [3] simulate  — Run simulation to see how changes affect accuracy
  [4] code      — View the actual Python calculation code
  [6] achievements — See your tuning achievements
  [?] help      — Show this manual
  [X] exit      — Return to forecast page

Workflow:
  1. Adjust weights using sliders
  2. Run simulation to see impact on accuracy/recall/precision
  3. Review which predictions would flip
  4. Apply changes (currently manual — copy weights to app.py)

The goal is to balance:
  • Accuracy: Overall correctness
  • Recall: Catching actual flares (minimize false negatives)
  • Precision: Avoiding false alarms (minimize false positives)

APPLYING CHANGES
________________

## Step 1: Create the config directory

In your biotracking project root, create:
```
biotracking/
  ├── app.py
  ├── db.py
  ├── templates/
  ├── config/          ← CREATE THIS DIRECTORY
  │   └── .gitkeep     ← CREATE THIS EMPTY FILE (optional, keeps folder in git)
  └── ...
```

Run this from your project root:
```bash
mkdir -p config
touch config/.gitkeep
```

## Step 2: Update .gitignore

Add this line to your `.gitignore`:
```
config/custom_weights.json
```

This ensures your personal model tuning stays private.

## Step 4: Test the system

1. Restart Flask
2. Go to `/forecast/lab`
3. You should see "✓ Using factory defaults" at the top
4. Type `2` to adjust weights
5. Change a weight, run simulation
6. Click "✓ Apply These Changes"
7. Confirm the dialog
8. Page should reload showing "⚠ Custom weights active"
9. Check that `config/custom_weights.json` was created
10. Click "Reset to Defaults" to test reset functionality

## How it works:

**Before custom weights:**
- `calculate_flare_prime_score()` uses hardcoded DEFAULT_WEIGHTS
- No config file exists
- Lab shows "✓ Using factory defaults"

**After applying custom weights:**
- Lab saves to `config/custom_weights.json`
- `calculate_flare_prime_score()` loads from config via `get_current_weights()`
- All predictions use custom weights
- Lab shows "⚠ Custom weights active"

**After reset:**
- `config/custom_weights.json` is deleted
- Back to factory defaults
- Lab shows "✓ Using factory defaults"

## File contents example:

`config/custom_weights.json` after customization:
```json
{
  "neurological": 2.0,
  "cognitive": 1.25,
  "musculature": 1.75,
  "migraine": 1.0,
  "pulmonary": 1.0,
  "dermatological": 0.75,
  "mucosal": 0.25,
  "rheumatic": 0.5
}
```

## Troubleshooting:

**"Permission denied" error when applying:**
- Check that `config/` directory exists and is writable
- Run: `chmod 755 config/`

**Weights not taking effect:**
- Restart Flask after applying changes
- Check Flask console for error messages
- Verify `config/custom_weights.json` exists and is valid JSON

**Want to manually edit weights:**
- Edit `config/custom_weights.json` directly
- Restart Flask
- Changes will take effect immediately

## Safety notes:

- Custom weights are stored locally, never committed to git
- Original defaults are always preserved in code
- Reset button deletes custom config instantly
- Each user's biotracking instance has independent weights

REMOTE ACCESS (RASPBERRY PI + TAILSCALE)
─────────────────────────────────────────
If you want to access biotracking from your phone while away from home:

Setup Overview:
  Phone/Laptop (anywhere)
       ↓ (Tailscale encrypted tunnel)
  Oracle Cloud VM (public IP, exit node)
       ↓ (Tailscale encrypted tunnel)  
  Raspberry Pi (your home, running biotracking)
       ↓ (localhost)
  SQLite database (never leaves the Pi)

Why this works:
  • Starlink uses CGNAT — no static public IP, can't port forward
  • Tailscale creates encrypted mesh network between devices
  • Oracle VM provides stable public IP as exit node
  • Database stays on Pi, Oracle VM only sees encrypted traffic

Quick Setup:
  1. Install biotracking on Raspberry Pi (see README)
  2. Install Tailscale on Pi: curl -fsSL https://tailscale.com/install.sh | sh
  3. Create Oracle Cloud free tier VM
  4. Install Tailscale on VM
  5. Configure nginx reverse proxy on VM
  6. Open Oracle firewall (ports 80/443)
  7. Add HTTPS with Let's Encrypt (recommended)
  8. Add basic auth to nginx (required for security)

Full instructions: See REMOTE_ACCESS.md in the repository

Security Notes:
  ⚠ Always use HTTPS (Let's Encrypt is free)
  ⚠ Always use authentication (nginx basic auth minimum)
  ⚠ Keep software updated on Oracle VM
  ⚠ Review Tailscale ACLs to restrict access
  ⚠ Understand: anything on the internet has risk

The most secure setup is local-only. Remote access is a trade-off.
If you're in an unsafe situation, local-only may be the right choice.

MORE INFORMATION
────────────────
  • Full setup instructions: README.md
  • Contributing guide: CONTRIBUTING.md
  • Remote access details: REMOTE_ACCESS.md
  • Repository: github.com/alaricmoore/biotracking
  • Contact: alaric.moore@pm.me

This is a one-person project maintained between doctor appointments.
Response times may vary.

Take care of yourself out there.

────────────────────────────────────────────────────────────────────────────
Press any key to return to main menu
"""


# ============================================================
# Config loading
# ============================================================

def load_config() -> dict:
    """Load local config. Exits cleanly if setup hasn't been run."""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if not os.path.exists(config_path):
        print("ERROR: config.json not found. Run setup.py first.")
        raise SystemExit(1)
    with open(config_path) as f:
        return json.load(f)


CONFIG = load_config()


# ============================================================
# Medication reminder notifications (ntfy)
# ============================================================

def _send_ntfy(message: str) -> None:
    """Send a push notification via ntfy.sh (or self-hosted ntfy server)."""
    import requests as _requests
    topic = CONFIG.get("ntfy_topic")
    server = CONFIG.get("ntfy_server", "https://ntfy.sh")
    if not topic:
        return
    try:
        _requests.post(
            f"{server}/{topic}",
            data=message.encode("utf-8"),
            headers={
                "Title": "Medication Reminder",
                "Priority": "high",
                "Tags": "pill",
            },
            timeout=5,
        )
    except Exception as e:
        print(f"[reminder] ntfy send failed: {e}")


def _send_ntfy_alert(message: str, title: str, priority: str = "default", tags: str = "warning") -> None:
    """Send a push notification with custom title, priority, and tags."""
    import requests as _requests
    topic = CONFIG.get("ntfy_topic")
    server = CONFIG.get("ntfy_server", "https://ntfy.sh")
    if not topic:
        return
    try:
        _requests.post(
            f"{server}/{topic}",
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": tags,
            },
            timeout=5,
        )
    except Exception as e:
        print(f"[flare-alert] ntfy send failed: {e}")


FLARE_ALERT_STATE_PATH = os.path.join(os.path.dirname(__file__), "config", "flare_alert_state.json")


def _check_flare_risk_alert() -> None:
    """Daily cron job: send ntfy flare warning when risk is elevated or cycle phase is changing."""
    if not CONFIG.get("ntfy_topic"):
        return

    today_str = date.today().isoformat()

    # Rate limit: only one alert per calendar day
    if os.path.exists(FLARE_ALERT_STATE_PATH):
        try:
            with open(FLARE_ALERT_STATE_PATH) as f:
                state = json.load(f)
            if state.get("last_alert_date") == today_str:
                return
        except Exception:
            pass

    # Load observations and inject cycle phase
    all_obs = db.get_all_daily_observations()
    if not all_obs or len(all_obs) < 3:
        return
    all_obs.sort(key=lambda x: x["date"], reverse=True)
    _inject_cycle_phase(all_obs)

    # 3-day weighted average score
    scores = [calculate_flare_prime_score(obs) for obs in all_obs[:3]]
    w3 = [1.0, 0.75, 0.5]
    weighted_score = sum(s * w for s, w in zip(scores, w3)) / sum(w3)

    # Tomorrow's cycle phase (forward-looking)
    tomorrow_str = (date.today() + timedelta(days=1)).isoformat()
    phase_by_date = _compute_phase_by_date_from_obs(all_obs)
    tomorrow_phase = phase_by_date.get(tomorrow_str)
    entering_high_risk_tomorrow = tomorrow_phase in ("pms", "luteal")
    today_phase = all_obs[0].get("cycle_phase_name") if all_obs else None

    MODERATE_THRESHOLD = 5.0
    HIGH_THRESHOLD = 8.0

    should_alert = weighted_score >= MODERATE_THRESHOLD or entering_high_risk_tomorrow
    if not should_alert:
        return

    # Build message body
    risk_info = get_risk_level(weighted_score)
    risk_label = risk_info["level"]

    factors = get_contributing_factors(all_obs[0])
    top_factors = ", ".join(f["name"] for f in factors[:3]) if factors else ""

    lines = [f"Score: {weighted_score:.1f}  |  {risk_label}"]
    if top_factors:
        lines.append(f"Factors: {top_factors}")
    if entering_high_risk_tomorrow and today_phase not in ("pms", "luteal"):
        lines.append(f"Entering {tomorrow_phase} phase tomorrow.")
    elif today_phase in ("pms", "luteal"):
        lines.append(f"Currently in {today_phase} phase.")

    message = "\n".join(lines)
    priority = "high" if weighted_score >= HIGH_THRESHOLD else "default"
    tags = "rotating_light" if weighted_score >= HIGH_THRESHOLD else "warning"

    _send_ntfy_alert(message, title=f"Flare risk: {risk_label}", priority=priority, tags=tags)

    # Persist state so we don't double-alert today
    try:
        os.makedirs(os.path.dirname(FLARE_ALERT_STATE_PATH), exist_ok=True)
        with open(FLARE_ALERT_STATE_PATH, "w") as f:
            json.dump({"last_alert_date": today_str, "last_score": round(weighted_score, 1)}, f)
    except Exception as e:
        print(f"[flare-alert] state save failed: {e}")


def _check_and_send_reminders() -> None:
    """Background job: send ntfy notifications for doses due in the next minute."""
    now = datetime.now()
    window_end = now + timedelta(minutes=1)
    try:
        pending = db.get_pending_doses(
            now.strftime("%Y-%m-%d %H:%M"),
            window_end.strftime("%Y-%m-%d %H:%M"),
        )
        for dose in pending:
            _send_ntfy(dose["dose_label"])
            db.mark_dose_notified(dose["id"])
    except Exception as e:
        print(f"[reminder] scheduler error: {e}")


# Start scheduler — guard against Flask debug-mode double-start
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    _tz = CONFIG.get("timezone", "UTC")
    _scheduler = BackgroundScheduler(timezone=_tz)
    _scheduler.add_job(_check_and_send_reminders, "interval", minutes=1)
    _alert_hour = CONFIG.get("flare_alert_hour", 8)
    _scheduler.add_job(_check_flare_risk_alert, "cron", hour=_alert_hour, minute=0)
    _scheduler.start()


# ============================================================
# Template context - available in every template
# ============================================================

@app.context_processor
def inject_globals():
    """Inject values available in every template."""
    return {
        "patient_name": CONFIG.get("patient_name", ""),
        "today": date.today().isoformat(),
        "app_version": CONFIG.get("app_version", "2.0.0"),
        "track_cycle": CONFIG.get("track_cycle", False),
    }


# ============================================================
# Index
# ============================================================

@app.route("/")
def index():
    """Home page - redirects to daily entry for today."""
    return redirect(url_for("daily_entry"))


# ============================================================
# Daily entry
# ============================================================

@app.route("/daily", methods=["GET"])
def daily_entry():
    """Daily entry form with date navigation. Defaults to today."""
    # Get date from query param or use today
    date_param = request.args.get("date")
    if date_param:
        try:
            entry_date = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            entry_date = date.today()
    else:
        entry_date = date.today()
    
    entry_date_str = entry_date.isoformat()
    
    # Calculate prev/next dates
    prev_date = (entry_date - timedelta(days=1)).isoformat()
    next_date = (entry_date + timedelta(days=1)).isoformat()
    is_today = (entry_date == date.today())
    
    # Auto-fetch and store UV for this date if not already present
    uv = uv_fetcher.fetch_and_store_uv_for_date(entry_date_str)
    
    # Load any existing entry for this date
    existing = db.get_daily_observations(entry_date_str)
    
    # Load active medications for the sidebar
    active_meds = db.get_active_medications()

    # Load today's scheduled doses for the reminder checklist
    todays_doses = db.get_todays_doses(entry_date_str)

    quick_mode = request.args.get("mode") == "quick"

    return render_template(
        "daily_entry.html",
        entry_date=entry_date_str,
        existing=existing,
        uv=uv,
        active_meds=active_meds,
        todays_doses=todays_doses,
        prev_date=prev_date,
        next_date=next_date,
        is_today=is_today,
        quick_mode=quick_mode,
    )


@app.route("/daily", methods=["POST"])
def daily_entry_submit():
    """Handle daily entry form submission."""
    form = request.form

    def get_bool(key):
        return 1 if form.get(key) == "on" else 0

    def get_float(key, default=None):
        val = form.get(key, "").strip()
        try:
            return float(val) if val else default
        except ValueError:
            return default

    data = {
        "date": form.get("date", date.today().isoformat()),
        "steps": get_float("steps"),
        "hours_slept": get_float("hours_slept"),
        "hrv": get_float("hrv"),
        "basal_temp_delta": get_float("basal_temp_delta"),
        "sun_exposure_min": get_float("sun_exposure_min"),
        "pain_scale": get_float("pain_scale"),
        "fatigue_scale": get_float("fatigue_scale"),
        "emotional_state": get_float("emotional_state"),
        "emotional_notes": form.get("emotional_notes", "").strip() or None,
        "neurological": get_bool("neurological"),
        "neuro_notes": form.get("neuro_notes", "").strip() or None,
        "cognitive": get_bool("cognitive"),
        "cognitive_notes": form.get("cognitive_notes", "").strip() or None,
        "musculature": get_bool("musculature"),
        "musculature_notes": form.get("musculature_notes", "").strip() or None,
        "migraine": get_bool("migraine"),
        "migraine_notes": form.get("migraine_notes", "").strip() or None,
        "pulmonary": get_bool("pulmonary"),
        "pulmonary_notes": form.get("pulmonary_notes", "").strip() or None,
        "gastro": get_bool("gastro"),
        "gastro_notes": form.get("gastro_notes", "").strip() or None,
        "mucosal": get_bool("mucosal"),
        "mucosal_notes": form.get("mucosal_notes", "").strip() or None,
        "dermatological": get_bool("dermatological"),
        "derm_notes": form.get("derm_notes", "").strip() or None,
        "rheumatic": get_bool("rheumatic"),
        "rheumatic_notes": form.get("rheumatic_notes", "").strip() or None,
        "strike_physical": get_bool("strike_physical"),
        "strike_environmental": get_bool("strike_environmental"),
        "flare_occurred": get_bool("flare_occurred"),
        "notes": form.get("notes", "").strip() or None,
        "period_flow": form.get("period_flow") or None,
        "cramping": form.get("cramping") or None,
        "cycle_notes": form.get("cycle_notes", "").strip() or None,
    }

    db.upsert_daily_observations(data)
    return redirect(url_for("daily_confirm", entry_date=data["date"]))


@app.route("/daily/confirm/<entry_date>")
def daily_confirm(entry_date):
    """Confirmation screen after daily entry submission."""
    entry = db.get_daily_observations(entry_date)
    uv = db.get_uv_data(entry_date)
    return render_template("daily_confirm.html", entry=entry, uv=uv)


# ============================================================
# Timeline
# ============================================================

@app.route("/timeline")
def timeline():
    """Timeline view - defaults to last 90 days."""
    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=90)).isoformat()

    # Allow URL params to override range
    if request.args.get("start"):
        start_date = request.args.get("start")
    if request.args.get("end"):
        end_date = request.args.get("end")

    data = db.get_timeline_data(start_date, end_date)
    
    # Get primary intervention info
    all_meds = db.get_all_medications()
    primary_med = next((m for m in all_meds if m.get("is_primary_intervention") == 1), None)
    
    intervention_date = None
    intervention_name = None
    if primary_med:
        intervention_date = primary_med["start_date"]
        intervention_name = primary_med["drug_name"]
        
    # Get secondary interventions 
    secondary_interventions = [
        {
            "drug_name": m["drug_name"],
            "start_date": m["start_date"]
        }
        for m in all_meds
        if m.get("is_secondary_intervention") == 1
    ]
    
    # Extract flare days from daily observations
    flare_days = [
        obs["date"] 
        for obs in data.get("daily", []) 
        if obs.get("flare_occurred") == 1
    ]  

    day_count = len(data.get("daily", []))

    return render_template(
        "timeline.html",
        start_date=start_date,
        end_date=end_date,
        timeline_json=json.dumps(data, default=str),
        intervention_date=intervention_date,
        intervention_name=intervention_name,
        secondary_interventions_json=json.dumps(secondary_interventions),
        flare_days_json=json.dumps(flare_days),
        day_count=day_count,      
    )

 


# ============================================================
# UV lag analysis
# ============================================================

def compute_lag_correlations(observations: list, uv_data: list) -> dict:
    """Compute Pearson correlation between UV dose and each symptom
    at lag windows of 0, 1, 2, and 3 days.

    UV dose = (UV index^1.5) × sun exposure minutes
    UV dose on day D is correlated against symptom on day D+lag.
    Exponential weighting reflects that high UV is disproportionately more damaging.
    
    A high correlation at lag=2 means UV exposure predicts
    that symptom two days later.

    Args:
        observations: list of daily_observation dicts (must include sun_exposure_min)
        uv_data: list of uv_data dicts (includes uv_noon)

    Returns:
        dict of {symptom_name: {lag_0: {...}, lag_1: {...}, ...}}
        Each lag contains: r, p, n, significant
    """
    import numpy as np
    from scipy import stats

    # Build date-indexed lookups
    obs_by_date = {o["date"]: o for o in observations}
    uv_by_date  = {u["date"]: u for u in uv_data}

    # Sorted date list that has UV, observation, AND sun exposure data
    dates_with_all = sorted([
        d for d in obs_by_date
        if d in uv_by_date 
        and uv_by_date[d].get("uv_noon") is not None
        and obs_by_date[d].get("sun_exposure_min") is not None
    ])

    if len(dates_with_all) < 10:
        return {}

    # Symptom targets - continuous scales and boolean flags
    targets = {
        "pain":          lambda o: o.get("pain_scale"),
        "fatigue":       lambda o: o.get("fatigue_scale"),
        "neurological":  lambda o: o.get("neurological"),
        "musculature":   lambda o: o.get("musculature"),
        "migraine":      lambda o: o.get("migraine"),
        "cognitive":     lambda o: o.get("cognitive"),
        "dermatological":lambda o: o.get("dermatological"),
        "pulmonary":     lambda o: o.get("pulmonary"),
        "rheumatic":     lambda o: o.get("rheumatic"),
        "gastro":        lambda o: o.get("gastro"),
        "mucosal":       lambda o: o.get("mucosal"),
        "flare":         lambda o: o.get("flare_occurred"),
    }

    lag_days = [0, 1, 2, 3]
    results = {}

    for symptom_name, getter in targets.items():
        results[symptom_name] = {}

        for lag in lag_days:
            uv_doses = []
            sym_vals = []

            for i, date_str in enumerate(dates_with_all):
                # UV dose on this date = UV index × minutes exposed
                uv_noon = uv_by_date[date_str].get("uv_noon")
                sun_min = obs_by_date[date_str].get("sun_exposure_min")
                
                if uv_noon is None or sun_min is None:
                    continue
                
                uv_dose = (float(uv_noon) ** 1.5) * float(sun_min)

                # Find the date lag days later
                lag_date = (
                    datetime.strptime(date_str, "%Y-%m-%d") +
                    timedelta(days=lag)
                ).strftime("%Y-%m-%d")

                lag_obs = obs_by_date.get(lag_date)
                if lag_obs is None:
                    continue

                sym_val = getter(lag_obs)
                if sym_val is None:
                    continue

                uv_doses.append(uv_dose)
                sym_vals.append(float(sym_val))

            # Need at least 8 paired observations for meaningful correlation
            if len(uv_doses) < 8:
                results[symptom_name][f"lag_{lag}"] = None
                continue

            uv_arr  = np.array(uv_doses)
            sym_arr = np.array(sym_vals)

            # Skip if no variance (all zeros e.g. rare symptom or always indoors)
            if uv_arr.std() == 0 or sym_arr.std() == 0:
                results[symptom_name][f"lag_{lag}"] = None
                continue

            r, p_value = stats.pearsonr(uv_arr, sym_arr)
            
            # Very strict significance for multiple comparisons (9 symptoms × 4 lags = 36 tests)
            # p < 0.0005 and |r| >= 0.35 (medium-to-large effect size)
            results[symptom_name][f"lag_{lag}"] = {
                "r":       round(float(r), 3),
                "p":       round(float(p_value), 4),
                "n":       len(uv_doses),
                "significant": float(p_value) < 0.0005 and abs(float(r)) >= 0.35,
            }

    return results

@app.route("/uv-lag")
def uv_lag():
    """UV lag correlation analysis view."""
    observations = db.get_all_daily_observations()
    if not observations:
        return render_template("uv_lag.html", has_data=False)

    start_date = observations[0]["date"]
    end_date   = observations[-1]["date"]
    uv_data    = db.get_uv_data_range(start_date, end_date)

    if not uv_data:
        return render_template("uv_lag.html", has_data=False,
                               no_uv_message=True)

    correlations = compute_lag_correlations(observations, uv_data)

    return render_template(
        "uv_lag.html",
        has_data=True,
        correlations_json=json.dumps(correlations, default=lambda x: int(x) if isinstance(x, bool) else str(x)),
        n_observations=len(observations),
        n_uv_days=len(uv_data),
        start_date=start_date,
        end_date=end_date,
    )


# ============================================================
# HRV and autonomic
# ============================================================


def compute_hrv_data(observations: list, intervention_date: str = None) -> dict:
    """Compute HRV trend with 7-day rolling average and intervention split."""
    import numpy as np

    hrv_obs = [o for o in observations if o.get("hrv") is not None]
    if not hrv_obs:
        return {}

    dates    = [o["date"] for o in hrv_obs]
    hrv_vals = [float(o["hrv"]) for o in hrv_obs]
    fatigue  = [o.get("fatigue_scale") for o in hrv_obs]
    pain     = [o.get("pain_scale") for o in hrv_obs]

    rolling = []
    for i in range(len(hrv_vals)):
        window = hrv_vals[max(0, i - 6): i + 1]
        rolling.append(round(sum(window) / len(window), 2) if len(window) >= 3 else None)

    # Split stats only if intervention date is provided
    pre_vals  = []
    post_vals = []
    if intervention_date:
        pre_vals  = [v for d, v in zip(dates, hrv_vals) if d < intervention_date]
        post_vals = [v for d, v in zip(dates, hrv_vals) if d >= intervention_date]

    def stats_dict(vals):
        if not vals:
            return {"mean": None, "std": None, "n": 0}
        arr = np.array(vals)
        return {"mean": round(float(arr.mean()), 2),
                "std":  round(float(arr.std()), 2),
                "n":    len(vals)}

    return {
        "dates":       dates,
        "hrv_raw":     hrv_vals,
        "hrv_rolling": rolling,
        "fatigue":     fatigue,
        "pain":        pain,
        "pre_intervention":  stats_dict(pre_vals),
        "post_intervention": stats_dict(post_vals),
    }


def compute_sleep_bbt_uv(observations: list) -> dict:
    """Build sleep/BBT dataset paired with UV from the previous day (lag 1).

    For each observation that has sleep or BBT data, look up UV noon
    from the day before. Returns aligned arrays for charting.
    """
    import db as _db

    obs_by_date = {o["date"]: o for o in observations}
    all_dates = sorted(obs_by_date.keys())

    dates      = []
    sleep_vals = []
    bbt_vals   = []
    uv_lag1    = []

    for date_str in all_dates:
        obs = obs_by_date[date_str]
        sleep = obs.get("hours_slept")
        bbt   = obs.get("basal_temp_delta")

        if sleep is None and bbt is None:
            continue

        # Get UV from the previous day
        prev_date = (datetime.strptime(date_str, "%Y-%m-%d") -
                     timedelta(days=1)).strftime("%Y-%m-%d")
        uv_row = _db.get_uv_data(prev_date)
        uv_noon = uv_row.get("uv_noon") if uv_row else None

        dates.append(date_str)
        sleep_vals.append(float(sleep) if sleep is not None else None)
        bbt_vals.append(float(bbt) if bbt is not None else None)
        uv_lag1.append(float(uv_noon) if uv_noon is not None else None)

    return {
        "dates":      dates,
        "sleep":      sleep_vals,
        "bbt":        bbt_vals,
        "uv_lag1":    uv_lag1,
    }


def _detect_ovulation_bbt(bbt_by_date: dict, cycle_start: date, cycle_end: date):
    """Detect ovulation from biphasic BBT shift within a cycle window.

    Collects non-null BBT readings in [cycle_start, cycle_end), requires >=8 data points.
    Computes a follicular-phase average from the first 5 readings, then finds the first
    date of a 3-consecutive-day sustained rise >= 0.1 deg F above that average.
    Returns the first day of the sustained rise, or None if pattern not found.
    """
    readings = []
    d = cycle_start
    while d < cycle_end:
        bbt = bbt_by_date.get(d.isoformat())
        if bbt is not None:
            readings.append((d, bbt))
        d += timedelta(days=1)

    if len(readings) < 8:
        return None

    follicular_avg = sum(v for _, v in readings[:5]) / 5
    threshold = follicular_avg + 0.1

    consecutive = 0
    first_high = None
    for d, bbt in readings[5:]:
        if bbt >= threshold:
            consecutive += 1
            if first_high is None:
                first_high = d
            if consecutive >= 3:
                return first_high
        else:
            consecutive = 0
            first_high = None
    return None


@app.route("/cycle")
def cycle_view():
    """Menstrual cycle calendar — opt-in via config track_cycle=true."""
    if not CONFIG.get("track_cycle"):
        return redirect(url_for("daily_entry"))

    year  = request.args.get("year",  type=int, default=date.today().year)
    month = request.args.get("month", type=int, default=date.today().month)

    # Fetch 12 months of history for cycle-length calculation, plus the current month
    history_start = (date(year, month, 1) - timedelta(days=365)).isoformat()
    month_last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, month_last_day).isoformat()
    all_data = db.get_cycle_data(history_start, month_end)

    # Build BBT lookup for the entire history window
    bbt_by_date = {
        row["date"]: row["basal_temp_delta"]
        for row in all_data
        if row.get("basal_temp_delta") is not None
    }

    # Detect period start days (first day of non-spotting flow after a gap)
    period_starts = []
    prev_had_period = False
    for row in all_data:
        has_period = bool(row.get("period_flow") and row.get("period_flow") != "spotting")
        if has_period and not prev_had_period:
            period_starts.append(row["date"])
        prev_had_period = has_period

    # Average cycle length — use last 6 cycles, discard gaps > 90 days (data holes, not cycles)
    lengths_raw: list[int] = []
    avg_cycle = 28
    if len(period_starts) >= 2:
        lengths_raw = [
            (date.fromisoformat(period_starts[i + 1]) -
             date.fromisoformat(period_starts[i])).days
            for i in range(len(period_starts) - 1)
        ]
        lengths = [l for l in lengths_raw if l <= 90]
        recent = lengths[-6:] if lengths else []
        avg_cycle = round(sum(recent) / len(recent)) if recent else 28

    # Build phase lookup for ALL historical cycles using BBT-detected ovulation where available
    phase_by_date: dict[str, str] = {}
    bbt_ovulations: dict[str, date] = {}  # period_start_str -> detected ovulation date

    for i, start_str in enumerate(period_starts):
        cycle_start = date.fromisoformat(start_str)
        cycle_end = (date.fromisoformat(period_starts[i + 1])
                     if i + 1 < len(period_starts)
                     else cycle_start + timedelta(days=avg_cycle))

        detected_ov = _detect_ovulation_bbt(bbt_by_date, cycle_start, cycle_end)
        if detected_ov:
            bbt_ovulations[start_str] = detected_ov
            lut = detected_ov
        else:
            lut = cycle_end - timedelta(days=14)

        pms = lut + timedelta(days=7)
        d = lut
        while d < cycle_end:
            phase_by_date[d.isoformat()] = "pms" if d >= pms else "luteal"
            d += timedelta(days=1)

    # Forward prediction for current (open) cycle — prefer BBT-detected ovulation
    next_period = pms_start = ovulation = luteal_start = None
    ovulation_source = "predicted"
    if period_starts:
        last_start = date.fromisoformat(period_starts[-1])
        detected_ov = _detect_ovulation_bbt(
            bbt_by_date, last_start, date.today() + timedelta(days=1)
        )
        if detected_ov:
            ovulation = detected_ov
            luteal_start = detected_ov
            next_period = detected_ov + timedelta(days=14)
            ovulation_source = "detected"
        else:
            next_period = last_start + timedelta(days=avg_cycle)
            ovulation = next_period - timedelta(days=14)
            luteal_start = ovulation

        pms_start = next_period - timedelta(days=7)

        # Extend phase_by_date forward into the predicted future
        d = luteal_start
        while d < next_period:
            if d.isoformat() not in phase_by_date:
                phase_by_date[d.isoformat()] = "pms" if d >= pms_start else "luteal"
            d += timedelta(days=1)

    # Filter observation data to current month for the display grid
    month_start_str = date(year, month, 1).isoformat()
    month_data = {
        row["date"]: row for row in all_data
        if row["date"] >= month_start_str
    }

    # BBT data points for the current month in calendar order (None if no data)
    bbt_points = []
    for d_num in range(1, month_last_day + 1):
        ds = date(year, month, d_num).isoformat()
        obs = month_data.get(ds)
        bbt = obs["basal_temp_delta"] if obs and obs.get("basal_temp_delta") is not None else None
        bbt_points.append((d_num, bbt))

    # Intervention markers: (drug_name, 'start') for new starts this month,
    # (drug_name, 'active') on day-1 for meds active from a prior month
    all_meds = db.get_all_medications()
    intervention_dates: dict = {}
    for m in all_meds:
        if not (m.get("is_primary_intervention") or m.get("is_secondary_intervention")):
            continue
        s = m["start_date"]
        e = m.get("end_date")
        if month_start_str <= s <= month_end:
            intervention_dates[s] = (m["drug_name"], "start")
        elif s < month_start_str and (e is None or e >= month_start_str):
            if month_start_str not in intervention_dates:
                intervention_dates[month_start_str] = (m["drug_name"], "active")

    # Flare counts by cycle phase (across all history)
    phase_day_counts: dict[str, int] = {"pms": 0, "luteal": 0, "follicular": 0, "period": 0}
    flare_phase_counts: dict[str, int] = {"pms": 0, "luteal": 0, "follicular": 0, "period": 0}
    for row in all_data:
        ds = row["date"]
        if bool(row.get("period_flow") and row["period_flow"] != "spotting"):
            ph = "period"
        else:
            ph = phase_by_date.get(ds, "follicular")
        phase_day_counts[ph] = phase_day_counts.get(ph, 0) + 1
        if row.get("flare_occurred"):
            flare_phase_counts[ph] = flare_phase_counts.get(ph, 0) + 1

    # Intervention cycle-length effects (up to 3 cycles before/after each intervention)
    intervention_effects = []
    for m in all_meds:
        if not (m.get("is_primary_intervention") or m.get("is_secondary_intervention")):
            continue
        s = m["start_date"]
        before = [l for ps, l in zip(period_starts, lengths_raw) if ps < s][-3:]
        after  = [l for ps, l in zip(period_starts[1:], lengths_raw) if ps > s][:3]
        if before or after:
            intervention_effects.append({
                "drug":       m["drug_name"],
                "start":      s,
                "before_avg": round(sum(before) / len(before)) if before else None,
                "after_avg":  round(sum(after)  / len(after))  if after  else None,
            })

    # Month navigation
    prev_year,  prev_month  = (year - 1, 12) if month == 1  else (year, month - 1)
    next_year,  next_month  = (year + 1, 1)  if month == 12 else (year, month + 1)

    return render_template(
        "cycle.html",
        year=year, month=month,
        month_name=date(year, month, 1).strftime("%B %Y"),
        month_data=month_data,
        month_last_day=month_last_day,
        phase_by_date=phase_by_date,
        avg_cycle=avg_cycle,
        next_period=next_period,
        pms_start=pms_start,
        ovulation=ovulation,
        ovulation_source=ovulation_source,
        luteal_start=luteal_start,
        period_starts=period_starts,
        bbt_points=bbt_points,
        bbt_ovulations=bbt_ovulations,
        intervention_dates=intervention_dates,
        flare_phase_counts=flare_phase_counts,
        phase_day_counts=phase_day_counts,
        intervention_effects=intervention_effects,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        cal=calendar,
    )


@app.route("/hrv")
def hrv_view():
    """HRV trend with rolling average, intervention split, and sleep/BBT/UV."""
    observations = db.get_all_daily_observations()
    all_meds = db.get_all_medications()
    
    # Find primary intervention (the medication marked as primary)
    primary_med = next((m for m in all_meds if m.get("is_primary_intervention") == 1), None)
    
    intervention_name = None
    intervention_date = None
    
    if primary_med:
        intervention_name = primary_med["drug_name"]
        intervention_date = primary_med["start_date"]
    
    # Find secondary interventions (medications marked as secondary)
    secondary_interventions = [
        {
            "drug_name": m["drug_name"],
            "start_date": m["start_date"]
        }
        for m in all_meds
        if m.get("is_secondary_intervention") == 1
    ]
    
    hrv_data = compute_hrv_data(observations, intervention_date)
    sleep_bbt_uv = compute_sleep_bbt_uv(observations)
    
    return render_template(
        "hrv.html",
        has_data=bool(hrv_data),
        hrv_json=json.dumps(hrv_data, default=lambda x: int(x) if isinstance(x, bool) else str(x)),
        sleep_json=json.dumps(sleep_bbt_uv, default=lambda x: int(x) if isinstance(x, bool) else str(x)),
        primary_intervention_name=intervention_name,
        primary_intervention_date=intervention_date,
        other_interventions_json=json.dumps(secondary_interventions),
    )


# ============================================================
# Clinical record
# ============================================================

@app.route("/clinical")
def clinical_record():
    """Record - labs, ANA, meds, events, clinicians."""
    labs = db.get_lab_results()
    ana = db.get_ana_results()
    meds = db.get_all_medications()
    events = db.get_clinical_events()
    clinicians = db.get_all_clinicians()
    test_names = db.get_lab_test_names()

    # Split active/inactive meds
    today_str = date.today().isoformat()
    active = [m for m in meds
              if m["start_date"] <= today_str and
                 (m.get("end_date") is None or m["end_date"] >= today_str)]
    inactive = [m for m in meds
                if m.get("end_date") and m["end_date"] < today_str]

    # Build taper schedule lookup keyed by medication_id
    taper_by_med = {}
    for med in active:
        t = db.get_active_taper_for_medication(med["id"])
        if t:
            taper_by_med[med["id"]] = t

    ntfy_configured = bool(CONFIG.get("ntfy_topic"))

    return render_template(
        "clinical_record.html",
        labs=labs,
        ana=ana,
        meds=meds,
        active=active,
        inactive=inactive,
        events=events,
        clinicians=clinicians,
        test_names=test_names,
        today=date.today().isoformat(),
        taper_by_med=taper_by_med,
        ntfy_configured=ntfy_configured,
    )
    
@app.route("/medication/update/<int:med_id>", methods=["POST"])
def update_medication(med_id):
    """Update an existing medication."""
    form = request.form
    
    db.update_medication(
        med_id=med_id,
        drug_name=form.get("drug_name"),
        dose=float(form.get("dose")) if form.get("dose") else None,
        unit=form.get("unit") or None,
        frequency=form.get("frequency") or None,
        category=form.get("category") or None,
        indication=form.get("indication") or None,
        start_date=form.get("start_date"),
        end_date=form.get("end_date") or None,
        notes=form.get("notes") or None,
        is_primary_intervention=form.get("is_primary_intervention") == "1",
        is_secondary_intervention=form.get("is_secondary_intervention") == "1",
    )
    
    return redirect(url_for("clinical_record") + "#medications")


@app.route("/medication/delete/<int:med_id>", methods=["POST"])
def delete_medication(med_id):
    """Delete a medication."""
    db.delete_medication(med_id)
    return redirect(url_for("clinical_record") + "#medications")


# ============================================================
# Taper schedules and dose reminders
# ============================================================

@app.route("/taper/create", methods=["POST"])
def taper_create():
    """Create a taper schedule with individual dose rows from the wizard form."""
    med_id = int(request.form.get("medication_id"))
    start_date = request.form.get("start_date")
    drug_name = request.form.get("drug_name", "medication")
    unit = request.form.get("unit", "tablet(s)")

    # Build dose rows from form fields: dose_label_N, dose_time_N, dose_amount_N
    doses_raw = {}
    for key, val in request.form.items():
        if key.startswith("dose_label_"):
            idx = key[len("dose_label_"):]
            doses_raw.setdefault(idx, {})["label"] = val
        elif key.startswith("dose_time_"):
            idx = key[len("dose_time_"):]
            doses_raw.setdefault(idx, {})["time"] = val
        elif key.startswith("dose_amount_"):
            idx = key[len("dose_amount_"):]
            doses_raw.setdefault(idx, {})["amount"] = val

    schedule_id = db.create_taper_schedule(med_id, start_date)

    dose_rows = []
    for idx in sorted(doses_raw.keys(), key=lambda x: int(x)):
        entry = doses_raw[idx]
        label = entry.get("label", "")
        time_str = entry.get("time", "08:00")
        amount = entry.get("amount")
        # datetime-local inputs submit as 'YYYY-MM-DDTHH:MM'; normalize to 'YYYY-MM-DD HH:MM'
        normalized_dt = time_str.replace("T", " ")[:16]
        dose_rows.append({
            "taper_schedule_id": schedule_id,
            "medication_id": med_id,
            "scheduled_datetime": normalized_dt,
            "dose_label": label,
            "dose_amount": float(amount) if amount else None,
            "dose_unit": unit,
        })

    db.insert_scheduled_doses(dose_rows)
    return redirect(url_for("clinical_record") + "#medications")


@app.route("/taper/delete/<int:schedule_id>", methods=["POST"])
def taper_delete(schedule_id):
    """Delete a taper schedule and all its doses."""
    db.delete_taper_schedule(schedule_id)
    return redirect(url_for("clinical_record") + "#medications")


@app.route("/dose/take/<int:dose_id>", methods=["POST"])
def dose_take(dose_id):
    """Mark a dose as taken."""
    taken_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.mark_dose_taken(dose_id, taken_at)
    # Redirect back to wherever the user came from (daily entry or clinical)
    return_url = request.form.get("return_url", url_for("daily_entry"))
    return redirect(return_url)


@app.route("/doses/today")
def doses_today():
    """JSON endpoint: today's scheduled doses."""
    today_str = date.today().isoformat()
    doses = db.get_todays_doses(today_str)
    return jsonify(doses)


#============================================================
# Clinician management
#============================================================

@app.route("/clinician/add", methods=["POST"])
def add_clinician():
    """Add a new clinician."""
    db.add_clinician({
        "name": request.form.get("name"),
        "specialty": request.form.get("specialty"),
        "clinic_name": request.form.get("clinic_name") or None,
        "address": request.form.get("address") or None,
        "phone": request.form.get("phone") or None,
        "email": request.form.get("email") or None,
        "network": request.form.get("network") or None,
        "notes": request.form.get("notes") or None,
    })
    return redirect(url_for("clinical_record") + "#clinicians")


@app.route("/clinician/update/<int:clinician_id>", methods=["POST"])
def update_clinician(clinician_id):
    """Update an existing clinician."""
    form = request.form
    
    db.update_clinician(
        clinician_id=clinician_id,
        name=form.get("name"),
        specialty=form.get("specialty"),
        clinic_name=form.get("clinic_name") or None,
        address=form.get("address") or None,
        phone=form.get("phone") or None,
        email=form.get("email") or None,
        network=form.get("network") or None,
        notes=form.get("notes") or None,
    )
    
    return redirect(url_for("clinical_record") + "#clinicians")


@app.route("/clinician/delete/<int:clinician_id>", methods=["POST"])
def delete_clinician(clinician_id):
    """Delete a clinician."""
    db.delete_clinician(clinician_id)
    return redirect(url_for("clinical_record") + "#clinicians")


# ============================================================
# Clinical record - add entries
# ============================================================

@app.route("/clinical/lab/add", methods=["POST"])
def add_lab():
    """Add a lab result."""
    form = request.form
    data = {
        "date": form.get("date"),
        "test_name": form.get("test_name", "").strip(),
        "numeric_value": float(form["numeric_value"])
            if form.get("numeric_value", "").strip() else None,
        "unit": form.get("unit", "").strip() or None,
        "qualitative_result": form.get("qualitative_result", "").strip() or None,
        "reference_range": form.get("reference_range", "").strip() or None,
        "flag": form.get("flag", "").strip() or None,
        "provider": form.get("provider", "").strip() or None,
        "lab_facility": form.get("lab_facility", "").strip() or None,
        "notes": form.get("notes", "").strip() or None,
    }
    db.add_lab_result(data)
    return redirect(url_for("clinical_record") + "#labs")



@app.route("/clinical/ana/add", methods=["POST"])
def add_ana():
    """Add an ANA result."""
    form = request.form
    patterns_raw = form.get("patterns", "").strip()
    patterns = [p.strip() for p in patterns_raw.split(",") if p.strip()]

    db.add_ana_result(
        date_str=form.get("date"),
        titer_integer=int(form["titer"]) if form.get("titer", "").strip() else None,
        screen_result=form.get("screen_result", "").strip(),
        patterns=patterns,
        provider=form.get("provider", "").strip() or None,
        notes=form.get("notes", "").strip() or None,
    )
    return redirect(url_for("clinical_record") + "#ana")


@app.route("/clinical/event/add", methods=["POST"])
def add_event():
    """Add a clinical event."""
    form = request.form
    data = {
        "date": form.get("date"),
        "event_type": form.get("event_type", "").strip(),
        "provider": form.get("provider", "").strip() or None,
        "facility": form.get("facility", "").strip() or None,
        "notes": form.get("notes", "").strip() or None,
        "follow_up_date": form.get("follow_up_date", "").strip() or None,
    }
    db.add_clinical_event(data)
    return redirect(url_for("clinical_record") + "#events")


@app.route("/medication/add", methods=["POST"])
def add_medication():
    """Add a new medication."""
    db.add_medication({
        "drug_name": request.form.get("drug_name"),
        "dose": request.form.get("dose"),
        "unit": request.form.get("unit"),
        "frequency": request.form.get("frequency"),
        "route": request.form.get("route"),
        "category": request.form.get("category"),
        "indication": request.form.get("indication"),
        "start_date": request.form.get("start_date"),
        "end_date": request.form.get("end_date") or None,
        "notes": request.form.get("notes"),
        "is_primary_intervention": request.form.get("is_primary_intervention") == "1",
        "is_secondary_intervention": request.form.get("is_secondary_intervention") == "1",
    })
    return redirect(url_for("clinical_record") + "#medications")

#=======================================
# Edit/Cancel/Delete
#=======================================

@app.route("/clinical/medication/end/<int:med_id>", methods=["POST"])
def end_medication(med_id):
    """Mark a medication as ended today."""
    end_date = request.form.get("end_date", date.today().isoformat())
    db.end_medication(med_id, end_date)
    return redirect(url_for("clinical_record") + "#medications")

# lab results update/delete

@app.route("/lab/update/<int:lab_id>", methods=["POST"])
def update_lab(lab_id):
    """Update an existing lab result."""
    form = request.form
    
    def get_float(key):
        val = form.get(key, "").strip()
        try:
            return float(val) if val else None
        except ValueError:
            return None
    
    db.update_lab_result(
        lab_id=lab_id,
        date=form.get("date"),
        test_name=form.get("test_name"),
        numeric_value=get_float("numeric_value"),
        unit=form.get("unit") or None,
        qualitative_result=form.get("qualitative_result") or None,
        reference_range=form.get("reference_range") or None,
        flag=form.get("flag") or None,
        provider=form.get("provider") or None,
        lab_facility=form.get("lab_facility") or None,
        notes=form.get("notes") or None,
    )
    
    return redirect(url_for("clinical_record") + "#labs")


@app.route("/lab/delete/<int:lab_id>", methods=["POST"])
def delete_lab(lab_id):
    """Delete a lab result."""
    db.delete_lab_result(lab_id)
    return redirect(url_for("clinical_record") + "#labs")


@app.route("/ana/update/<int:ana_id>", methods=["POST"])
def update_ana(ana_id):
    """Update an existing ANA result."""
    form = request.form
    
    db.update_ana_result(
        ana_id=ana_id,
        date=form.get("date"),
        titer=form.get("titer") or None,
        patterns=form.get("patterns") or None,
        screen_result=form.get("screen_result") or None,
        provider=form.get("provider") or None,
        notes=form.get("notes") or None,
    )
    
    return redirect(url_for("clinical_record") + "#ana")


@app.route("/ana/delete/<int:ana_id>", methods=["POST"])
def delete_ana(ana_id):
    """Delete an ANA result."""
    db.delete_ana_result(ana_id)
    return redirect(url_for("clinical_record") + "#ana")


@app.route("/event/update/<int:event_id>", methods=["POST"])
def update_event(event_id):
    """Update an existing clinical event."""
    form = request.form
    
    db.update_clinical_event(
        event_id=event_id,
        date=form.get("date"),
        event_type=form.get("event_type"),
        provider=form.get("provider") or None,
        facility=form.get("facility") or None,
        notes=form.get("notes") or None,
    )
    
    return redirect(url_for("clinical_record") + "#events")


@app.route("/event/delete/<int:event_id>", methods=["POST"])
def delete_event(event_id):
    """Delete a clinical event."""
    db.delete_clinical_event(event_id)
    return redirect(url_for("clinical_record") + "#events")

#======================================
# Export Lab/Meds/Clinicians/Events
#======================================

import csv
from io import StringIO
from flask import Response

@app.route("/export/labs")
def export_labs():
    """Export lab results as CSV within date range."""
    start_date = request.args.get("start")
    end_date = request.args.get("end")
    
    if not start_date or not end_date:
        return "Missing date range parameters", 400
    
    # Get labs in date range
    all_labs = db.get_lab_results()
    filtered_labs = [
        lab for lab in all_labs
        if start_date <= lab["date"] <= end_date
    ]
    
    # Sort by date (most recent first)
    filtered_labs.sort(key=lambda x: x["date"], reverse=True)
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Date',
        'Test Name',
        'Numeric Value',
        'Unit',
        'Qualitative Result',
        'Reference Range',
        'Flag',
        'Provider',
        'Lab Facility',
        'Notes'
    ])
    
    # Write data rows
    for lab in filtered_labs:
        writer.writerow([
            lab.get('date', ''),
            lab.get('test_name', ''),
            lab.get('numeric_value', '') if lab.get('numeric_value') is not None else '',
            lab.get('unit', '') or '',
            lab.get('qualitative_result', '') or '',
            lab.get('reference_range', '') or '',
            lab.get('flag', '') or '',
            lab.get('provider', '') or '',
            lab.get('lab_facility', '') or '',
            lab.get('notes', '') or ''
        ])
    
    # Prepare response
    csv_data = output.getvalue()
    output.close()
    
    # Generate filename with date range
    filename = f"lab_results_{start_date}_to_{end_date}.csv"
    
    # Return as downloadable CSV
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route("/export/clinicians")
def export_clinicians():
    """Export all clinicians as CSV."""
    
    # Get all clinicians
    clinicians = db.get_all_clinicians()
    
    # Sort by name
    clinicians.sort(key=lambda x: x.get('name', '').lower())
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Name',
        'Specialty',
        'Clinic Name',
        'Phone',
        'Email/Portal',
        'Network',
        'Address',
        'Notes'
    ])
    
    # Write data rows
    for c in clinicians:
        writer.writerow([
            c.get('name', ''),
            c.get('specialty', ''),
            c.get('clinic_name', '') or '',
            c.get('phone', '') or '',
            c.get('email', '') or '',
            c.get('network', '') or '',
            c.get('address', '') or '',
            c.get('notes', '') or ''
        ])
    
    # Prepare response
    csv_data = output.getvalue()
    output.close()
    
    # Generate filename with today's date
    today = date.today().isoformat()
    filename = f"clinicians_{today}.csv"
    
    # Return as downloadable CSV
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )
    
@app.route("/export/medications")
def export_medications():
    """Export medications as CSV with filter (active/all/inactive)."""
    
    filter_type = request.args.get("filter", "active")
    
    # Get all medications
    all_meds = db.get_all_medications()
    
    # Filter based on selection
    today_str = date.today().isoformat()
    
    if filter_type == "active":
        filtered_meds = [
            m for m in all_meds 
            if m["start_date"] <= today_str and
               (m.get("end_date") is None or m["end_date"] >= today_str)
        ]
        filename_suffix = "active"
    elif filter_type == "inactive":
        filtered_meds = [
            m for m in all_meds 
            if m.get("end_date") and m["end_date"] < today_str
        ]
        filename_suffix = "inactive"
    else:  # all
        filtered_meds = all_meds
        filename_suffix = "all"
    
    # Sort by start date (most recent first)
    filtered_meds.sort(key=lambda x: x.get("start_date", ""), reverse=True)
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Drug Name',
        'Dose',
        'Unit',
        'Frequency',
        'Route',
        'Category',
        'Indication',
        'Start Date',
        'End Date',
        'Primary Intervention',
        'Secondary Intervention',
        'Notes'
    ])
    
    # Write data rows
    for med in filtered_meds:
        writer.writerow([
            med.get('drug_name', ''),
            med.get('dose', '') if med.get('dose') is not None else '',
            med.get('unit', '') or '',
            med.get('frequency', '') or '',
            med.get('route', '') or '',
            med.get('category', '') or '',
            med.get('indication', '') or '',
            med.get('start_date', ''),
            med.get('end_date', '') or '',
            'Yes' if med.get('is_primary_intervention') == 1 else 'No',
            'Yes' if med.get('is_secondary_intervention') == 1 else 'No',
            med.get('notes', '') or ''
        ])
    
    # Prepare response
    csv_data = output.getvalue()
    output.close()
    
    # Generate filename
    today = date.today().isoformat()
    filename = f"medications_{filename_suffix}_{today}.csv"
    
    # Return as downloadable CSV
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )
    
@app.route("/export/events")
def export_events():
    """Export clinical events as CSV within date range and optional event type filter."""
    
    start_date = request.args.get("start")
    end_date = request.args.get("end")
    event_type = request.args.get("type", "all")
    
    if not start_date or not end_date:
        return "Missing date range parameters", 400
    
    # Get all events
    all_events = db.get_clinical_events()
    
    # Filter by date range
    filtered_events = [
        event for event in all_events
        if start_date <= event["date"] <= end_date
    ]
    
    # Filter by event type if not "all"
    if event_type != "all":
        filtered_events = [
            event for event in filtered_events
            if event.get("event_type") == event_type
        ]
    
    # Sort by date (most recent first)
    filtered_events.sort(key=lambda x: x["date"], reverse=True)
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Date',
        'Event Type',
        'Provider',
        'Facility',
        'Follow-up Date',
        'Notes'
    ])
    
    # Write data rows
    for event in filtered_events:
        writer.writerow([
            event.get('date', ''),
            event.get('event_type', ''),
            event.get('provider', '') or '',
            event.get('facility', '') or '',
            event.get('follow_up_date', '') or '',
            event.get('notes', '') or ''
        ])
    
    # Prepare response
    csv_data = output.getvalue()
    output.close()
    
    # Generate filename
    type_suffix = event_type if event_type != "all" else "all"
    filename = f"events_{type_suffix}_{start_date}_to_{end_date}.csv"
    
    # Return as downloadable CSV
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )
    
    
    

# ============================================================
# Forecast Laboratory Helpers
# ============================================================

def _compute_phase_by_date_from_obs(all_obs: list) -> dict:
    """Build {date_str: 'pms'|'luteal'} from obs list using same logic as cycle_view.
    Returns {} if track_cycle is False or insufficient cycle data.
    """
    if not CONFIG.get('track_cycle'):
        return {}

    sorted_obs = sorted(all_obs, key=lambda r: r['date'])
    bbt_by_date = {
        r['date']: r['basal_temp_delta']
        for r in sorted_obs
        if r.get('basal_temp_delta') is not None
    }

    # Detect period starts (exclude spotting, same as cycle_view)
    period_starts: list = []
    in_period = False
    for row in sorted_obs:
        has_flow = bool(row.get('period_flow') and row['period_flow'] != 'spotting')
        if has_flow and not in_period:
            period_starts.append(row['date'])
            in_period = True
        elif not has_flow:
            in_period = False

    if len(period_starts) < 2:
        return {}

    lengths_raw = [
        (date.fromisoformat(period_starts[i + 1]) - date.fromisoformat(period_starts[i])).days
        for i in range(len(period_starts) - 1)
    ]
    lengths = [l for l in lengths_raw if l <= 90]
    recent = lengths[-6:] if lengths else []
    avg_cycle = round(sum(recent) / len(recent)) if recent else 28

    phase_by_date: dict = {}
    for i, start_str in enumerate(period_starts):
        cycle_start = date.fromisoformat(start_str)
        cycle_end = (
            date.fromisoformat(period_starts[i + 1])
            if i + 1 < len(period_starts)
            else cycle_start + timedelta(days=avg_cycle)
        )
        detected_ov = _detect_ovulation_bbt(bbt_by_date, cycle_start, cycle_end)
        lut = detected_ov if detected_ov else cycle_end - timedelta(days=14)
        pms = lut + timedelta(days=7)
        d = lut
        while d < cycle_end:
            phase_by_date[d.isoformat()] = 'pms' if d >= pms else 'luteal'
            d += timedelta(days=1)

    return phase_by_date


def _inject_cycle_phase(obs_list: list) -> None:
    """Annotate obs dicts in-place with cycle_in_high_risk_phase and cycle_phase_name."""
    if not CONFIG.get('track_cycle'):
        return
    phase_by_date = _compute_phase_by_date_from_obs(obs_list)
    for obs in obs_list:
        phase = phase_by_date.get(obs['date'])
        obs['cycle_in_high_risk_phase'] = phase in ('pms', 'luteal')
        obs['cycle_phase_name'] = phase


def calculate_flare_prime_score(obs):
    """
    Calculate flare prime score for a single observation.
    Based on refined logic with exponential UV weighting.
    
    UPDATED 2026-03-05: Weights adjusted based on accuracy analysis
    - Lowered threshold from 10 → 8 (improve recall from 20.9%)
    - Increased neurological: 0.5 → 1.5 (appeared in 51 missed flares)
    - Increased cognitive: 0.5 → 1.0 (appeared in 34 missed flares)
    - Increased musculature: 1.0 → 1.5 (appeared in 44 missed flares)
    
    Weights can be customized via Forecast Lab (/forecast/lab)
    """
    score = 0.0
    
    # Load current weights (from config or defaults)
    weights = get_current_weights()
    
    # 1. UV Exposure (exponential weighting: UV^1.5 × minutes)
    sun_min = obs.get('sun_exposure_min') or 0
    if sun_min >= 100:
        score += 3
    elif sun_min >= 70:
        score += 1.25
    
    # 2. Physical Overexertion (steps / hours slept)
    steps = obs.get('steps') or 0
    hours_slept = obs.get('hours_slept') or 8
    if hours_slept > 0:
        exertion_ratio = steps / hours_slept
        if exertion_ratio >= 2000:
            score += 2.0
        elif exertion_ratio >= 1500:
            score += 1.5
    
    # 3. Basal Temperature (simplified, non-overlapping)
    basal_temp = obs.get('basal_temp_delta') or 0
    if basal_temp >= 0.8:
        score += 3
    elif basal_temp >= 0.5:
        score += 2
    elif basal_temp >= 0.3:
        score += 1
    
    # 4. Symptoms (WEIGHTS FROM CONFIG)
    if obs.get('neurological'):
        score += weights['neurological']
    if obs.get('cognitive'):
        score += weights['cognitive']
    if obs.get('musculature'):
        score += weights['musculature']
    if obs.get('migraine'):
        score += weights['migraine']
    if obs.get('pulmonary'):
        score += weights['pulmonary']
    if obs.get('dermatological'):
        score += weights['dermatological']
    if obs.get('mucosal'):
        score += weights['mucosal']
    
    # 5. Rheumatic (parse notes for joint type)
    if obs.get('rheumatic'):
        rheum_notes = (obs.get('rheumatic_notes') or '').lower()
        major_joints = ['hip', 'knee', 'shoulder', 'elbow', 'ankle', 'wrist', 'jaw']
        minor_joints = ['finger', 'toe', 'hand']
        
        if any(joint in rheum_notes for joint in major_joints):
            score += 2.0
        elif any(joint in rheum_notes for joint in minor_joints):
            score += 1.0
        else:
            score += weights['rheumatic']
    
    # 6. Pain Scale
    pain = obs.get('pain_scale') or 0
    if pain >= 7:
        score += 1
    
    # 7. Fatigue Scale
    fatigue = obs.get('fatigue_scale') or 0
    if fatigue >= 7:
        score += 3
    elif fatigue > 5:
        score += 1
    elif fatigue > 3:
        score += 0.5
    
    # 8. Emotional State
    emotional = obs.get('emotional_state') or 5
    if emotional <= 4:
        score += 2
    
    return round(score, 1)

def calculate_model_stats(observations, custom_weights=None):
    """Calculate model accuracy metrics."""
    from collections import Counter
    
    true_pos = 0
    true_neg = 0
    false_pos = 0
    false_neg = 0
    
    for obs in observations:
        if custom_weights:
            # Use custom weights for simulation
            score = calculate_flare_score_with_weights(obs, custom_weights)
        else:
            # Use current weights (from config or defaults)
            score = calculate_flare_prime_score(obs)
        
        predicted_flare = score >= 8
        actual_flare = obs.get('flare_occurred') == 1
        
        if predicted_flare and actual_flare:
            true_pos += 1
        elif not predicted_flare and not actual_flare:
            true_neg += 1
        elif predicted_flare and not actual_flare:
            false_pos += 1
        else:
            false_neg += 1
    
    total = len(observations)
    correct = true_pos + true_neg
    
    accuracy = round((correct / total * 100) if total > 0 else 0, 1)
    
    predicted_pos = true_pos + false_pos
    precision = round((true_pos / predicted_pos * 100) if predicted_pos > 0 else 0, 1)
    
    actual_pos = true_pos + false_neg
    recall = round((true_pos / actual_pos * 100) if actual_pos > 0 else 0, 1)
    
    return {
        'accuracy': accuracy,
        'precision': precision,
        'recall': recall,
        'true_positives': true_pos,
        'true_negatives': true_neg,
        'false_positives': false_pos,
        'false_negatives': false_neg
    }

def analyze_prediction_flips(observations, custom_weights):
    """Identify which predictions would change with new weights."""
    flips_to_positive = []
    flips_to_negative = []
    
    for obs in observations[:10]:
        old_score = calculate_flare_prime_score(obs)
        new_score = calculate_flare_score_with_weights(obs, custom_weights)
        
        old_pred = old_score >= 8
        new_pred = new_score >= 8
        
        if not old_pred and new_pred:
            flips_to_positive.append(obs['date'])
        elif old_pred and not new_pred:
            flips_to_negative.append(obs['date'])
    
    summary = ""
    if flips_to_positive:
        summary += f"> Would now predict flare on: {', '.join(flips_to_positive)}<br>"
    if flips_to_negative:
        summary += f"> Would no longer predict flare on: {', '.join(flips_to_negative)}<br>"
    if not summary:
        summary = "> No prediction changes in the last 10 days."
    
    return {'summary': summary}


def assign_grade(accuracy):
    """Assign letter grade."""
    if accuracy >= 85:
        return 'A'
    elif accuracy >= 75:
        return 'B'
    elif accuracy >= 65:
        return 'C'
    elif accuracy >= 50:
        return 'D'
    else:
        return 'F'    
# ============================================================
# Forecast Laboratory
# ============================================================

@app.route("/forecast/lab")
def forecast_lab():
    """
    Experimental model tuning interface.
    Terminal-style UI for adjusting weights and running simulations.
    """
    # Get current model performance
    all_obs = db.get_all_daily_observations()
    if not all_obs or len(all_obs) < 7:
        return redirect(url_for('forecast'))
    
    # Calculate current metrics (reuse from forecast_accuracy)
    all_obs.sort(key=lambda x: x['date'], reverse=True)
    _inject_cycle_phase(all_obs)
    analysis_set = all_obs[:60]

    # Calculate current stats
    model_stats = calculate_model_stats(analysis_set)
    
    # Get current weights (from config or defaults)
    current_weights = get_current_weights()
    
    # Check if using custom weights
    using_custom = os.path.exists(CUSTOM_WEIGHTS_PATH)
    
    # Current symptom weights for display
    symptoms = [
        {'key': 'neurological', 'name': 'Neurological', 
         'weight': current_weights['neurological'], 
         'description': 'Numbness, tingling, vision changes'},
        {'key': 'cognitive', 'name': 'Cognitive', 
         'weight': current_weights['cognitive'],
         'description': 'Brain fog, memory, word recall'},
        {'key': 'musculature', 'name': 'Musculature', 
         'weight': current_weights['musculature'],
         'description': 'Muscle pain, cramping, weakness'},
        {'key': 'migraine', 'name': 'Migraine', 
         'weight': current_weights['migraine'],
         'description': 'Headaches, light sensitivity'},
        {'key': 'pulmonary', 'name': 'Pulmonary', 
         'weight': current_weights['pulmonary'],
         'description': 'Air hunger, chest discomfort'},
        {'key': 'dermatological', 'name': 'Dermatological', 
         'weight': current_weights['dermatological'],
         'description': 'Rash, skin changes, photosensitivity'},
        {'key': 'mucosal', 'name': 'Mucosal', 
         'weight': current_weights['mucosal'],
         'description': 'Dry mouth, dry eyes, nasal dryness'},
        {'key': 'rheumatic', 'name': 'Rheumatic (base)',
         'weight': current_weights['rheumatic'],
         'description': 'Joint pain without specificity'},
    ]

    if CONFIG.get('track_cycle'):
        symptoms.append({
            'key': 'cycle_phase',
            'name': 'Cycle Phase (PMS/Luteal)',
            'weight': current_weights.get('cycle_phase', 1.0),
            'description': 'Elevated risk during luteal and PMS phases of cycle'
        })
    
    # Model code snippet
    model_code = '''def calculate_flare_prime_score(obs):
    """Calculate flare risk score."""
    score = 0.0
    weights = get_current_weights()  # Loads from config
    
    # Symptoms (using custom weights)
    if obs.get('neurological'):
        score += weights['neurological']
    if obs.get('cognitive'):
        score += weights['cognitive']
    if obs.get('musculature'):
        score += weights['musculature']
    # ... (see full code in app.py)
    
    return round(score, 1)'''
    
    # Achievements (check localStorage or session for unlocked ones)
    achievements = [
        {'icon': '🏆', 'name': 'First Experiment', 'unlocked': False,
         'description': 'Adjusted your first weight'},
        {'icon': '📈', 'name': 'Recall Hero', 'unlocked': False,
         'description': 'Improved recall by 10%'},
        {'icon': '🎯', 'name': 'Precision Master', 'unlocked': model_stats['precision'] > 90,
         'description': 'Maintained >90% precision'},
        {'icon': '🧪', 'name': 'Mad Scientist', 'unlocked': False,
         'description': 'Ran 10 simulations'},
        {'icon': '⚖️', 'name': 'Perfect Balance', 'unlocked': False,
         'description': 'Achieved 80%+ accuracy, recall, and precision'},
    ]
    
    return render_template(
        "forecast_lab.html",
        current_accuracy=model_stats['accuracy'],
        current_recall=model_stats['recall'],
        current_precision=model_stats['precision'],
        false_negatives=model_stats['false_negatives'],
        false_positives=model_stats['false_positives'],
        symptoms=symptoms,
        current_weights=current_weights,
        model_code=model_code,
        achievements=achievements,
        manual_text=FORECAST_LAB_MANUAL,
        using_custom=using_custom  
    )
    
    

@app.route("/forecast/lab/simulate", methods=["POST"])
def forecast_lab_simulate():
    """
    Run simulation with custom weights.
    Returns new accuracy metrics and which predictions would flip.
    """
    from flask import request, jsonify
    
    custom_weights = request.json.get('weights', {})
    
    # Get data
    all_obs = db.get_all_daily_observations()
    all_obs.sort(key=lambda x: x['date'], reverse=True)
    _inject_cycle_phase(all_obs)
    analysis_set = all_obs[:60]

    # Calculate stats with custom weights
    new_stats = calculate_model_stats(analysis_set, custom_weights)
    
    # Calculate stats with current weights (for comparison)
    current_stats = calculate_model_stats(analysis_set, None)
    
    # Find which predictions would flip
    flips = analyze_prediction_flips(analysis_set, custom_weights)
    
    return jsonify({
        'accuracy': new_stats['accuracy'],
        'recall': new_stats['recall'],
        'precision': new_stats['precision'],
        'grade': assign_grade(new_stats['accuracy']),
        'accuracy_change': round(new_stats['accuracy'] - current_stats['accuracy'], 1),
        'recall_change': round(new_stats['recall'] - current_stats['recall'], 1),
        'precision_change': round(new_stats['precision'] - current_stats['precision'], 1),
        'flip_summary': flips['summary']
    })


# ============================================================
# Lab Simulation Apply & Restart
# ============================================================

@app.route("/forecast/lab/apply", methods=["POST"])
def forecast_lab_apply():
    """
    Apply custom weights to the model.
    Saves weights to config file.
    """
    from flask import request, jsonify
    
    try:
        custom_weights = request.json.get('weights', {})
        
        # Validate weights (all must be numbers between 0 and 3)
        for key, value in custom_weights.items():
            if not isinstance(value, (int, float)) or value < 0 or value > 3:
                return jsonify({'success': False, 'error': f'Invalid weight for {key}'}), 400
        
        # Save to config
        save_custom_weights(custom_weights)
        
        # Recalculate stats with new weights
        all_obs = db.get_all_daily_observations()
        all_obs.sort(key=lambda x: x['date'], reverse=True)
        _inject_cycle_phase(all_obs)
        analysis_set = all_obs[:60]
        new_stats = calculate_model_stats(analysis_set)
        
        return jsonify({
            'success': True,
            'message': 'Weights applied successfully!',
            'new_accuracy': new_stats['accuracy'],
            'new_recall': new_stats['recall'],
            'new_precision': new_stats['precision']
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/forecast/lab/reset", methods=["POST"])
def forecast_lab_reset():
    """
    Reset to factory default weights.
    Deletes custom config file.
    """
    from flask import jsonify
    
    try:
        reset_to_default_weights()
        
        return jsonify({
            'success': True,
            'message': 'Reset to factory defaults successfully!'
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# Forecast
# ============================================================
@app.route("/forecast")
def forecast():
    """
    Flare risk forecast page.
    Calculates flare prime score based on recent observations.
    """
    from datetime import datetime, timedelta
    
    # Get last 30 days of observations for analysis
    all_obs = db.get_all_daily_observations()
    if not all_obs:
        return render_template("forecast.html", has_data=False)
    
    # Sort by date
    all_obs.sort(key=lambda x: x['date'], reverse=True)
    _inject_cycle_phase(all_obs)

    # Need at least 7 days
    if len(all_obs) < 7:
        return render_template("forecast.html", has_data=False)
    
    # Get last 7 days for trend
    last_7 = all_obs[:7]
    today_obs = all_obs[0] if all_obs else None
    
    if not today_obs:
        return render_template("forecast.html", has_data=False)
    
    # Calculate scores for last 7 days
    scores_7day = []
    for obs in last_7:
        score = calculate_flare_prime_score(obs)
        scores_7day.append({
            'date': obs['date'],
            'score': score
        })
    
    # Today's score with 3-day weighted average
    today_score = scores_7day[0]['score']
    
    # 3-day rolling weighted average (if we have enough data)
    if len(scores_7day) >= 3:
        weighted_score = (
            scores_7day[0]['score'] * 1.0 +  # today
            scores_7day[1]['score'] * 0.75 +  # yesterday
            scores_7day[2]['score'] * 0.5     # day before
        ) / 2.25
    else:
        weighted_score = today_score
    
    # Determine risk level and color
    risk_info = get_risk_level(weighted_score)
    
    # Get contributing factors (what's adding to score today)
    factors = get_contributing_factors(today_obs)
    
    # Get recommendations based on risk level
    recommendations = get_recommendations(risk_info['level'], factors)
    
    # Build trend data for chart
    trend_data = {
        'dates': [format_date_short(s['date']) for s in reversed(scores_7day)],
        'scores': [s['score'] for s in reversed(scores_7day)]
    }
    
    # Build score breakdown by category
    breakdown = get_score_breakdown(today_obs)
    
    return render_template(
        "forecast.html",
        has_data=True,
        n_days=len(all_obs),
        today_score=round(weighted_score, 1),
        max_score=25,  # Theoretical maximum
        risk_percentage=min(100, (weighted_score / 25) * 100),
        risk_level=risk_info['level'],
        risk_color=risk_info['color'],
        risk_description=risk_info['description'],
        factors=factors,
        recommendations=recommendations,
        trend_data=trend_data,
        breakdown=breakdown
    )

def calculate_flare_prime_score(obs):
    """
    Calculate flare prime score for a single observation.
    Based on refined logic with exponential UV weighting.
    
    UPDATED 2026-03-05: Weights adjusted based on accuracy analysis
    - Lowered threshold from 10 → 8 (improve recall from 20.9%)
    - Increased neurological: 0.5 → 1.5 (appeared in 51 missed flares)
    - Increased cognitive: 0.5 → 1.0 (appeared in 34 missed flares)
    - Increased musculature: 1.0 → 1.5 (appeared in 44 missed flares)
    """
    score = 0.0
    
    # 1. UV Exposure (exponential weighting: UV^1.5 × minutes)
    sun_min = obs.get('sun_exposure_min') or 0
    if sun_min >= 100:
        score += 3
    elif sun_min >= 70:
        score += 1.25
    
    # 2. Physical Overexertion (steps / hours slept)
    steps = obs.get('steps') or 0
    hours_slept = obs.get('hours_slept') or 8
    if hours_slept > 0:
        exertion_ratio = steps / hours_slept
        if exertion_ratio >= 2000:
            score += 2.0
        elif exertion_ratio >= 1500:
            score += 1.5
    
    # 3. Basal Temperature (simplified, non-overlapping)
    basal_temp = obs.get('basal_temp_delta') or 0
    if basal_temp >= 0.8:
        score += 3
    elif basal_temp >= 0.5:
        score += 2
    elif basal_temp >= 0.3:
        score += 1
    
    # 4. Symptoms (UPDATED WEIGHTS)
    if obs.get('neurological'):
        score += 1.5  # CHANGED from 0.5
    if obs.get('cognitive'):
        score += 1.0  # CHANGED from 0.5
    if obs.get('musculature'):
        score += 1.5  # CHANGED from 1.0
    if obs.get('migraine'):
        score += 1    # unchanged
    if obs.get('pulmonary'):
        score += 1    # unchanged
    if obs.get('dermatological'):
        score += 0.75  # unchanged
    if obs.get('mucosal'):
        score += 0.25  # unchanged
    # gastro: +0 (waiting for 3 months of data)
    
    # 5. Rheumatic (parse notes for joint type)
    if obs.get('rheumatic'):
        rheum_notes = (obs.get('rheumatic_notes') or '').lower()
        major_joints = ['hip', 'knee', 'shoulder', 'elbow', 'ankle', 'wrist', 'jaw']
        minor_joints = ['finger', 'toe', 'hand']
        
        if any(joint in rheum_notes for joint in major_joints):
            score += 2.0
        elif any(joint in rheum_notes for joint in minor_joints):
            score += 1.0
        else:
            score += 0.5
    
    # 6. Pain Scale
    pain = obs.get('pain_scale') or 0
    if pain >= 7:
        score += 1
    
    # 7. Fatigue Scale
    fatigue = obs.get('fatigue_scale') or 0
    if fatigue >= 7:
        score += 3
    elif fatigue > 5:
        score += 1
    elif fatigue > 3:
        score += 0.5
    
    # 8. Emotional State
    emotional = obs.get('emotional_state') or 5
    if emotional <= 4:
        score += 2

    # 9. Cycle phase (PMS/luteal risk elevation)
    if obs.get('cycle_in_high_risk_phase'):
        score += get_current_weights().get('cycle_phase', 1.0)

    return round(score, 1)



def get_risk_level(score):
    """
    Determine risk level based on score.
    
    UPDATED 2026-03-05: Lowered thresholds to improve recall
    - Low: 0-5 (unchanged)
    - Moderate: 5-8 (was 5-10)
    - High: 8-12 (was 10-15)
    - Critical: 12+ (was 15+)
    """
    if score < 5:
        return {
            'level': 'Low Risk',
            'color': '#4a9e6e',
            'description': 'Your flare risk is low. Keep up your current routine and rest patterns.'
        }
    elif score < 8:  # CHANGED from 10
        return {
            'level': 'Moderate Risk',
            'color': '#d4b84a',
            'description': 'Elevated risk detected. Consider reducing physical demands and UV exposure.'
        }
    elif score < 12:  # CHANGED from 15
        return {
            'level': 'High Risk',
            'color': '#d4784a',
            'description': 'High flare risk. Prioritize rest, avoid sun exposure, and monitor symptoms closely.'
        }
    else:  # 12+, was 15+
            return {
                'level': 'Critical Risk',
                'color': '#c94040',
                'description': 'Critical flare risk. Consider a rest day and avoid all triggering activities.'
            }


def get_contributing_factors(obs: dict) -> list:
        """Identify what's contributing to today's risk score."""
        factors = []
        
        # UV exposure
        sun_min = obs.get('sun_exposure_min') or 0
        if sun_min >= 100:
            factors.append({'name': 'High UV exposure', 'points': 3, 'color': '#d4b84a'})
        elif sun_min >= 70:
            factors.append({'name': 'Moderate UV exposure', 'points': 1.25, 'color': '#d4b84a'})
        
        # Overexertion
        steps = obs.get('steps') or 0
        hours_slept = obs.get('hours_slept') or 8
        if hours_slept > 0:
            exertion_ratio = steps / hours_slept
            if exertion_ratio >= 2000:
                factors.append({'name': 'Severe overexertion', 'points': 2, 'color': '#c94040'})
            elif exertion_ratio >= 1500:
                factors.append({'name': 'Moderate overexertion', 'points': 1.5, 'color': '#d4784a'})
        
        # Temperature
        basal_temp = obs.get('basal_temp_delta') or 0
        if basal_temp >= 0.8:
            factors.append({'name': 'High fever', 'points': 3, 'color': '#c94040'})
        elif basal_temp >= 0.5:
            factors.append({'name': 'Moderate fever', 'points': 2, 'color': '#d4784a'})
        elif basal_temp >= 0.3:
            factors.append({'name': 'Mild fever', 'points': 1, 'color': '#d4b84a'})
        
        # Active symptoms
        if obs.get('migraine'):
            factors.append({'name': 'Migraine', 'points': 1, 'color': '#c94040'})
        if obs.get('pulmonary'):
            factors.append({'name': 'Pulmonary symptoms', 'points': 1, 'color': '#4ab8b8'})
        if obs.get('musculature'):
            factors.append({'name': 'Muscle symptoms', 'points': 1.5, 'color': '#d4a054'})  # CHANGED
        if obs.get('dermatological'):
            factors.append({'name': 'Skin symptoms', 'points': 0.75, 'color': '#d4784a'})
        if obs.get('cognitive'):
            factors.append({'name': 'Cognitive symptoms', 'points': 1.0, 'color': '#9b72cf'})  # CHANGED
        if obs.get('neurological'):
            factors.append({'name': 'Neurological symptoms', 'points': 1.5, 'color': '#4a90d9'})  # CHANGED
        if obs.get('mucosal'):
            factors.append({'name': 'Mucosal symptoms', 'points': 0.25, 'color': '#d4c4a0'})
        
        # Rheumatic
        if obs.get('rheumatic'):
            rheum_notes = (obs.get('rheumatic_notes') or '').lower()
            if any(j in rheum_notes for j in ['hip', 'knee', 'shoulder', 'elbow', 'ankle', 'wrist', 'jaw']):
                factors.append({'name': 'Major joint pain', 'points': 2, 'color': '#e85d9e'})
            elif any(j in rheum_notes for j in ['finger', 'toe', 'hand']):
                factors.append({'name': 'Minor joint pain', 'points': 1, 'color': '#e85d9e'})
            else:
                factors.append({'name': 'Rheumatic symptoms', 'points': 0.5, 'color': '#e85d9e'})
        
        # High fatigue
        fatigue = obs.get('fatigue_scale') or 0
        if fatigue >= 7:
            factors.append({'name': 'Severe fatigue', 'points': 3, 'color': '#d4a054'})
        elif fatigue > 5:
            factors.append({'name': 'Moderate fatigue', 'points': 1, 'color': '#d4a054'})
        
        # High pain
        pain = obs.get('pain_scale') or 0
        if pain >= 7:
            factors.append({'name': 'High pain', 'points': 1, 'color': '#c94040'})
        
        # Low emotional state
        emotional = obs.get('emotional_state') or 5
        if emotional <= 3:
            factors.append({'name': 'Low emotional state', 'points': 2, 'color': '#7a8499'})

        # Cycle phase
        if obs.get('cycle_in_high_risk_phase'):
            phase_label = 'PMS phase' if obs.get('cycle_phase_name') == 'pms' else 'Luteal phase'
            cycle_weight = get_current_weights().get('cycle_phase', 1.0)
            factors.append({'name': phase_label, 'points': cycle_weight, 'color': '#9563ec'})

        return factors
    
def get_recommendations(risk_level: str, factors: list) -> list:
    """Generate actionable recommendations based on risk."""
    recs = []
    
    if risk_level == 'Low Risk':
        recs.append({'icon': '✓', 'text': 'Maintain current routine and rest schedule'})
        recs.append({'icon': '☀', 'text': 'Continue with normal sun protection practices'})
        recs.append({'icon': '⛆', 'text': 'Stay hydrated and maintain balanced nutrition'})
    
    elif risk_level == 'Moderate Risk':
        recs.append({'icon': '⚠', 'text': 'Reduce physical demands and pace activities'})
        recs.append({'icon': '☀', 'text': 'Limit UV exposure, stay in shade during peak hours'})
        recs.append({'icon': '⏾', 'text': 'Prioritize 8+ hours of sleep tonight'})
        recs.append({'icon': '❆', 'text': 'Use cooling strategies if overheated'})
    
    elif risk_level == 'High Risk':
        recs.append({'icon': '⚠', 'text': 'Avoid strenuous activity and sun exposure'})
        recs.append({'icon': '⏾', 'text': 'Rest is critical - cancel non-essential plans'})
        recs.append({'icon': '℞', 'text': 'Have NSAIDs and comfort measures ready'})
        recs.append({'icon': '⦨', 'text': 'Monitor temperature and symptoms closely'})
    
    else:  # Critical Risk
        recs.append({'icon': '𝚾𝚾𝚾𝚾', 'text': 'Take a full rest day - no exceptions'})
        recs.append({'icon': '⌂', 'text': 'Stay indoors in cool, comfortable environment'})
        recs.append({'icon': '℞', 'text': 'Use all available symptom management tools'})
        recs.append({'icon': '✆', 'text': 'Consider contacting healthcare provider if symptoms worsen'})
    
    # Add specific recommendations based on factors
    factor_names = [f['name'] for f in factors]
    if any('UV' in name for name in factor_names):
        recs.append({'icon': '♛', 'text': 'Wear protective clothing and broad-spectrum sunscreen if going outside'})
    if any('joint' in name.lower() for name in factor_names):
        recs.append({'icon': '❄', 'text': 'Apply cold therapy to affected joints'})
    
    return recs[:5]  # Limit to 5 recommendations


def get_score_breakdown(obs: dict) -> list:
    """Break down score by category."""
    breakdown = []
    
    # UV/Environmental
    sun_min = obs.get('sun_exposure_min') or 0
    uv_score = 3 if sun_min >= 100 else (1.25 if sun_min >= 70 else 0)
    breakdown.append({
        'name': 'UV Exposure',
        'score': uv_score,
        'color': '#d4b84a',
        'description': f'{sun_min} minutes'
    })
    
    # Physical Load
    steps = obs.get('steps') or 0
    hours_slept = obs.get('hours_slept') or 8
    exertion = 0
    ratio = 0
    if hours_slept > 0:
        ratio = steps / hours_slept
        if ratio >= 2000:
            exertion = 2.0
        elif ratio >= 1500:
            exertion = 1.5
    breakdown.append({
        'name': 'Physical Load',
        'score': exertion,
        'color': '#d4a054',
        'description': f'{int(ratio)} steps/hr slept' if hours_slept > 0 else 'N/A'
    })
    
    # Temperature
    basal_temp = obs.get('basal_temp_delta') or 0
    temp_score = 0
    if basal_temp >= 0.8:
        temp_score = 3
    elif basal_temp >= 0.5:
        temp_score = 2
    elif basal_temp >= 0.3:
        temp_score = 1
    breakdown.append({
        'name': 'Temperature',
        'score': temp_score,
        'color': '#c94040',
        'description': f'+{basal_temp:.1f}°F' if basal_temp > 0 else 'Normal'
    })
    
    # Symptoms
    symptom_score = 0
    symptom_count = 0
    for symptom in ['neurological', 'cognitive', 'musculature', 'migraine', 
                    'pulmonary', 'dermatological', 'rheumatic', 'mucosal']:
        if obs.get(symptom):
            symptom_count += 1
            if symptom == 'migraine' or symptom == 'musculature' or symptom == 'pulmonary':
                symptom_score += 1
            elif symptom == 'dermatological':
                symptom_score += 0.75
            elif symptom == 'cognitive' or symptom == 'neurological':
                symptom_score += 0.5
            elif symptom == 'mucosal':
                symptom_score += 0.25
    # Add rheumatic separately (parsed for joints)
    if obs.get('rheumatic'):
        rheum_notes = (obs.get('rheumatic_notes') or '').lower()
        if any(j in rheum_notes for j in ['hip', 'knee', 'shoulder', 'elbow', 'ankle', 'wrist', 'jaw']):
            symptom_score += 2
        elif any(j in rheum_notes for j in ['finger', 'toe', 'hand']):
            symptom_score += 1
        else:
            symptom_score += 0.5
    
    breakdown.append({
        'name': 'Symptoms',
        'score': round(symptom_score, 1),
        'color': '#9b72cf',
        'description': f'{symptom_count} active'
    })
    
    # Pain/Fatigue
    pain = obs.get('pain_scale') or 0
    fatigue = obs.get('fatigue_scale') or 0
    pf_score = 0
    if pain >= 7:
        pf_score += 1
    if fatigue >= 7:
        pf_score += 3
    elif fatigue > 5:
        pf_score += 1
    elif fatigue > 3:
        pf_score += 0.5
    
    breakdown.append({
        'name': 'Pain & Fatigue',
        'score': pf_score,
        'color': '#e85d9e',
        'description': f'P:{pain} F:{fatigue}'
    })

    # Cycle phase (only when tracking enabled)
    if CONFIG.get('track_cycle'):
        cw = get_current_weights()
        cycle_score = cw.get('cycle_phase', 1.0) if obs.get('cycle_in_high_risk_phase') else 0
        breakdown.append({
            'name': 'Cycle Phase',
            'score': cycle_score,
            'color': '#9563ec',
            'description': obs.get('cycle_phase_name') or 'follicular/period'
        })

    return breakdown


def format_date_short(date_str: str) -> str:
    """Format date as 'Mar 4' for chart labels."""
    from datetime import datetime
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    return dt.strftime('%b %d')

# ============================================================
# Forecast History
# ============================================================

@app.route("/forecast/history")
def forecast_history():
    """Show past 30 days of predictions vs actuals."""
    
    # Get last 30 days
    all_obs = db.get_all_daily_observations()
    if not all_obs:
        return redirect(url_for('forecast'))
    
    all_obs.sort(key=lambda x: x['date'], reverse=True)
    _inject_cycle_phase(all_obs)
    last_30 = all_obs[:30]

    history = []
    correct = 0
    false_pos = 0
    false_neg = 0
    
    for obs in last_30:
        score = calculate_flare_prime_score(obs)
        risk_info = get_risk_level(score)
        
        # Did a flare occur?
        flare_occurred = obs.get('flare_occurred') == 1
        
        # Did we predict high risk? (score >= 8)
        predicted_high = score >= 8 #Changed from 10 to catch more actual flares. 

        # Check if prediction was correct
        if predicted_high and flare_occurred:
            correct += 1
            prediction_correct = True
        elif not predicted_high and not flare_occurred:
            correct += 1
            prediction_correct = True
        elif predicted_high and not flare_occurred:
            false_pos += 1
            prediction_correct = False
        elif not predicted_high and flare_occurred:
            false_neg += 1
            prediction_correct = False
        else:
            prediction_correct = None
        
        # Get top contributing factors
        factors = get_contributing_factors(obs)
        top_factors = ', '.join([f['name'] for f in factors[:3]]) if factors else 'None'
        
        history.append({
            'date': obs['date'],
            'score': round(score, 1),
            'risk_level': risk_info['level'],
            'risk_color': risk_info['color'],
            'flare_occurred': flare_occurred,
            'predicted_high_risk': predicted_high,
            'prediction_correct': prediction_correct,
            'top_factors': top_factors
        })
    
    # Calculate accuracy
    total = len(last_30)
    accuracy = round((correct / total * 100) if total > 0 else 0, 1)
    
    return render_template(
        "forecast_history.html",
        history=history,
        correct_predictions=correct,
        false_positives=false_pos,
        false_negatives=false_neg,
        accuracy_percent=accuracy
    )
    
# ============================================================
# Forecast Accuracy Analysis and Self-Grading
# ============================================================

@app.route("/forecast/accuracy")
def forecast_accuracy():
    """
    Analyze model accuracy and suggest weight adjustments.
    Self-grading system that learns from false predictions.
    """
    from collections import Counter
    
    # Get requested time window
    days_param = request.args.get('days', '60')
    
    # Get all observations
    all_obs = db.get_all_daily_observations()
    if not all_obs:
        return redirect(url_for('forecast'))
    
    all_obs.sort(key=lambda x: x['date'], reverse=True)
    _inject_cycle_phase(all_obs)

    # Select analysis window
    if days_param == 'all':
        analysis_set = all_obs
        days_display = 'all'
    else:
        days_int = int(days_param)
        analysis_set = all_obs[:days_int]
        days_display = days_int
    
    # Calculate predictions vs actuals
    true_positives = 0   # Predicted flare, flare occurred
    true_negatives = 0   # Predicted no flare, no flare
    false_positives = 0  # Predicted flare, no flare (false alarm)
    false_negatives = 0  # Predicted no flare, but flare occurred (missed)
    
    # Track which factors appear in false predictions
    false_pos_factors = Counter()
    false_neg_factors = Counter()
    problem_cases = []
    
    for obs in analysis_set:
        score = calculate_flare_prime_score(obs)
        predicted_flare = score >= 8  # CHANGED from 10 
        actual_flare = obs.get('flare_occurred') == 1
        
        if predicted_flare and actual_flare:
            true_positives += 1
        elif not predicted_flare and not actual_flare:
            true_negatives += 1
        elif predicted_flare and not actual_flare:
            false_positives += 1
            # Track factors present in false alarm
            factors = get_contributing_factors(obs)
            for f in factors:
                false_pos_factors[f['name']] += 1
            
            # Add to problem cases
            if len(problem_cases) < 10:
                problem_cases.append({
                    'date': obs['date'],
                    'type': 'False Alarm',
                    'type_color': '#d4784a',
                    'score': round(score, 1),
                    'factors': ', '.join([f['name'] for f in factors[:3]])
                })
        elif not predicted_flare and actual_flare:
            false_negatives += 1
            # Track factors present in missed flare
            factors = get_contributing_factors(obs)
            for f in factors:
                false_neg_factors[f['name']] += 1
            
            # Add to problem cases
            if len(problem_cases) < 10:
                problem_cases.append({
                    'date': obs['date'],
                    'type': 'Missed Flare',
                    'type_color': '#c94040',
                    'score': round(score, 1),
                    'factors': ', '.join([f['name'] for f in factors[:3]])
                })
    
    # Calculate metrics
    total = len(analysis_set)
    correct = true_positives + true_negatives
    accuracy = round((correct / total * 100) if total > 0 else 0, 1)
    
    # Precision: Of all predicted flares, how many were correct?
    predicted_pos = true_positives + false_positives
    precision = round((true_positives / predicted_pos * 100) if predicted_pos > 0 else 0, 1)
    
    # Recall: Of all actual flares, how many did we catch?
    actual_pos = true_positives + false_negatives
    recall = round((true_positives / actual_pos * 100) if actual_pos > 0 else 0, 1)
    
    # False alarm rate
    predicted_pos_total = true_positives + false_positives
    false_alarm_rate = round((false_positives / predicted_pos_total * 100) if predicted_pos_total > 0 else 0, 1)
    
    # Assign grade
    if accuracy >= 85:
        grade = 'A'
        grade_color = '#4a9e6e'
        grade_desc = 'Excellent - Model is highly accurate'
    elif accuracy >= 75:
        grade = 'B'
        grade_color = '#4ab8b8'
        grade_desc = 'Good - Model performs well with minor issues'
    elif accuracy >= 65:
        grade = 'C'
        grade_color = '#d4b84a'
        grade_desc = 'Fair - Model needs improvement'
    elif accuracy >= 50:
        grade = 'D'
        grade_color = '#d4784a'
        grade_desc = 'Poor - Significant adjustments needed'
    else:
        grade = 'F'
        grade_color = '#c94040'
        grade_desc = 'Failing - Model requires major revision'
    
    # Generate weight adjustment suggestions
    suggestions = []
    
    # If too many false alarms, suggest reducing weights of common factors
    if false_positives > 5:
        for factor, count in false_pos_factors.most_common(3):
            if count >= 3:  # Factor appears in 3+ false alarms
                suggestions.append({
                    'factor': factor,
                    'current_weight': 'Current',
                    'suggested_weight': '↓ Reduce',
                    'reason': f'Appears in {count} false alarms. May be over-weighted.',
                    'color': '#d4784a'
                })
    
    # If too many missed flares, suggest increasing weights of common factors
    if false_negatives > 3:
        for factor, count in false_neg_factors.most_common(3):
            if count >= 2:  # Factor appears in 2+ missed flares
                suggestions.append({
                    'factor': factor,
                    'current_weight': 'Current',
                    'suggested_weight': '↑ Increase',
                    'reason': f'Appears in {count} missed flares. May be under-weighted.',
                    'color': '#c94040'
                })
    
    # Specific suggestions based on patterns
    if false_alarm_rate > 40:
        suggestions.insert(0, {
            'factor': 'Overall Threshold',
            'current_weight': '10 points',
            'suggested_weight': '12 points',
            'reason': 'High false alarm rate suggests threshold is too sensitive.',
            'color': '#9b72cf'
        })
    
    if recall < 70:
        suggestions.insert(0, {
            'factor': 'Overall Threshold',
            'current_weight': '10 points',
            'suggested_weight': '8 points',
            'reason': 'Low recall suggests threshold is too conservative.',
            'color': '#9b72cf'
        })
    
    return render_template(
        "forecast_accuracy.html",
        n_days=len(analysis_set),
        days=days_display,
        grade=grade,
        grade_color=grade_color,
        grade_description=grade_desc,
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        false_alarm_rate=false_alarm_rate,
        correct_predictions=correct,
        total_predictions=total,
        true_positives=true_positives,
        true_negatives=true_negatives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        suggestions=suggestions,
        problem_cases=problem_cases[:10]
    )

# ============================================================
# Search
# ============================================================

@app.route("/search", methods=["GET", "POST"])
def search():
    """Search through observations and clinical notes."""
    
    # Get query from either GET or POST
    query = request.args.get("q", "").strip() or request.form.get("query", "").strip()
    
    # Easter egg: redirect to lab for help queries
    if query.lower() in ['help', 'user manual', 'cli', 'lab', 'code', 'weights', 'tune', 'manual']:
        return redirect(url_for('forecast_lab'))

    grouped = {
        "daily":       [],
        "labs":        [],
        "events":      [],
        "medications": [],
    }
    total = 0

    # Always fetch full dataset for report summary and chart
    all_observations = db.get_all_daily_observations()
    all_meds         = db.get_all_medications()

    tracking_start = all_observations[0]["date"] if all_observations else None
    tracking_end   = all_observations[-1]["date"] if all_observations else None

    today_str = date.today().isoformat()
    active_meds = [
        m for m in all_meds
        if m["start_date"] <= today_str and
           (m.get("end_date") is None or m["end_date"] >= today_str)
    ]

    uv_all = []
    if tracking_start and tracking_end:
        uv_all = db.get_uv_data_range(tracking_start, tracking_end)

    chart_dataset = {
        "dates": [o["date"] for o in all_observations],
        "sleep": [o.get("hours_slept") for o in all_observations],
        "bbt":   [o.get("basal_temp_delta") for o in all_observations],
        "uv":    {u["date"]: u.get("uv_noon") for u in uv_all},
    }

    if query:
        q = query.lower()

        # Daily entries
        for o in all_observations:
            fields = [
                o.get("notes") or "",
                o.get("neuro_notes") or "",
                o.get("cognitive_notes") or "",
                o.get("musculature_notes") or "",
                o.get("migraine_notes") or "",
                o.get("air_hunger_notes") or "",
                o.get("derm_notes") or "",
                o.get("emotional_notes") or "",
            ]
            combined = " ".join(fields).lower()
            if q in combined:
                snippet = next(
                    (f.strip() for f in fields if q in f.lower() and f.strip()),
                    ""
                )
                grouped["daily"].append({
                    "id":      f"daily_{o['date']}",
                    "date":    o["date"],
                    "type":    "daily",
                    "title":   "daily entry",
                    "snippet": snippet[:200] if snippet else combined[:200],
                    "pain":    o.get("pain_scale"),
                    "fatigue": o.get("fatigue_scale"),
                })
                total += 1

        # Lab results
        labs = db.get_lab_results()
        for lab in labs:
            fields = [
                lab.get("test_name") or "",
                lab.get("notes") or "",
                lab.get("provider") or "",
                lab.get("lab_facility") or "",
            ]
            combined = " ".join(fields).lower()
            if q in combined:
                val = (f"{lab['numeric_value']} {lab['unit'] or ''}".strip()
                       if lab.get("numeric_value") is not None
                       else lab.get("qualitative_result") or "")
                grouped["labs"].append({
                    "id":      f"lab_{lab['id']}",
                    "date":    lab["date"],
                    "type":    "lab",
                    "title":   lab["test_name"],
                    "snippet": f"{val} — {lab.get('notes') or lab.get('provider') or ''}".strip(" —"),
                })
                total += 1

        # Clinical events
        events = db.get_clinical_events()
        for e in events:
            fields = [
                e.get("notes") or "",
                e.get("provider") or "",
                e.get("facility") or "",
                e.get("event_type") or "",
            ]
            combined = " ".join(fields).lower()
            if q in combined:
                snippet = next(
                    (f.strip() for f in fields if q in f.lower() and f.strip()),
                    ""
                )
                grouped["events"].append({
                    "id":      f"event_{e['id']}",
                    "date":    e["date"],
                    "type":    "event",
                    "title":   f"{e['event_type']} — {e.get('provider') or e.get('facility') or ''}".strip(" —"),
                    "snippet": snippet[:200],
                })
                total += 1

        # Medications
        for med in all_meds:
            fields = [
                med.get("drug_name") or "",
                med.get("indication") or "",
                med.get("notes") or "",
            ]
            combined = " ".join(fields).lower()
            if q in combined:
                dose_str = f"{med.get('dose') or ''} {med.get('unit') or ''} {med.get('frequency') or ''}".strip()
                grouped["medications"].append({
                    "id":      f"med_{med['id']}",
                    "date":    med["start_date"],
                    "type":    "medication",
                    "title":   med["drug_name"],
                    "snippet": f"{dose_str} — {med.get('indication') or ''}".strip(" —"),
                })
                total += 1

        for key in grouped:
            grouped[key].sort(key=lambda x: x["date"], reverse=True)

    return render_template(
        "search.html",
        query=query,
        grouped=grouped,
        total=total,
        tracking_start=tracking_start,
        tracking_end=tracking_end,
        active_meds=active_meds,
        chart_dataset_json=json.dumps(chart_dataset),
        patient_name=CONFIG.get("patient_name", ""),
    )
    
# ============================================================
# Data Management & Export
# ============================================================

import zipfile
import shutil
from pathlib import Path
from datetime import datetime

@app.route("/export/all-data")
def export_all_data():
    """Export complete database and all data as ZIP file."""
    
    # Create temporary directory for exports
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_dir = Path(f"/tmp/biotracking_export_{timestamp}")
    temp_dir.mkdir(exist_ok=True)
    zip_path = None  # Initialize here
    
    try:
        # 1. Copy SQLite database
        db_path = Path("biotracking.db")  # Adjust to your actual DB path
        if db_path.exists():
            shutil.copy(db_path, temp_dir / "biotracking.db")
        
        # 2. Export all tables as CSV
        export_csvs_to_directory(temp_dir)
        
        # 3. Create ZIP file
        zip_path = temp_dir.parent / f"biotracking_backup_{timestamp}.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in temp_dir.rglob('*'):
                if file.is_file():
                    zipf.write(file, file.relative_to(temp_dir))
        
        # 4. Send ZIP file
        return send_file(
            zip_path,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'biotracking_backup_{timestamp}.zip'
        )
    
    finally:
        # Cleanup temp directory
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        if zip_path and zip_path.exists():  # Check if zip_path was created
            zip_path.unlink()
        


def export_csvs_to_directory(directory: Path):
    """Export all database tables as CSV files to a directory."""
    
    # Daily observations
    daily_obs = db.get_all_observations()  # You'll need this function in db.py
    write_csv(directory / "daily_observations.csv", daily_obs, [
        'date', 'sun_exposure_min', 'neurological', 'musculature', 'migraine',
        'cognitive', 'dermatological', 'pulmonary', 'rheumatic', 'gastro', 'mucosal',
        'pain_scale', 'fatigue_scale', 'emotional_state', 'flare_occurred',
        'basal_temp_delta', 'hours_slept', 'hrv', 'steps', 'notes'
    ])
    
    # Labs
    labs = db.get_lab_results()
    write_csv(directory / "labs.csv", labs, [
        'date', 'test_name', 'numeric_value', 'unit', 'qualitative_result',
        'reference_range', 'flag', 'provider', 'lab_facility', 'notes'
    ])
    
    # Medications
    meds = db.get_all_medications()
    write_csv(directory / "medications.csv", meds, [
        'drug_name', 'dose', 'unit', 'frequency', 'route', 'category',
        'indication', 'start_date', 'end_date', 'is_primary_intervention',
        'is_secondary_intervention', 'notes'
    ])
    
    # Events
    events = db.get_clinical_events()
    write_csv(directory / "events.csv", events, [
        'date', 'event_type', 'provider', 'facility', 'follow_up_date', 'notes'
    ])
    
    # Clinicians
    clinicians = db.get_all_clinicians()
    write_csv(directory / "clinicians.csv", clinicians, [
        'name', 'specialty', 'clinic_name', 'phone', 'email', 'network',
        'address', 'notes'
    ])
    
    # ANA results
    ana_results = db.get_ana_results()
    write_csv(directory / "ana_results.csv", ana_results, [
        'date', 'titer', 'screen_result', 'patterns', 'provider', 'notes'
    ])


def write_csv(filepath: Path, data: list, columns: list):
    """Write data to CSV file."""
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    
    for row in data:
        writer.writerow([row.get(col, '') for col in columns])
    
    filepath.write_text(output.getvalue())

# ============================================================
# Clinical Report
# ============================================================

def generate_findings(observations, uv_data, start_date, end_date, n_obs=None):
    """Auto-generate clinical findings from data."""
    import numpy as np
    from scipy import stats

    findings = []
    if n_obs is None:
        n_obs = len(observations)

    # UV lag correlation for period
    if len(observations) >= 10 and len(uv_data) >= 10:
        obs_by_date = {o["date"]: o for o in observations}
        uv_by_date  = {u["date"]: u for u in uv_data}

        dates_with_both = [d for d in obs_by_date
                           if d in uv_by_date and uv_by_date[d].get("uv_noon")]

        if len(dates_with_both) >= 10:
            uv_vals = []
            muscle_vals = []
            for d in dates_with_both:
                uv = uv_by_date[d].get("uv_noon")
                muscle = obs_by_date[d].get("musculature")
                if uv is not None and muscle is not None:
                    uv_vals.append(float(uv))
                    muscle_vals.append(float(muscle))

            if len(uv_vals) >= 8:
                r, p = stats.pearsonr(np.array(uv_vals), np.array(muscle_vals))
                if p < 0.01 and abs(r) >= 0.15:
                    findings.append({
                        "type": "uv_correlation",
                        "text": f"UV exposure shows significant same-day correlation with musculature symptoms (r={r:.3f}, p={p:.4f}, n={len(uv_vals)})."
                    })

    # Flare frequency
    if observations:
        flare_n = sum(1 for o in observations if o.get('flare_occurred') == 1)
        period_days = max(
            (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days, 1
        )
        per_month = round(flare_n / period_days * 30, 1)
        if flare_n > 0:
            findings.append({
                'type': 'flare_frequency',
                'text': f'{flare_n} flare{"s" if flare_n != 1 else ""} recorded in this period '
                        f'({per_month}/month over {period_days} days).'
            })
        else:
            findings.append({'type': 'flare_frequency', 'text': 'No flares recorded in this period.'})

    # Highest-burden symptom category
    if observations and n_obs:
        sym_counts = {
            key: sum(1 for o in observations if o.get(key))
            for key in ['neurological', 'cognitive', 'musculature', 'migraine',
                        'pulmonary', 'dermatological', 'rheumatic', 'gastro', 'mucosal']
        }
        labels = {
            'neurological': 'Neurological', 'cognitive': 'Cognitive',
            'musculature': 'Musculature', 'migraine': 'Migraine',
            'pulmonary': 'Pulmonary', 'dermatological': 'Dermatological',
            'rheumatic': 'Rheumatic', 'gastro': 'Gastrointestinal', 'mucosal': 'Mucosal'
        }
        top = max(sym_counts, key=sym_counts.get)
        top_pct = round(sym_counts[top] / n_obs * 100)
        if sym_counts[top] > 0:
            findings.append({
                'type': 'symptom_burden',
                'text': f'{labels[top]} symptoms were the most frequently reported category, '
                        f'present on {sym_counts[top]} of {n_obs} days ({top_pct}%).'
            })

        # Neurological involvement — flag for rheumatology
        neuro_n = sym_counts.get('neurological', 0)
        neuro_pct = round(neuro_n / n_obs * 100)
        if neuro_pct >= 10:
            findings.append({
                'type': 'neurological',
                'text': f'Neurological symptoms present on {neuro_n} of {n_obs} days ({neuro_pct}%). '
                        f'This may warrant neurology consultation or expanded ANA panel.'
            })

    # Medications started during this period
    all_meds = db.get_all_medications()
    meds_started = [m for m in all_meds if start_date <= m['start_date'] <= end_date]
    for med in meds_started:
        dose_str = f"{med.get('dose', '') or ''} {med.get('unit', '') or ''}".strip()
        indication = f" — {med['indication']}" if med.get('indication') else ''
        findings.append({
            'type': 'medication_change',
            'text': f"{med['drug_name']}{(' ' + dose_str) if dose_str else ''} "
                    f"started {med['start_date']}{indication}."
        })

    return findings

# ============================================================
# UV correlated report generation
# ============================================================

@app.route("/report")
def clinical_report():
    """Standalone clinical report page with auto-generated findings."""
    # Date range - default last 90 days
    end_date = request.args.get("end", date.today().isoformat())
    start_date = request.args.get(
        "start",
        (date.today() - timedelta(days=90)).isoformat()
    )
    
    # Fetch data for period
    observations = [o for o in db.get_all_daily_observations()
                    if start_date <= o["date"] <= end_date]
    
    uv_data = db.get_uv_data_range(start_date, end_date) if observations else []
    
    # Active medications
    all_meds = db.get_all_medications()
    today_str = date.today().isoformat()
    active_meds = [m for m in all_meds
                   if m["start_date"] <= today_str and
                      (m.get("end_date") is None or m["end_date"] >= today_str)]
    
    # Flagged lab abnormals in period
    all_labs = db.get_lab_results()
    flagged_labs = [lab for lab in all_labs
                    if start_date <= lab["date"] <= end_date
                    and lab.get("flag") in ("high", "low", "critical", "abnormal")]
    
    # Clinical events in period
    all_events = db.get_clinical_events()
    events = [e for e in all_events
              if start_date <= e["date"] <= end_date]
    events.sort(key=lambda x: x["date"], reverse=True)
    
    # Mean pain/fatigue for period
    pain_vals = [o.get("pain_scale") for o in observations
                 if o.get("pain_scale") is not None]
    fatigue_vals = [o.get("fatigue_scale") for o in observations
                    if o.get("fatigue_scale") is not None]
    
    mean_pain = round(sum(pain_vals) / len(pain_vals), 1) if pain_vals else None
    mean_fatigue = round(sum(fatigue_vals) / len(fatigue_vals), 1) if fatigue_vals else None

    # Flare summary
    flare_days = [o for o in observations if o.get('flare_occurred') == 1]
    flare_count = len(flare_days)
    flare_dates = sorted(o['date'] for o in flare_days)
    recent_flare = flare_dates[-1] if flare_dates else None

    # Symptom frequency (only categories present at least once)
    SYMPTOM_KEYS = [
        ('neurological',   'Neurological'),
        ('cognitive',      'Cognitive'),
        ('musculature',    'Musculature'),
        ('migraine',       'Migraine'),
        ('pulmonary',      'Pulmonary'),
        ('dermatological', 'Dermatological'),
        ('rheumatic',      'Rheumatic'),
        ('gastro',         'Gastrointestinal'),
        ('mucosal',        'Mucosal'),
    ]
    n_obs = len(observations)
    symptom_freq = sorted(
        [
            {'name': label, 'count': count,
             'percent': round(count / n_obs * 100) if n_obs else 0}
            for key, label in SYMPTOM_KEYS
            if (count := sum(1 for o in observations if o.get(key)))
        ],
        key=lambda x: x['count'], reverse=True
    )

    # ANA — all-time positive results only (negatives excluded; ANA fluctuates in early disease)
    all_ana = db.get_ana_results() if hasattr(db, 'get_ana_results') else []
    positive_ana = sorted(
        [a for a in all_ana
         if (a.get('screen_result') or '').lower().strip()
            not in ('negative', 'neg', 'nonreactive', '')],
        key=lambda a: a['date']
    )

    # Auto-generated findings
    findings = generate_findings(observations, uv_data, start_date, end_date, n_obs)
    
    # UV lag correlations for this period
    correlations = compute_lag_correlations(observations, uv_data) if observations and uv_data else {}
    
    # Full tracking period
    all_obs = db.get_all_daily_observations()
    tracking_start = all_obs[0]["date"] if all_obs else None
    tracking_end   = all_obs[-1]["date"] if all_obs else None
    
    # Primary intervention for report context
    primary_intervention = CONFIG.get("primary_intervention") or {}
    intervention_name = primary_intervention.get("name")
    intervention_date = primary_intervention.get("start_date")
    
    return render_template(
        "report.html",
        start_date=start_date,
        end_date=end_date,
        tracking_start=tracking_start,
        tracking_end=tracking_end,
        patient_name=CONFIG.get("patient_name", ""),
        primary_intervention_name=intervention_name,
        primary_intervention_date=intervention_date,
        observations=observations,
        active_meds=active_meds,
        flagged_labs=flagged_labs,
        events=events,
        mean_pain=mean_pain,
        mean_fatigue=mean_fatigue,
        flare_count=flare_count,
        flare_dates=flare_dates,
        recent_flare=recent_flare,
        symptom_freq=symptom_freq,
        n_obs=n_obs,
        positive_ana=positive_ana,
        findings=findings,
        correlations_json=json.dumps(correlations),
        today=date.today().strftime("%B %d, %Y"),
    )
# ============================================================
# API endpoints for Chart.js (JSON only)
# ============================================================

@app.route("/api/timeline")
def api_timeline():
    """JSON endpoint for timeline chart data."""
    end_date = request.args.get("end", date.today().isoformat())
    start_date = request.args.get(
        "start",
        (date.today() - timedelta(days=90)).isoformat()
    )
    data = db.get_timeline_data(start_date, end_date)
    return jsonify(data)


@app.route("/api/uv-lag")
def api_uv_lag():
    """JSON endpoint for UV lag correlation data."""
    observations = db.get_all_daily_observations()
    if not observations:
        return jsonify({"error": "no data"})
    start = observations[0]["date"]
    end = observations[-1]["date"]
    uv_data = db.get_uv_data_range(start, end)
    return jsonify({"observations": observations, "uv": uv_data})

# ============================================================
# DELETE ALL DATA
# ============================================================

@app.route("/delete/all-data", methods=["POST"])
def delete_all_data():
    """
    NUCLEAR OPTION: Delete ALL tracking data.
    This is irreversible and should only be called after multiple confirmations.
    """
    try:
        # Close any open connections
        db.close_all_connections()  
        
        # Delete the SQLite database file
        db_path = Path("biotracking.db")
        if db_path.exists():
            db_path.unlink()
        
        # Recreate empty database with schema
        from setup import create_database
        create_database()
        
        return jsonify({"success": True, "message": "All data deleted"}), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    print("\nbiotracking")
    print("===========")
    print(f"Patient: {CONFIG.get('patient_name', 'not set')}")
    print(f"Starting server...")
    print(f"\nLocal:  http://localhost:5000")
    print(f"Phone:  connect to same wifi, visit http://<your-mac-ip>:5000\n")

    app.run(
        host="0.0.0.0",   # accessible from phone on same network
        port=5000,
        debug=True,        # set to False when you want cleaner output
    )
    