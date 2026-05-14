import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import get_db, init_db, seed_db

app = Flask(__name__)
app.secret_key = "dev-secret-change-in-production"


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
            "SELECT SUM(amount) AS total, COUNT(*) AS cnt FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        total_amount = agg["total"] or 0
        top_row = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ?"
            " GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            (user_id,),
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
            " FROM expenses WHERE user_id = ?"
            " ORDER BY date DESC, id DESC LIMIT 5",
            (user_id,),
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
            " FROM expenses WHERE user_id = ?"
            " GROUP BY category ORDER BY cat_total DESC",
            (user_id,),
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
                           transactions=transactions, categories=categories)


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
    app.run(debug=True, port=5001)
