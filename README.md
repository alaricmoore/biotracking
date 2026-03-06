# biotracking

A local-only health tracking application for patients navigating complex diagnostic journeys.

Built for people who need to see patterns in their own data when the medical system isn't connecting the dots yet.

(Well, built for one person who needed to see patterns, but she figured she couldn't be the only nut out there.)

---

## Why This Exists

It's easy to gaslight yourself into thinking you're having panic attacks and are lazy. And sometimes people have panic attacks and are lazy, and that's entirely normal.

But when the shortness of breath is uncoupled from emotion, when the "laziness" is less sloth and more that you're stuck in a quagmire of quicksand despite wanting to do *so much* -- there's something making your body react that way.

The sun was making me sick.

At least that was my intuition, but that seemed insane. I had low vitamin D for years and was told to get more sun. But like clockwork, high UV index days would leave me sick the next day, or two, or three. A sunburn put me in bed for a week with what felt like the flu.

I figured I was just getting older. Also I'm hella pale, maybe this was a white people thing no one had mentioned to me.

But coupled with a family history sprinkled with, and a genetic profile loaded for, SARDs and connective tissue disease associated alleles -- I decided to quantify it. Yes, it came to be seen by me through the data, that unfortunatley, very much so; The sun is making me sick.

That's why I started a spreadsheet. But it was useless in clinic -- rows upon rows of entries with no succinct way to visually communicate what they meant in a 15-minute appointment ,while exhausted and in pain and anxious about being dismissed again. After 90+ days I gave up. I got depressed. I kept getting sick. My sick leave was running dry at work, and with out a diagnosis I didn't feel confident that I could get FMLA protection.

Then I picked it back up. I can't remember exactly what the impetus was -- probably another rheumatologist doubting me while ER doctors were writing "I believe her condition to be rheumatic in nature", meanwhile my dermatologist was doing her damnedest to get the best biopsy shave for DIF this side of the Mississippi. Damn near the size of a mercury dime.

Claude Sonnet helped me build it. I'm not a strong coder -- I can get around, and I know how to make infinity while loops, but I'm far from skilled. An LLM assisted me in building the stack, troubleshooting bugs, and providing the kind of cognitive support I could direct, debug, and reiterate. And if Claude can be annoyed, I most certainly annoyed that poor tireless machine.

Meanwhile, I was in and out of doctors appointments and a few ER visits, and eventually arrived at a shiny new "cool, I was right" / "fuck, why do I have to be right about this?" diagnosis. Eight months from when I started aggressively seeking treatment to confirmed diagnosis. I beat the odds -- the average diagnostic delay is four to seven years. I'm lucky. A lot of people aren't.

My current diagnosis is acute cutaneous lupus erythematosus with systemic involvement, confirmed by biopsy and with woefully unremarkable serology. But autoimmune disease evolves, & we are constantly learning new things about the human body. The differential will shift. The ICD codes may change. Whether we end up calling it lupus or the Hokey Pokey Disease, getting that process *started* -- having longitudinal evidence, having dates, having correlations -- matters enormously for health outcomes down the road.

This tool isn't a lupus tracker, necessarily, though it is designed around an evolving case of predictably photosensitive lupus. It's a *you* tracker, the intent is you can change it to fit your case. Whatever you've got going on.

---

## What It Does

Biotracking helps you:

- Track daily symptoms, biometrics, and environmental factors (including UV exposure, in fact especially UV exposure)
- Visualize correlations over time (does UV exposure predict your symptom flares? does low HRV precede bad days?)
- Generate clinical reports to bring to appointments (when you know damn well your brain is not going to remember everything, plus it has graphs!)
- Keep a longitudinal record of labs, medications, & clinical events, as well a list of your clinicians
- Run flare forecasting based on your own historical patterns
- Visualize trends pre/post medical interventions such as hydroxychloriquine or steroids or biologics or what have you.
- Keep all your data local -- nothing leaves your computer, if you don't want it to.

This is not a medical product. This is a tool for veracity: for people who need to make their invisible patterns visible.

---

## Important Disclaimers

### Not Medical Advice

This application is a data tracking and visualization tool only. It is not:

- A diagnostic tool
- Medical advice
- A replacement for professional medical care
- Approved, endorsed, or reviewed by any medical authority

Always consult qualified healthcare providers for medical decisions. This app helps you organize your own observations -- what you do with that information is between you and your clinicians.

### Privacy & Data Ethics

- Your data never leaves your computer. No cloud storage, no third-party APIs for health data, no analytics, no tracking.
- UV data comes from public weather APIs (Open-Meteo and Visual Crossing) using only your coordinates —- no personal health information is transmitted.
- You own your data. The database is a standard SQLite file you can back up, export, or delete at any time.
- This is a single-user, local application. One instance per person, one database per instance.
- Do not use this application to track anyone's health data without their informed consent. Don't be creepy.

---

## Features

### Data Tracking

- Daily observations: pain, fatigue, symptoms by category, biometrics (HRV, sleep, basal temp), sun exposure
- Clinical record: lab results, ANA titers, medications, clinical events, clinician list
- Auto-fetch UV data for photosensitivity tracking
- Import from Apple Health: HRV, sleep hours, wrist temperature, daylight exposure
- Import from any CSV file iffn it's configured correctly for the import function.

### Analysis & Visualization

- Timeline view: pain, fatigue, and UV index over time with symptom flags
- UV lag correlation: statistical analysis of UV exposure vs symptom onset with configurable lag windows
- Flare forecasting: risk assessment based on your historical patterns
- HRV trends: heart rate variability with pre/post medication comparison
- Symptom comparison charts: adjustable, overlayable, yours
- Flare precursor analysis: what most commonly precedes your flares (UV? low HRV? poor sleep? all three?)
- Model accuracy assessment: self-grading analysis so you know how well your own model is predicting

### Reporting

- Keyword search across all notes, labs, and events
- Generate clinical reports from search results or date ranges
- Printable summaries with auto-generated findings, flagged labs, and event timelines
- Export all data: labs, medications, events, clinician list

### The Lab

There's a CLI "interface" hidden in the app where you can manually adjust the weights of symptom classes in the prediction model. Get it to 100% accuracy with no false positives or false negatives and you unlock achievements. It's in there because sometimes you need to feel like you have some control over something that usually feels uncontrollable. Plus it's 1337 haxor green. That's fun. I don't care what you say about it.

---

## Requirements

- macOS, Linux, or Windows (tested primarily on macOS and Linux... actually not tested on Windows. Sorry.)
- Python 3.9 or later (earlier veersions work, but watch your D's and d's)
- A web browser (Brave, Firefox, Safari, Edge, Opera, Tor...)
- Optional: iPhone with Apple Health for biometric import (I have an apple watch, because access to raw data for free and it's also a watch)

---

## Installation

### Step 1: Install Python

**macOS/Linux:** Python 3 is likely already installed. Open Terminal and check:

```bash
python3 --version
```

If you see Python 3.9 or higher, you're good. If not, download from [python.org](https://python.org).

**Windows:** Download Python from [python.org](https://python.org) and make sure to check "Add Python to PATH" during installation.

### Step 2: Download Biotracking

**Option A: Download ZIP (easiest if you're not familiar with git)**

1. Go to the GitHub repository page
2. Click the green **Code** button
3. Click **Download ZIP**
4. Unzip the file to a folder you can find (like `Documents/biotracking`)

**Option B: Clone with git**

```bash
git clone https://github.com/alaricmoore/biotracking.git
cd biotracking
```

### Step 3: Set Up the Application

Open Terminal (Mac/Linux) or Command Prompt (Windows), navigate to the biotracking folder, and run:

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

- Your name (for reports)
- Location coordinates (for UV data — you can find these by Googling "my coordinates" or using [latlong.net](https://latlong.net))
- Timezone (e.g., `America/Chicago`, `America/New_York`, `Europe/London`)
- Baseline body temperature in Fahrenheit (your normal resting temp, usually around 97-99°F)

> **Important for coordinates:** If you're in North America, your longitude should be negative. For example, Oklahoma City is `35.4676, -97.5164` (note the minus sign on longitude). The setup script will warn you if you forget.

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
Phone:  connect to same wifi, visit http://<your-ip>:5000
```

Open your browser and go to `http://localhost:5000`. Try adding today's entry to make sure everything works.

---

## Accessing from Your Phone

If you want to enter data from your phone while on the same WiFi network:

**Find your computer's IP address:**

- **macOS:** System Settings > Network > click your connection > look for IP Address
- **Windows:** Open Command Prompt, type `ipconfig`, look for "IPv4 Address"
- **Linux:** Run `hostname -I`

Then on your phone (same WiFi network), open a browser and go to `http://YOUR-IP-ADDRESS:5000`.

Bookmark it for easy access.

---

## Importing Your Data

### From Apple Health

Biotracking can import HRV, sleep hours, wrist temperature, and daylight exposure from Apple Health, or whatever else you are tracking. Which provides free-of-cost raw data downloads.

**Export from Apple Health:**

1. Open the Health app on your iPhone
2. Tap your profile picture in the top right
3. Scroll down and tap **Export All Health Data**
4. AirDrop the export to your Mac, or save to Files and transfer via iCloud
5. The file is going to be huge, just a warning.

**Recommended: Use the Health Export app (free tier is fine)**

1. Download [Health Export](https://apps.apple.com/app/health-export/id1477722520) from the App Store
2. Select: Heart Rate Variability, Sleep Analysis, Apple Sleeping Wrist Temperature, Time in Daylight
3. Set your date range, export as CSV daily average
4. Transfer the CSV to your computer
5. Also download period tracking if you desire. I haven't been because steroids ruined my cycle, but I will add that funcitonality soon.

**Import:**

```bash
python import_apple_health.py path/to/your_export.csv

# Preview without writing:
python import_apple_health.py ~/Downloads/health_export.csv --dry-run

# Create new rows for dates that don't exist yet:
python import_apple_health.py ~/Downloads/health_export.csv --create-new
```

### From Your Own Symptom Tracker

If you've been tracking in a spreadsheet, you can import it. Required column: `Date` (in YYYY-MM-DD, MM/DD/YYYY, or "Jul 22, 2025" format). Optional columns are mapped automatically for symptom flags, pain/fatigue scales, sleep hours, and notes.

```bash
python import_tracker.py path/to/your_tracker.csv --dry-run
python import_tracker.py path/to/your_tracker.csv
```

### Lab Results

```csv
Date,Test,Value,Units,Lab,Doctor
2021-04-16,C4,28,mg/dL,LabCorp,Dr. Smith
```

```bash
python import_labs.py path/to/labs.csv --dry-run
python import_labs.py path/to/labs.csv
```

The script auto-detects reference ranges and flags common tests (C3, C4, CRP, ESR, anti-dsDNA, etc.).

### UV Data Backfill

After importing historical data, fetch UV values for those dates:

```bash
python backfill_uv.py
```

You'll need a free [Visual Crossing](https://visualcrossing.com) API key. Add it to `config.json`:

```json
"visual_crossing_key": "YOUR_KEY_HERE"
```

> The free tier allows 1000 records/day. Historical UV uses ~24 records per day, so you can backfill about 40 days for free. Beyond that, the metered plan is $0.0001/record.

---

## Using the Application

### Daily Entry

Navigate to **today** in the top nav. Log:

- UV strip (auto-fetched)
- Biometrics: sleep hours, HRV, basal temp delta, steps, sun exposure
- Symptom toggles: click to enable, text field appears for notes
- Scales: pain, fatigue, emotional state
- Flare flags: physical/cognitive load, environmental triggers, flare occurrence (these help the model confirm positive/negative predicitons)
- General notes: free text

Hit save. You can edit the same day multiple times.

### Timeline

Pain, fatigue, and UV over time with symptom category flags, HRV and basal temp trends, and flare days marked. Use the date range picker to zoom in.

### Forecast

A model that attempts to forecast low/medium/high flare risk for that day based on historical trends, weighting of symptoms and triggers. Also comes with a model analysis and forecast prediciton grade. If you want to fiddle with things via the UI and not risk mungling the source, there might be like a game or something in there. Poke around.

### UV Lag Analysis

Pearson correlation between UV exposure and each symptom category at 0h, 24h, 48h, and 72h lag windows. Asterisked bars are statistically significant. The darkest bar shows when UV is most predictive of that symptom for you specifically.

### HRV & Autonomic

HRV trend with 7-day rolling average, pre/post medication comparison, HRV vs pain/fatigue overlays, sleep/basal temp/UV relationships. This is mainly because of my situation, but it's poorly studied so why not track it? (Requires wearable that can somewhat reliably report HRV/day)

### Clinical Record

Five tabs: Labs, ANA, Medications, Events, Clinicians. Everything dated, everything searchable, everything exportable.

### Search

Keyword search across all notes, labs, events, clinicians, and medications. Check boxes on results to generate a report from selected entries.

### Report

Standalone clinical summary with active medications, mean symptom burden, flagged lab abnormalities, clinical events timeline, and UV lag analysis chart. Hit **print / save PDF** to generate a document for appointments.

---

## Troubleshooting

**"Port 5000 is already in use"** (common on macOS which uses 5000 for AirPlay)

Edit `app.py` and change `port=5000` to `port=5001`, then visit `http://localhost:5001`.

**UV data shows all zeros**

Check your longitude sign. North America longitudes should be negative (e.g., Oklahoma City: `35.4676, -97.5164`). Edit `config.json` and run `python backfill_uv.py --force`.

**Can't access from phone**

Make sure phone and computer are on the same WiFi. Verify the app is running. Try `http://` not `https://`. Check there's no firewall blocking port 5000.

**"No module named 'pandas'"**

You're not in the virtual environment. Run `source .venv/bin/activate` (Mac/Linux) or `.venv\Scripts\activate` (Windows) first.

---

## Data Management

**Your data lives in two files:**

- `biotracking.db` — the SQLite database
- `config.json` — your settings and API keys

**Back them up:**

```bash
cp biotracking.db biotracking_backup_$(date +%Y%m%d).db
```

**Export options:**

- In-app: export buttons for labs, medications, events, clinician list (CSV)
- In-app UI delete function on search page (I have not actually tested the UI delete, but the full db export works)
- DB Browser for SQLite (GUI tool, free)
- Command line: `sqlite3 biotracking.db .dump > backup.sql`

**Reset everything:**

```bash
rm biotracking.db config.json
python setup.py
```

This deletes all your data. Back up first.

---

## For Developers

### Contributing

This project welcomes contributions, especially from people with lived experience of diagnostic complexity. Whether as patients, clinicians, loved ones, or those for whom this is their special interest.

Areas where help is needed:

- Additional data import formats (Fitbit, Garmin, etc.)
- More correlation analysis methods
- PDF export improvements
- Accessibility improvements
- Documentation and tutorials
- Translations
- New designs to include other evolving hard-to-diagnose disease that isn't my flavor of lupus.

Please open an issue before starting work on a major feature.

Also reach out to me at <alaric.moore@pm.me>

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
├── import_labs.py
├── import_tracker.py
├── import_apple_health.py
├── migrate_symptoms.py 
├── backfill_uv.py
├── biotracking.db      # SQLite database (gitignored)
├── templates/          # HTML templates
│   ├── base.html
│   ├── daily_entry.html
│   ├── timeline.html
│   ├── uv_lag.html
│   ├── hrv.html
│   ├── forecast_history.html
│   ├── forecast_accuracy.html
│   ├── forecast_lab.html
│   ├── forecast.html
│   ├── daily_confirm.html
│   ├── clinical_record.html
│   ├── search.html
│   └── report.html
└── import_*.py         # Data import scripts
```

---

## Philosophy

**Patients are the experts on their own bodies.** You know when something is wrong, even when tests are "normal." You also probably, for the most part, know the difference between normal and "oh no this is no good now." Trust that instinct.

**Correlation is worth investigating, even when causation isn't proven.** If UV exposure consistently precedes your symptoms, that pattern matters -- regardless of whether a doctor believes you yet. Or hell, you don't believe you yet.

**Your data is yours.** No surveillance, no selling, no cloud lock-in. You can delete everything and walk away at any time.

**Invisible illness deserves visible evidence.** When your symptoms are dismissed as anxiety or "borderline," a longitudinal graph can shift the conversation.

**Diagnostic complexity is real.** Some conditions take years to name. The average diagnostic delay for lupus alone is four to seven years, and it isn't even a particularly rare disease, merely uncommon. Tools like this exist to help you survive that journey and shorten it where and when possible.

---

## Acknowledgments

Built by C. Alaric Moore, a USPS technician and mechanic and patient who got tired of being told her labs were normal.

Assisted by Claude Sonnet (Anthropic) for development support, h/t to Github's copilot for closing parentheses and other surprisningly convenient features.

Inspired by every patient who was told "your labs are fine" when they knew something was deeply wrong. Dedicated to the ones still waiting for someone to believe them.

Also inspired by the rheumatologist who fired me for being right about a lab interpretation. I might be sick, but I'm still a stubborn Okie.

---

## License

GNU Affero General Public License v3.0 (AGPL-3.0)

This software is free for individuals and non-profits with attribution. Commercial entities wishing to use, modify, or deploy this software must obtain a separate commercial license.

The AGPL-3.0 requires that if you modify and deploy this software (including as a web service), you must make your modified source code available under the same license.

See the [LICENSE](LICENSE) file for full terms. For commercial licensing inquiries, contact the author.

---

## Support

For bugs, feature requests, or questions, open an issue on GitHub. Check existing issues first -- your question might already be answered.

This is currently a one-person project built between doctor appointments and strenous work shifts. Response times may vary.

Take care of yourself. Trust your observations. Keep asking questions.
