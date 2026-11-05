# Northstar University Management System

A Django server-rendered university operations portal using SQLite for local development. The fictional Northstar University branding and demo records are illustrative; replace them before production deployment.

## Local setup

The workspace venv and Django are already present. Activate it and run:

```bash
source venv/bin/activate
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open http://127.0.0.1:8000/. The Django admin is at http://127.0.0.1:8000/admin/.

The demo data is safe to seed repeatedly. It resets the listed demo passwords to the documented values each time.

## Demonstration accounts

| Role | Email | Password |
| --- | --- | --- |
| Super administrator | `admin@northstar.edu` | `NorthstarAdmin2026!` |
| Registrar | `registrar@northstar.edu` | `NorthstarRegistrar2026!` |
| Lecturer | `lecturer@northstar.edu` | `NorthstarLecturer2026!` |
| Finance officer | `finance@northstar.edu` | `NorthstarFinance2026!` |
| Student | `student@northstar.edu` | `NorthstarStudent2026!` |

Use only fictional demo data in local development. Change all demo passwords before exposing the application to a network.

## Implemented workflows

- Email/password authentication, role-specific workspaces, Django password change/reset, and admin user management.
- Student and lecturer profiles, department/programme hierarchy, academic years, semesters, and academic units.
- Public admission application submission, staff review, approval-created student account, and admission notification.
- Student unit registration with department, active-semester, duplicate, and prerequisite checks; registrar approval/rejection.
- CAT, assignment, and exam score entry, configurable grade thresholds, result publication, and published-mark protection.
- Fee structures, student charges, manual payment recording in KES, payment balance validation, and collection reports.
- Lecturer/room timetable conflict validation.
- Attendance sessions and records with duplicate protection and enrolment validation.
- Book catalogue, checkout/return, copy counts, overdue detection, and assessed fine calculation.
- Announcements, notifications, audit entries, role-scoped CSV exports, and responsive role dashboards with live database counts.

Most record maintenance screens use shared Django ModelForms and are also available through Django admin. Deactivation is provided through status/active fields rather than destructive deletes for core university records.

## Configuration and deployment notes

Copy `.env.example` values into your environment before deployment. `SECRET_KEY`, `DEBUG`, allowed hosts, and database connection details are read from environment variables. SQLite is the local default; set `DB_ENGINE=django.db.backends.postgresql` and the `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` variables for PostgreSQL (install a PostgreSQL driver in the deployment environment).

Password reset uses Django's console email backend locally, so the reset URL is printed in the server console. Configure a real email backend before production. Uploaded admissions documents accept PDF/JPG/PNG up to 5 MB. Configure private media storage and access controls before using real applicant documents.

Set `LIBRARY_DAILY_FINE` to configure the manual overdue fine rate in KES per day (defaults to `20.00`).

M-PESA is represented as an explicitly manual payment method only. No Daraja API integration is configured. Chart.js, Bootstrap, Bootstrap Icons, and the login image are delivered by external CDNs; an internet connection is needed for those assets.

Before production, set `DEBUG=False`, use a strong unique `SECRET_KEY`, configure HTTPS, PostgreSQL, secure media and email storage, backups, logging, and a production WSGI server. Run `python manage.py check --deploy` after production settings are configured.

## Tests

Run the automated workflow and authorization tests with:

```bash
python manage.py test
```
# university-management-system
