# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Spendly** — a Flask-based personal expense tracker. The project is structured as a step-by-step student build; many routes and the entire database layer are intentionally stubbed out as placeholders for future implementation.

## Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the dev server (port 5001)
python app.py

# Run tests
pytest

# Run a single test file
pytest tests/test_something.py

# Run a single test by name
pytest -k "test_name"
```

## Architecture

**Single-file Flask app** — all routes live in `app.py`. No blueprints yet.

**Template inheritance** — `templates/base.html` defines the shared nav, footer, and asset includes. All page templates extend it via `{% extends "base.html" %}`. Page-specific CSS is injected via `{% block head %}` and page-specific JS via `{% block scripts %}`.

**Static assets** — `static/css/style.css` is global; `static/css/landing.css` is landing-page-only (loaded only by `landing.html`). `static/js/main.js` is a shared stub where future JS will go.

**Database layer** — `database/db.py` is a student-written stub. When implemented it must provide:
- `get_db()` — SQLite connection with `row_factory` and foreign keys enabled
- `init_db()` — creates tables with `CREATE TABLE IF NOT EXISTS`
- `seed_db()` — inserts sample dev data

The SQLite file is `expense_tracker.db` (gitignored).

## Placeholder Routes

Several routes in `app.py` return plain strings — these are future student implementation steps:
- `/logout` — Step 3
- `/profile` — Step 4
- `/expenses/add` — Step 7
- `/expenses/<id>/edit` — Step 8
- `/expenses/<id>/delete` — Step 9
