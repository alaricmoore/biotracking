"""
biotracking db.py
-----------------
All database logic lives here. Nothing else in the application
touches SQLite directly. Flask routes call these functions only.

All dates are stored and accepted as strings in YYYY-MM-DD format.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from typing import Optional


DB_FILE = "biotracking.db"


# ============================================================
# Connection management
# ============================================================

@contextmanager
def get_db():
    """Context manager for database connections.
    Automatically commits on success and rolls back on error.
    
    Usage:
        with get_db() as conn:
            conn.execute(...)
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def today():
    """Return today's date as YYYY-MM-DD string."""
    return date.today().isoformat()


# ============================================================
# daily_observations
# ============================================================

def upsert_daily_observations(data: dict) -> bool:
    """Insert or update a daily observation row.
    
    Args:
        data: dict with keys matching daily_observations columns.
              'date' is required. All other fields are optional.
    
    Returns:
        True on success.
    """
    if "date" not in data:
        raise ValueError("daily observation requires a 'date' field")

    fields = [
        "date", "steps", "hours_slept", "hrv", "basal_temp_delta",
        "sun_exposure_min", "pain_scale", "fatigue_scale",
        "emotional_state", "emotional_notes",
        "neurological", "neuro_notes",
        "cognitive", "cognitive_notes",
        "musculature", "musculature_notes",
        "migraine", "migraine_notes",
        "pulmonary", "pulmonary_notes",
        "rheumatic", "rheumatic_notes",
        "dermatological", "derm_notes",
        "mucosal", "mucosal_notes",
        "gastro", "gastro_notes",
        "strike_physical", "strike_environmental", "flare_occurred",
        "notes"
    ]

    # Only include fields present in data
    present = {k: data[k] for k in fields if k in data}
    columns = ", ".join(present.keys())
    placeholders = ", ".join(["?" for _ in present])
    updates = ", ".join([f"{k}=excluded.{k}" for k in present if k != "date"])

    sql = f"""
        INSERT INTO daily_observations ({columns})
        VALUES ({placeholders})
        ON CONFLICT(date) DO UPDATE SET {updates}
    """

    with get_db() as conn:
        conn.execute(sql, list(present.values()))

    return True


def get_daily_observations(date_str: str) -> Optional[dict]:
    """Fetch a single daily observation by date."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM daily_observations WHERE date = ?",
            (date_str,)
        ).fetchone()
    return dict(row) if row else None


def get_daily_observations_range(start_date: str, end_date: str) -> list[dict]:
    """Fetch all daily observations between two dates inclusive."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM daily_observations
               WHERE date BETWEEN ? AND ?
               ORDER BY date ASC""",
            (start_date, end_date)
        ).fetchall()
    return [dict(row) for row in rows]


def get_all_daily_observations() -> list[dict]:
    """Fetch all daily observations ordered by date."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_observations ORDER BY date ASC"
        ).fetchall()
    return [dict(row) for row in rows]

def get_all_observations():
    """Get all daily observations."""
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT * FROM daily_observations 
            ORDER BY date DESC
        """)
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


# ============================================================
# uv_data
# ============================================================

def upsert_uv_data(date_str: str, uv_morning: float, uv_noon: float,
                   uv_evening: float, source: str = "api") -> bool:
    """Insert or update UV data for a given date."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO uv_data (date, uv_morning, uv_noon, uv_evening, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                uv_morning=excluded.uv_morning,
                uv_noon=excluded.uv_noon,
                uv_evening=excluded.uv_evening,
                source=excluded.source
        """, (date_str, uv_morning, uv_noon, uv_evening, source))
    return True


def get_uv_data(date_str: str) -> Optional[dict]:
    """Fetch UV data for a specific date."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM uv_data WHERE date = ?", (date_str,)
        ).fetchone()
    return dict(row) if row else None


def get_uv_data_range(start_date: str, end_date: str) -> list[dict]:
    """Fetch UV data for a date range."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM uv_data
               WHERE date BETWEEN ? AND ?
               ORDER BY date ASC""",
            (start_date, end_date)
        ).fetchall()
    return [dict(row) for row in rows]


# ============================================================
# lab_results
# ============================================================

def add_lab_result(data: dict) -> int:
    """Insert a lab result. Returns the new row id."""
    required = {"date", "test_name"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"lab_result missing required fields: {missing}")

    if not data.get("numeric_value") and not data.get("qualitative_result"):
        raise ValueError("lab_result requires numeric_value or qualitative_result")

    fields = [
        "date", "test_name", "numeric_value", "unit",
        "qualitative_result", "reference_range", "flag",
        "provider", "lab_facility", "notes"
    ]
    present = {k: data[k] for k in fields if k in data}
    columns = ", ".join(present.keys())
    placeholders = ", ".join(["?" for _ in present])

    with get_db() as conn:
        cursor = conn.execute(
            f"INSERT INTO lab_results ({columns}) VALUES ({placeholders})",
            list(present.values())
        )
        return cursor.lastrowid


def get_lab_results(test_name: Optional[str] = None,
                    start_date: Optional[str] = None,
                    end_date: Optional[str] = None) -> list[dict]:
    """Fetch lab results, optionally filtered by test name and date range."""
    conditions = []
    params = []

    if test_name:
        conditions.append("test_name = ?")
        params.append(test_name)
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM lab_results {where} ORDER BY date ASC, test_name ASC",
            params
        ).fetchall()
    return [dict(row) for row in rows]


def get_lab_test_names() -> list[str]:
    """Return a sorted list of all distinct test names."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT test_name FROM lab_results ORDER BY test_name ASC"
        ).fetchall()
    return [row[0] for row in rows]


def delete_lab_result(result_id: int) -> bool:
    """Delete a lab result by id."""
    with get_db() as conn:
        conn.execute("DELETE FROM lab_results WHERE id = ?", (result_id,))
    return True


# ============================================================
# ana_results
# ============================================================

def add_ana_result(date_str: str, titer_integer: Optional[int],
                   screen_result: str, patterns: list[str],
                   provider: Optional[str] = None,
                   notes: Optional[str] = None) -> int:
    """Insert an ANA result. Patterns stored as JSON array.
    
    Args:
        date_str: YYYY-MM-DD
        titer_integer: titer as integer (40, 80, 160, etc.)
        screen_result: 'positive' or 'negative'
        patterns: list of AC codes e.g. ['AC-4', 'AC-29']
        provider: ordering provider name
        notes: free text
    
    Returns:
        New row id.
    """
    patterns_json = json.dumps(patterns)
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO ana_results
                (date, titer_integer, screen_result, patterns, provider, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (date_str, titer_integer, screen_result, patterns_json, provider, notes))
        return cursor.lastrowid


def get_ana_results(start_date: Optional[str] = None,
                    end_date: Optional[str] = None) -> list[dict]:
    """Fetch ANA results, with patterns deserialized to lists."""
    conditions = []
    params = []
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM ana_results {where} ORDER BY date ASC",
            params
        ).fetchall()

    results = []
    for row in rows:
        d = dict(row)
        d["patterns"] = json.loads(d["patterns"]) if d["patterns"] else []
        results.append(d)
    return results


# ============================================================
# clinical_events
# ============================================================

def add_clinical_event(data: dict) -> int:
    """Insert a clinical event. Returns new row id."""
    required = {"date", "event_type"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"clinical_event missing required fields: {missing}")

    fields = ["date", "event_type", "provider", "facility", "notes", "follow_up_date"]
    present = {k: data[k] for k in fields if k in data}
    columns = ", ".join(present.keys())
    placeholders = ", ".join(["?" for _ in present])

    with get_db() as conn:
        cursor = conn.execute(
            f"INSERT INTO clinical_events ({columns}) VALUES ({placeholders})",
            list(present.values())
        )
        return cursor.lastrowid


def get_clinical_events(event_type: Optional[str] = None,
                        start_date: Optional[str] = None,
                        end_date: Optional[str] = None) -> list[dict]:
    """Fetch clinical events, optionally filtered."""
    conditions = []
    params = []
    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM clinical_events {where} ORDER BY date ASC",
            params
        ).fetchall()
    return [dict(row) for row in rows]


# ============================================================
# medications
# ============================================================

def add_medication(data: dict) -> int:
    """Add a new medication."""
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO medications (
                drug_name, dose, unit, frequency, route, category,
                indication, start_date, end_date, notes,
                is_primary_intervention, is_secondary_intervention
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("drug_name"),
            data.get("dose"),
            data.get("unit"),
            data.get("frequency"),
            data.get("route"),
            data.get("category"),
            data.get("indication"),
            data.get("start_date"),
            data.get("end_date"),
            data.get("notes"),
            1 if data.get("is_primary_intervention") else 0,
            1 if data.get("is_secondary_intervention") else 0,
        ))
        return c.lastrowid


def end_medication(med_id: int, end_date: str) -> bool:
    """Mark a medication course as ended."""
    with get_db() as conn:
        conn.execute(
            "UPDATE medications SET end_date = ? WHERE id = ?",
            (end_date, med_id)
        )
    return True


def get_active_medications(as_of_date: Optional[str] = None) -> list[dict]:
    """Return medications active on a given date (default: today)."""
    as_of = as_of_date or today()
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM medications
            WHERE start_date <= ?
              AND (end_date IS NULL OR end_date >= ?)
            ORDER BY drug_name ASC
        """, (as_of, as_of)).fetchall()
    return [dict(row) for row in rows]


def get_all_medications() -> list[dict]:
    """Return full medication history ordered by start date."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM medications ORDER BY start_date ASC"
        ).fetchall()
    return [dict(row) for row in rows]


# ============================================================
# Full text search across note fields
# ============================================================

def search_notes(query: str) -> list[dict]:
    """Search across all note fields in daily_observations.
    
    Returns matching rows with date, source field, and matching text.
    Uses SQLite LIKE for broad compatibility.
    """
    patterns = f"%{query}%"
    results = []

    note_fields = [
        ("neuro_notes", "neurological"),
        ("cognitive_notes", "cognitive"),
        ("musculature_notes", "musculature"),
        ("migraine_notes", "migraine"),
        ("air_hunger_notes", "air hunger"),
        ("rheumatic_notes", "rheumatic"),
        ("word_loss_notes", "word loss"),
        ("derm_notes", "dermatological"),
        ("notes", "general"),
    ]

    with get_db() as conn:
        for field, label in note_fields:
            rows = conn.execute(
                f"""SELECT date, '{label}' as category, {field} as matched_text
                    FROM daily_observations
                    WHERE {field} LIKE ?
                    ORDER BY date ASC""",
                (patterns,)
            ).fetchall()
            results.extend([dict(row) for row in rows])

        # Also search clinical event notes
        rows = conn.execute(
            """SELECT date, event_type as category, notes as matched_text
               FROM clinical_events
               WHERE notes LIKE ?
               ORDER BY date ASC""",
            (patterns,)
        ).fetchall()
        results.extend([dict(row) for row in rows])

    # Sort all results by date
    results.sort(key=lambda x: x["date"])
    return results


# ============================================================
# Timeline query - joins everything for the timeline view
# ============================================================

def get_timeline_data(start_date: str, end_date: str) -> dict:
    """Fetch all data needed for the timeline view in one call.
    
    Returns a dict with keys:
        - daily: list of daily_observations
        - uv: list of uv_data
        - labs: list of lab_results
        - ana: list of ana_results
        - events: list of clinical_events
        - medications: list of medications active during this period
    """
    return {
        "daily": get_daily_observations_range(start_date, end_date),
        "uv": get_uv_data_range(start_date, end_date),
        "labs": get_lab_results(start_date=start_date, end_date=end_date),
        "ana": get_ana_results(start_date=start_date, end_date=end_date),
        "events": get_clinical_events(start_date=start_date, end_date=end_date),
        "medications": get_all_medications(),  # filtered in frontend by date
    }
    
    # Add these functions to db.py

def update_lab_result(lab_id: int, date: str, test_name: str,
                      numeric_value: Optional[float] = None,
                      unit: Optional[str] = None,
                      qualitative_result: Optional[str] = None,
                      reference_range: Optional[str] = None,
                      flag: Optional[str] = None,
                      provider: Optional[str] = None,
                      lab_facility: Optional[str] = None,
                      notes: Optional[str] = None) -> bool:
    """Update an existing lab result."""
    with get_db() as conn:
        conn.execute("""
            UPDATE lab_results
            SET date = ?,
                test_name = ?,
                numeric_value = ?,
                unit = ?,
                qualitative_result = ?,
                reference_range = ?,
                flag = ?,
                provider = ?,
                lab_facility = ?,
                notes = ?
            WHERE id = ?
        """, (date, test_name, numeric_value, unit, qualitative_result,
              reference_range, flag, provider, lab_facility, notes, lab_id))
    return True


def update_ana_result(ana_id: int, date: str,
                      titer: Optional[str] = None,
                      patterns: Optional[str] = None,
                      screen_result: Optional[str] = None,
                      provider: Optional[str] = None,
                      notes: Optional[str] = None) -> bool:
    """Update an existing ANA result."""
    with get_db() as conn:
        conn.execute("""
            UPDATE ana_results
            SET date = ?,
                titer_integer = ?,
                patterns = ?,
                screen_result = ?,
                provider = ?,
                notes = ?
            WHERE id = ?
        """, (date, titer, patterns, screen_result, provider, notes, ana_id))
    return True


def delete_ana_result(ana_id: int) -> bool:
    """Delete an ANA result."""
    with get_db() as conn:
        conn.execute("DELETE FROM ana_results WHERE id = ?", (ana_id,))
    return True


def update_clinical_event(event_id: int, date: str, event_type: str,
                          provider: Optional[str] = None,
                          facility: Optional[str] = None,
                          notes: Optional[str] = None) -> bool:
    """Update an existing clinical event."""
    with get_db() as conn:
        conn.execute("""
            UPDATE clinical_events
            SET date = ?,
                event_type = ?,
                provider = ?,
                facility = ?,
                notes = ?
            WHERE id = ?
        """, (date, event_type, provider, facility, notes, event_id))
    return True


def delete_clinical_event(event_id: int) -> bool:
    """Delete a clinical event."""
    with get_db() as conn:
        conn.execute("DELETE FROM clinical_events WHERE id = ?", (event_id,))
    return True


# ============================================================
# clinicians
# ============================================================

def add_clinician(data: dict) -> int:
    """Add a new clinician/provider."""
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO clinicians (
                name, specialty, clinic_name, address, 
                phone, email, network, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("name"),
            data.get("specialty"),
            data.get("clinic_name"),
            data.get("address"),
            data.get("phone"),
            data.get("email"),
            data.get("network"),
            data.get("notes"),
        ))
        return c.lastrowid


def get_all_clinicians() -> list[dict]:
    """Get all clinicians ordered by name."""
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT * FROM clinicians 
            ORDER BY name ASC
        """)
        return [dict(row) for row in c.fetchall()]


def update_clinician(clinician_id: int, name: str, specialty: str,
                     clinic_name: Optional[str] = None,
                     address: Optional[str] = None,
                     phone: Optional[str] = None,
                     email: Optional[str] = None,
                     network: Optional[str] = None,
                     notes: Optional[str] = None) -> bool:
    """Update an existing clinician."""
    with get_db() as conn:
        conn.execute("""
            UPDATE clinicians
            SET name = ?,
                specialty = ?,
                clinic_name = ?,
                address = ?,
                phone = ?,
                email = ?,
                network = ?,
                notes = ?
            WHERE id = ?
        """, (name, specialty, clinic_name, address, phone, email, network, notes, clinician_id))
    return True


def delete_clinician(clinician_id: int) -> bool:
    """Delete a clinician."""
    with get_db() as conn:
        conn.execute("DELETE FROM clinicians WHERE id = ?", (clinician_id,))
    return True


def update_medication(med_id: int, drug_name: str, start_date: str,
                     dose: Optional[float] = None,
                     unit: Optional[str] = None,
                     frequency: Optional[str] = None,
                     category: Optional[str] = None,
                     indication: Optional[str] = None,
                     end_date: Optional[str] = None,
                     notes: Optional[str] = None,
                     is_primary_intervention: bool = False,
                     is_secondary_intervention: bool = False) -> bool:
    """Update an existing medication."""
    with get_db() as conn:
        conn.execute("""
            UPDATE medications
            SET drug_name = ?,
                dose = ?,
                unit = ?,
                frequency = ?,
                category = ?,
                indication = ?,
                start_date = ?,
                end_date = ?,
                notes = ?,
                is_primary_intervention = ?,
                is_secondary_intervention = ?
            WHERE id = ?
        """, (drug_name, dose, unit, frequency, category, indication,
              start_date, end_date, notes,
              1 if is_primary_intervention else 0,
              1 if is_secondary_intervention else 0,
              med_id))
    return True


def delete_medication(med_id: int) -> bool:
    """Delete a medication."""
    with get_db() as conn:
        conn.execute("DELETE FROM medications WHERE id = ?", (med_id,))
    return True

def close_all_connections():
    """Close any open database connections."""
    # If you're using connection pooling, close the pool here
    # For basic sqlite3, this may not be necessary
    pass