import os
import sqlite3
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import get_db, init_db, seed_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def _resolve_date_filter(args):
    today = date.today()
    first_of_month = today.replace(day=1)
    last_month_end = first_of_month - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    d = today.replace(day=1)
    for _ in range(3):
        d = (d - timedelta(days=1)).replace(day=1)
    three_months_start = d

    periods = [
        {"key": "this_month",    "label": "This Month",    "start": first_of_month.isoformat(),               "end": today.isoformat()},
        {"key": "last_month",    "label": "Last Month",    "start": last_month_start.isoformat(),              "end": last_month_end.isoformat()},
        {"key": "last_3_months", "label": "Last 3 Months", "start": three_months_start.isoformat(),           "end": today.isoformat()},
        {"key": "this_year",     "label": "This Year",     "start": today.replace(month=1, day=1).isoformat(), "end": today.isoformat()},
        {"key": "all_time",      "label": "All Time",      "start": "2000-01-01",                              "end": "2099-12-31"},
    ]

    raw_from = args.get("from_date", "")
    raw_to   = args.get("to_date", "")
    try:
        datetime.strptime(raw_from, "%Y-%m-%d")
        datetime.strptime(raw_to,   "%Y-%m-%d")
        from_date, to_date = raw_from, raw_to
    except ValueError:
        from_date = periods[0]["start"]
        to_date   = periods[0]["end"]

    if from_date > to_date:
        from_date = periods[0]["start"]
        to_date   = periods[0]["end"]

    active_period = next(
        (p["key"] for p in periods if from_date == p["start"] and to_date == p["end"]),
        "custom",
    )

    return from_date, to_date, periods, active_period


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("register.html")

    name     = request.form.get("name", "").strip()
    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    confirm_password = request.form.get("confirm_password", "")

    if not name or not email or not password or not confirm_password:
        return render_template("register.html", error="All fields are required.")

    if len(password) < 8:
        return render_template("register.html",
                               error="Password must be at least 8 characters.")

    if password != confirm_password:
        return render_template("register.html",
                               error="Passwords do not match.")

    password_hash = generate_password_hash(password)

    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return render_template("register.html",
                               error="An account with that email already exists.")
    finally:
        conn.close()

    return redirect(url_for("login", registered=1))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        success = "Account created successfully! Please sign in." if request.args.get("registered") else None
        return render_template("login.html", success=success)

    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not email or not password:
        return render_template("login.html", error="Invalid email or password.")

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid email or password.")

    session.clear()
    session["user_id"]   = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    from_date, to_date, periods, active_period = _resolve_date_filter(request.args)

    conn = get_db()
    try:

        # --- user info ---
        row = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        parts = row["name"].split()
        initials = (parts[0][0] + parts[1][0]).upper() if len(parts) >= 2 else parts[0][0].upper()
        user = {
            "name":         row["name"],
            "email":        row["email"],
            "member_since": datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S").strftime("%B %Y"),
            "initials":     initials,
        }

        # --- stats ---
        agg = conn.execute(
            "SELECT SUM(amount) AS total, COUNT(*) AS cnt FROM expenses"
            " WHERE user_id = ? AND date BETWEEN ? AND ?",
            (user_id, from_date, to_date),
        ).fetchone()
        total_amount = agg["total"] or 0
        top_row = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ? AND date BETWEEN ? AND ?"
            " GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            (user_id, from_date, to_date),
        ).fetchone()
        stats = {
            "total_spent":       f"₹{total_amount:,.0f}",
            "transaction_count": agg["cnt"],
            "top_category":      top_row["category"] if top_row else "—",
        }

        # --- transactions ---
        badge_map = {
            "Food":          "badge-green",
            "Groceries":     "badge-green",
            "Transport":     "badge-gold",
            "Utilities":     "badge-gold",
            "Bills":         "badge-gold",
            "Health":        "badge-blue",
            "Entertainment": "badge-muted",
            "Shopping":      "badge-muted",
            "Other":         "badge-muted",
        }
        rows = conn.execute(
            "SELECT date, description, category, amount"
            " FROM expenses WHERE user_id = ? AND date BETWEEN ? AND ?"
            " ORDER BY date DESC, id DESC LIMIT 5",
            (user_id, from_date, to_date),
        ).fetchall()
        transactions = [
            {
                "date":        datetime.strptime(r["date"], "%Y-%m-%d").strftime("%-d %b %Y"),
                "description": r["description"] or "",
                "category":    r["category"],
                "badge_class": badge_map.get(r["category"], "badge-muted"),
                "amount":      f"₹{r['amount']:,.0f}",
            }
            for r in rows
        ]

        # --- categories ---
        cat_rows = conn.execute(
            "SELECT category, SUM(amount) AS cat_total"
            " FROM expenses WHERE user_id = ? AND date BETWEEN ? AND ?"
            " GROUP BY category ORDER BY cat_total DESC",
            (user_id, from_date, to_date),
        ).fetchall()
        categories = [
            {
                "name":    r["category"],
                "amount":  f"₹{r['cat_total']:,.0f}",
                "percent": round(r["cat_total"] / total_amount * 100) if total_amount else 0,
            }
            for r in cat_rows
        ]

    finally:
        conn.close()

    return render_template("profile.html",
                           user=user, stats=stats,
                           transactions=transactions, categories=categories,
                           periods=periods, from_date=from_date,
                           to_date=to_date, active_period=active_period)


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


with app.app_context():
    init_db()
    seed_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=5001)
