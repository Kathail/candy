# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Candy Route Planner is a Flask web application for managing sales routes, customer visits, payments, and balances for a candy/beverage distribution business.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server (debug mode)
FLASK_ENV=development python app.py

# Run with gunicorn (production)
gunicorn app:app

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

**Stack:** Flask 3.0 + SQLAlchemy + Jinja2 templates + Tailwind CSS + HTMX + Alpine.js

**Database:** SQLite for development (`instance/candy_route.db`), PostgreSQL for production via `DATABASE_URL` environment variable.

### Key Files

- `app.py` - Single-file Flask app containing all routes, models, and configuration
- `templates/base.html` - Base layout with Tailwind theme configuration
- `templates/partials/` - Reusable HTMX partial templates for dynamic updates

### Database Models (defined in app.py)

- **Customer** - name, city, address, phone, notes, balance, last_visit
- **RouteStop** - customer_id, route_date, sequence, completed, notes
- **Payment** - customer_id, amount, payment_date, acknowledged, notes

### Main Routes

| Route | Purpose |
|-------|---------|
| `/` | Dashboard with daily metrics |
| `/route` | Today's delivery route with completion tracking |
| `/customers` | Customer management (search/filter/pagination) |
| `/balances` | Outstanding balances view |
| `/planner` | Route planning for upcoming visits |
| `/analytics` | Business analytics and KPIs |

### Frontend Pattern

The app uses HTMX for partial page updates. Most actions return HTML fragments from `templates/partials/` rather than full page reloads. Alpine.js handles client-side interactivity like modals and mobile menu toggles.
