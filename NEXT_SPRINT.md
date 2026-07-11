# Next Sprint — deliberately out of scope for now

*(Multi-TA accounts shipped: email + password sign-in, per-TA team scoping,
and in-place upgrade of pre-accounts databases — the first account registered
adopts existing teams.)*

## Instructor read-only dashboard

A cross-TA view for instructors: all teams across all TAs with roll-up
status dots, risk flags, and export-all. Suggested shape:

- `role` column on `ta` (`ta` / `instructor`).
- Instructor routes are read-only versions of the Summary tab plus a
  cohort-wide risk table (`metrics.py` already computes everything needed —
  it's pure and takes plain data, so it can be reused unchanged).
- Exports reuse `export.py` as-is; "export all" would iterate every TA's
  teams instead of `services.teams_for(g.ta)`.

## Account hardening (needed before hosting beyond a trusted few)

- **CSRF protection** (e.g. Flask-WTF) — there are real sessions now, so
  cross-site request forgery is meaningful once the app is reachable beyond
  localhost.
- **Password reset** — currently whoever runs the server resets passwords
  from a Flask shell; a proper flow needs outbound email.
- **Invite-only registration** — `/register` is open; fine on a LAN handed
  to a few TAs, not fine on the public internet.
- Rate-limit `/login`.

## Hosting follow-ups

*(Deployed on PythonAnywhere free tier — see DEPLOY.md. `DATABASE_URL` and
`HTTPS_ONLY` env vars are supported for any future host.)*

- Move to Postgres only if many TAs write concurrently — SQLAlchemy makes
  that a connection-string change plus a one-time data copy.
- Browser-local call drafts are keyed by call id only; if two TAs shared a
  browser profile, scope draft keys by account too.

## Smaller follow-ups

- Remove / archive members who leave a team mid-course (currently members
  can be edited but not removed, to protect historical call entries).
- Per-call "duplicate last call's scores" shortcut for stable teams.
- Bulk milestone advance ("everyone moves to M3") across teams.
- Per-TA cohort label, if two TAs ever run different cohorts on one server
  (it's a single app-wide setting today).
