# Gym Swift — Deployment & Subscription Management Guide

This guide covers (1) running locally, (2) deploying to the internet, and
(3) how **you, the software provider**, manage the gyms that buy Gym Swift on a
subscription and make sure they've paid before they keep access.

---

## 1. Run it locally (PyCharm or terminal)

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/ → click **Create gym account**. The database is a
bundled SQLite file — no setup needed. Migrations are included so it runs
immediately.

---

## 2. Deploy to the internet

Gym Swift is a standard Django app. It ships ready for production:

- **WhiteNoise** serves CSS/JS, so you don't need nginx for static files.
- **gunicorn** is the production web server.
- **dj-database-url** reads `DATABASE_URL` so you can use PostgreSQL.
- Settings read everything from **environment variables**.

### Environment variables to set (see `.env.example`)

| Variable | Example | Purpose |
|---|---|---|
| `SECRET_KEY` | a long random string | Django crypto. **Required in production.** |
| `DEBUG` | `False` | Never run production with `True`. |
| `ALLOWED_HOSTS` | `mygym.com,www.mygym.com` | Domains allowed to serve the app. |
| `CSRF_TRUSTED_ORIGINS` | `https://mygym.com` | For HTTPS form posts. |
| `DATABASE_URL` | `postgres://user:pass@host:5432/db` | Optional. Omit to use SQLite. |

Generate a secret key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

### Option A — Render.com (easiest, free tier)

1. Push this folder to a GitHub repo.
2. On Render: **New → Web Service**, connect the repo.
3. Build command: `./build.sh`   Start command: `gunicorn gymkhana.wsgi:application`
4. Add the environment variables above. Add a free **PostgreSQL** instance and
   copy its Internal Database URL into `DATABASE_URL`.
5. Deploy. `build.sh` runs `collectstatic` + `migrate` automatically.

### Option B — Railway.app

1. New Project → Deploy from GitHub.
2. Railway detects the `Procfile`. Add a PostgreSQL plugin (sets `DATABASE_URL`).
3. Add `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS=*.up.railway.app` (or your domain).
4. Deploy.

### Option C — PythonAnywhere

1. Upload the project / clone the repo.
2. Create a virtualenv, `pip install -r requirements.txt`.
3. In the Web tab, set the WSGI file to point at `gymkhana.wsgi`.
4. Set env vars in the WSGI file, run `migrate` and `collectstatic` in a console.

### Option D — DigitalOcean App Platform (recommended for you, via GitHub)

This is what you're using. App Platform deploys straight from your GitHub repo.

1. **Push your code to GitHub** (see the 3 commands at the very bottom of this file).
2. On DigitalOcean: **Create → Apps → GitHub**, pick the `gym-swift` repo, branch `main`.
3. It auto-detects Python/Django. Set:
   - **Run command:** `python manage.py migrate --noinput && gunicorn gymkhana.wsgi:application`
   - **Build command:** `pip install -r requirements.txt && python manage.py collectstatic --noinput`
4. **Add a database:** in the app, **Create/Attach → Dev Database (PostgreSQL)**.
   DigitalOcean injects a `DATABASE_URL` automatically — the app reads it.
5. **Environment variables** (App → Settings → App-Level Environment Variables):
   ```
   SECRET_KEY      = (a long random string)
   DEBUG           = False
   ALLOWED_HOSTS   = ${APP_DOMAIN}        (or your-app.ondigitalocean.app)
   ```
6. **Migrations** run automatically on every deploy (they're in the Run command
   above). No manual step needed for tables.

#### ⭐ Getting to your admin panel (this is the part you asked about)

The "panel to manage other people's gyms" **is the Django admin at `/admin/`**.
It only appears once you create a superuser on the server. On DigitalOcean:

1. Open your app → **Console** tab (gives you a shell inside the running app).
2. Run:
   ```bash
   python manage.py createsuperuser
   ```
   Enter a username, email, password — **this account is YOU, the software provider.**
3. Go to `https://your-app.ondigitalocean.app/admin/` and log in with it.
4. You'll see **Gyms**, **Members**, **Payments**, etc. for *every* gym. Open
   **Gyms** to manage each customer's subscription (status, paid-until date, fee).

> Note: a gym owner's normal login (the one they make at `/register/`) is **not**
> a superuser, so they only see their own gym and never the admin panel. Only the
> superuser you create above can see `/admin/` and manage everyone.

### Option E — Your own VPS (Ubuntu)

```bash
sudo apt update && sudo apt install python3-venv nginx
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY=... DEBUG=False ALLOWED_HOSTS=yourdomain.com
python manage.py collectstatic --noinput
python manage.py migrate
gunicorn gymkhana.wsgi:application --bind 127.0.0.1:8000 --workers 3
```
Put nginx in front as a reverse proxy to `127.0.0.1:8000` and add HTTPS with
Certbot. (WhiteNoise still serves the static files, so nginx only needs to proxy.)

### After any deploy
Create your **provider super-admin** account (this is YOU, not a gym owner):
```bash
python manage.py createsuperuser
```

---

## 3. Selling on subscription — how to manage paying customers

Every gym that signs up is a separate, isolated tenant. Each gym carries its own
subscription fields, and a built-in gate (`SubscriptionMiddleware`) **blocks a
gym automatically the moment its subscription lapses** — their data is kept safe,
they just can't log in to use it until you renew them.

### The control panel: Django admin
Go to **`/admin/`** and log in with your super-admin account. Open **Gyms**.
You'll see every customer gym with these columns you can edit inline:

- **Subscription status** — `trial`, `active`, `expired`, or `suspended`
- **Subscription until** — the date access is allowed up to
- **Subscription fee** — the monthly amount you charge that gym

### Typical workflow

1. **New customer signs up** at `/register/`. They automatically get a **30-day
   trial** (`status = trial`, `subscription_until = today + 30 days`).
2. **They pay you** for their first month/year.
3. In `/admin/` → Gyms, select that gym and either:
   - use the bulk action **"Extend subscription by 1 month"**, or
   - set **subscription_until** to the date they've paid through and
     **subscription_status = active**.
4. **If they DON'T pay:** do nothing. When `subscription_until` passes, the
   middleware blocks them and shows a "Subscription expired — contact provider"
   page. Their members/payments/history remain intact.
5. **To cut someone off immediately** (e.g. a chargeback): select the gym and run
   the **"Mark SUSPENDED"** action — they're blocked right away regardless of date.
6. **To reactivate:** extend the date (or "Mark ACTIVE") and they're back in
   instantly with all their data.

### How the block works (so you can trust it)
- A logged-in gym user hits any page → middleware checks their gym.
- `subscription_active` is **False** when status is `suspended`, OR when
  `subscription_until` is in the past.
- If inactive, every page redirects to `/subscription-expired/` (except logout).
- **Super-admins are never blocked**, so you always have access.

### Tracking who has paid
The admin list view is your ledger: sort/filter by **Subscription status** and
**Subscription until** to see who's active, who's expiring soon, and who's
overdue. Use **subscription_fee** to record what each gym pays and
**subscription_notes** for payment references (e.g. "Paid via bank transfer,
ref 12345, through 31 Aug").

> For fully automated online billing later, you can plug in Stripe/2Checkout and
> have their webhook update `subscription_until` — but the manual admin workflow
> above needs no extra services and works from day one.

---

## 4. Owner vs Employee mode (inside each gym)
- Each gym sets a **4-digit Owner Key** at signup (changeable in Settings).
- Front-desk staff use the app in **Employee mode**: members, attendance,
  payments, lockers — but **no Reports, Expenses, Salaries, or Settings**.
- Click **"Owner"** in the top bar and enter the 4-digit key to unlock the
  financial/owner features. Click **"Lock"** to return to Employee mode.

---

## 5. Backups
- **SQLite:** back up the `gymkhana.db` file regularly.
- **PostgreSQL:** use `pg_dump` (most hosts have automatic daily backups).

---

## Pushing your code to GitHub (run these 3 commands)

From inside the unzipped `gym-swift` folder:

```bash
git init && git add -A && git commit -m "Gym Swift updates"
git remote add origin https://github.com/asfandkhan8585-cpu/gym-swift.git   # first time only
git push -u origin main
```

If the repo already has commits and rejects the push, pull first:
```bash
git pull origin main --allow-unrelated-histories
git push -u origin main
```
After the push, DigitalOcean auto-redeploys (if auto-deploy is on) or click **Deploy**.
