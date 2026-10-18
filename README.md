# SE-Tracker

A web app for Software Engineering course TAs to track their teams through
client calls and milestones — replacing per-team Excel sheets with a workflow
built around **zero re-typing**:

- **Roster entered once.** Members auto-populate every call sheet, milestone
  grid, and export row. Editing a member updates everywhere.
- **Tasks flow between calls.** "Tasks for next call" recorded in call *N*
  appears as "Tasks Assigned (Prev Call)" in call *N+1* automatically.
- **Evidence links remember themselves.** Each member's evidence field
  prefills with their last non-empty link, falling back to the team repo URL.
- **"New call" is one click** — call number, milestone, date, roster,
  carried tasks, and evidence are all pre-filled; the TA only enters what's
  new (Spoke, scores, progress, remarks).
- **Metrics are always derived, never stored** — averages, contribution
  status, and risk flags are recomputed live, so a `#DIV/0!` is impossible.

## Setup

```sh
pip install -r requirements.txt
python app.py
```

Then open <http://127.0.0.1:5050>. The SQLite database (`se_tracker.db`) is
created automatically next to `app.py`.

Run the tests:

```sh
python -m pytest
```

## TA accounts

Each TA registers with a name, email, and password (hashed with Werkzeug —
no extra auth libraries). Teams, calls, milestone grids, summaries, and
exports are all scoped to the signed-in TA; another TA's teams simply don't
exist for you (they 404). Sign-in survives server restarts.

- **First run**: open the app → *Create an account*. If the database predates
  accounts, it's upgraded in place and **the first account registered adopts
  all existing teams** — register yourself before handing out the URL.
- Change your name or password anytime in **Settings**.

There is no password reset — this is a hand-out-to-a-few-people tool; whoever
runs the server can reset a password from a Flask shell if someone forgets.

## Everyday use

1. **Create a team** (sidebar → *+ New team*): team number, optional project
   name, default repo URL, and the roster. That's the last time you type any
   of it.
2. **During a call**: open the team → *Calls* tab → **+ New call**. One card
   per member: big Y/N toggles for Present/Spoke, score steppers
   (0–3 / 0–2 / 0–2 in 0.5 steps, blank allowed) with a live total, and the
   carried-forward tasks already filled in. The footer shows
   "3 of 5 members logged" as you go. **Save call** saves everyone at once.
   Drafts autosave to your browser as you type — a failed save keeps your
   entries and offers a retry.
3. **After a milestone**: *Milestones* tab → pick the milestone → fill the
   grid (report section, Code/Tests/Demo, remarks; evidence is prefilled).
4. **Before escalating**: *Summary* tab shows per-member attendance, silence,
   evidence counts, average score, contribution status, and risk flags — with
   the threshold rules spelled out in the legend so you can defend a flag.

## Overview dashboard

Sidebar → **Overview** (`/dashboard`) shows the signed-in TA's own students:
KPI tiles, team ranking, status per team, attendance vs. score (one dot per
student), attendance/speaking and score trends by call, a milestone heatmap,
per-team drill-down with sparklines, and a "Needs attention" list. Everything
is computed live in `overview.py` from the same `metrics.py` rules as the
Summary tab.

## Demo — `/demo`

A read-only TA view with seeded sample data (four teams), for showing the tool
to someone without an account. It's seeded on first visit (`demo_seed.py`).
Writes are refused on the server, not just hidden in the UI, and the demo
account never shows up in `/admin`.

## Admin overview — `/admin`

A read-only, cross-TA version of the overview for course staff. It adds a TA
filter, a TA comparison, calls per week, risk reasons, a searchable and
sortable table of every student, per-team detail pages, and an export of all
teams (one folder per TA). Sign-in is **Google only**: the verified email must be on the allowlist
(`DEFAULT_ADMIN_EMAILS` in `admin.py`, or the `ADMIN_EMAILS` env var). The
list is re-checked on every request. Admin sessions are separate from TA
sessions.

Local testing without Google: run with `ADMIN_DEV_EMAIL=<allowlisted email>
python app.py`. It is honoured only in debug mode.

## Deployment

See [DEPLOY.md](DEPLOY.md): a Google Cloud e2-micro VM in Mumbai running
gunicorn behind Caddy (automatic HTTPS), with nightly SQLite backups to Cloud
Storage. Ready-made files are in `deploy/gcp/`. `create_app` honors
`DATABASE_URL`, `HTTPS_ONLY=1`, `SECRET_KEY`, `BEHIND_PROXY=1`, and the Google
OAuth variables.

## Importing existing Excel data

Sidebar → **Import data**. Convert your legacy per-team workbooks to JSON
(the page includes a ready-made prompt you can paste into Claude along with
your .xlsx files — full spec in [docs/IMPORT_FORMAT.md](docs/IMPORT_FORMAT.md)),
paste the JSON, and hit Import. Everything is created under your account.

- All-or-nothing: invalid payloads import **nothing** and list every problem
  with its location.
- Team numbers that already exist in your account are rejected — delete the old team first
  (Edit team → **Delete team**) or renumber in the JSON.
- "Tasks for next call" is reconstructed from the following call's
  "Tasks Assigned (Prev Call)", so carry-forward keeps working on imported
  history.

## Changing the cohort label

Sidebar → **Settings** → edit *Cohort label* (default `SEP2026`). It's used
in export filenames, e.g. `SEP2026-Team-096.xlsx`. Stored in the `setting`
table, so it applies app-wide.

## Adding M6 to a team

Team page → *Milestones* tab → **+ Add M6**. Milestones are a per-team list
(default M1–M5, capped at M6), so one team gaining M6 doesn't affect others.

## Excel export

- Per team: the **Export .xlsx** button on the team page produces
  `{cohort}-Team-{NNN}.xlsx` with the exact legacy sheets:
  `Team_Info`, `Client_Calls`, `Milestone_Submissions`, `Call_Summary`
  (header kept literally as `Avg Score (12 Calls)`), and `Risk_Flags`.
- All teams: sidebar → **Export all teams** downloads a zip of per-team files.

Header rows are locked byte-for-byte by `tests/test_export.py` — if a header
ever drifts from the legacy format, the test suite fails.

## Project layout

| File | What it does |
| --- | --- |
| `app.py` | Flask app + TA routes, `/demo` (`python app.py` to run) |
| `admin.py` | `/admin` blueprint: Google Sign-In, allowlist, cross-TA overview |
| `overview.py` | Dashboard numbers for any set of teams (TA, demo, admin) |
| `demo_seed.py` | Seeded read-only demo account |
| `models.py` | SQLAlchemy models (Team, Member, Call, CallEntry, MilestoneSubmission, Setting) |
| `services.py` | Carry-forward logic, milestone grid prefill, remark chips, sidebar roll-ups |
| `metrics.py` | Pure computed metrics (avg score, statuses, risk rules) — fully unit-tested |
| `export.py` | Legacy-format Excel export via openpyxl |
| `static/` | `app.css` (design tokens, light/dark), `app.js` (forms), `motion.js` (animation), `overview.js` (charts) |
| `deploy/gcp/` | VM setup script, systemd unit, Caddyfile, backup script |
| `tests/` | Metrics, carry-forward, export, auth/scoping, overview, demo, admin tests |

See `NEXT_SPRINT.md` for what's deliberately out of scope in v1.
