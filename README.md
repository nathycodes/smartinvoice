# SmartInvoice NG — Voice and Text-Based Smart Invoice Generator

A Django web app that lets Nigerian SMEs generate invoices by speaking or typing
a plain-English sentence, e.g.:

  "Create invoice for John Doe, 2 bags of rice at 15000 naira each, due in 7 days"

## Quick start

```bash
# 1. Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate

# 2. Install dependencies
pip install django pillow

# 3. Run database migrations (only needed if you delete db.sqlite3)
python manage.py migrate

# 4. Start the dev server
python manage.py runserver
```

Then open http://127.0.0.1:8000/ in **Google Chrome** (the voice feature needs
a browser that supports the Web Speech API — Chrome and Edge work; Firefox
does not support speech recognition).

## Demo login

The project ships with a pre-seeded demo account so you can explore it immediately:

- **Username:** `ngozi`
- **Password:** `ngozi12345`

This account ("SwiftMart Provisions & Electronics") already has sample
customers, products, invoices (created via real voice/text commands), and
payments, so the Dashboard, Reports, and Command Log pages all have data to show.

There's also a Django admin superuser:

- **URL:** http://127.0.0.1:8000/admin/
- **Username:** `admin`
- **Password:** `admin12345`

## Starting fresh (your own business)

Go to http://127.0.0.1:8000/signup/ to create a brand-new business account —
it starts empty so you can build up your own customers, products, and invoices.

## Re-seeding demo data

If you want to reset and regenerate the demo business from scratch:

```bash
python manage.py flush --noinput
python manage.py shell -c "from django.contrib.auth.models import User; User.objects.create_superuser('admin','admin@smartinvoice.ng','admin12345')"
python manage.py shell < seed_demo.py
```

## Project structure

```
smartinvoice/        Django project settings/urls
invoices/            Main app
  models.py          Business, Customer, Product, Invoice, InvoiceItem, Payment, CommandLog
  parser.py           The rule-based NLP command parsing engine (core feature)
  views.py            All page logic
  forms.py             Django forms
  templates/invoices/  HTML templates (dashboard, command panel, invoices, reports...)
  static/invoices/     CSS (style.css) and JS (voice.js — Web Speech API integration)
seed_demo.py          Script that populates realistic demo data via the real parser
manage.py             Django management entrypoint
db.sqlite3            Pre-seeded SQLite database (delete + migrate to start clean)
```

## How the voice/text parsing works

See `invoices/parser.py` — it's a self-contained, dependency-free module you
can run directly to see example output:

```bash
python invoices/parser.py
```

It uses regex/pattern matching (no paid AI API) to extract the customer name,
line items, quantities, prices, discount %, and due date from a single sentence.

## Tech stack

Python 3.12 · Django 6.0 · SQLite · HTML/CSS/JavaScript · Web Speech API (browser-native voice input)
