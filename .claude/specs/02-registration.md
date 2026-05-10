# Spec: Registration

## Overview
Implement user registration so new visitors can create a Spendly account. The `/register`
route currently only handles GET (renders the form). This step wires up the POST handler:
validate input, reject duplicate emails, hash the password with werkzeug, insert the user
into the `users` table, and redirect to `/login` on success. No session is set here — that
belongs to the login step.

## Depends on
- Step 01 — Database setup (`users` table must exist, `get_db()` must be working)

## Routes
- `GET  /register` — render registration form — public (already exists, no change needed)
- `POST /register` — process registration form — public (add this handler)

## Database changes
No database changes. The `users` table from Step 01 already has all required columns:
`id`, `name`, `email`, `password_hash`, `created_at`.

## Templates
- **Modify:** `templates/register.html` — already contains `{% if error %}` block and
  a POST form; no structural changes needed unless error display styling is missing from CSS.

## Files to change
- `app.py` — add `POST` to the register route, import `request` / `redirect` / `url_for`
  from Flask, add form-handling logic

## Files to create
No new files.

## New dependencies
No new dependencies. `werkzeug.security` is already installed and imported in `database/db.py`.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — never format user input into SQL strings
- Hash passwords with `werkzeug.security.generate_password_hash`
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Do NOT set a session cookie in this step — that belongs to the login step
- Validate all three fields (name, email, password) server-side; re-render the form with
  an `error` message on any validation failure instead of raising an unhandled exception
- Password minimum length: 8 characters
- On duplicate email, catch the `sqlite3.IntegrityError` and return a user-friendly error
  ("An account with that email already exists.")
- On success, redirect to `url_for('login')` — do not redirect to a dashboard that does
  not exist yet
- Import `get_db` in `app.py` (it is already imported; just use it)

## Definition of done
- [ ] `GET /register` still renders the form without errors
- [ ] Submitting the form with all valid fields inserts a new row into `users`
- [ ] The stored password is a hash (not plain text) — verify via SQLite browser or `sqlite3` CLI
- [ ] Successful registration redirects to `/login`
- [ ] Submitting with a duplicate email re-renders the form with a visible error message
- [ ] Submitting with a password shorter than 8 characters re-renders with a visible error
- [ ] Submitting with a missing name or email re-renders with a visible error
- [ ] No unhandled exceptions reach the browser during any of the above cases
- [ ] App starts and runs without errors (`python app.py`)
