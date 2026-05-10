import sqlite3
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

    user = {
        "name": "Rahul Ghadiya",
        "email": "rahul@example.com",
        "member_since": "January 2024",
        "initials": "RG",
    }

    stats = {
        "total_spent": "₹24,680",
        "transaction_count": 34,
        "top_category": "Food & Dining",
    }

    transactions = [
        {"date": "10 May 2025", "description": "Swiggy Order",    "category": "Food & Dining", "badge_class": "badge-green", "amount": "₹340"},
        {"date": "09 May 2025", "description": "Ola Cab",          "category": "Transport",     "badge_class": "badge-gold",  "amount": "₹180"},
        {"date": "08 May 2025", "description": "Netflix",          "category": "Entertainment", "badge_class": "badge-muted", "amount": "₹499"},
        {"date": "07 May 2025", "description": "Big Bazaar",       "category": "Groceries",     "badge_class": "badge-green", "amount": "₹1,240"},
        {"date": "05 May 2025", "description": "Electricity Bill", "category": "Utilities",     "badge_class": "badge-gold",  "amount": "₹850"},
    ]

    categories = [
        {"name": "Food & Dining", "amount": "₹8,420", "percent": 34},
        {"name": "Groceries",     "amount": "₹5,100", "percent": 21},
        {"name": "Utilities",     "amount": "₹4,000", "percent": 16},
        {"name": "Transport",     "amount": "₹3,960", "percent": 16},
        {"name": "Entertainment", "amount": "₹3,200", "percent": 13},
    ]

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
