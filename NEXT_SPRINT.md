# Next Sprint — deliberately out of scope for now

*(Multi-TA accounts shipped: email + password sign-in, per-TA team scoping,
and in-place upgrade of pre-accounts databases — the first account registered
adopts existing teams.)*

*(Shipped for SEP2026: the `/admin` cross-TA overview with Google Sign-In and
an allowlist, the read-only `/demo`, CSRF protection, a `/login` throttle,
and team numbers unique per TA rather than app-wide.)*

## Account hardening (needed before hosting beyond a trusted few)

- **Password reset** — currently whoever runs the server resets passwords
  from a Flask shell; a proper flow needs outbound email.
- **Invite-only registration** — `/register` is open; fine on a LAN handed
  to a few TAs, not fine on the public internet.
- The `/login` throttle is per gunicorn worker and in memory. Move it to a
  shared store if the app ever runs on more than one VM.

## Hosting follow-ups

*(Deployed on a GCP e2-micro VM in asia-south1 — see DEPLOY.md.)*

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
