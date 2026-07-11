"""Carry-forward logic and DB-backed helpers.

This module is the heart of the "zero re-typing" principle: everything a new
call or milestone grid can inherit from existing data is prefilled here.
"""

from collections import Counter
from datetime import date

import metrics
from models import Call, CallEntry, MilestoneSubmission, Team, db

DEFAULT_REMARK_CHIPS = ["Good", "Has to interact more in client meets"]

STATUS_DOT = {
    metrics.STATUS_ACTIVE: "green",
    metrics.STATUS_AT_RISK: "yellow",
    metrics.STATUS_LOW: "red",
    metrics.STATUS_NO_CALLS: "gray",
}


def parse_score(value, max_value):
    """Blank stays blank; otherwise snap to 0.5 steps within [0, max]."""
    if value is None or value == "":
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"not a number: {value!r}")
    return min(max(round(score * 2) / 2, 0), max_value)


def _entry_for(call, member):
    return next((e for e in call.entries if e.member_id == member.id), None)


def sorted_calls(team):
    return sorted(team.calls, key=lambda c: c.call_no)


def last_evidence(team, member):
    """Member's most recent non-empty evidence link, else the team repo URL."""
    for call in reversed(sorted_calls(team)):
        entry = _entry_for(call, member)
        if entry and entry.evidence_link.strip():
            return entry.evidence_link
    return team.repo_url or ""


def create_next_call(team):
    """One-click prefilled call: the TA should only enter what's new.

    Call # increments, milestone defaults to the current one, date is today,
    every member starts Present=Y with tasks carried from the previous call's
    "tasks for next" and evidence prefilled from their last link / team repo.
    """
    calls = sorted_calls(team)
    prev = calls[-1] if calls else None
    call = Call(
        team=team,
        call_no=prev.call_no + 1 if prev else 1,
        milestone=prev.milestone if prev else team.milestones[0],
        week="",
        date=date.today(),
    )
    db.session.add(call)
    for member in team.members:
        prev_entry = _entry_for(prev, member) if prev else None
        call.entries.append(
            CallEntry(
                member=member,
                present=True,
                spoke=False,
                tasks_assigned_prev=prev_entry.tasks_for_next if prev_entry else "",
                evidence_link=last_evidence(team, member),
            )
        )
    db.session.commit()
    return call


def member_records(team, member):
    """metrics.py records for one member, oldest call first.

    Only calls where the member has an entry count — a member added mid-course
    isn't penalised for calls that predate them. (In normal use every call has
    an entry for every member, created at call creation.)
    """
    records = []
    for call in sorted_calls(team):
        entry = _entry_for(call, member)
        if entry:
            records.append(
                {
                    "present": entry.present,
                    "spoke": entry.spoke,
                    "evidence_link": entry.evidence_link,
                    "scores": entry.scores,
                }
            )
    return records


def team_summary(team):
    """[(member, metrics dict, dot color), ...] in roster order."""
    rows = []
    for member in team.members:
        m = metrics.member_metrics(member_records(team, member))
        rows.append((member, m, STATUS_DOT[m["contribution_status"]]))
    return rows


def team_sidebar_info(team):
    """Roll-up for the sidebar: worst member status dot, calls logged, last call date."""
    severity = {"red": 3, "yellow": 2, "green": 1, "gray": 0}
    dot = "gray"
    for _, _, member_dot in team_summary(team):
        if severity[member_dot] > severity[dot]:
            dot = member_dot
    calls = sorted_calls(team)
    return {
        "team": team,
        "dot": dot,
        "call_count": len(calls),
        "last_call_date": calls[-1].date if calls else None,
    }


def milestone_grid(team, milestone):
    """One row per roster member for the milestone grid, prefilled.

    Existing submissions come back as-is; members without one get a fresh row
    with the evidence link prefilled by the same last-evidence-else-repo rule.
    """
    existing = {
        s.member_id: s
        for s in MilestoneSubmission.query.filter_by(team_id=team.id, milestone=milestone)
    }
    rows = []
    for member in team.members:
        sub = existing.get(member.id)
        rows.append(
            {
                "member": member,
                "report_section": sub.report_section if sub else "",
                "code": sub.code if sub else "",
                "tests": sub.tests if sub else "",
                "demo": sub.demo if sub else "",
                "evidence_link": sub.evidence_link if sub else last_evidence(team, member),
                "remarks": sub.remarks if sub else "",
            }
        )
    return rows


def save_milestone_grid(team, milestone, rows):
    """Upsert submissions from [{member_id, report_section, code, ...}, ...]."""
    roster_ids = {m.id for m in team.members}
    for row in rows:
        member_id = int(row["member_id"])
        if member_id not in roster_ids:
            continue
        sub = MilestoneSubmission.query.filter_by(
            team_id=team.id, member_id=member_id, milestone=milestone
        ).first()
        if not sub:
            sub = MilestoneSubmission(team_id=team.id, member_id=member_id, milestone=milestone)
            db.session.add(sub)
        sub.report_section = row.get("report_section", "")
        sub.code = row.get("code", "")
        sub.tests = row.get("tests", "")
        sub.demo = row.get("demo", "")
        sub.evidence_link = row.get("evidence_link", "")
        sub.remarks = row.get("remarks", "")
    db.session.commit()


def remark_chips(limit=6):
    """The TA's most-used remarks as tappable chips, defaults always included."""
    counts = Counter(
        e.remarks.strip()
        for e in CallEntry.query.filter(CallEntry.remarks != "")
        if e.remarks.strip()
    )
    for default in DEFAULT_REMARK_CHIPS:
        counts[default] += 0  # defaults always offered, even with no data yet
    chips = [text for text, _ in counts.most_common(limit)]
    for default in DEFAULT_REMARK_CHIPS:
        if default not in chips:
            chips.append(default)
    return chips


def teams_for(ta):
    """The signed-in TA's teams — every list, roll-up, and export is scoped by this."""
    return Team.query.filter_by(ta_id=ta.id).order_by(Team.team_number).all()
