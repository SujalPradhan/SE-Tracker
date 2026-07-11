# SE-Tracker import format

Paste this JSON into **Import data** (sidebar) while signed in — everything
is created under your account. Import is all-or-nothing: if anything is
invalid, nothing is saved and every problem is listed with its location.

## Shape

```json
{
  "teams": [
    {
      "team_number": 96,
      "project_name": "Campus Eats",
      "repo_url": "https://github.com/org/repo",
      "milestones": ["M1", "M2", "M3", "M4", "M5"],
      "members": [
        {"name": "Ananya Rao", "role": "Project Manager", "email": "ananya@study.iitm.ac.in"}
      ],
      "calls": [
        {
          "call_no": 1,
          "week": "W1",
          "milestone": "M1",
          "date": "2026-06-20",
          "entries": [
            {
              "member": "Ananya Rao",
              "present": "Y",
              "spoke": "N",
              "tasks_assigned_prev": "Draft requirements doc",
              "progress": "Doc v1 shared",
              "evidence_link": "https://github.com/org/repo/pull/3",
              "role_fulfillment": 2.5,
              "client_interaction": null,
              "initiative": 1,
              "remarks": "Good"
            }
          ]
        }
      ],
      "milestone_submissions": [
        {
          "member": "Ananya Rao",
          "milestone": "M1",
          "report_section": "Introduction",
          "code": "Y",
          "tests": "N",
          "demo": "",
          "evidence_link": "https://github.com/org/repo/pull/3",
          "remarks": "On time"
        }
      ]
    }
  ]
}
```

## Mapping from the legacy workbook

| Sheet | Goes to |
| --- | --- |
| `Team_Info` | `team_number` (numeric part of Team ID: `"096"` → `96`) + one `members` entry per row |
| `Client_Calls` | Group rows by `Call #` → one `calls` object per call (`week`, `milestone` from its rows); each row becomes an `entries` object |
| `Milestone_Submissions` | One `milestone_submissions` entry per row |
| `Call_Summary`, `Risk_Flags` | **Skip** — computed live by the app |

## Field rules

- `member` in entries/submissions must match a `members[].name` **exactly**.
- `present` / `spoke`: `"Y"` / `"N"` (booleans also accepted).
- Scores (`role_fulfillment` 0–3, `client_interaction` 0–2, `initiative` 0–2):
  numbers in 0.5 steps; a blank cell becomes `null`. **Do not include Total
  Score** — it is computed.
- Do not invent data: blank cells stay `""` (text) or `null` (scores/date).
- `date`: `YYYY-MM-DD`, or omit it — the legacy sheet has no date column.
- `milestones` is optional (defaults to M1–M5) and auto-extends to any
  milestone referenced by a call or submission (M6 max).
- `week`, `project_name`, `repo_url`, and all text fields are optional.
- `tasks_for_next` is optional: for call N it is derived automatically from
  call N+1's `tasks_assigned_prev` (the reverse of the app's carry-forward),
  so imported history keeps carrying tasks forward like natively logged calls.

## Constraints

- Team numbers must not already exist in the app — delete the old team
  (Edit team → Delete team) or renumber in the payload.
- One entry per member per call; one submission per member per milestone.
