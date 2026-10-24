"""
EcoTrack - Personal Carbon Footprint Monitoring & Smart Reduction System
Final Year BSc Computer Science Project

Flow: Register/Login -> Profile -> Daily Check-In -> CO2e Calculation ->
      Emission Analysis -> Personalized Suggestion -> What-If Simulator ->
      Reduction Goal -> Progress Tracking
"""

import re
import sys
import csv
import io
import json
from datetime import date, datetime, timedelta

try:
    import mysql.connector
    from flask import (
        Flask, render_template, request, redirect,
        url_for, session, flash, jsonify, g, Response
    )
    from werkzeug.security import generate_password_hash, check_password_hash
except ImportError as e:
    print("=" * 60)
    print("EcoTrack could not start: a required package is missing.")
    print("Missing package error:", e)
    print()
    print("Fix: open a terminal in the project folder and run:")
    print("    pip install -r requirements.txt")
    print("If you're using a virtual environment, make sure it is")
    print("activated first (venv\\Scripts\\activate on Windows, or")
    print("source venv/bin/activate on macOS/Linux).")
    print("=" * 60)
    input("Press Enter to exit...")
    sys.exit(1)

from config import Config
from carbon import calculate_assessment, footprint_status

app = Flask(__name__)
app.config.from_object(Config)

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# =====================================================
# DATABASE HELPERS
# =====================================================

def get_db():
    """Open (or reuse) a MySQL connection for the current request."""
    if "db" not in g:
        g.db = mysql.connector.connect(
            host=app.config["MYSQL_HOST"],
            port=app.config["MYSQL_PORT"],
            user=app.config["MYSQL_USER"],
            password=app.config["MYSQL_PASSWORD"],
            database=app.config["MYSQL_DB"],
        )
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, params=None, fetchone=False, fetchall=False, commit=False):
    """Small helper to run a parameterized query and optionally fetch/commit."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(sql, params or ())
    result = None
    if fetchone:
        result = cursor.fetchone()
    elif fetchall:
        result = cursor.fetchall()
    if commit:
        db.commit()
        result = cursor.lastrowid
    cursor.close()
    return result


def ensure_feature_schema():
    """Create additive feature tables for installations using the old schema."""
    db = get_db()
    cursor = db.cursor()
    for statement in (
        "ALTER TABLE users ADD COLUMN date_of_birth DATE NULL",
        "ALTER TABLE users ADD COLUMN state VARCHAR(100) NULL",
        "ALTER TABLE users ADD COLUMN country VARCHAR(100) NULL",
        "ALTER TABLE users ADD COLUMN household_size INT NULL",
        "ALTER TABLE users ADD COLUMN occupation VARCHAR(150) NULL",
    ):
        try:
            cursor.execute(statement)
        except Exception:
            # Existing installations will report duplicate-column errors.
            db.rollback()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS assessments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            answers JSON NOT NULL,
            result JSON NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB
    """)
    db.commit()
    cursor.close()


def get_emission_factors():
    """Load all emission factors from the DB into a nested dict:
    { 'transport': {'Petrol Bike': 0.05, ...}, 'electricity': {...}, ... }
    """
    rows = query("SELECT category, activity_type, factor, unit FROM emission_factors",
                 fetchall=True)
    factors = {}
    for row in rows:
        factors.setdefault(row["category"], {})[row["activity_type"]] = float(row["factor"])
    return factors


def compute_checkin_streak(user_id):
    """Count consecutive days (ending today or yesterday) with a recorded
    check-in. A gap of a day breaks the streak."""
    rows = query(
        "SELECT date FROM daily_activities WHERE user_id=%s ORDER BY date DESC LIMIT 90",
        (user_id,), fetchall=True,
    )
    recorded_dates = {r["date"] for r in rows}

    cursor_date = date.today()
    if cursor_date not in recorded_dates:
        # Today not logged yet - streak still counts if yesterday was logged.
        cursor_date -= timedelta(days=1)

    streak = 0
    while cursor_date in recorded_dates:
        streak += 1
        cursor_date -= timedelta(days=1)
    return streak


# =====================================================
# AUTH HELPERS
# =====================================================

def login_required(view_func):
    from functools import wraps

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped


def current_user():
    if "user_id" not in session:
        return None
    return query("SELECT * FROM users WHERE id = %s", (session["user_id"],), fetchone=True)


# =====================================================
# CALCULATION LOGIC
# =====================================================

def calculate_emissions(transport_type, distance, electricity, food_type, waste, factors):
    """Activity Amount x Emission Factor = Estimated CO2e, per category."""
    distance = float(distance or 0)
    electricity = float(electricity or 0)
    waste = float(waste or 0)

    transport_factor = factors.get("transport", {}).get(transport_type, 0)
    electricity_factor = factors.get("electricity", {}).get("Grid Electricity", 0)
    food_factor = factors.get("food", {}).get(food_type, 0)
    waste_factor = factors.get("waste", {}).get("General Waste", 0)

    transport_co2 = round(distance * transport_factor, 3)
    electricity_co2 = round(electricity * electricity_factor, 3)
    food_co2 = round(food_factor, 3)  # food factor is already a per-day value
    waste_co2 = round(waste * waste_factor, 3)

    total_co2 = round(transport_co2 + electricity_co2 + food_co2 + waste_co2, 3)

    return {
        "transport_co2": transport_co2,
        "electricity_co2": electricity_co2,
        "food_co2": food_co2,
        "waste_co2": waste_co2,
        "total_co2": total_co2,
    }


CATEGORY_META = {
    "transport": {"label": "Transport", "icon": "🚌", "color": "#2f9e64"},
    "electricity": {"label": "Electricity", "icon": "💡", "color": "#e0a83e"},
    "food": {"label": "Food", "icon": "🍽️", "color": "#c9694f"},
    "waste": {"label": "Waste", "icon": "🗑️", "color": "#6b8fc9"},
}

# Rule-based suggestion bank (no ML). Each category has more tips than shown
# by default, so the UI can offer a short "top tips" list plus an optional
# "more tips" expansion without turning the check-in into a huge list.
SUGGESTION_BANK = {
    "transport": {
        "impact_note": "Transport is usually the easiest category to cut quickly by switching a few regular trips.",
        "tips": [
            "Try reducing unnecessary short vehicle trips.",
            "Consider walking or cycling for short distances.",
            "Use public transport where practical.",
            "Explore carpooling for regular routes like college or work.",
            "Combine multiple short errands into a single trip.",
            "Try the What-If Simulator to compare your current commute with a greener alternative.",
        ],
    },
    "electricity": {
        "impact_note": "Small daily habits around appliances add up to a noticeable monthly difference.",
        "tips": [
            "Switch off appliances that aren't in use, instead of leaving them on standby.",
            "Reduce unnecessary AC usage — try a higher thermostat setting.",
            "Keep an eye on your highest-consumption appliances (AC, geyser, washing machine).",
            "Use natural light during the day where possible.",
            "Unplug chargers and devices once fully charged.",
            "Run high-load appliances (washing machine, dishwasher) with full loads only.",
        ],
    },
    "food": {
        "impact_note": "Food choices a few days a week can meaningfully shift your average footprint.",
        "tips": [
            "Try to reduce food waste at home — plan portions ahead.",
            "Consider lower-emission food choices a few days a week.",
            "Choose seasonal and locally grown produce where available.",
            "Store leftovers properly instead of discarding them.",
        ],
    },
    "waste": {
        "impact_note": "Segregation and reuse habits compound over time and reduce landfill-linked emissions.",
        "tips": [
            "Segregate waste at the source (wet / dry / recyclable).",
            "Recycle and reuse materials where possible.",
            "Cut down on single-use plastics and packaging.",
            "Compost kitchen/food waste where feasible.",
        ],
    },
}


def get_suggestions(breakdown, top_n=3):
    """Rule-based suggestions (no ML) ranked by emission category.

    Returns the highest-emission category as the primary focus (top_n tips +
    an impact note), plus a full ranked list so the UI can offer additional
    tips for the other categories too, without overwhelming the user by
    default.
    """
    categories = {
        "transport": breakdown["transport_co2"],
        "electricity": breakdown["electricity_co2"],
        "food": breakdown["food_co2"],
        "waste": breakdown["waste_co2"],
    }
    ranked = sorted(categories, key=categories.get, reverse=True)
    highest = ranked[0]

    primary_bank = SUGGESTION_BANK[highest]
    primary_tips = primary_bank["tips"][:top_n]
    more_tips = primary_bank["tips"][top_n:]

    other_categories = []
    for cat in ranked[1:]:
        other_categories.append({
            "category": cat,
            "meta": CATEGORY_META[cat],
            "tips": SUGGESTION_BANK[cat]["tips"][:2],
        })

    return {
        "highest_category": highest,
        "meta": CATEGORY_META[highest],
        "impact_note": primary_bank["impact_note"],
        "suggestions": primary_tips,
        "more_suggestions": more_tips,
        "other_categories": other_categories,
    }


# =====================================================
# VALIDATION HELPERS
# =====================================================

def is_valid_email(email):
    return bool(EMAIL_REGEX.match(email or ""))


def is_non_negative(*values):
    try:
        return all(float(v) >= 0 for v in values)
    except (TypeError, ValueError):
        return False


# =====================================================
# ROUTES: PUBLIC PAGES
# =====================================================

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    ensure_feature_schema()
    if request.method == "POST":
        form = request.form
        name = form.get("name", "").strip()
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")

        errors = []
        if not name or len(name) < 2 or len(name) > 150:
            errors.append("Please enter your full name.")
        if not is_valid_email(email):
            errors.append("Please enter a valid email address.")
        if (len(password) < 8 or not re.search(r"[A-Z]", password)
                or not re.search(r"[a-z]", password) or not re.search(r"\d", password)
                or not re.search(r"[^A-Za-z0-9]", password)):
            errors.append("Password must be 8+ characters with uppercase, lowercase, number and special character.")
        if password != form.get("confirm_password", ""):
            errors.append("Passwords do not match.")

        existing = query("SELECT id FROM users WHERE email = %s", (email,), fetchone=True)
        if existing:
            errors.append("This email is already registered. Please log in.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("register.html", form=form)

        try:
            query(
                """INSERT INTO users (name, email, password_hash, age, city,
                   transport_mode, avg_daily_distance, food_pattern, avg_electricity)
                   VALUES (%s,%s,%s,0,'','Walking',0,'Vegetarian',0)""",
                (name, email, generate_password_hash(password)), commit=True,
            )
        except Exception:
            flash("That email address is already registered or could not be saved.", "danger")
            return render_template("register.html", form=form)
        flash("Account created successfully. You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", form={})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = query("SELECT * FROM users WHERE email = %s", (email,), fetchone=True)
        if user and check_password_hash(user["password_hash"], password):
            session.permanent = True
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/assessment", methods=["GET", "POST"])
@login_required
def assessment():
    ensure_feature_schema()
    user_id = session["user_id"]
    if request.method == "POST":
        answers = {key: value for key, value in request.form.items() if key != "action"}
        session["assessment_answers"] = answers
        if request.form.get("action") == "save":
            flash("Assessment progress saved. You can resume it any time.", "success")
            return redirect(url_for("assessment"))
        result = calculate_assessment(answers)
        query("INSERT INTO assessments (user_id, answers, result) VALUES (%s, %s, %s)",
              (user_id, json.dumps(answers), json.dumps(result)), commit=True)
        session.pop("assessment_answers", None)
        return render_template("assessment.html", answers=answers, result=result,
                               status=footprint_status(result["total_yearly"]))

    latest = query("SELECT result, answers FROM assessments WHERE user_id=%s ORDER BY created_at DESC LIMIT 1",
                   (user_id,), fetchone=True)
    answers = session.get("assessment_answers", {})
    result = json.loads(latest["result"]) if latest else None
    if not answers and latest:
        answers = json.loads(latest["answers"])
    return render_template("assessment.html", answers=answers, result=result,
                           status=footprint_status(result["total_yearly"]) if result else None)


# =====================================================
# ROUTES: DASHBOARD
# =====================================================

@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    ensure_feature_schema()
    today = date.today()
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=6)
    month_start = today.replace(day=1)

    today_row = query(
        "SELECT * FROM daily_activities WHERE user_id=%s AND date=%s",
        (user_id, today), fetchone=True,
    )
    yesterday_row = query(
        "SELECT * FROM daily_activities WHERE user_id=%s AND date=%s",
        (user_id, yesterday), fetchone=True,
    )
    week_total = query(
        "SELECT COALESCE(SUM(total_co2),0) AS total FROM daily_activities "
        "WHERE user_id=%s AND date BETWEEN %s AND %s",
        (user_id, week_start, today), fetchone=True,
    )["total"]
    month_total = query(
        "SELECT COALESCE(SUM(total_co2),0) AS total FROM daily_activities "
        "WHERE user_id=%s AND date BETWEEN %s AND %s",
        (user_id, month_start, today), fetchone=True,
    )["total"]

    # Latest entry available (today, or the most recent prior entry)
    latest_row = today_row or query(
        "SELECT * FROM daily_activities WHERE user_id=%s ORDER BY date DESC LIMIT 1",
        (user_id,), fetchone=True,
    )

    largest_category = None
    comparison = None
    suggestion_info = None
    if today_row:
        breakdown = {
            "transport_co2": float(today_row["transport_co2"]),
            "electricity_co2": float(today_row["electricity_co2"]),
            "food_co2": float(today_row["food_co2"]),
            "waste_co2": float(today_row["waste_co2"]),
        }
        largest_category = max(
            ("transport", "electricity", "food", "waste"),
            key=lambda c: breakdown[f"{c}_co2"],
        )
        suggestion_info = get_suggestions(breakdown)

        if yesterday_row:
            diff = float(yesterday_row["total_co2"]) - float(today_row["total_co2"])
            comparison = {"diff": round(abs(diff), 2), "improved": diff >= 0}

    active_goal = query(
        "SELECT * FROM goals WHERE user_id=%s AND is_active=1 "
        "ORDER BY created_at DESC LIMIT 1",
        (user_id,), fetchone=True,
    )
    goal_progress = None
    if active_goal:
        goal_progress = compute_goal_progress(user_id, active_goal)

    streak = compute_checkin_streak(user_id)
    latest_assessment = query(
        "SELECT result FROM assessments WHERE user_id=%s ORDER BY created_at DESC LIMIT 1",
        (user_id,), fetchone=True,
    )
    assessment_result = json.loads(latest_assessment["result"]) if latest_assessment else None

    return render_template(
        "dashboard.html",
        today_row=today_row,
        latest_row=latest_row,
        week_total=round(float(week_total), 2),
        month_total=round(float(month_total), 2),
        largest_category=largest_category,
        comparison=comparison,
        suggestion_info=suggestion_info,
        active_goal=active_goal,
        goal_progress=goal_progress,
        streak=streak,
        assessment_result=assessment_result,
    )


@app.route("/api/chart-data")
@login_required
def api_chart_data():
    """JSON data for Chart.js: category breakdown (today) + last 7 day trend."""
    user_id = session["user_id"]
    today = date.today()
    week_start = today - timedelta(days=6)

    today_row = query(
        "SELECT * FROM daily_activities WHERE user_id=%s AND date=%s",
        (user_id, today), fetchone=True,
    )
    category_data = [0, 0, 0, 0]
    if today_row:
        category_data = [
            float(today_row["transport_co2"]),
            float(today_row["electricity_co2"]),
            float(today_row["food_co2"]),
            float(today_row["waste_co2"]),
        ]

    trend_rows = query(
        "SELECT date, total_co2 FROM daily_activities "
        "WHERE user_id=%s AND date BETWEEN %s AND %s ORDER BY date",
        (user_id, week_start, today), fetchall=True,
    )
    trend_map = {r["date"]: float(r["total_co2"]) for r in trend_rows}
    labels, values = [], []
    for i in range(7):
        d = week_start + timedelta(days=i)
        labels.append(d.strftime("%d %b"))
        values.append(trend_map.get(d, 0))

    return jsonify({
        "category_labels": ["Transport", "Electricity", "Food", "Waste"],
        "category_data": category_data,
        "trend_labels": labels,
        "trend_data": values,
    })


# =====================================================
# ROUTES: DAILY CHECK-IN
# =====================================================

@app.route("/checkin", methods=["GET", "POST"])
@login_required
def checkin():
    user_id = session["user_id"]
    factors = get_emission_factors()
    today = date.today()
    existing = query(
        "SELECT * FROM daily_activities WHERE user_id=%s AND date=%s",
        (user_id, today), fetchone=True,
    )

    if request.method == "POST":
        transport_type = request.form.get("transport_type", "")
        transport_distance = request.form.get("transport_distance", "0")
        electricity = request.form.get("electricity", "0")
        food_type = request.form.get("food_type", "")
        waste_amount = request.form.get("waste_amount", "0")

        errors = []
        if not transport_type or transport_type not in factors.get("transport", {}):
            errors.append("Please select a valid transport type.")
        if not food_type or food_type not in factors.get("food", {}):
            errors.append("Please select a valid food category.")
        if not is_non_negative(transport_distance, electricity, waste_amount):
            errors.append("Distance, electricity and waste values cannot be negative.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("checkin.html", factors=factors, existing=existing)

        breakdown = calculate_emissions(
            transport_type, transport_distance, electricity, food_type, waste_amount, factors
        )

        if existing:
            query(
                """UPDATE daily_activities SET transport_type=%s, transport_distance=%s,
                   electricity=%s, food_type=%s, waste_amount=%s, transport_co2=%s,
                   electricity_co2=%s, food_co2=%s, waste_co2=%s, total_co2=%s
                   WHERE id=%s""",
                (transport_type, transport_distance, electricity, food_type, waste_amount,
                 breakdown["transport_co2"], breakdown["electricity_co2"],
                 breakdown["food_co2"], breakdown["waste_co2"], breakdown["total_co2"],
                 existing["id"]),
                commit=True,
            )
            flash("Today's check-in was updated.", "success")
        else:
            query(
                """INSERT INTO daily_activities
                   (user_id, date, transport_type, transport_distance, electricity,
                    food_type, waste_amount, transport_co2, electricity_co2,
                    food_co2, waste_co2, total_co2)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (user_id, today, transport_type, transport_distance, electricity,
                 food_type, waste_amount, breakdown["transport_co2"],
                 breakdown["electricity_co2"], breakdown["food_co2"],
                 breakdown["waste_co2"], breakdown["total_co2"]),
                commit=True,
            )
            flash("Today's carbon check-in was recorded.", "success")

        suggestion_info = get_suggestions(breakdown)
        return render_template(
            "checkin.html", factors=factors, existing=None,
            result=breakdown, suggestion_info=suggestion_info,
        )

    return render_template("checkin.html", factors=factors, existing=existing)


# =====================================================
# ROUTES: WHAT-IF SIMULATOR
# =====================================================

@app.route("/simulator", methods=["GET", "POST"])
@login_required
def simulator():
    factors = get_emission_factors()
    result = None

    if request.method == "POST":
        current_type = request.form.get("current_type")
        current_distance = request.form.get("current_distance", "0")
        alt_type = request.form.get("alt_type")
        alt_distance = request.form.get("alt_distance", "0")

        if not is_non_negative(current_distance, alt_distance):
            flash("Distance values cannot be negative.", "danger")
        elif current_type not in factors.get("transport", {}) or alt_type not in factors.get("transport", {}):
            flash("Please select valid transport options.", "danger")
        else:
            current_co2 = round(float(current_distance) * factors["transport"][current_type], 3)
            alt_co2 = round(float(alt_distance) * factors["transport"][alt_type], 3)
            reduction = round(current_co2 - alt_co2, 3)
            result = {
                "current_type": current_type,
                "current_distance": current_distance,
                "alt_type": alt_type,
                "alt_distance": alt_distance,
                "current_co2": current_co2,
                "alt_co2": alt_co2,
                "reduction": reduction,
            }

    return render_template("simulator.html", factors=factors, result=result)


# =====================================================
# ROUTES: HISTORY
# =====================================================

@app.route("/history")
@login_required
def history():
    user_id = session["user_id"]
    rows = query(
        "SELECT * FROM daily_activities WHERE user_id=%s ORDER BY date DESC LIMIT 60",
        (user_id,), fetchall=True,
    )
    return render_template("history.html", rows=rows)


@app.route("/history/export")
@login_required
def export_history():
    """Download the user's full check-in history as a CSV file."""
    user_id = session["user_id"]
    rows = query(
        "SELECT date, transport_type, transport_distance, electricity, food_type, "
        "waste_amount, transport_co2, electricity_co2, food_co2, waste_co2, total_co2 "
        "FROM daily_activities WHERE user_id=%s ORDER BY date DESC",
        (user_id,), fetchall=True,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Transport Type", "Distance (km)", "Electricity (kWh)",
        "Food Type", "Waste (kg)", "Transport CO2e (kg)", "Electricity CO2e (kg)",
        "Food CO2e (kg)", "Waste CO2e (kg)", "Total CO2e (kg)",
    ])
    for r in rows:
        writer.writerow([
            r["date"], r["transport_type"], r["transport_distance"], r["electricity"],
            r["food_type"], r["waste_amount"], r["transport_co2"], r["electricity_co2"],
            r["food_co2"], r["waste_co2"], r["total_co2"],
        ])

    filename = f"ecotrack_history_{date.today().isoformat()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# =====================================================
# ROUTES: GOAL
# =====================================================

def compute_goal_progress(user_id, goal):
    """Progress = how much of the target reduction (vs baseline) has been achieved."""
    recent = query(
        "SELECT COALESCE(AVG(total_co2),0) AS avg_co2 FROM daily_activities "
        "WHERE user_id=%s AND date BETWEEN %s AND %s",
        (user_id, goal["start_date"], date.today()), fetchone=True,
    )["avg_co2"]
    recent = float(recent)
    baseline = float(goal["baseline_co2"])
    target_pct = float(goal["target_percentage"])

    if baseline <= 0:
        return {"percent": 0, "recent_avg": recent, "baseline": baseline, "target_value": None}

    target_value = round(baseline * (1 - target_pct / 100), 3)
    achieved_reduction = baseline - recent
    needed_reduction = baseline - target_value

    if needed_reduction <= 0:
        percent = 100
    else:
        percent = max(0, min(100, round((achieved_reduction / needed_reduction) * 100)))

    return {
        "percent": percent,
        "recent_avg": round(recent, 2),
        "baseline": round(baseline, 2),
        "target_value": target_value,
    }


@app.route("/goal", methods=["GET", "POST"])
@login_required
def goal():
    user_id = session["user_id"]

    if request.method == "POST":
        target_percentage = request.form.get("target_percentage", "")
        target_date_str = request.form.get("target_date", "")

        try:
            target_percentage_val = float(target_percentage)
            target_date_val = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            flash("Please provide a valid percentage and target date.", "danger")
            return redirect(url_for("goal"))

        if target_percentage_val <= 0 or target_percentage_val > 90:
            flash("Target percentage should be between 1 and 90.", "danger")
            return redirect(url_for("goal"))

        if target_date_val <= date.today():
            flash("Target date must be in the future.", "danger")
            return redirect(url_for("goal"))

        # Baseline = average of the last 7 recorded days (or the single latest entry)
        baseline_row = query(
            "SELECT COALESCE(AVG(total_co2),0) AS avg_co2 FROM ("
            "  SELECT total_co2 FROM daily_activities WHERE user_id=%s "
            "  ORDER BY date DESC LIMIT 7"
            ") AS recent",
            (user_id,), fetchone=True,
        )
        baseline_co2 = float(baseline_row["avg_co2"]) if baseline_row else 0

        # Deactivate previous goals, then create the new one
        query("UPDATE goals SET is_active=0 WHERE user_id=%s", (user_id,), commit=True)
        query(
            """INSERT INTO goals (user_id, target_percentage, baseline_co2, start_date, target_date)
               VALUES (%s, %s, %s, %s, %s)""",
            (user_id, target_percentage_val, baseline_co2, date.today(), target_date_val),
            commit=True,
        )
        flash("Your reduction goal has been set.", "success")
        return redirect(url_for("goal"))

    active_goal = query(
        "SELECT * FROM goals WHERE user_id=%s AND is_active=1 ORDER BY created_at DESC LIMIT 1",
        (user_id,), fetchone=True,
    )
    progress = compute_goal_progress(user_id, active_goal) if active_goal else None

    return render_template("goal.html", active_goal=active_goal, progress=progress)


# =====================================================
# ROUTES: PROFILE
# =====================================================

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user_id = session["user_id"]
    ensure_feature_schema()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        city = request.form.get("city", "").strip()
        state = request.form.get("state", "").strip()
        country = request.form.get("country", "").strip()
        occupation = request.form.get("occupation", "").strip()
        household_size = request.form.get("household_size", "")
        dob_text = request.form.get("date_of_birth", "")
        transport_mode = request.form.get("transport_mode", "")
        avg_daily_distance = request.form.get("avg_daily_distance", "")
        food_pattern = request.form.get("food_pattern", "")
        avg_electricity = request.form.get("avg_electricity", "")

        errors = []
        if not name or not city or not transport_mode or not dob_text:
            errors.append("Name, date of birth, city and transport mode are required.")
        try:
            date_of_birth = datetime.strptime(dob_text, "%Y-%m-%d").date()
            if date_of_birth >= date.today():
                errors.append("Date of birth cannot be in the future.")
            age = date.today().year - date_of_birth.year - ((date.today().month, date.today().day) < (date_of_birth.month, date_of_birth.day))
            if age < 1 or age > 120:
                errors.append("Please enter a valid date of birth.")
        except (TypeError, ValueError):
            date_of_birth = None
            age = 0
            errors.append("Please enter a valid date of birth.")
        if not household_size.isdigit() or not 1 <= int(household_size) <= 30:
            errors.append("Household size must be between 1 and 30.")
        if not is_non_negative(avg_daily_distance, avg_electricity):
            errors.append("Distance and electricity values cannot be negative.")
        if food_pattern not in ("Vegetarian", "Mixed"):
            errors.append("Please select a valid food pattern.")

        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            query(
                     """UPDATE users SET name=%s, age=%s, date_of_birth=%s, city=%s,
                         state=%s, country=%s, household_size=%s, occupation=%s,
                         transport_mode=%s, avg_daily_distance=%s, food_pattern=%s, avg_electricity=%s
                   WHERE id=%s""",
                     (name, age, date_of_birth, city, state, country, int(household_size),
                      occupation, transport_mode, avg_daily_distance, food_pattern,
                      avg_electricity, user_id),
                commit=True,
            )
            session["user_name"] = name
            flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))

    user = current_user()
    return render_template("profile.html", user=user, now_date=date.today().isoformat())


# =====================================================
# ENTRY POINT
# =====================================================

def check_database_connection():
    """Try connecting to MySQL/MariaDB before starting the server, and print
    a clear, actionable message instead of letting the app crash silently
    (which is what makes the console window close instantly on Windows)."""
    try:
        test_conn = mysql.connector.connect(
            host=app.config["MYSQL_HOST"],
            port=app.config["MYSQL_PORT"],
            user=app.config["MYSQL_USER"],
            password=app.config["MYSQL_PASSWORD"],
            database=app.config["MYSQL_DB"],
        )
        test_conn.close()
        print(f"[OK] Connected to MySQL database '{app.config['MYSQL_DB']}' "
              f"as '{app.config['MYSQL_USER']}'@'{app.config['MYSQL_HOST']}'.")
        return True
    except mysql.connector.Error as db_err:
        print("=" * 60)
        print("EcoTrack could not connect to the database.")
        print("Error detail:", db_err)
        print()
        print("Most common fixes:")
        print("  1. Start MySQL from the XAMPP Control Panel (not just Apache).")
        print("  2. Import database/ecotrack.sql via phpMyAdmin, or run:")
        print("       mysql -u root -p < database/ecotrack.sql")
        print("     This creates the 'ecotrack' database EcoTrack expects.")
        print("  3. If your MySQL root user has a password (or a different")
        print("     username), set it in config.py or via environment")
        print("     variables: MYSQL_USER, MYSQL_PASSWORD, MYSQL_HOST, MYSQL_PORT.")
        print("=" * 60)
        return False


if __name__ == "__main__":
    if not check_database_connection():
        input("\nPress Enter to exit...")
        sys.exit(1)

    print("Starting EcoTrack at http://localhost:5000 ...")
    try:
        app.run(debug=True)
    except Exception as run_err:  # noqa: BLE001 - top-level safety net for a student project
        print("=" * 60)
        print("EcoTrack crashed while running:", run_err)
        print("If port 5000 is already in use, close the other program")
        print("using it, or run with a different port, e.g.:")
        print("    app.run(debug=True, port=5001)")
        print("=" * 60)
        input("\nPress Enter to exit...")
        sys.exit(1)
