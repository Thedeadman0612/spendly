# Spec: Login and Logout

## Overview
Implement session-based login and logout so registered users can authenticate and maintain
a session across requests. The `GET /login` route already exists and renders the form; this
step adds the `POST /login` handler that verifies credentials, sets a Flask session, and
redirects to the dashboard (or a placeholder). The `/logout` placeholder route is promoted
to a real implementation that clears the session and redirects to the landing page.
A `secret_key` must be set on the app to enable signed session cookies.

## Depends on
- Step 01 — Database setup (`users` table and `get_db()` must be working)
- Step 02 — Registration (a user must exist to log in against)

## Routes
- `GET  /login`  — render login form — public (already exists, extend to accept `?registered=1` flash — already done)
- `POST /login`  — process login credentials, set session, redirect — public (add this handler)
- `GET  /logout` — clear session, redirect to landing — logged-in (replace placeholder)

## Database changes
No database changes. The `users` table already has `email` and `password_hash`.

## Templates
- **Modify:** `templates/login.html` — ensure the form has `method="POST"` and `action="{{ url_for('login') }}"`;
  add an `{% if error %}` block to display server-side errors (mirror the pattern in `register.html`)
- **Modify:** `templates/base.html` — add a logout link in the nav that is only visible when
  `session.user_id` is set; hide login/register links when the user is logged in

## Files to change
- `app.py` — add `session` to Flask imports; add `check_password_hash` to werkzeug imports;
  set `app.secret_key`; add `POST` handler to the `/login` route; replace the `/logout`
  placeholder with a real implementation

## Files to create
No new files.

## New dependencies
No new dependencies. `werkzeug.security` and Flask sessions are already available.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — never format user input into SQL strings
- Verify passwords with `werkzeug.security.check_password_hash`
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Store only `user_id` and `user_name` in the session — never store the password hash
- `app.secret_key` must be set before any session usage; use a hard-coded dev string for
  now (e.g. `"dev-secret-change-in-production"`) — a later step can move it to an env var
- On bad credentials (wrong email OR wrong password), show a single generic error:
  "Invalid email or password." — do not reveal which field was wrong
- Redirect after successful login to `url_for('dashboard')` if that route exists, otherwise
  to `url_for('landing')` as a temporary target (update when dashboard is built)
- `/logout` must use `session.clear()` and redirect to `url_for('landing')`
- Do not guard any existing routes with `@login_required` in this step — that belongs to a
  later hardening step

## Definition of done
- [ ] `GET /login` renders the login form without errors
- [ ] Submitting valid credentials sets a session and redirects away from `/login`
- [ ] After login, `session['user_id']` holds the correct user's integer id
- [ ] Submitting an unknown email re-renders `/login` with "Invalid email or password."
- [ ] Submitting a correct email but wrong password re-renders `/login` with the same error
- [ ] `GET /logout` clears the session and redirects to the landing page
- [ ] After logout, `session.get('user_id')` is `None`
- [ ] The nav in `base.html` shows a logout link only when a user is logged in
- [ ] App starts and runs without errors (`python app.py`)
- [ ] No unhandled exceptions reach the browser during any of the above cases
