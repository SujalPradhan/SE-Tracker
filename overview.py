"""Overview dashboard numbers — shared by the TA, demo, and admin views.

Everything is derived from the teams passed in (never a global query), so a
TA's overview can only ever contain that TA's students. The result is plain
data: templates render it and the charts receive it as JSON.
"""

from collections import Counter, defaultdict
from datetime import timedelta

import metrics
import services

MAX_SCORE = 7  # role_fulfillment (3) + client_interaction (2) + initiative (2)

STATUS_KEY = {
    metrics.STATUS_ACTIVE: "active",
    metrics.STATUS_AT_RISK: "risk",
    metrics.STATUS_LOW: "low",
    metrics.STATUS_NO_CALLS: "none",
}
STATUS_LABEL = {"active": "Active", "risk": "At risk", "low": "Low", "none": "No calls"}
STATUS_ORDER = ["active", "risk", "low", "none"]
SEVERITY = {"none": 0, "active": 1, "risk": 2, "low": 3}


def _pct(part, whole):
    return round(part / whole * 100) if whole else None


def _mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def _student(team, member, ta_name):
    records = services.member_records(team, member)
    m = metrics.member_metrics(records)
    logged, attended = m["calls_logged"], m["calls_attended"]
    status = STATUS_KEY[m["contribution_status"]]
    series = []
    for call in services.sorted_calls(team):
        entry = next((e for e in call.entries if e.member_id == member.id), None)
        if entry:
            series.append(round(metrics.call_total(entry.scores), 2) if entry.present else None)
    return {
        "id": member.id,
        "name": member.name,
        "role": member.role,
        "team_id": team.id,
        "team": team.display_number,
        "ta": ta_name,
        "avg": None if m["avg_score"] is None else round(m["avg_score"], 2),
        "avg_display": m["avg_display"],
        "logged": logged,
        "attended": attended,
        "attendance": _pct(attended, logged),
        "speaking": _pct(attended - m["silent_calls"], attended),
        "evidence": _pct(m["calls_with_evidence"], logged),
        "status": status,
        "reasons": metrics.risk_reasons(records),
        "series": series,
    }


def build_overview(teams, ta_names=None):
    """Dashboard data for exactly these teams.

    ta_names: optional {ta_id: name}, filled in on each student/team (admin view).
    """
    ta_names = ta_names or {}
    team_rows, students = [], []
    by_call = defaultdict(lambda: {"total": 0, "present": 0, "spoke": 0, "scores": []})
    milestone_names = set()

    for team in teams:
        ta_name = ta_names.get(team.ta_id, "")
        members = [_student(team, member, ta_name) for member in team.members]
        students.extend(members)
        calls = services.sorted_calls(team)
        entries = [e for c in calls for e in c.entries]
        present = [e for e in entries if e.present]

        for call in calls:
            bucket = by_call[call.call_no]
            for e in call.entries:
                bucket["total"] += 1
                bucket["scores"].append(metrics.call_total(e.scores))
                if e.present:
                    bucket["present"] += 1
                    bucket["spoke"] += 1 if e.spoke else 0

        status_counts = Counter(s["status"] for s in members)
        worst = max((s["status"] for s in members), key=SEVERITY.get, default="none")
        team_rows.append({
            "id": team.id,
            "number": team.display_number,
            "project": team.project_name,
            "ta": ta_name,
            "ta_id": team.ta_id,
            "avg": _mean([s["avg"] for s in members]),
            "attendance": _pct(len(present), len(entries)),
            "speaking": _pct(sum(1 for e in present if e.spoke), len(present)),
            "calls": len(calls),
            "last_call": calls[-1].date.isoformat() if calls and calls[-1].date else None,
            "members": len(members),
            "flagged": sum(1 for s in members if s["reasons"]),
            "status": worst,
            "status_counts": {k: status_counts.get(k, 0) for k in STATUS_ORDER},
            "milestones": _milestone_cells(team),
        })
        milestone_names.update(team.milestones)

    # Within each team, strongest first; students with no calls go last.
    order = {t["id"]: i for i, t in enumerate(team_rows)}
    students.sort(key=lambda s: (order[s["team_id"]], s["avg"] is None, -(s["avg"] or 0)))
    flagged = sorted((s for s in students if s["reasons"]), key=lambda s: s["avg"] or 0)

    all_entries = sum(b["total"] for b in by_call.values())
    all_present = sum(b["present"] for b in by_call.values())
    all_spoke = sum(b["spoke"] for b in by_call.values())
    status_counts = Counter(s["status"] for s in students)
    reasons = Counter(r for s in students for r in s["reasons"])

    return {
        "kpis": {
            "teams": len(team_rows),
            "students": len(students),
            "calls": sum(t["calls"] for t in team_rows),
            "avg": _mean([s["avg"] for s in students]),
            "attendance": _pct(all_present, all_entries),
            "speaking": _pct(all_spoke, all_present),
            "flagged": sum(1 for s in students if s["reasons"]),
        },
        "max_score": MAX_SCORE,
        "status_counts": {k: status_counts.get(k, 0) for k in STATUS_ORDER},
        "status_labels": STATUS_LABEL,
        "teams": team_rows,
        "students": students,
        "flagged": flagged,
        "trend": [
            {
                "call": no,
                "attendance": _pct(b["present"], b["total"]),
                "speaking": _pct(b["spoke"], b["present"]),
                "avg": _mean(b["scores"]),
            }
            for no, b in sorted(by_call.items())
        ],
        "milestones": sorted(milestone_names, key=lambda m: int(m[1:]) if m[1:].isdigit() else 99),
        "reasons": reasons.most_common(),
    }


def _milestone_cells(team):
    """{milestone: {code, tests, demo, done}} as % of the roster marked Y."""
    roster = len(team.members)
    subs = defaultdict(list)
    for sub in team.submissions:
        subs[sub.milestone].append(sub)
    cells = {}
    for name in team.milestones:
        rows = subs.get(name, [])
        if not rows or not roster:
            cells[name] = None
            continue
        parts = {f: _pct(sum(1 for s in rows if getattr(s, f) == "Y"), roster)
                 for f in ("code", "tests", "demo")}
        parts["done"] = round(sum(parts.values()) / 3)
        cells[name] = parts
    return cells


def build_admin_extras(teams, tas, overview, weeks=12):
    """Cross-TA comparison and weekly call activity for the admin view."""
    per_ta = []
    for ta in tas:
        rows = [t for t in overview["teams"] if t["ta_id"] == ta.id]
        team_ids = {t["id"] for t in rows}
        studs = [s for s in overview["students"] if s["team_id"] in team_ids]
        last = max((t["last_call"] for t in rows if t["last_call"]), default=None)
        per_ta.append({
            "id": ta.id,
            "name": ta.name,
            "email": ta.email,
            "teams": len(rows),
            "students": len(studs),
            "calls": sum(t["calls"] for t in rows),
            "avg": _mean([s["avg"] for s in studs]),
            "flagged": sum(1 for s in studs if s["reasons"]),
            "last_call": last,
        })
    per_ta.sort(key=lambda r: (-r["teams"], r["name"].lower()))

    dated = [c.date for t in teams for c in t.calls if c.date]
    activity = []
    if dated:
        end = max(dated)
        end_monday = end - timedelta(days=end.weekday())
        counts = Counter((d - timedelta(days=d.weekday())) for d in dated)
        for i in range(weeks - 1, -1, -1):
            monday = end_monday - timedelta(weeks=i)
            activity.append({"week": monday.isoformat(), "label": monday.strftime("%d %b"),
                             "calls": counts.get(monday, 0)})
    return {"per_ta": per_ta, "activity": activity}
