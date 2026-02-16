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

@app.route("/uv-lag")
def uv_lag():
    """UV lag correlation analysis view."""
    # Default to all available data
    observations = db.get_all_daily_observations()
    if not observations:
        return render_template("uv_lag.html", has_data=False)

    start_date = observations[0]["date"]
    end_date = observations[-1]["date"]
    uv_data = db.get_uv_data_range(start_date, end_date)

    return render_template(
        "uv_lag.html",
        has_data=True,
        observations_json=json.dumps(observations, default=str),
        uv_json=json.dumps(uv_data, default=str),
    )


# ============================================================
# HRV and autonomic
# ============================================================

@app.route("/hrv")
def hrv_view():
    """HRV trend vs symptom load view."""
    observations = db.get_all_daily_observations()
    return render_template(
        "hrv.html",
        observations_json=json.dumps(observations, default=str),
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
    """Keyword search across all note fields."""
    query = request.args.get("q", "").strip()
    results = db.search_notes(query) if query else []
    return render_template("search.html", query=query, results=results)


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