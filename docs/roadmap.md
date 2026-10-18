# Roadmap

Things we've chosen not to build yet, and what would change our minds.

## Already done

- **TA accounts.** Each TA signs in with email and password and only sees
  their own teams.
- **SEP2026 release:**
  - the overview dashboard;
  - the cross-TA `/admin` view with Google sign-in;
  - the read-only `/demo`;
  - CSRF protection and a login throttle;
  - team numbers unique per TA, so two TAs can both have a Team 1;
  - the move to Google Cloud.

## Accounts

- **Password reset.** For now, whoever runs the server resets passwords from
  a Flask shell. A proper reset flow needs outbound email, which we haven't
  set up.
- **Invite-only sign-up.** Anyone with the link can register right now.
  That's been fine for a handful of TAs. If the link starts getting passed
  around, limit sign-up to IITM addresses or invites.
- **Login throttle.** It lives in memory, per worker. If we ever run more
  than one server, it needs a shared store.

## Hosting

- **Postgres.** Only worth it if lots of TAs save at the same time. Because
  the app uses SQLAlchemy, switching means a new connection string and a
  one-time data copy.
- **Draft keys.** Unsaved call drafts are stored in the browser per call. If
  two TAs ever shared one browser profile, the drafts should also be keyed by
  account.

## Smaller ideas

- Archive students who leave a team partway through. Right now you can edit
  members but not remove them, so their past call records stay intact.
- A "copy last call's scores" button for teams that don't change much week to
  week.
- Move every team to the next milestone at once.
- A cohort label per TA. It's one setting for the whole app today.
