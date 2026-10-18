# Import format

If you have teams in the old Excel workbooks, you can bring them in through
**Import data** in the sidebar. Turn the workbooks into JSON in the shape
below and paste it in. The import page also has a ready-made prompt: give it
to Claude along with your `.xlsx` files and it will do the conversion for you.

Everything is created under your account. The import is all or nothing: if
anything is wrong, nothing is saved, and you get a list of every problem and
where it is.

## The JSON

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

## Where things come from in the old workbook

| Sheet | Goes to |
| --- | --- |
| `Team_Info` | `team_number` (the number in the Team ID, so `"096"` becomes `96`), plus one `members` entry per row |
| `Client_Calls` | Group the rows by `Call #`. Each group is one `calls` object (take `week` and `milestone` from its rows), and each row is one of its `entries` |
| `Milestone_Submissions` | One `milestone_submissions` entry per row |
| `Call_Summary`, `Risk_Flags` | Skip these. The app works them out. |

## Rules

- `member` in entries and submissions must match a name in `members`
  exactly.
- `present` and `spoke` are `"Y"` or `"N"`. `true` and `false` also work.
- Scores are numbers in steps of 0.5: `role_fulfillment` 0–3,
  `client_interaction` 0–2, `initiative` 0–2. An empty cell becomes `null`.
  Leave out Total Score, because the app adds it up.
- Don't fill in gaps. Empty text stays `""`, and an empty score or date
  stays `null`.
- `date` is `YYYY-MM-DD`. The old sheet has no date column, so it's usually
  left out.
- `milestones` is optional. It defaults to M1–M5 and grows to cover any
  milestone a call or submission mentions, up to M6.
- `week`, `project_name`, `repo_url` and the other text fields are optional.
- `tasks_for_next` is optional too. For call N it's filled in from call N+1's
  `tasks_assigned_prev`, so carry-forward keeps working on imported history.

## Limits

- You can't import a team number you already have. Delete the old team first
  (Edit team → Delete team), or change the number in the JSON. Other TAs'
  team numbers don't matter.
- Give one entry per student per call, and one submission per student per
  milestone.
