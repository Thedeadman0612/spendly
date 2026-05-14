# Spec: Backend Routes For Profile Page

## Overview
This step replaces every hardcoded dict and list in the `/profile` view with real
SQLite queries. The profile page UI from Step 4 already exists and is already
receiving the right context variable names (`user`, `stats`, `transactions`,
`categories`); this step makes those variables live. No template changes are
expected — only the view logic in `app.py` changes.

## Depends on
- Step 1: Database setup (`users` and `expenses` tables must exist)
- Step 2: Registration (real user rows must be creatable)
- Step 3: Login + Logout (session must store `user_id`)
- Step 4: Profile page design (`profile.html` template and its context variables must be finalized)

## Routes
- `GET /profile` — already exists; replace hardcoded context with live DB data — logged-in only

No new routes.

## Database changes
No database changes. The existing schema is sufficient:

```
users    (id, name, email, password_hash, created_at)
expenses (id, user_id, amount, category, date, description, created_at)
```

## Templates
- **Modify:** none — `profile.html` already expects the correct context keys.
  If any key names differ from what the template uses, align the Python dict
  keys to match the template (do not change the template).

## Files to change
- `app.py` — rewrite the body of the `profile()` view function:
  1. Fetch the logged-in user row from `users` by `session["user_id"]`
  2. Compute `stats` with three aggregation queries (or one combined query)
  3. Fetch the five most-recent expense rows for `transactions`
  4. Fetch per-category totals for `categories`, compute percentage of grand total
  5. Format all monetary amounts as `₹X,XXX` strings
  6. Format `member_since` from the ISO `created_at` field (e.g. "May 2026")
  7. Map each category name to a CSS badge class

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw sqlite3 via `get_db()`
- Parameterised queries only — never f-string or %-format SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Keep all DB connections in a `try/finally` block and call `conn.close()` in `finally`
- Open one connection per logical operation group; do not hold a connection across
  all queries if they can each be short-lived
- Do not import any new modules not already in `app.py`
- `member_since` must be derived from `users.created_at` using Python's `datetime`
  module (already available in stdlib — no extra import needed beyond what's used)
- Badge-class mapping must be a plain Python dict at the top of the view function,
  not a separate helper file

### Queries to implement

```sql
-- 1. User row
SELECT id, name, email, created_at FROM users WHERE id = ?

-- 2. Aggregate stats (can be one query with multiple columns)
SELECT
    COALESCE(SUM(amount), 0)  AS total_spent,
    COUNT(*)                   AS transaction_count
FROM expenses WHERE user_id = ?

-- 3. Top category
SELECT category
FROM expenses
WHERE user_id = ?
GROUP BY category
ORDER BY SUM(amount) DESC
LIMIT 1

-- 4. Recent transactions (5 rows)
SELECT date, description, category, amount
FROM expenses
WHERE user_id = ?
ORDER BY date DESC, id DESC
LIMIT 5

-- 5. Category breakdown
SELECT category, SUM(amount) AS total
FROM expenses
WHERE user_id = ?
GROUP BY category
ORDER BY total DESC
```

### Amount formatting helper (inline, no separate function needed)

```python
# Format a float as ₹X,XXX — use Python's built-in format spec
f"₹{amount:,.0f}"
```

### Badge-class mapping

```python
BADGE_MAP = {
    "Food":          "badge-green",
    "Food & Dining": "badge-green",
    "Groceries":     "badge-green",
    "Transport":     "badge-gold",
    "Utilities":     "badge-gold",
    "Bills":         "badge-gold",
    "Health":        "badge-blue",
    "Entertainment": "badge-muted",
    "Shopping":      "badge-muted",
}
DEFAULT_BADGE = "badge-muted"
```

Use `BADGE_MAP.get(category, DEFAULT_BADGE)` when building each transaction row.

### Percentage calculation for categories

```python
grand_total = sum(row["total"] for row in category_rows)
percent = round((row["total"] / grand_total) * 100) if grand_total else 0
```

## Definition of done
- [ ] Visiting `/profile` while logged in shows the **real** user's name and email (not "Rahul Ghadiya" / "rahul@example.com")
- [ ] `member_since` on the profile page reflects the user's actual `created_at` date (e.g. "May 2026"), not a hardcoded string
- [ ] "Total Spent" stat matches the actual sum of that user's expenses in the database
- [ ] "Transactions" stat matches the actual count of that user's expense rows
- [ ] "Top Category" stat reflects the category with the highest total spend for that user
- [ ] Recent transactions table shows real rows from the `expenses` table, ordered newest first
- [ ] Category breakdown percentages sum to 100 % (or close; rounding artefacts are acceptable)
- [ ] A brand-new registered user (zero expenses) sees ₹0 total, 0 transactions, and empty tables — no crash
- [ ] All amounts are displayed as `₹X,XXX` (INR, comma-formatted, no decimals)
- [ ] No hardcoded user data remains in the `profile()` view function
- [ ] `pytest` passes with no regressions
