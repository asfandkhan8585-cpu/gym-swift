# Gym Swift — Gym Management Software

A complete, multi-tenant gym management web app built with **Django + SQL**.
Clean, fast, information-dense UI with switchable color themes.

> **Quick start:** open in PyCharm -> `pip install -r requirements.txt` ->
> `python manage.py migrate` -> `python manage.py runserver` ->
> visit http://127.0.0.1:8000/ and click **Create gym account**.
>
> **Deploying or selling it?** See **DEPLOYMENT.md** for hosting steps and the
> full subscription-management guide.

---

## Features

- **Multi-tenant / multi-user** — every gym signs up and gets a fully isolated
  workspace. Gyms never see each other's data.
- **Owner vs Employee roles** — front-desk staff run day-to-day operations;
  Reports, Expenses, Salaries and Settings are locked behind a **4-digit Owner
  Key**. Switch modes from the top bar.
- **Subscription gating (SaaS)** — sell it to multiple gyms; lapsed subscriptions
  are blocked automatically while their data is preserved. Managed from /admin/.
- **Dashboard** — big at-a-glance cards: active members, today's check-ins,
  revenue, net profit, expenses, defaulters, staff, lockers.
- **Members** — full Pakistan profile (CNIC/Form-B, blood group, emergency
  contact, medical notes), Gents/Ladies/Open shifts, trainer assignment,
  referrals. **Printable member record** card.
- **Former members archive** — removing a member keeps their record (with date &
  reason) and can be restored anytime; data is never lost.
- **Memberships** — Monthly / 3-Month / 6-Month / Annual and custom plans,
  with per-service flags (cardio, free weights, personal trainer, locker, steam).
- **Attendance** — one-tap present/absent for members and staff, live search.
- **Payments** — Cash / EasyPaisa / JazzCash / Bank Transfer, auto paid/partial/
  overdue status, one-click defaulter list.
- **Lockers** — visual grid; a locker is assigned only after its fee is paid,
  and is fully cleared (no lingering name) when released.
- **Expenses** — 15 categories with breakdown.
- **Employees** — full staff records, salary payment (auto-logged as expense),
  staff attendance, trainer specialization + trainees.
- **Reports & analytics** — monthly P&L, 6-month revenue-vs-expense trend,
  collection rate, active-plan distribution, top members, expense breakdown.
- **WhatsApp** — copy-paste fee reminders / welcome / expiry messages with
  auto-filled placeholders and one-click wa.me links.
- **Themes** — Light, Sage, Olive, Ocean, Charcoal (dark).
- **Currencies** — 150+ world currencies; pick yours in Settings and it's used
  everywhere.

---

## First-time use

1. Visit / -> you're sent to login.
2. Click **Create gym account** (/register/): enter gym name, username,
   password, and a **4-digit Owner Key**. You get a 30-day trial and land in
   Settings.
3. Fill in your gym's phone, currency, timings and payment details.
4. Add members, mark attendance, record payments.

**Multiple gyms:** each owner just visits /register/. Data is fully separate.

---

## Tech
- Django (Python) · SQLite (default) or PostgreSQL · WhiteNoise · gunicorn
- Semantic HTML5 + vanilla CSS3 (CSS-variable theming) — no JS frameworks
- Timezone: Asia/Karachi

## Project structure
```
gym-swift/
├── manage.py
├── requirements.txt
├── Procfile, build.sh, .python-version, .env.example   # deployment
├── DEPLOYMENT.md                                    # hosting + subscriptions
├── gymkhana/        # project config (settings, urls, wsgi)
├── gym/             # main app (models, views, forms, admin, middleware, migrations)
├── templates/gym/   # all HTML templates
└── static/css/      # the themed stylesheet
```

## Django admin (provider)
```bash
python manage.py createsuperuser
```
Then /admin/ to manage gyms and their subscriptions.
