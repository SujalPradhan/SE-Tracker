# SE-Tracker

SE-Tracker is a small web app for Software Engineering course TAs. Each TA
used to keep one Excel sheet per team for client calls and milestones. This
app replaces those sheets, and it's built so you never have to type the same
thing twice.

Live (SEP2026): https://34-100-168-34.sslip.io. To look around without an
account, open [`/demo`](https://34-100-168-34.sslip.io/demo).

## Why it exists

The spreadsheets worked, but a lot of the work was re-typing: the roster on
every tab, last week's tasks into this week's row, the same repo link over and
over. SE-Tracker fills those in for you:

- You enter the roster once. It shows up on every call sheet, milestone grid
  and export, and if you fix a name it's fixed everywhere.
- What you write under "Tasks for next call" shows up as "Tasks assigned" on
  the next call.
- Each student's evidence link starts as their last one, or the team repo if
  they haven't given one yet.
- A new call is one click. The call number, milestone, date and roster are
  already filled in, so during the call you only record attendance, scores and
  notes.
- Averages, statuses and risk flags are calculated when you open the page.
  They're never stored, so they can't go stale or show `#DIV/0!`.

## What's in it

**For TAs**

- **Teams, calls and milestones.** One card per student during a call, with
  Y/N toggles and +/- buttons for scores. Drafts autosave in your browser,
  and a failed save keeps everything you typed.
- **Summary tab.** Shows attendance, how often each student was silent,
  evidence, average score and risk flags. The rules behind each flag are
  listed on the page, so you can explain a flag to the student.
- **Overview (`/dashboard`).** Your own students at a glance:
  - team ranking and status mix;
  - attendance vs. score, one dot per student;
  - trends across calls;
  - a milestone heatmap;
  - a short "needs attention" list.
- **Excel export** in the original sheet format, per team or all at once.
- **Import** of old workbooks via JSON. See
  [docs/import-format.md](docs/import-format.md).
- **Light or dark.** Pick it at the bottom of the sidebar, or let it follow
  your system.

**For course staff**

- **`/admin`** is the same overview across every TA, plus:
  - a TA filter and a TA comparison;
  - calls per week;
  - a searchable table of every student.

  It's read-only. You sign in with Google, and only emails on the allowlist
  in `admin.py` can get in.
- **`/demo`** is a read-only TA account with four sample teams. It's handy for
  showing the tool to someone. You can't change anything in it, and it never
  appears in `/admin`.

## Running it locally

You need Python 3.11+.

```sh
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5050 and create an account. The SQLite database
(`se_tracker.db`) is created next to `app.py` on first run.

To try `/admin` without setting up Google, start the app with an
allowlisted email. This only works in debug mode:

```sh
ADMIN_DEV_EMAIL=23f2004759@ds.study.iitm.ac.in python app.py
```

Tests:

```sh
python -m pytest
```

## A typical week

1. **Add your teams.** In the sidebar, use **New team** and enter the team
   number, project name, repo URL and roster.
2. **During a client call,** go to the team's **Calls** tab and click
   **New call**. Mark who was present and who spoke, score each person, jot
   down progress and next tasks, then click **Save call** (or ⌘S).
3. **After a milestone,** fill in the **Milestones** tab: report section,
   Code / Tests / Demo, and remarks.
4. **Before you raise a concern,** check the **Summary** tab or the
   **Overview**.

A few smaller things:

- The cohort label (default `SEP2026`) is in **Settings**. It's used in
  export filenames like `SEP2026-Team-096.xlsx`.
- Teams start with milestones M1–M5. You can add M6 per team from the
  Milestones tab.
- There's no "forgot password" flow. Whoever runs the server can reset a
  password from a Flask shell.

## Project layout

```
app.py            Flask app, TA routes, /demo — run this
admin.py          /admin: Google sign-in, allowlist, cross-TA views
overview.py       numbers behind the dashboards (TA, demo, admin)
metrics.py        averages, statuses and risk rules (pure, unit-tested)
services.py       carry-forward, milestone grids, sidebar summaries
models.py         database models
export.py         Excel export in the legacy format
importer.py       JSON import of old workbooks
demo_seed.py      sample data for /demo

templates/        Jinja pages
static/           app.css, app.js (forms), motion.js (animation), overview.js (charts)
deploy/gcp/       VM setup script, systemd unit, Caddyfile, backup script
docs/             deployment, import format, roadmap
tests/            pytest suite
```

## More docs

- [docs/deployment.md](docs/deployment.md): how it runs on Google Cloud, and
  how to redeploy or restore a backup.
- [docs/import-format.md](docs/import-format.md): the JSON format for
  importing old Excel data.
- [docs/roadmap.md](docs/roadmap.md): what's not built yet, and why.
