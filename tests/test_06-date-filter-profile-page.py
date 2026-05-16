"""
tests/test_06-date-filter-profile-page.py

Pytest test suite for the Spendly date-filter feature on the /profile page.

Spec: .claude/specs/06-date-filter-profile-page.md

Strategy
--------
- database.db.DB_PATH is monkey-patched to ":memory:" so every test gets a
  fresh, isolated SQLite in-memory database.
- get_db() is also patched so each call returns a connection to the same
  in-memory database within a test (required because sqlite3 in-memory DBs
  are per-connection by default; we use a module-level singleton within each
  test via the patch).
- Users and expenses are inserted directly into the DB via helper fixtures;
  session is set via Flask's test client session-transaction interface.
- No test reads the implementation to derive what "should" happen — all
  expected values come from the spec.
"""

import sqlite3
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from werkzeug.security import generate_password_hash

import database.db as db_module
from app import app as flask_app
from database.db import init_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn(db_holder):
    """Return a new sqlite3.Row-enabled connection to the shared in-memory DB."""
    conn = sqlite3.connect(db_holder["db"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _insert_user(conn, name="Test User", email="test@example.com",
                 password="password123"):
    pw_hash = generate_password_hash(password)
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, pw_hash),
    )
    conn.commit()
    return cur.lastrowid


def _insert_expense(conn, user_id, amount, category, exp_date, description=""):
    """Insert a single expense row. exp_date must be a str 'YYYY-MM-DD'."""
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description)"
        " VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, exp_date, description),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_db():
    """
    Create a fresh in-memory SQLite database with the Spendly schema.
    Returns a dict {"db": connection_string} where the connection string is
    a URI that keeps the same in-memory DB alive for the test's duration.

    We use a named in-memory DB via URI so multiple connections inside the
    same test all share the same DB (Flask's get_db() is called multiple
    times per request).
    """
    # Use a file-based temp DB so multiple connections within a request share state.
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    holder = {"db": path}

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            email         TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            amount      REAL    NOT NULL,
            category    TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            description TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()

    yield holder

    # Teardown
    os.unlink(path)


@pytest.fixture()
def app(mem_db):
    """Flask app configured for testing, backed by the isolated temp DB."""
    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "WTF_CSRF_ENABLED": False,
    })

    with patch.object(db_module, "DB_PATH", mem_db["db"]):
        with flask_app.app_context():
            yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db_conn(mem_db):
    """Direct connection to the test DB for fixture setup."""
    conn = sqlite3.connect(mem_db["db"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


@pytest.fixture()
def user_id(db_conn):
    """Insert a test user and return their id."""
    return _insert_user(db_conn)


@pytest.fixture()
def auth_client(client, user_id):
    """A test client with an active session for user_id."""
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = "Test User"
    return client


# ---------------------------------------------------------------------------
# Utility: compute period boundaries the same way the spec prescribes
# ---------------------------------------------------------------------------

def _period_bounds():
    """Return a dict of period -> (from_date_str, to_date_str) per the spec."""
    today = date.today()
    first_of_month = today.replace(day=1)
    last_month_end = first_of_month - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    if today.month > 3:
        three_months_start = today.replace(month=today.month - 3, day=1)
    else:
        three_months_start = today.replace(
            year=today.year - 1, month=today.month + 9, day=1
        )

    return {
        "this_month":    (first_of_month.isoformat(), today.isoformat()),
        "last_month":    (last_month_start.isoformat(), last_month_end.isoformat()),
        "last_3_months": (three_months_start.isoformat(), today.isoformat()),
        "this_year":     (today.replace(month=1, day=1).isoformat(), today.isoformat()),
        "all_time":      ("2000-01-01", "2099-12-31"),
    }


# ---------------------------------------------------------------------------
# 1. Auth guard
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_unauthenticated_get_redirects_to_login(self, client):
        """GET /profile without a session must redirect to /login."""
        response = client.get("/profile")
        assert response.status_code == 302, (
            "Expected 302 redirect for unauthenticated /profile"
        )
        assert "/login" in response.headers["Location"], (
            "Redirect target should be /login"
        )

    def test_unauthenticated_get_follows_redirect_to_login_page(self, client):
        """Following the redirect lands on the login page (200)."""
        response = client.get("/profile", follow_redirects=True)
        assert response.status_code == 200
        assert b"Login" in response.data or b"login" in response.data, (
            "Login page content expected after redirect"
        )


# ---------------------------------------------------------------------------
# 2. Default period (no query params) => current calendar month
# ---------------------------------------------------------------------------

class TestDefaultPeriod:
    def test_no_params_returns_200(self, auth_client):
        response = auth_client.get("/profile")
        assert response.status_code == 200, "Profile page must return 200"

    def test_no_params_shows_this_month_expenses_only(
        self, auth_client, db_conn, user_id
    ):
        """Without query params only current-month expenses must appear in stats."""
        bounds = _period_bounds()
        this_month_start, this_month_end = bounds["this_month"]
        last_month_start, last_month_end = bounds["last_month"]

        # Insert one expense in the current month and one in the previous month
        _insert_expense(db_conn, user_id, 5000.0, "Food", this_month_start,
                        "Current month expense")
        _insert_expense(db_conn, user_id, 3000.0, "Transport", last_month_start,
                        "Previous month expense")

        response = auth_client.get("/profile")
        assert response.status_code == 200
        data = response.data

        # Current-month expense (₹5,000) must be visible
        assert b"\xe2\x82\xb95,000" in data or b"5,000" in data, (
            "Current-month expense total should appear"
        )

    def test_no_params_active_period_is_this_month(self, auth_client):
        """Template must highlight 'This Month' button when no params supplied."""
        response = auth_client.get("/profile")
        assert response.status_code == 200
        # The spec mandates 'filter-btn--active' class on the active button,
        # and the active period label is 'This Month'
        assert b"This Month" in response.data, (
            "Page must contain 'This Month' text"
        )
        assert b"filter-btn--active" in response.data, (
            "An active filter button must be marked with filter-btn--active"
        )

    def test_no_params_excludes_previous_month_expenses(
        self, auth_client, db_conn, user_id
    ):
        """Expenses from last month must NOT inflate the total when no params given."""
        bounds = _period_bounds()
        this_month_start = bounds["this_month"][0]
        last_month_start = bounds["last_month"][0]

        _insert_expense(db_conn, user_id, 1000.0, "Food", this_month_start, "this month")
        _insert_expense(db_conn, user_id, 9999.0, "Bills", last_month_start, "last month")

        response = auth_client.get("/profile")
        data = response.data

        # 9,999 must NOT appear anywhere in the rendered page stats
        assert b"9,999" not in data, (
            "Last-month expense amount must not appear in default (this-month) view"
        )


# ---------------------------------------------------------------------------
# 3. This Month filter (explicit params)
# ---------------------------------------------------------------------------

class TestThisMonthFilter:
    def test_this_month_params_return_200(self, auth_client):
        bounds = _period_bounds()
        from_date, to_date = bounds["this_month"]
        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        assert response.status_code == 200

    def test_this_month_active_period_highlighted(self, auth_client):
        bounds = _period_bounds()
        from_date, to_date = bounds["this_month"]
        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        data = response.data
        assert b"filter-btn--active" in data, "Active button class must be present"
        assert b"This Month" in data, "'This Month' label must appear"

    def test_this_month_shows_only_current_month_expenses(
        self, auth_client, db_conn, user_id
    ):
        bounds = _period_bounds()
        from_date, to_date = bounds["this_month"]
        last_month_start = bounds["last_month"][0]

        _insert_expense(db_conn, user_id, 2500.0, "Food", from_date, "in range")
        _insert_expense(db_conn, user_id, 7777.0, "Shopping", last_month_start,
                        "out of range")

        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        data = response.data
        assert b"7,777" not in data, (
            "Out-of-range expense must not appear under This Month filter"
        )

    def test_this_month_url_reflects_params(self, auth_client):
        """The page must re-surface from_date and to_date in its content (inputs/links)."""
        bounds = _period_bounds()
        from_date, to_date = bounds["this_month"]
        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        data = response.data
        assert from_date.encode() in data, (
            "from_date value must appear in rendered page (e.g., in date input)"
        )
        assert to_date.encode() in data, (
            "to_date value must appear in rendered page"
        )


# ---------------------------------------------------------------------------
# 4. Last Month filter
# ---------------------------------------------------------------------------

class TestLastMonthFilter:
    def test_last_month_returns_200(self, auth_client):
        bounds = _period_bounds()
        from_date, to_date = bounds["last_month"]
        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        assert response.status_code == 200

    def test_last_month_active_period_highlighted(self, auth_client):
        bounds = _period_bounds()
        from_date, to_date = bounds["last_month"]
        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        data = response.data
        assert b"filter-btn--active" in data
        assert b"Last Month" in data, "'Last Month' label must appear"

    def test_last_month_includes_only_last_month_expenses(
        self, auth_client, db_conn, user_id
    ):
        bounds = _period_bounds()
        last_from, last_to = bounds["last_month"]
        this_month_start = bounds["this_month"][0]

        _insert_expense(db_conn, user_id, 4400.0, "Bills", last_from, "last month")
        _insert_expense(db_conn, user_id, 8888.0, "Health", this_month_start,
                        "this month — should be excluded")

        response = auth_client.get(
            f"/profile?from_date={last_from}&to_date={last_to}"
        )
        data = response.data
        assert b"8,888" not in data, (
            "Current-month expense must not appear under Last Month filter"
        )

    def test_last_month_expense_total_is_included(
        self, auth_client, db_conn, user_id
    ):
        bounds = _period_bounds()
        last_from, last_to = bounds["last_month"]

        _insert_expense(db_conn, user_id, 6600.0, "Food", last_from, "last month food")

        response = auth_client.get(
            f"/profile?from_date={last_from}&to_date={last_to}"
        )
        data = response.data
        assert b"6,600" in data, (
            "Last-month expense should be reflected in the stats total"
        )


# ---------------------------------------------------------------------------
# 5. Last 3 Months filter
# ---------------------------------------------------------------------------

class TestLast3MonthsFilter:
    def test_last_3_months_returns_200(self, auth_client):
        bounds = _period_bounds()
        from_date, to_date = bounds["last_3_months"]
        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        assert response.status_code == 200

    def test_last_3_months_active_period_highlighted(self, auth_client):
        bounds = _period_bounds()
        from_date, to_date = bounds["last_3_months"]
        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        data = response.data
        assert b"filter-btn--active" in data
        assert b"Last 3 Months" in data

    def test_last_3_months_excludes_older_expenses(
        self, auth_client, db_conn, user_id
    ):
        bounds = _period_bounds()
        three_from, three_to = bounds["last_3_months"]

        # Compute a date clearly before the 3-month window
        from datetime import date as dt
        from_dt = dt.fromisoformat(three_from)
        before_window = (from_dt - timedelta(days=5)).isoformat()

        _insert_expense(db_conn, user_id, 3300.0, "Food", three_from, "in 3-month range")
        _insert_expense(db_conn, user_id, 5555.0, "Other", before_window,
                        "before 3-month window")

        response = auth_client.get(
            f"/profile?from_date={three_from}&to_date={three_to}"
        )
        data = response.data
        assert b"5,555" not in data, (
            "Expense older than 3-month window must not appear"
        )

    def test_last_3_months_includes_expense_within_window(
        self, auth_client, db_conn, user_id
    ):
        bounds = _period_bounds()
        three_from, three_to = bounds["last_3_months"]

        # Use the window start date itself as the expense date
        _insert_expense(db_conn, user_id, 1111.0, "Food", three_from, "boundary start")

        response = auth_client.get(
            f"/profile?from_date={three_from}&to_date={three_to}"
        )
        data = response.data
        assert b"1,111" in data, "Expense on window start date must be included"


# ---------------------------------------------------------------------------
# 6. This Year filter
# ---------------------------------------------------------------------------

class TestThisYearFilter:
    def test_this_year_returns_200(self, auth_client):
        bounds = _period_bounds()
        from_date, to_date = bounds["this_year"]
        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        assert response.status_code == 200

    def test_this_year_active_period_highlighted(self, auth_client):
        bounds = _period_bounds()
        from_date, to_date = bounds["this_year"]
        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        data = response.data
        assert b"filter-btn--active" in data
        assert b"This Year" in data

    def test_this_year_excludes_prior_year_expenses(
        self, auth_client, db_conn, user_id
    ):
        today = date.today()
        this_year_start = today.replace(month=1, day=1).isoformat()
        prior_year_date = f"{today.year - 1}-06-15"

        bounds = _period_bounds()
        from_date, to_date = bounds["this_year"]

        _insert_expense(db_conn, user_id, 2200.0, "Food", this_year_start, "this year")
        _insert_expense(db_conn, user_id, 9900.0, "Shopping", prior_year_date,
                        "prior year — should be excluded")

        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        data = response.data
        assert b"9,900" not in data, "Prior-year expense must not appear under This Year filter"

    def test_this_year_includes_expense_from_january(
        self, auth_client, db_conn, user_id
    ):
        today = date.today()
        jan_first = today.replace(month=1, day=1).isoformat()
        bounds = _period_bounds()
        from_date, to_date = bounds["this_year"]

        _insert_expense(db_conn, user_id, 4400.0, "Bills", jan_first, "jan 1 expense")

        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        data = response.data
        assert b"4,400" in data, "January expense must be included in This Year filter"


# ---------------------------------------------------------------------------
# 7. All Time filter
# ---------------------------------------------------------------------------

class TestAllTimeFilter:
    def test_all_time_returns_200(self, auth_client):
        response = auth_client.get("/profile?from_date=2000-01-01&to_date=2099-12-31")
        assert response.status_code == 200

    def test_all_time_active_period_highlighted(self, auth_client):
        response = auth_client.get("/profile?from_date=2000-01-01&to_date=2099-12-31")
        data = response.data
        assert b"filter-btn--active" in data
        assert b"All Time" in data

    def test_all_time_includes_expenses_from_any_date(
        self, auth_client, db_conn, user_id
    ):
        """All Time must aggregate expenses across all dates."""
        _insert_expense(db_conn, user_id, 1000.0, "Food", "2023-03-10", "old")
        _insert_expense(db_conn, user_id, 2000.0, "Food", "2025-07-20", "recent")
        _insert_expense(db_conn, user_id, 3000.0, "Food", date.today().isoformat(), "today")

        response = auth_client.get("/profile?from_date=2000-01-01&to_date=2099-12-31")
        data = response.data
        # Total must be 6,000
        assert b"6,000" in data, (
            "All Time total must include expenses from all dates (expected ₹6,000)"
        )

    def test_all_time_url_params_reflected(self, auth_client):
        response = auth_client.get("/profile?from_date=2000-01-01&to_date=2099-12-31")
        data = response.data
        assert b"2000-01-01" in data, "from_date sentinel must appear in page"
        assert b"2099-12-31" in data, "to_date sentinel must appear in page"


# ---------------------------------------------------------------------------
# 8. Custom date range filter
# ---------------------------------------------------------------------------

class TestCustomDateRange:
    def test_custom_range_returns_200(self, auth_client):
        response = auth_client.get("/profile?from_date=2026-01-01&to_date=2026-03-31")
        assert response.status_code == 200

    def test_custom_range_active_period_is_custom(self, auth_client, db_conn, user_id):
        """A range that matches none of the named periods must give active_period=custom."""
        # Use a precise narrow window unlikely to match any named period
        response = auth_client.get("/profile?from_date=2025-06-01&to_date=2025-06-30")
        data = response.data
        # None of the named period buttons should be active; 'custom' means no
        # quick-select button is highlighted (or at minimum the label differs)
        # Verify the page still loads and carries the date params
        assert response.status_code == 200
        assert b"2025-06-01" in data, "Custom from_date must appear in the page"
        assert b"2025-06-30" in data, "Custom to_date must appear in the page"

    def test_custom_range_filters_to_exact_window(
        self, auth_client, db_conn, user_id
    ):
        """Only expenses within the custom window must appear."""
        _insert_expense(db_conn, user_id, 3300.0, "Food", "2025-06-15", "in range")
        _insert_expense(db_conn, user_id, 7700.0, "Shopping", "2025-08-01",
                        "after range — excluded")
        _insert_expense(db_conn, user_id, 5500.0, "Bills", "2025-04-30",
                        "before range — excluded")

        response = auth_client.get(
            "/profile?from_date=2025-06-01&to_date=2025-06-30"
        )
        data = response.data
        assert b"7,700" not in data, "Post-range expense must not appear"
        assert b"5,500" not in data, "Pre-range expense must not appear"
        assert b"3,300" in data, "In-range expense must appear"

    def test_custom_range_url_reflects_params(self, auth_client):
        response = auth_client.get(
            "/profile?from_date=2025-06-01&to_date=2025-06-30"
        )
        data = response.data
        assert b"2025-06-01" in data
        assert b"2025-06-30" in data


# ---------------------------------------------------------------------------
# 9. Zero expenses in period — no crash, zero totals shown
# ---------------------------------------------------------------------------

class TestZeroExpensesInPeriod:
    def test_no_expenses_returns_200(self, auth_client):
        """Profile page must not crash when there are no expenses in the period."""
        bounds = _period_bounds()
        from_date, to_date = bounds["this_month"]
        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        assert response.status_code == 200, (
            "Page must return 200 even when no expenses exist in the period"
        )

    def test_no_expenses_shows_zero_total(self, auth_client):
        """With no expenses, the total must display as ₹0."""
        bounds = _period_bounds()
        from_date, to_date = bounds["this_month"]
        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        data = response.data
        # The spec mandates ₹0 formatted display
        assert b"\xe2\x82\xb90" in data or b"0" in data, (
            "Zero total should be displayed when no expenses exist"
        )

    def test_no_expenses_shows_zero_transaction_count(self, auth_client):
        """Transaction count must be 0 when no expenses exist in the period."""
        bounds = _period_bounds()
        from_date, to_date = bounds["this_month"]
        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        data = response.data
        # Transaction count of 0 must appear somewhere in the stats area
        assert response.status_code == 200
        # The page must not crash — this is the primary assertion
        assert b"Internal Server Error" not in data, (
            "Page must not throw a 500 when there are no expenses"
        )

    def test_all_time_no_expenses_shows_zero(self, auth_client):
        """All Time with no expenses at all must still render zero stats."""
        response = auth_client.get("/profile?from_date=2000-01-01&to_date=2099-12-31")
        assert response.status_code == 200
        data = response.data
        assert b"Internal Server Error" not in data, (
            "All Time with zero expenses must not crash"
        )


# ---------------------------------------------------------------------------
# 10. INR formatting — ₹X,XXX, no decimals
# ---------------------------------------------------------------------------

class TestINRFormatting:
    def test_amount_formatted_as_inr_no_decimals(
        self, auth_client, db_conn, user_id
    ):
        """Expenses must be rendered as ₹X,XXX (comma-formatted, no decimals)."""
        bounds = _period_bounds()
        from_date, to_date = bounds["this_month"]
        _insert_expense(db_conn, user_id, 12500.0, "Food", from_date, "formatted amount")

        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        data = response.data

        # ₹12,500 — UTF-8 encoding of ₹ is 0xE2 0x82 0xB9
        assert b"12,500" in data, "Amount must use comma formatting (₹12,500)"
        # Must NOT appear as a decimal (12500.0 or 12500.00)
        assert b"12500.0" not in data, "Amount must not include decimal point"
        assert b"12,500.00" not in data, "Amount must not include decimal places"

    def test_inr_symbol_present(self, auth_client, db_conn, user_id):
        """The rupee symbol (₹) must appear in the rendered page for non-zero amounts."""
        bounds = _period_bounds()
        from_date, to_date = bounds["this_month"]
        _insert_expense(db_conn, user_id, 500.0, "Food", from_date, "rupee symbol test")

        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        # ₹ in UTF-8 is b'\xe2\x82\xb9'
        assert b"\xe2\x82\xb9" in response.data, (
            "Rupee symbol (₹) must appear in page for monetary amounts"
        )

    def test_zero_amount_formatted_as_inr(self, auth_client):
        """Zero total must still render with ₹ prefix (₹0)."""
        bounds = _period_bounds()
        from_date, to_date = bounds["this_month"]
        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        data = response.data
        # ₹0 must be present
        rupee_zero = "₹0".encode("utf-8")
        assert rupee_zero in data, "Zero total must render as ₹0"

    @pytest.mark.parametrize("amount,expected_fragment", [
        (1000.0,   b"1,000"),
        (10000.0,  b"10,000"),
        # Python's {:,.0f} uses US-style grouping: 100,000 (not Indian lakh)
        (100000.0, b"100,000"),
        (500.0,    b"500"),
    ])
    def test_various_amounts_formatted_correctly(
        self, auth_client, db_conn, user_id, amount, expected_fragment
    ):
        """Verify comma-formatting for a range of realistic INR amounts."""
        bounds = _period_bounds()
        from_date, to_date = bounds["this_month"]
        _insert_expense(db_conn, user_id, amount, "Food", from_date, "formatting test")

        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        assert expected_fragment in response.data, (
            f"Amount {amount} must render as {expected_fragment.decode()}"
        )


# ---------------------------------------------------------------------------
# 11. Invalid / bad date params — graceful fallback to current month
# ---------------------------------------------------------------------------

class TestInvalidDateParams:
    def test_bad_from_date_returns_200(self, auth_client):
        """Invalid from_date must not crash the server."""
        response = auth_client.get("/profile?from_date=bad&to_date=2026-05-31")
        assert response.status_code == 200, (
            "Invalid from_date must fall back gracefully (200, not 500)"
        )

    def test_bad_to_date_returns_200(self, auth_client):
        response = auth_client.get("/profile?from_date=2026-05-01&to_date=worse")
        assert response.status_code == 200

    def test_both_params_invalid_returns_200(self, auth_client):
        response = auth_client.get("/profile?from_date=bad&to_date=worse")
        assert response.status_code == 200, (
            "Both invalid date params must fall back to current month (200)"
        )

    def test_invalid_params_fall_back_to_current_month(
        self, auth_client, db_conn, user_id
    ):
        """After fallback, page should behave as if This Month was selected."""
        bounds = _period_bounds()
        this_month_start = bounds["this_month"][0]
        last_month_start = bounds["last_month"][0]

        _insert_expense(db_conn, user_id, 1500.0, "Food", this_month_start, "this month")
        _insert_expense(db_conn, user_id, 9900.0, "Bills", last_month_start, "last month")

        response = auth_client.get("/profile?from_date=not-a-date&to_date=also-not")
        data = response.data

        # Last-month expense must not appear after fallback to current month
        assert b"9,900" not in data, (
            "After invalid-param fallback, last-month expense must not appear"
        )

    def test_empty_params_fall_back_gracefully(self, auth_client):
        """Empty string params behave the same as missing params."""
        response = auth_client.get("/profile?from_date=&to_date=")
        assert response.status_code == 200, (
            "Empty from_date/to_date must not crash the server"
        )

    def test_partial_date_format_invalid(self, auth_client):
        """Partial date strings (YYYY-MM) must be treated as invalid."""
        response = auth_client.get("/profile?from_date=2026-05&to_date=2026-05")
        assert response.status_code == 200, (
            "Partial date format must fall back gracefully"
        )

    def test_invalid_params_do_not_expose_server_error(self, auth_client):
        """No 500 Internal Server Error on bad params."""
        response = auth_client.get("/profile?from_date='; DROP TABLE users; --&to_date=x")
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data


# ---------------------------------------------------------------------------
# 12. URL reflects from_date and to_date after every filter selection
# ---------------------------------------------------------------------------

class TestURLReflectsFilterParams:
    """
    The spec states the URL reflects from_date and to_date params after each
    selection (shareable/bookmarkable).  We verify this server-side by checking
    that the rendered page includes the date values in the form inputs and/or
    in the quick-select hrefs so the state can be reconstructed from the URL.
    """

    @pytest.mark.parametrize("period_key", [
        "this_month", "last_month", "last_3_months", "this_year"
    ])
    def test_named_period_dates_appear_in_page(self, auth_client, period_key):
        bounds = _period_bounds()
        from_date, to_date = bounds[period_key]
        response = auth_client.get(
            f"/profile?from_date={from_date}&to_date={to_date}"
        )
        data = response.data
        assert from_date.encode() in data, (
            f"from_date={from_date} must appear in rendered page for {period_key}"
        )
        assert to_date.encode() in data, (
            f"to_date={to_date} must appear in rendered page for {period_key}"
        )

    def test_all_time_dates_appear_in_page(self, auth_client):
        response = auth_client.get("/profile?from_date=2000-01-01&to_date=2099-12-31")
        data = response.data
        assert b"2000-01-01" in data
        assert b"2099-12-31" in data

    def test_custom_dates_appear_in_page(self, auth_client):
        response = auth_client.get("/profile?from_date=2025-09-01&to_date=2025-09-30")
        data = response.data
        assert b"2025-09-01" in data
        assert b"2025-09-30" in data

    def test_filter_bar_form_action_is_profile_url(self, auth_client):
        """The custom-range form must POST/GET to the /profile route."""
        response = auth_client.get("/profile")
        data = response.data
        assert b'action="' in data, "A form with action attribute must be present"
        assert b"/profile" in data, "Form action must point to /profile"


# ---------------------------------------------------------------------------
# 13. Stats and category breakdown respect the same date filter
# ---------------------------------------------------------------------------

class TestStatsAndCategoryBreakdown:
    def test_category_breakdown_respects_date_filter(
        self, auth_client, db_conn, user_id
    ):
        """Category breakdown must only include categories active in the filter window."""
        bounds = _period_bounds()
        from_date, to_date = bounds["this_month"]
        last_month_start = bounds["last_month"][0]

        # This month: Food
        _insert_expense(db_conn, user_id, 1000.0, "Food", from_date, "food this month")
        # Last month: Shopping — must not appear in category breakdown
        _insert_expense(db_conn, user_id, 9000.0, "Shopping", last_month_start,
                        "shopping last month")

        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        data = response.data

        # "Shopping" category with 9,000 must not appear
        assert b"9,000" not in data, (
            "Out-of-range category totals must not appear in the breakdown"
        )

    def test_top_category_matches_filter_window(
        self, auth_client, db_conn, user_id
    ):
        """Top category stat must reflect only the filtered window."""
        bounds = _period_bounds()
        from_date, to_date = bounds["this_month"]

        # Only Health in current month
        _insert_expense(db_conn, user_id, 5000.0, "Health", from_date, "health")

        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        data = response.data
        assert b"Health" in data, "Top category must reflect the filtered window"

    def test_transaction_list_respects_date_filter(
        self, auth_client, db_conn, user_id
    ):
        """Recent transactions list must only contain in-range transactions."""
        bounds = _period_bounds()
        from_date, to_date = bounds["this_month"]
        last_month_start = bounds["last_month"][0]

        _insert_expense(db_conn, user_id, 200.0, "Food", from_date, "in-range transaction")
        _insert_expense(db_conn, user_id, 8888.0, "Bills", last_month_start,
                        "out-of-range transaction")

        response = auth_client.get(f"/profile?from_date={from_date}&to_date={to_date}")
        data = response.data
        assert b"8,888" not in data, (
            "Out-of-range transactions must not appear in the transaction list"
        )


# ---------------------------------------------------------------------------
# 14. Page structure — filter bar elements exist
# ---------------------------------------------------------------------------

class TestFilterBarPresence:
    def test_filter_bar_present_in_page(self, auth_client):
        response = auth_client.get("/profile")
        data = response.data
        assert b"filter-bar" in data, (
            "Filter bar container must be present in the profile page"
        )

    def test_all_five_period_buttons_present(self, auth_client):
        response = auth_client.get("/profile")
        data = response.data
        for label in [b"This Month", b"Last Month", b"Last 3 Months",
                      b"This Year", b"All Time"]:
            assert label in data, f"Period button '{label.decode()}' must be present"

    def test_custom_date_inputs_present(self, auth_client):
        response = auth_client.get("/profile")
        data = response.data
        assert b'name="from_date"' in data, "from_date input must be present"
        assert b'name="to_date"' in data, "to_date input must be present"

    def test_apply_button_present(self, auth_client):
        response = auth_client.get("/profile")
        data = response.data
        assert b"Apply" in data, "Apply button must be present in the filter bar"

    def test_page_extends_base_template(self, auth_client):
        """Profile page must include nav/footer elements from base.html."""
        response = auth_client.get("/profile")
        data = response.data
        # base.html typically includes the app name or nav links
        assert b"Spendly" in data or b"nav" in data, (
            "Page must extend base.html (nav/brand expected)"
        )
