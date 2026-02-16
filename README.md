# biotracking

**A local-only health tracking application for patients navigating complex diagnostic journeys.**

Built for people who need to see patterns in their own data when the medical system isn't connecting the dots yet.

---

## Why This Exists

If you're here, you might be familiar with the diagnostic odyssey: symptoms that don't fit neatly into a single specialty, providers who dismiss correlations you can see clearly, test results that are "borderline" or "nonspecific," and the exhausting work of being your own medical detective.

This app exists because **tracking your health data shouldn't require a computer science degree**, and **your most sensitive health information shouldn't live in someone else's cloud**.

Biotracking helps you:

- Track daily symptoms, biometrics, and environmental factors (like UV exposure)
- Visualize correlations over time (e.g., does UV exposure predict symptom flares?)
- Generate clinical reports to bring to appointments
- Keep a longitudinal record of labs, medications, and clinical events
- **Keep all your data local** — nothing leaves your computer

This is not a medical product. This is a tool for **veracity seeking** — for people who need to make their invisible patterns visible.

---

## Important Disclaimers

### Not Medical Advice

This application is a **data tracking and visualization tool only**. It is not:

- A diagnostic tool
- Medical advice
- A replacement for professional medical care
- Approved, endorsed, or reviewed by any medical authority

**Always consult qualified healthcare providers for medical decisions.** This app helps you organize your own observations — what you do with that information is between you and your doctors.

### Privacy & Data Ethics

- **Your data never leaves your computer.** No cloud storage, no third-party APIs for health data, no analytics, no tracking.
- UV data comes from public weather APIs (Open-Meteo and Visual Crossing) using only your coordinates — no personal health information is transmitted.
- **You own your data.** The database is a standard SQLite file you can back up, export, or delete at any time.
- This is a single-user, local application. One instance per person, one database per instance.

**Do not use this application to track anyone's health data without their informed consent.**

---

## Features

### Data Tracking

- **Daily observations**: Pain, fatigue, symptoms by category, biometrics (HRV, sleep, basal temp), sun exposure
- **Clinical record**: Lab results, ANA titers, medications, clinical events
- **Auto-fetch UV data** for photosensitivity tracking
- **Import from Apple Health**: HRV, sleep hours, wrist temperature, daylight exposure

### Analysis & Visualization

- **Timeline view**: Pain, fatigue, and UV index over time with symptom flags
- **UV lag correlation**: Statistical analysis of UV exposure vs symptom onset with configurable lag windows
- **HRV trends**: Heart rate variability with pre/post medication comparison
- **Sleep/BBT/UV relationship**: 3-day rolling averages to identify patterns

### Reporting

- **Keyword search** across all notes, labs, and events
- **Generate clinical reports** from search results or date ranges
- **Printable summaries** with auto-generated findings, flagged labs, and event timelines

---

## Requirements

- **macOS, Linux, or Windows** (tested primarily on macOS)
- **Python 3.9 or later**
- **A web browser** (Chrome, Firefox, Safari, Edge — any modern browser)
- **Optional**: iPhone with Apple Health for biometric import

---

## Installation

### Step 1: Install Python

**macOS/Linux**: Python 3 is likely already installed. Open **Terminal** and check:

```bash
python3 --version
```

If you see `Python 3.9` or higher, you're good. If not, download from [python.org](https://www.python.org/downloads/).

**Windows**: Download Python from [python.org](https://www.python.org/downloads/) and make sure to check "Add Python to PATH" during installation.

---

### Step 2: Download Biotracking

**Option A: Download ZIP** (easiest if you're not familiar with git)

1. Go to the GitHub repository page
2. Click the green **Code** button
3. Click **Download ZIP**
4. Unzip the file to a folder you can find (like `Documents/biotracking`)

**Option B: Clone with git** (if you're comfortable with git)

```bash
git clone https://github.com/yourusername/biotracking.git
cd biotracking
```

---

### Step 3: Set Up the Application

Open **Terminal** (Mac/Linux) or **Command Prompt** (Windows), navigate to the biotracking folder, and run:

```bash
# Create a virtual environment (recommended)
python3 -m venv .venv

# Activate it
# Mac/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run first-time setup
python setup.py
```

The setup script will ask you for:

- **Your name** (for reports)
- **Location coordinates** (for UV data — you can find these by Googling "my coordinates" or using [latlong.net](https://www.latlong.net/))
- **Timezone** (e.g., `America/Chicago`, `America/New_York`, `Europe/London`)
- **Baseline body temperature** in Fahrenheit (your normal resting temp, usually around 97-99°F)

**Important for coordinates**: If you're in North America, your longitude should be **negative**. For example, Oklahoma City is `35.4676, -97.5164` (note the minus sign on longitude). The setup script will warn you if you forget.

---

### Step 4: Start the Application

```bash
python app.py
```

You should see:

```
biotracking
===========
Patient: Your Name
Starting server...

Local:  http://localhost:5000
Phone:  connect to same wifi, visit http://<your-mac-ip>:5000
```

**Open your browser** and go to `http://localhost:5000`

You should see the biotracking interface. Try adding today's entry to make sure everything works.

---

## Accessing from Your Phone

If you want to enter data from your phone while on the same WiFi network:

### Step 1: Find Your Computer's IP Address

**macOS**:

1. Open **System Settings** → **Network**
2. Click your connected network (WiFi or Ethernet)
3. Look for "IP Address" — it will be something like `192.168.1.147`

**Windows**:

1. Open **Command Prompt**
2. Type `ipconfig`
3. Look for "IPv4 Address" under your active connection

**Linux**:

```bash
hostname -I
```

### Step 2: Connect from Phone

1. Make sure your phone is on the **same WiFi network** as your computer
2. Open a browser on your phone
3. Go to `http://YOUR-IP-ADDRESS:5000` (replace with your actual IP)
4. Bookmark it for easy access

**Example**: If your IP is `192.168.1.147`, visit `http://192.168.1.147:5000`

---

## Importing Your Data

### From Apple Health

Biotracking can import HRV, sleep hours, wrist temperature, and daylight exposure from Apple Health.

#### Step 1: Export from Apple Health

1. Open the **Health** app on your iPhone
2. Tap your **profile picture** in the top right
3. Scroll down and tap **Export All Health Data**
4. Wait for the export to complete (can take a few minutes)
5. **AirDrop** the export to your Mac, or save to Files and transfer via iCloud

You'll get a file called `export.zip`. **Unzip it.**

#### Step 2: Use Health Export App (Recommended)

The raw Apple Health export is in XML format and difficult to work with. We recommend using the free **Health Export** app:

1. Download **Health Export** from the App Store (free tier is fine)
2. Select the metrics you want:
   - Heart Rate Variability (HRV)
   - Sleep Analysis
   - Apple Sleeping Wrist Temperature
   - Time in Daylight
3. Set the date range to cover your tracking period
4. Export as **CSV, daily average**
5. **AirDrop** or transfer the CSV to your computer

#### Step 3: Import the CSV

In Terminal, from the biotracking folder:

```bash
python import_apple_health.py path/to/your_export.csv
```

**Example**:

```bash
python import_apple_health.py ~/Downloads/health_export.csv
```

The script will:

- Fill in HRV, sleep, wrist temp, and daylight for existing observation dates
- Create new observation rows for dates that don't exist yet (use `--create-new` flag)
- Skip rows that already have data unless you use `--overwrite`

**Dry run first** to preview without writing:

```bash
python import_apple_health.py ~/Downloads/health_export.csv --dry-run
```

---

### From Your Own Symptom Tracker

If you've been tracking symptoms in a spreadsheet, you can import them. The CSV should have these columns:

**Required**:

- `Date` — in format YYYY-MM-DD, MM/DD/YYYY, or "Jul 22, 2025"

**Optional** (biotracking will map these automatically):

- Symptom flags: columns with headers like "Neurological (Y/N)", "Migraine (Y/N)" — values should be Y/N or yes/no
- Pain/fatigue scales: numeric 0-10 values
- Sleep hours: numeric hours
- Notes: any text column will be preserved

**Example CSV**:

```csv
Date,Pain (0-10),Fatigue (0-10),Neurological (Y/N),Notes
2025-07-22,4,5,Y,Bad headache after sun exposure
2025-07-23,3,4,N,Feeling better today
```

**Import it**:

```bash
python import_tracker.py path/to/your_tracker.csv --dry-run
python import_tracker.py path/to/your_tracker.csv  # for real
```

---

### Lab Results

If you have lab results in a CSV, the format should be:

```csv
Date,Test,Value,Units,Lab,Doctor
2021-04-16,C4,28,mg/dL,LabCorp,Dr. Smith
2021-04-16,anti-dsDNA,18.42,IU/mL,LabCorp,Dr. Smith
```

**Import**:

```bash
python import_labs.py path/to/labs.csv --dry-run
python import_labs.py path/to/labs.csv
```

The script auto-detects reference ranges and flags for common tests (C3, C4, CRP, ESR, anti-dsDNA, etc.).

---

### UV Data Backfill

After importing historical data, you'll want UV values for those dates. Run:

```bash
python backfill_uv.py
```

This fetches UV data from Visual Crossing for all dates that have observations but no UV data yet.

**Cost**: Visual Crossing's free tier allows 1000 records/day. Historical UV uses ~24 records per day, so you can backfill about 40 days for free. Beyond that, the metered plan is $0.0001/record (about $0.19 for 80 days).

You'll need a **free Visual Crossing API key**:

1. Sign up at [visualcrossing.com](https://www.visualcrossing.com/)
2. Get your API key from the dashboard
3. Add it to `config.json`:

   ```json
   "visual_crossing_key": "YOUR_KEY_HERE"
   ```

---

## Using the Application

### Daily Entry

Navigate to **today** in the top nav. You'll see:

- **UV strip** (auto-fetched for today)
- **Biometrics**: Sleep hours, HRV, basal temp delta, steps, sun exposure
- **Symptom toggles**: Click to enable, text field appears for notes
- **Scales**: Pain, fatigue, emotional state (drag sliders or type numbers)
- **Flare flags**: Physical/cognitive load, environmental triggers, flare occurrence
- **General notes**: Free text

Hit **save** when done. You can edit the same day multiple times — it updates the existing entry.

---

### Timeline

Shows pain, fatigue, and UV noon over time with:

- Symptom category flags (colored dots)
- HRV and basal temp trends
- Flare days marked with vertical bands

Use the date range picker to zoom in on specific periods.

---

### UV Lag Analysis

Calculates Pearson correlation between UV exposure and each symptom category at 0h, 24h, 48h, and 72h lag windows.

**Reading the results**:

- **r value**: Correlation coefficient (-1 to 1). Higher absolute value = stronger relationship.
- **Asterisk (*)**: Statistically significant (p < 0.01 and |r| ≥ 0.15)
- **Lag window**: The darkest/tallest bar shows when UV exposure is most predictive of that symptom

**Example**: If musculature shows `r=0.296*` at lag 0, that means UV exposure on a given day significantly correlates with muscle symptoms that same day.

---

### HRV & Autonomic

Shows:

- HRV trend with 7-day rolling average
- Pre/post medication comparison (if you're tracking a medication start date)
- HRV vs pain/fatigue overlays
- Sleep/basal temp/UV relationship (3-day rolling average)

---

### Clinical Record

Four tabs for entering:

- **Labs**: Test name, value, units, reference range, provider
- **ANA**: Titer, patterns (AC-2, AC-4, etc.), screen result
- **Medications**: Drug, dose, frequency, start/end dates
- **Events**: Encounters, procedures, ER visits, biopsies

Forms are collapsible — click "add entry" to expand.

---

### Search

Keyword search across all notes, labs, events, and medications. Results are grouped by type.

**Use it to**:

- Find all mentions of a specific medication or symptom
- Pull up notes from a particular provider
- Generate reports from selected entries (check boxes → "generate report")

---

### Report

Standalone clinical summary with:

- Patient info and date range
- Active medications
- Mean pain/fatigue for period
- Auto-generated findings (e.g., UV correlations)
- Flagged lab abnormalities
- Clinical events timeline
- UV/sleep/temp chart

Use the date range picker to scope the report (defaults to last 90 days). Hit **print / save PDF** to generate a document for appointments.

---

## Troubleshooting

### "Port 5000 is already in use"

macOS uses port 5000 for AirPlay. Edit `app.py` and change:

```python
port=5000,
```

to:

```python
port=5001,
```

Then visit `http://localhost:5001` instead.

---

### UV Data Shows All Zeros

**Check your longitude sign**. If you're in North America, longitude should be **negative**. For example:

- New York: `40.7128, -74.0060` (note the minus)
- Oklahoma City: `35.4676, -97.5164`
- Los Angeles: `34.0522, -118.2437`

Edit `config.json` and fix the sign, then run `python backfill_uv.py --force` to re-fetch.

---

### Can't Access from Phone

1. Make sure phone and computer are on the **same WiFi network**
2. Check that the app is running (`python app.py` in Terminal)
3. Verify you're using the correct IP address (run `hostname -I` on Mac/Linux)
4. Try `http://` not `https://`
5. Make sure there's no firewall blocking port 5000

---

### Import Script Says "No Module Named 'pandas'"

You're not in the virtual environment. Run:

```bash
source .venv/bin/activate  # Mac/Linux
.venv\Scripts\activate      # Windows
```

Then try the import again.

---

## Data Management

### Backup Your Data

Your data lives in two files:

- `biotracking.db` — the SQLite database
- `config.json` — your settings and API keys

**Back them up regularly**:

```bash
cp biotracking.db biotracking_backup_$(date +%Y%m%d).db
cp config.json config_backup.json
```

Store backups somewhere safe (external drive, encrypted cloud storage).

---

### Export Data

SQLite databases can be exported to CSV, JSON, or other formats using tools like:

- [DB Browser for SQLite](https://sqlitebrowser.org/) (GUI)
- Command line: `sqlite3 biotracking.db .dump > backup.sql`

---

### Reset Everything

If you want to start fresh:

```bash
rm biotracking.db config.json
python setup.py
```

**This deletes all your data.** Back up first if you might want it later.

---

## For Developers

### Contributing

This project welcomes contributions, especially from people with lived experience of diagnostic complexity. Areas where help is needed:

- Additional data import formats (Fitbit, Garmin, etc.)
- More correlation analysis methods
- PDF export improvements
- Accessibility improvements
- Documentation and tutorials

**Please open an issue before starting work on a major feature.**

---

### Project Structure

```
biotracking/
├── app.py              # Flask routes only
├── db.py               # All database operations
├── uv_fetcher.py       # UV API integration
├── setup.py            # First-run configuration
├── requirements.txt    # Python dependencies
├── .gitignore          # Keeps sensitive data out of git
├── config.json         # User settings (gitignored)
├── biotracking.db      # SQLite database (gitignored)
├── templates/          # HTML templates
│   ├── base.html
│   ├── daily_entry.html
│   ├── timeline.html
│   ├── uv_lag.html
│   ├── hrv.html
│   ├── clinical_record.html
│   ├── search.html
│   └── report.html
└── import_*.py         # Data import scripts
```

---

### Running Tests

(Tests not yet implemented — contributions welcome!)

---

## Philosophy

This application is built on a few core principles:

1. **Patients are the experts on their own bodies.** You know when something is wrong, even when tests are "normal."

2. **Correlation is worth investigating**, even when causation isn't proven. If UV exposure consistently precedes your symptoms, that pattern matters — regardless of whether a doctor believes you.

3. **Your data is yours.** No surveillance, no selling, no cloud lock-in. You can delete everything and walk away at any time.

4. **Invisible illness deserves visible evidence.** When your symptoms are dismissed as anxiety or "borderline," a longitudinal graph can shift the conversation.

5. **Diagnostic complexity is real.** Some conditions don't fit neatly into textbook presentations, and the diagnostic process can take years. Tools like this exist to help you survive that journey.

---

## Acknowledgments

Built by a person who is navigating the medical system with conditions that refuse to be simple.

Inspired by every patient who was told "your labs are normal" when they knew something was deeply wrong.

---

## License

MIT License - see LICENSE file for details.

**This is not medical software.** Use at your own risk. The authors are not responsible for any medical decisions made using this tool.

---

## Support

For bugs, feature requests, or questions:

- Open an issue on GitHub
- Check existing issues first — your question might already be answered

**This is a volunteer project.** Response times may vary.

---

**Take care of yourself. Trust your observations. Keep asking questions.**
