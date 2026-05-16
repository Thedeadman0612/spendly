# Spec: Date Filter for Profile Page

## Overview
This step adds a date-range filter to the profile page so users can scope their
stats, recent transactions, and category breakdown to a specific time window.
The filter is driven by query-string parameters (`from_date` and `to_date`)
that are applied to every SQL query in the `/profile` view. A filter bar in the
template provides five quick-select period buttons (This Month, Last Month,
Last 3 Months, This Year, All Time) plus two `<input type="date">` fields for
a custom range. The URL updates on each selection so the filtered state is
bookmarkable and shareable.

## Depends on
- Step 1: Database setup (`expenses` table must exist with a `date` column)
- Step 2: Registration (real users must exist)
- Step 3: Login + Logout (session must store `user_id`)
- Step 4: Profile page design (`profile.html` template in place)
- Step 5: Backend routes for profile page (live DB queries driving the page)

## Routes
- `GET /profile` — already exists; extend to accept optional `from_date` and
  `to_date` query parameters (ISO date strings, e.g. `2026-05-01`) and apply
  them to all expense queries — logged-in only

No new routes.

## Database changes
No database changes. The existing schema is sufficient:

```
expenses (id, user_id, amount, category, date, description, created_at)
```

The `date` column (stored as `TEXT` in `YYYY-MM-DD` format) is used in SQL
`BETWEEN` clauses to implement the filter.

## Templates
- **Modify:** `templates/profile.html` — add a filter bar section between the
  stats row and the two-column grid. The filter bar must:
  - Contain five quick-select period buttons: "This Month", "Last Month",
    "Last 3 Months", "This Year", "All Time"
  - Contain a custom date range row with a `from_date` date input, a `to_date`
    date input, and an "Apply" button
  - Wrap the whole bar in a `<form method="GET" action="{{ url_for('profile') }}">`
    so the custom range submits as query params
  - Highlight the active quick-select button based on the current `active_period`
    context variable passed from the view
  - Each quick-select button should be an `<a>` tag linking to `/profile` with
    the correct `from_date` and `to_date` query params pre-computed (not JS)
  - Display the currently active date range as a human-readable subtitle below
    the stats row heading (e.g. "1 May 2026 – 16 May 2026")

- **Create:** `static/css/date-filter.css` — styles for the filter bar only
  (loaded via `{% block head %}` in `profile.html`)

## Files to change
- `app.py` — extend the `profile()` view function:
  1. Read `from_date` and `to_date` from `request.args`; default to the current
     calendar month if neither is provided
  2. Validate that both values parse as `YYYY-MM-DD`; if invalid, silently fall
     back to the current month default
  3. Pass `from_date` and `to_date` as parameters to every `expenses` query
     using `AND date BETWEEN ? AND ?`
  4. Determine `active_period` (one of `this_month`, `last_month`,
     `last_3_months`, `this_year`, `all_time`, or `custom`) by comparing the
     parsed dates against the known period boundaries; pass it to the template
  5. Pass `from_date`, `to_date`, and `active_period` as additional context
     variables to `render_template`
  6. Pre-compute the five period date ranges in the view and pass them to the
     template as a `periods` list so the template does no date arithmetic

- `templates/profile.html` — add filter bar (see Templates section above)

## Files to create
- `static/css/date-filter.css` — filter bar styles

## New dependencies
No new dependencies. Date arithmetic uses Python's `datetime` module (already
imported in `app.py`).

## Rules for implementation
- No SQLAlchemy or ORMs — use raw sqlite3 via `get_db()`
- Parameterised queries only — never f-string or %-format SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Keep all DB connections in a `try/finally` block and call `conn.close()` in `finally`
- Do not import any new modules not already in `app.py` (`datetime` is already imported)
- The "All Time" period should pass `from_date = "2000-01-01"` and `to_date = "2099-12-31"` to keep the SQL uniform (always use `BETWEEN`)
- Quick-select buttons must be plain `<a>` links — no JavaScript required for them
- The custom range form uses a standard HTML `<form method="GET">` — no JavaScript required
- Active period detection must be done server-side in the view, not in the template

### Period date calculations (Python, in the view)

```python
from datetime import date, timedelta

today = date.today()

# This Month
this_month_start = today.replace(day=1)
this_month_end   = today

# Last Month
first_of_this_month = today.replace(day=1)
last_month_end      = first_of_this_month - timedelta(days=1)
last_month_start    = last_month_end.replace(day=1)

# Last 3 Months  (approx — go back 3 calendar months from today)
if today.month > 3:
    three_months_start = today.replace(month=today.month - 3, day=1)
else:
    three_months_start = today.replace(year=today.year - 1,
                                        month=today.month + 9, day=1)
three_months_end = today

# This Year
this_year_start = today.replace(month=1, day=1)
this_year_end   = today

# All Time sentinel
ALL_TIME_START = "2000-01-01"
ALL_TIME_END   = "2099-12-31"
```

### SQL filter clause (add to every expenses query)

```sql
-- Replace  WHERE user_id = ?
-- With     WHERE user_id = ? AND date BETWEEN ? AND ?
-- Params:  (user_id, from_date, to_date)
```

### Period list passed to template

```python
periods = [
    {"key": "this_month",   "label": "This Month",   "from": this_month_start.isoformat(),  "to": this_month_end.isoformat()},
    {"key": "last_month",   "label": "Last Month",   "from": last_month_start.isoformat(),  "to": last_month_end.isoformat()},
    {"key": "last_3_months","label": "Last 3 Months","from": three_months_start.isoformat(),"to": three_months_end.isoformat()},
    {"key": "this_year",    "label": "This Year",    "from": this_year_start.isoformat(),   "to": this_year_end.isoformat()},
    {"key": "all_time",     "label": "All Time",     "from": ALL_TIME_START,                "to": ALL_TIME_END},
]
```

### Active period detection

```python
def detect_period(from_date_str, to_date_str, periods):
    for p in periods[:-1]:  # skip all_time; check it last
        if from_date_str == p["from"] and to_date_str == p["to"]:
            return p["key"]
    if from_date_str == ALL_TIME_START and to_date_str == ALL_TIME_END:
        return "all_time"
    return "custom"
```

### Filter bar template markup (inside `{% block content %}`)

```html
{# Filter bar #}
<div class="filter-bar">
  <div class="filter-periods">
    {% for p in periods %}
    <a href="{{ url_for('profile', from_date=p.from, to_date=p.to) }}"
       class="filter-btn {% if active_period == p.key %}filter-btn--active{% endif %}">
      {{ p.label }}
    </a>
    {% endfor %}
  </div>
  <form method="GET" action="{{ url_for('profile') }}" class="filter-custom">
    <input type="date" name="from_date" value="{{ from_date }}" class="filter-input">
    <span class="filter-sep">to</span>
    <input type="date" name="to_date"   value="{{ to_date }}"   class="filter-input">
    <button type="submit" class="filter-apply-btn">Apply</button>
  </form>
</div>
```

## Definition of done
- [ ] Visiting `/profile` with no query params defaults to the current calendar
      month (stats and transactions reflect only that month's expenses)
- [ ] Clicking "This Month" highlights that button and shows only current-month expenses
- [ ] Clicking "Last Month" highlights that button and shows only last-month expenses
- [ ] Clicking "Last 3 Months" highlights that button and shows only expenses
      from the past three calendar months
- [ ] Clicking "This Year" highlights that button and shows only this year's expenses
- [ ] Clicking "All Time" highlights that button and shows all expenses regardless of date
- [ ] Entering a custom from/to date and clicking "Apply" filters stats,
      transactions, and category breakdown to that exact range
- [ ] The URL reflects `from_date` and `to_date` query params after every filter
      selection (shareable/bookmarkable)
- [ ] A user with zero expenses in the selected period sees ₹0 total, 0
      transactions, empty tables, and no crash
- [ ] All monetary amounts remain formatted as `₹X,XXX` (INR, comma-formatted, no decimals)
- [ ] `pytest` passes with no regressions
