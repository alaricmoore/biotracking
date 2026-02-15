"""
biotracking setup.py
--------------------
Run once to initialize the database and create your local config file.
Your config file will be created at config.json and is gitignored -
it will never be committed to GitHub.

Usage:
    python setup.py
"""

import json
import os
import sqlite3
import sys


CONFIG_FILE = "config.json"
DB_FILE = "biotracking.db"


def prompt(message, default=None):
    """Prompt the user for input with an optional default."""
    if default:
        result = input(f"{message} [{default}]: ").strip()
        return result if result else default
    result = input(f"{message}: ").strip()
    return result


def create_config():
    """Walk the user through creating their local config file."""
    print("\n--- biotracking first-time setup ---")
    print("This config file is gitignored and stays on your machine only.\n")

    config = {}

    config["patient_name"] = prompt("Your name or identifier (used in exports only)")

    print("\nLocation is used only to pull UV index data from a weather API.")
    print("It is stored locally in config.json and never sent with any health data.\n")
    config["location_lat"] = float(prompt("Latitude (e.g. 35.4676 for Oklahoma City)"))
    config["location_lon"] = float(prompt("Longitude (e.g. -97.5164 for Oklahoma City)"))
    config["timezone"] = prompt("Timezone", default="America/Chicago")

    print("\nBaseline values help calculate meaningful deltas over time.")
    config["temp_baseline_f"] = float(
        prompt("Your baseline wrist temperature in °F (e.g. 97.4)")
    )

    config["app_version"] = "2.0.0"

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\nConfig saved to {CONFIG_FILE} (gitignored - stays local)")
    return config


def create_database():
    """Create the SQLite database and all tables."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Enable WAL mode for better concurrent read performance
    c.execute("PRAGMA journal_mode=WAL")

    # --------------------------------------------------------
    # daily_observations
    # Core symptom and biometric data, one row per day
    # --------------------------------------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_observations (
            date                TEXT PRIMARY KEY,  -- YYYY-MM-DD
            steps               INTEGER,
            hours_slept         REAL,
            hrv                 REAL,
            basal_temp_delta    REAL,              -- deviation from personal baseline
            sun_exposure_min    INTEGER,           -- minutes, from Apple Health or manual
            pain_scale          REAL,              -- 0-10
            fatigue_scale       REAL,              -- 0-10
            emotional_state     REAL,              -- 0-10
            emotional_notes     TEXT,

            -- Neurological
            neurological        INTEGER DEFAULT 0, -- boolean
            neuro_notes         TEXT,

            -- Cognitive
            cognitive           INTEGER DEFAULT 0,
            cognitive_notes     TEXT,

            -- Musculature
            musculature         INTEGER DEFAULT 0,
            musculature_notes   TEXT,

            -- Migraine / headache
            migraine            INTEGER DEFAULT 0,
            migraine_notes      TEXT,

            -- Air hunger / chest discomfort
            air_hunger          INTEGER DEFAULT 0,
            air_hunger_notes    TEXT,

            -- Dermatological
            dermatological      INTEGER DEFAULT 0,
            derm_notes          TEXT,

            -- Word loss / stuttering
            word_loss           INTEGER DEFAULT 0,

            -- Flare tracking
            strike_physical     INTEGER DEFAULT 0, -- boolean
            strike_environmental INTEGER DEFAULT 0,
            flare_occurred      INTEGER DEFAULT 0,

            -- Catch-all
            notes               TEXT
        )
    """)

    # --------------------------------------------------------
    # uv_data
    # UV index by date, pulled from API or entered manually
    # --------------------------------------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS uv_data (
            date        TEXT PRIMARY KEY,  -- YYYY-MM-DD
            uv_morning  REAL,
            uv_noon     REAL,
            uv_evening  REAL,
            source      TEXT DEFAULT 'api' -- 'api' or 'manual'
        )
    """)

    # --------------------------------------------------------
    # lab_results
    # General labs - numeric or qualitative
    # --------------------------------------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS lab_results (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            date                TEXT NOT NULL,      -- YYYY-MM-DD
            test_name           TEXT NOT NULL,
            numeric_value       REAL,               -- nullable
            unit                TEXT,               -- nullable
            qualitative_result  TEXT,               -- 'positive', 'negative', etc.
            reference_range     TEXT,               -- e.g. '0-20 IU/mL'
            flag                TEXT,               -- 'high', 'low', 'abnormal', 'normal'
            provider            TEXT,
            lab_facility        TEXT,
            notes               TEXT
        )
    """)

    # --------------------------------------------------------
    # ana_results
    # ANA gets its own table due to titer + pattern complexity
    # --------------------------------------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS ana_results (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT NOT NULL,          -- YYYY-MM-DD
            titer_integer   INTEGER,                -- stored as int: 40, 80, 160
            screen_result   TEXT,                   -- 'positive' or 'negative'
            patterns        TEXT,                   -- JSON array: ["AC-4","AC-29"]
            provider        TEXT,
            notes           TEXT
        )
    """)

    # --------------------------------------------------------
    # clinical_events
    # Encounters, biopsies, injections, procedures
    # --------------------------------------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS clinical_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT NOT NULL,          -- YYYY-MM-DD
            event_type      TEXT NOT NULL,          -- 'encounter', 'biopsy', 'injection', 'procedure', 'other'
            provider        TEXT,
            facility        TEXT,
            notes           TEXT,
            follow_up_date  TEXT                    -- nullable YYYY-MM-DD
        )
    """)

    # --------------------------------------------------------
    # medications
    # Prescriptions, supplements, OTCs - one row per course
    # --------------------------------------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS medications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_name   TEXT NOT NULL,
            dose        REAL,
            unit        TEXT,                       -- 'mg', 'mcg', 'IU', etc.
            frequency   TEXT,                       -- 'daily', 'twice daily', 'as needed', etc.
            route       TEXT,                       -- 'oral', 'topical', 'nasal', 'IV', etc.
            category    TEXT,                       -- 'prescription', 'supplement', 'OTC'
            indication  TEXT,                       -- reason / purpose
            start_date  TEXT NOT NULL,              -- YYYY-MM-DD
            end_date    TEXT,                       -- nullable, null = currently active
            notes       TEXT
        )
    """)

    # --------------------------------------------------------
    # FTS5 virtual table for keyword search across note fields
    # --------------------------------------------------------
    c.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_search
        USING fts5(
            date,
            source_table,
            notes_text,
            content=''
        )
    """)

    conn.commit()
    conn.close()
    print(f"Database created at {DB_FILE} (gitignored - stays local)")


def verify_setup():
    """Quick sanity check that everything was created correctly."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in c.fetchall()]
    conn.close()

    expected = [
        "daily_observations",
        "uv_data",
        "lab_results",
        "ana_results",
        "clinical_events",
        "medications",
        "notes_search"
    ]

    missing = [t for t in expected if t not in tables]
    if missing:
        print(f"\nWarning: missing tables: {missing}")
        return False

    print(f"\nVerification passed. Tables created: {', '.join(expected)}")
    return True


def main():
    print("biotracking setup")
    print("=================")

    # Check for existing setup
    if os.path.exists(CONFIG_FILE) and os.path.exists(DB_FILE):
        confirm = input(
            "\nSetup files already exist. Re-run setup? "
            "This will NOT delete existing data. (y/n): "
        ).strip().lower()
        if confirm != "y":
            print("Setup cancelled.")
            sys.exit(0)

    create_config()
    create_database()
    verify_setup()

    print("\n--- Setup complete ---")
    print("Next steps:")
    print("  1. Activate your virtual environment: source .venv/bin/activate")
    print("  2. Install dependencies: pip install -r requirements.txt")
    print("  3. Run the app: python app.py")
    print("  4. Open your browser to: http://localhost:5000")
    print("\nTo access from your phone, connect to the same wifi network")
    print("and visit: http://<your-mac-ip>:5000")


if __name__ == "__main__":
    main()