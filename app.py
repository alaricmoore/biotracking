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

import json
import os
from datetime import date, datetime, timedelta

from flask import Flask, jsonify, render_template, request, redirect, url_for

import db
import uv_fetcher


app = Flask(__name__)


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
# Template context - available in every template
# ============================================================

@app.context_processor
def inject_globals():
    """Inject values available in every template."""
    return {
        "patient_name": CONFIG.get("patient_name", ""),
        "today": date.today().isoformat(),
        "app_version": CONFIG.get("app_version", "2.0.0"),
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
    """Daily entry form. Auto-fetches UV for today on load."""
    today_str = date.today().isoformat()

    # Auto-fetch and store today's UV index
    uv = uv_fetcher.fetch_and_store_uv_for_date(today_str)

    # Load any existing entry for today (for pre-population on re-entry)
    existing = db.get_daily_observation(today_str)

    # Load active medications for the sidebar
    active_meds = db.get_active_medications()

    return render_template(
        "daily_entry.html",
        entry_date=today_str,
        existing=existing,
        uv=uv,
        active_meds=active_meds,
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
        "air_hunger": get_bool("air_hunger"),
        "air_hunger_notes": form.get("air_hunger_notes", "").strip() or None,
        "dermatological": get_bool("dermatological"),
        "derm_notes": form.get("derm_notes", "").strip() or None,
        "word_loss": get_bool("word_loss"),
        "strike_physical": get_bool("strike_physical"),
        "strike_environmental": get_bool("strike_environmental"),
        "flare_occurred": get_bool("flare_occurred"),
        "notes": form.get("notes", "").strip() or None,
    }

    db.upsert_daily_observation(data)
    return redirect(url_for("daily_confirm", entry_date=data["date"]))


@app.route("/daily/confirm/<entry_date>")
def daily_confirm(entry_date):
    """Confirmation screen after daily entry submission."""
    entry = db.get_daily_observation(entry_date)
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

    return render_template(
        "timeline.html",
        start_date=start_date,
        end_date=end_date,
        # Pass as JSON for Chart.js
        timeline_json=json.dumps(data, default=str),
    )


# ============================================================
# UV lag analysis
# ============================================================

def compute_lag_correlations(observations: list, uv_data: list) -> dict:
    """Compute Pearson correlation between UV noon and each symptom
    at lag windows of 0, 1, 2, and 3 days.

    UV on day D is correlated against symptom on day D+lag.
    A high correlation at lag=2 means UV exposure predicts
    that symptom two days later.

    Args:
        observations: list of daily_observation dicts
        uv_data: list of uv_data dicts

    Returns:
        dict of {symptom_name: {lag_0: r, lag_1: r, lag_2: r, lag_3: r}}
        r values are Pearson correlation coefficients (-1 to 1)
        None means insufficient data for that lag/symptom combination
    """
    import numpy as np
    from scipy import stats

    # Build date-indexed lookups
    obs_by_date = {o["date"]: o for o in observations}
    uv_by_date  = {u["date"]: u for u in uv_data}

    # Sorted date list that has both UV and observation data
    dates_with_both = sorted([
        d for d in obs_by_date
        if d in uv_by_date and uv_by_date[d].get("uv_noon") is not None
    ])

    if len(dates_with_both) < 10:
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
        "air_hunger":    lambda o: o.get("air_hunger"),
        "flare":         lambda o: o.get("flare_occurred"),
    }

    lag_days = [0, 1, 2, 3]
    results = {}

    for symptom_name, getter in targets.items():
        results[symptom_name] = {}

        for lag in lag_days:
            uv_vals = []
            sym_vals = []

            for i, date_str in enumerate(dates_with_both):
                # UV on this date
                uv_noon = uv_by_date[date_str].get("uv_noon")
                if uv_noon is None:
                    continue

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

                uv_vals.append(float(uv_noon))
                sym_vals.append(float(sym_val))

            # Need at least 8 paired observations for meaningful correlation
            if len(uv_vals) < 8:
                results[symptom_name][f"lag_{lag}"] = None
                continue

            uv_arr  = np.array(uv_vals)
            sym_arr = np.array(sym_vals)

            # Skip if no variance (all zeros e.g. rare symptom)
            if uv_arr.std() == 0 or sym_arr.std() == 0:
                results[symptom_name][f"lag_{lag}"] = None
                continue

            r, p_value = stats.pearsonr(uv_arr, sym_arr)
            results[symptom_name][f"lag_{lag}"] = {
                "r":       round(float(r), 3),
                "p":       round(float(p_value), 4),
                "n":       len(uv_vals),
                "significant": float(p_value) < 0.01 and abs(float(r)) >= 0.15,
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


@app.route("/hrv")
def hrv_view():
    """HRV trend with rolling average, intervention split, and sleep/BBT/UV."""
    observations = db.get_all_daily_observations()
    
    # Read primary intervention from config
    primary_intervention = CONFIG.get("primary_intervention") or {}
    intervention_name = primary_intervention.get("name", "intervention")
    intervention_date = primary_intervention.get("start_date")
    
    hrv_data = compute_hrv_data(observations, intervention_date)
    sleep_bbt_uv = compute_sleep_bbt_uv(observations)
    
    # Get other notable medication starts for reference lines
    all_meds = db.get_all_medications()
    other_interventions = [
        {"drug_name": m["drug_name"], "start_date": m["start_date"]}
        for m in all_meds
        if m.get("start_date") and
           m.get("start_date") != intervention_date and
           m.get("category") in ("prescription", "injection")
    ]
    
    return render_template(
        "hrv.html",
        has_data=bool(hrv_data),
        hrv_json=json.dumps(hrv_data, default=lambda x: int(x) if isinstance(x, bool) else str(x)),
        sleep_json=json.dumps(sleep_bbt_uv, default=lambda x: int(x) if isinstance(x, bool) else str(x)),
        primary_intervention_name=intervention_name,
        primary_intervention_date=intervention_date,
        other_interventions_json=json.dumps(other_interventions),
    )


# ============================================================
# Clinical record
# ============================================================

@app.route("/clinical")
def clinical_record():
    """Clinical record - labs, ANA, meds, events."""
    labs = db.get_lab_results()
    ana = db.get_ana_results()
    meds = db.get_all_medications()
    events = db.get_clinical_events()
    test_names = db.get_lab_test_names()

    return render_template(
        "clinical_record.html",
        labs=labs,
        ana=ana,
        meds=meds,
        events=events,
        test_names=test_names,
    )


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


@app.route("/clinical/medication/add", methods=["POST"])
def add_medication():
    """Add a medication course."""
    form = request.form
    data = {
        "drug_name": form.get("drug_name", "").strip(),
        "dose": float(form["dose"]) if form.get("dose", "").strip() else None,
        "unit": form.get("unit", "").strip() or None,
        "frequency": form.get("frequency", "").strip() or None,
        "route": form.get("route", "oral").strip(),
        "category": form.get("category", "prescription").strip(),
        "indication": form.get("indication", "").strip() or None,
        "start_date": form.get("start_date"),
        "end_date": form.get("end_date", "").strip() or None,
        "notes": form.get("notes", "").strip() or None,
    }
    db.add_medication(data)
    return redirect(url_for("clinical_record") + "#medications")


@app.route("/clinical/medication/end/<int:med_id>", methods=["POST"])
def end_medication(med_id):
    """Mark a medication as ended today."""
    end_date = request.form.get("end_date", date.today().isoformat())
    db.end_medication(med_id, end_date)
    return redirect(url_for("clinical_record") + "#medications")


# ============================================================
# Search
# ============================================================

@app.route("/search")
def search():
    """Keyword search across all note fields, grouped by source type."""
    query = request.args.get("q", "").strip()

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
        hcq_start=HCQ_START_DATE,
    )

# ============================================================
# Clinical Report
# ============================================================

def generate_findings(observations, uv_data, start_date, end_date):
    """Auto-generate clinical findings from data."""
    import numpy as np
    from scipy import stats
    
    findings = []
    
    # UV lag correlation for period
    if len(observations) >= 10 and len(uv_data) >= 10:
        obs_by_date = {o["date"]: o for o in observations}
        uv_by_date  = {u["date"]: u for u in uv_data}
        
        dates_with_both = [d for d in obs_by_date 
                           if d in uv_by_date and uv_by_date[d].get("uv_noon")]
        
        if len(dates_with_both) >= 10:
            # Same-day musculature correlation
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
    
    return findings


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
    
    # Auto-generated findings
    findings = generate_findings(observations, uv_data, start_date, end_date)
    
    # Chart data for period
    chart_dataset = {
        "dates": [o["date"] for o in observations],
        "sleep": [o.get("hours_slept") for o in observations],
        "bbt":   [o.get("basal_temp_delta") for o in observations],
        "uv":    {u["date"]: u.get("uv_noon") for u in uv_data},
    }
    
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
        findings=findings,
        chart_dataset_json=json.dumps(chart_dataset),
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