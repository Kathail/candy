# Candy Route Planner

A web application for managing sales routes, customer visits, payments, and balances for a candy/beverage distribution business. Built with Flask and designed for mobile-first field use with offline support.

## Features

### Route Management
- **Daily route view** with stop-by-stop completion tracking
- **Quick-add customers** directly from the route page
- **Route optimization** that groups stops by city
- **Route summary** with completion stats and next-day preview
- **Batch receipt downloads** as a ZIP of PDFs for the day's payments

### Customer Management
- Full CRUD with search, filter, sort, and pagination
- **Customer profiles** with payment history, visit history, and activity log
- **Status tracking**: active, inactive (archived), and lead pipeline
- **Tax exempt** flag per customer for reporting
- **Balance tracking** with payment recording and receipt generation

### Lead Pipeline
- Separate lead management view
- Import leads from CSV
- Convert leads to active customers with one click
- Track lead source (referral, walk-in, cold-call, website, social, other)

### Payments & Balances
- Record payments from route, customer profile, or balances page
- **Auto-generated receipt numbers** (format: `RCP-YYYYMMDD-XXXX`)
- **PDF receipts** with previous balance, payment amount, and new balance
- **Aging buckets** (0-30, 31-60, 61-90, 90+ days) based on last payment
- Payment deletion with automatic balance restoration

### Analytics & Reports
- **Dashboard** with daily KPIs: route progress, collections, customer health
- **Analytics page** with revenue charts, top customers, city breakdown, route efficiency
- **Financial reports** exportable as CSV, PDF, or Excel
- Tax exempt sales reports with customer and transaction detail
- Configurable date ranges (week, month, quarter, year, custom)

### Data Import/Export
- CSV import for customers and leads (with duplicate detection)
- CSV export for customers, payments, and route history
- JSON database export/import for instance migration
- Admin reimport from seed CSV

### Progressive Web App
- Service worker for offline caching
- Offline payment queue that syncs when connectivity returns
- Installable on mobile devices via manifest.json

### Authentication & Authorization
- Role-based access: **admin** and **sales** roles
- Admin panel for user management (add, delete, toggle roles)
- Password change with 12-character minimum
- CSRF protection on all forms
- Safe redirect validation

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask 3.0, SQLAlchemy, Flask-Migrate (Alembic) |
| Database | SQLite (dev), PostgreSQL (prod) |
| Frontend | Jinja2 templates, Tailwind CSS, HTMX, Alpine.js |
| PDF | ReportLab |
| Excel | openpyxl |
| Auth | Flask-Login, Werkzeug password hashing |
| CSRF | Flask-WTF |
| Server | Gunicorn (prod) |

## Project Structure

```
candy/
├── wsgi.py                  # Entry point
├── requirements.txt         # Python dependencies
├── CLAUDE.md                # Dev instructions for Claude Code
├── app/
│   ├── __init__.py          # App factory, extensions (db, migrate, csrf, login)
│   ├── models.py            # User, Customer, RouteStop, Payment, ActivityLog
│   ├── helpers.py           # admin_required, safe redirect, PDF receipt generation
│   ├── init_db.py           # DB init, schema migrations, seed data
│   └── routes/
│       ├── __init__.py      # Blueprint registration
│       ├── auth.py          # Login, logout, change password
│       ├── admin.py         # User management, CSV imports
│       ├── dashboard.py     # Home dashboard with KPIs
│       ├── customers.py     # Customer CRUD, payments, activity log
│       ├── route.py         # Daily route, stops, receipts, summary
│       ├── planner.py       # Route planning, calendar, optimization
│       ├── balances.py      # Outstanding balances, payment recording
│       ├── analytics.py     # Business analytics and charts
│       ├── leads.py         # Lead pipeline management
│       ├── reports.py       # Financial and tax reports (CSV/PDF/Excel)
│       ├── api.py           # JSON APIs for offline mode
│       └── exports.py       # CSV data exports
├── templates/
│   ├── base.html            # Layout with nav, global search, payment modal
│   ├── dashboard.html       # Dashboard page
│   ├── route.html           # Daily route page
│   ├── customers.html       # Customer list page
│   ├── customer_profile.html # Individual customer page
│   ├── leads.html           # Leads list page
│   ├── balances.html        # Balances page
│   ├── planner.html         # Route planner page
│   ├── analytics.html       # Analytics page with Chart.js
│   ├── reports.html         # Reports and exports page
│   ├── login.html           # Login page
│   ├── change_password.html # Password change page
│   ├── route_summary.html   # End-of-day route summary
│   ├── partials/            # HTMX partial templates
│   ├── admin/               # Admin panel templates
│   └── errors/              # 404, 500, offline pages
└── static/
    ├── css/app.css          # Custom styles
    ├── js/app.js            # Client-side JS
    ├── js/offline.js        # Offline queue and sync
    ├── sw.js                # Service worker
    ├── manifest.json        # PWA manifest
    ├── icons/               # App icons
    └── vendor/              # Tailwind, HTMX, Alpine.js, Chart.js
```

## Getting Started

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
# Clone the repo
git clone <repo-url> candy
cd candy

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Run (Development)

```bash
FLASK_ENV=development python3 wsgi.py
```

The app starts at `http://127.0.0.1:5000`. On first run, a default admin user is created with a random password printed to the console.

### Run (Production)

```bash
export DATABASE_URL=postgresql://user:pass@host:5432/candy
export SECRET_KEY=your-secret-key
export ADMIN_PASSWORD=your-admin-password

gunicorn wsgi:app
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection URL | `sqlite:///candy_route.db` |
| `SECRET_KEY` | Flask secret key for sessions and CSRF | Dev key (insecure) |
| `FLASK_ENV` | Set to `development` for debug mode | `production` |
| `FLASK_HOST` | Host to bind to | `127.0.0.1` |
| `FLASK_PORT` | Port to bind to | `5000` |
| `ADMIN_PASSWORD` | Password for auto-created admin user | Random (printed to console) |

## Database

### Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| **User** | Authentication | username, email, role (admin/sales) |
| **Customer** | Customer records | name, city, balance, status (active/inactive/lead), tax_exempt |
| **RouteStop** | Route schedule | customer_id, route_date, sequence, completed |
| **Payment** | Payment records | amount, payment_date, receipt_number, previous_balance |
| **ActivityLog** | Audit trail | customer_id, action, description |

Money fields (`balance`, `amount`, `previous_balance`) use `Numeric(10, 2)` for precision.

### Migrations

The app includes automatic schema migrations in `init_db.py` that run on startup. For new migrations, Flask-Migrate (Alembic) is configured:

```bash
flask db init       # First time only
flask db migrate -m "description"
flask db upgrade
```

## Data Import

### Import customers from CSV

```bash
# Import with clear (replaces existing data)
python import_customers.py customers_cleaned.csv

# Import without clearing
python import_customers.py customers_cleaned.csv --no-clear

# Only clear data
python import_customers.py customers_cleaned.csv --clear-only
```

CSV format: `name` (required), `address`, `city`, `phone`, `notes`, `balance`

### Import leads from CSV

```bash
python import_leads.py leads.csv
```

### Clean customer data

```bash
python clean_customers.py
```

Removes duplicates, standardizes city names, and cleans phone numbers.

### Database export/import

```bash
# Export to JSON
python export_database.py backup.json

# Import from JSON
python import_database.py backup.json --clear
```

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/customers/search?q=` | GET | Quick customer search (returns JSON) |
| `/api/route/today` | GET | Today's route data for offline mode |
| `/api/sync` | POST | Sync queued offline payments |
| `/customer/<id>/details` | GET | Customer details for planner modal |
| `/planner/all-stops` | GET | All scheduled stops for calendar view |

## Frontend Architecture

The app uses **HTMX** for dynamic partial updates without full page reloads. Key patterns:

- **Search/filter**: `hx-get` triggers return table row partials from `templates/partials/`
- **Stop completion**: `hx-post` updates individual stop cards inline
- **Activity log**: `hx-get` loads customer activity on demand
- **Global search**: Alpine.js component in `base.html` calls `/api/customers/search`
- **Route planner**: Alpine.js manages drag-and-drop with `hx-post` for persistence
- **Payment modal**: Global modal in `base.html` for quick payments from any page

## Deployment

### Render

The app is configured for Render deployment:

- Automatically converts `postgres://` URLs to `postgresql://`
- Gunicorn as the production server
- `DATABASE_URL` from Render's PostgreSQL addon

Set these environment variables in the Render dashboard:
- `DATABASE_URL` (auto-set by Render PostgreSQL)
- `SECRET_KEY`
- `ADMIN_PASSWORD`

## License

Private project.
