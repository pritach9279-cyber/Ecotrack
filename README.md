Flow: Register/Login → Profile → Daily Check-In → CO₂e Calculation →
Emission Analysis → Personalized Suggestion → What-If Simulator →
Reduction Goal → Progress Tracking

## Tech Stack

- **Frontend:** HTML5, CSS3, vanilla JavaScript, Chart.js
- **Backend:** Python Flask
- **Database:** MySQL (via XAMPP)

## Project Structure

```
ecotrack/
├── app.py                 # All Flask routes, calculations, suggestions
├── config.py               # App configuration (DB credentials, secret key)
├── requirements.txt
├── templates/               # Jinja2 HTML templates
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── checkin.html
│   ├── simulator.html
│   ├── history.html
│   ├── goal.html
│   └── profile.html
├── static/
│   ├── css/style.css
│   ├── js/script.js
│   └── images/
├── database/
│   └── ecotrack.sql        # Schema + seed data for emission_factors
└── README.md
```

## Setup Instructions (XAMPP + Python)

### 1. Start MySQL via XAMPP
Open the XAMPP Control Panel and start the **MySQL** module (Apache is not
needed — Flask runs its own dev server).

### 2. Create the database
Open **phpMyAdmin** (`http://localhost/phpmyadmin`) → **Import** →
select `database/ecotrack.sql` → **Go**.

Or from a terminal:
```bash
mysql -u root -p < database/ecotrack.sql
```
(Default XAMPP MySQL has no password — just press Enter if prompted.)

This creates the `ecotrack` database with the existing tracking tables plus
`assessments`, and seeds
`emission_factors` with the values used for all calculations.

### 3. Install Python dependencies
It's recommended to use a virtual environment:
```bash
cd ecotrack
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
```

### 4. Configure database credentials (if needed)
Default settings in `config.py` match a standard XAMPP setup
(`host=localhost`, `user=root`, `password=""`, `db=ecotrack`).
Copy `.env.example` to `.env` and provide `SECRET_KEY` and database
settings as environment variables.
The application reads environment variables directly; `.env` is ignored by git.
Set `SESSION_COOKIE_SECURE=1` when serving over HTTPS in production.

### 5. Run the application
```bash
python app.py
```
Visit **http://localhost:5000** in your browser.

## How the Calculation Works

For each daily check-in:
```
Activity Amount × Emission Factor = Estimated CO2e
```
Calculated separately for Transport, Electricity, Food, and Waste, then summed:
```
Total CO2e = Transport + Electricity + Food + Waste
```
All emission factors live in the `emission_factors` table, so they can be
tuned without touching code. All results are clearly labelled as
**estimates**, not exact scientific measurements.

## Key Features

- **Daily Check-In** — a short form (not a survey) for transport, electricity,
  food, and waste.
- **Simple registration** — a validated email and securely hashed password,
  followed by immediate login.
- **Carbon Assessment** — resumable Food, Travel, Electricity, and Waste sections
  with monthly, annual, category, and configurable status estimates.
- **Dashboard** — today/week/month totals, largest emission category, a
  "Beat Yesterday" comparison, Chart.js category-breakdown and 7-day trend
  charts, and goal progress.
- **Rule-Based Suggestions** — no ML; the highest emission category drives
  1–3 relevant, practical tips.
- **What-If Simulator** — the project's core unique feature: compare a
  current transport choice against an alternative and see the potential
  estimated CO₂e reduction instantly.
- **Reduction Goals** — set a target percentage and target date; progress is
  computed against a baseline average of recent activity.
- **History** — a table of the last 60 recorded days.

## Security Notes

- Passwords are hashed with Werkzeug's `generate_password_hash` /
  `check_password_hash` — never stored in plain text.
- Registration creates a `users` row after form validation; passwords are stored
  only as Werkzeug hashes.
- All SQL queries use parameterized statements (no string concatenation).
- Server-side validation rejects negative numbers, invalid emails, and
  missing required fields (mirrored with basic HTML5 `required`/`min`
  attributes on the frontend).
- Protected pages (dashboard, check-in, simulator, history, goal, profile)
  require an active Flask session; unauthenticated visits redirect to
  `/login`.
- A user can only submit one `daily_activities` row per date — a repeat
  check-in on the same day **updates** that day's record instead of
  duplicating it (enforced by a unique `(user_id, date)` key).

## Notes for Viva / Demonstration

Suggested demo flow, matching the project's core concept
**(Measure → Analyze → Suggest → Simulate → Reduce → Track)**:

1. Register a new account with realistic profile values.
2. Log a Daily Check-In (e.g., a car-heavy day) → see the CO₂e breakdown and
   the personalized suggestion for the highest category.
3. Open the **What-If Simulator** → compare "Petrol Car" vs "Public Bus" for
   the same distance → show the potential estimated reduction.
4. Set a **Reduction Goal** (e.g., 15% over a month).
5. Log a greener check-in the next day → show the **dashboard** updating:
   "Beat Yesterday" message, charts, and goal progress bar.
6. Open **History** to show the stored record of past days.