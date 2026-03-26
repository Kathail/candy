# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Candy Route Planner is a Flask web application for managing sales routes, customer visits, payments, and balances for a candy/beverage distribution business.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server (debug mode)
FLASK_ENV=development python wsgi.py

# Run with gunicorn (production)
gunicorn wsgi:app

# Import customer data from CSV
python import_customers.py customers_cleaned.csv              # Import with clear
python import_customers.py customers_cleaned.csv --clear-only # Only clear data
python import_customers.py customers_cleaned.csv --no-clear   # Import without clearing

# Clean customer CSV data (removes duplicates, standardizes cities, cleans phone numbers)
python clean_customers.py
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection URL | `sqlite:///candy_route.db` |
| `SECRET_KEY` | Flask secret key for sessions/CSRF | dev key (change in prod) |
| `FLASK_ENV` | Set to `development` for debug mode | production |
| `FLASK_HOST` | Host to bind to | `127.0.0.1` |
| `FLASK_PORT` | Port to bind to | `5000` |

## Architecture

**Stack:** Flask 3.0 + SQLAlchemy + Flask-Migrate + Jinja2 templates + Tailwind CSS + HTMX + Alpine.js

**Database:** SQLite for development (`instance/candy_route.db`), PostgreSQL for production via `DATABASE_URL` environment variable. Flask-Migrate (Alembic) is configured for schema migrations. Money columns use `Numeric(10, 2)` — never use `Float` for currency.

### Project Structure

```
wsgi.py              # Entry point (creates app, runs init_db, starts server)
app/
├── __init__.py      # App factory (create_app), extension init (db, migrate, csrf, login)
├── models.py        # User, Customer, RouteStop, Payment, ActivityLog
├── helpers.py       # is_safe_redirect_url, admin_required, generate_receipt_pdf
├── init_db.py       # Database init, schema migrations, seed data
└── routes/
    ├── __init__.py  # Blueprint registration
    ├── auth.py      # login, logout, change_password
    ├── admin.py     # user management, CSV imports, reimport
    ├── dashboard.py # / (home dashboard)
    ├── customers.py # CRUD, search, archive, payments, activity
    ├── route.py     # today's route, stops, receipts, summary, offline/sw
    ├── planner.py   # route planning, calendar, optimize
    ├── balances.py  # outstanding balances, record payment
    ├── analytics.py # KPIs, charts, metrics
    ├── leads.py     # lead CRUD, convert to customer
    ├── reports.py   # tax reports, financial exports (CSV/PDF/Excel)
    ├── api.py       # JSON APIs (offline sync, today's route)
    └── exports.py   # CSV exports (customers, payments, routes)
templates/           # Jinja2 templates
static/              # CSS, JS, icons, service worker
```

### Database Models (defined in app/models.py)

- **User** - username, email, password_hash, role (admin/sales)
- **Customer** - name, city, address, phone, notes, balance, last_visit, status, tax_exempt
- **RouteStop** - customer_id, route_date, sequence, completed, notes
- **Payment** - customer_id, amount, payment_date, receipt_number, previous_balance, notes
- **ActivityLog** - customer_id, action, description, created_at

### Blueprint URL Mapping

| Blueprint | URL Prefix | Key Endpoints |
|-----------|-----------|---------------|
| `dashboard` | `/` | Dashboard |
| `route` | `/route` | Today's route, stops, receipts |
| `customers` | `/customers` | Customer CRUD, payments |
| `balances` | `/balances` | Outstanding balances |
| `planner` | `/planner` | Route planning |
| `analytics` | `/analytics` | Business analytics |
| `leads` | `/leads` | Lead management |
| `reports` | `/reports` | Tax/financial reports |
| `auth` | `/login`, `/logout`, `/change-password` | Authentication |
| `admin` | `/admin/*` | User management, imports |
| `api` | `/api/*` | JSON APIs |
| `exports` | `/export/*` | CSV exports |

### Frontend Pattern

The app uses HTMX for partial page updates. Most actions return HTML fragments from `templates/partials/` rather than full page reloads. Alpine.js handles client-side interactivity like modals and mobile menu toggles.
