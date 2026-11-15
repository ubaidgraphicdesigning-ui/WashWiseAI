# WashWise AI — Real Business Edition

A Streamlit + Supabase application for a laundry and dry-cleaning business. Public visitors can view the overview, services and track an order without creating an account. Staff-only operations use a shared Staff PIN.

## Features
- Supabase PostgreSQL persistence; no sample customers or orders are seeded.
- Business profile, service catalogue, customers, orders, order items and status history.
- Transactional order creation, payments and inventory adjustments through PostgreSQL functions.
- Inventory, expenses, payments, PDF receipts, reports and optional Gemini AI insights.
- Public order tracking verifies order number plus the last four digits of the registered phone number.
- Private customer and financial records are restricted to the staff workspace.

## Important access model
This assignment edition has no username/password login or signup. Public pages are open; operational pages require a shared Staff PIN. This is a lightweight single-business pilot model, not production-grade multi-user SaaS authentication. For a commercial multi-tenant product, implement individual Supabase Auth identities, membership/role tables, tenant-level RLS policies and audit attribution.

## Supabase setup
1. Create a Supabase project.
2. Open SQL Editor and run the complete `schema.sql`.
3. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
4. Add your Project URL, Supabase Secret key and a private Staff PIN.

Example:
```toml
SUPABASE_URL = "https://YOUR_PROJECT_REF.supabase.co"
SUPABASE_SECRET_KEY = "sb_secret_your_server_secret"
ADMIN_PIN = "choose-a-long-private-pin"
GEMINI_API_KEY = ""
GEMINI_MODEL = "gemini-2.5-flash"
```

Never commit `.streamlit/secrets.toml`, API keys or real customer data. The Supabase Secret key stays server-side and must never be embedded in browser code.

## Run locally (Windows PowerShell)
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

## Deploy on Streamlit Community Cloud
1. Select this GitHub repository.
2. Set the main file path to `streamlit_app.py`.
3. Add the TOML values in app Settings → Secrets.
4. Deploy and test public pages and the Staff PIN separately.

## Tests
```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

See `PROJECT_NOTES.md` for the intended no-login access model. Apply the database schema before running the app.
