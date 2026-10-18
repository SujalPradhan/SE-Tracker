"""Import legacy per-team data from a JSON payload into a TA's account.

The payload mirrors the legacy Excel workbook (see docs/IMPORT_FORMAT.md):
teams with members, calls with per-member entries keyed by member name, and
milestone submissions. Import is all-or-nothing — if anything in the payload
is invalid, nothing is written and every problem is reported with its
location.

Because the legacy Client_Calls sheet has no "tasks for next call" column,
each entry's tasks_for_next is derived from the NEXT call's
"Tasks Assigned (Prev Call)" for the same member (the reverse of the app's
carry-forward), so imported history behaves exactly like natively logged
calls when the next call is created.
"""

import json
import re
from datetime import date

from models import (
    DEFAULT_MILESTONES,
    MAX_MILESTONES,
    SCORE_FIELDS,
    Call,
    CallEntry,
    Member,
    MilestoneSubmission,
    Team,
    db,
)
from services import parse_score

MILESTONE_RE = re.compile(rf"^M[1-{MAX_MILESTONES}]$")

ENTRY_TEXT_FIELDS = ("tasks_assigned_prev", "progress", "evidence_link", "remarks",
                     "tasks_for_next")
SUBMISSION_YN_FIELDS = ("code", "tests", "demo")


def _text(value):
    return "" if value is None else str(value).strip()


def _yn(value, default):
    """Accept booleans or Y/N-ish strings (the sheets use Y/N)."""
    if isinstance(value, bool):
        return value
    if value is None or _text(value) == "":
        return default
    upper = _text(value).upper()
    if upper in ("Y", "YES", "TRUE", "1"):
        return True
    if upper in ("N", "NO", "FALSE", "0"):
        return False
    raise ValueError(f"expected Y or N, got {value!r}")


def _validate_team(raw, index, seen_numbers, errors):
    """Normalize one team dict; records problems in `errors`."""
    where = f"teams[{index}]"
    team = {"members": [], "calls": [], "milestone_submissions": []}

    try:
        team["team_number"] = int(str(raw.get("team_number", "")).strip())
    except ValueError:
        errors.append(f"{where}: team_number must be a number, got {raw.get('team_number')!r}")
        team["team_number"] = None
    if team["team_number"] in seen_numbers:
        errors.append(f"{where}: duplicate team_number {team['team_number']} in payload")
    seen_numbers.add(team["team_number"])

    team["project_name"] = _text(raw.get("project_name"))
    team["repo_url"] = _text(raw.get("repo_url"))

    member_names = set()
    for i, m in enumerate(raw.get("members") or []):
        name = _text(m.get("name"))
        if not name:
            errors.append(f"{where}.members[{i}]: name is required")
            continue
        if name in member_names:
            errors.append(f"{where}.members[{i}]: duplicate member name {name!r}")
        member_names.add(name)
        team["members"].append(
            {"name": name, "role": _text(m.get("role")), "email": _text(m.get("email"))}
        )
    if not team["members"]:
        errors.append(f"{where}: at least one member is required")

    referenced_milestones = set()
    seen_call_nos = set()
    for i, c in enumerate(raw.get("calls") or []):
        team["calls"].append(
            _validate_call(c, f"{where}.calls[{i}]", member_names, seen_call_nos,
                           referenced_milestones, errors)
        )

    seen_subs = set()
    for i, s in enumerate(raw.get("milestone_submissions") or []):
        team["milestone_submissions"].append(
            _validate_submission(s, f"{where}.milestone_submissions[{i}]", member_names,
                                 seen_subs, referenced_milestones, errors)
        )

    # Milestone list: as given (or default), auto-extended with anything referenced.
    milestones = [_text(m) for m in (raw.get("milestones") or DEFAULT_MILESTONES)]
    bad = [m for m in milestones if not MILESTONE_RE.match(m)]
    if bad:
        errors.append(f"{where}: milestones must be M1–M{MAX_MILESTONES}, got {bad}")
        milestones = list(DEFAULT_MILESTONES)
    team["milestones"] = sorted(set(milestones) | referenced_milestones,
                                key=lambda m: int(m[1:]))
    return team


def _validate_submission(raw, where, member_names, seen_subs, referenced_milestones, errors):
    sub = {
        "member": _text(raw.get("member")),
        "milestone": _text(raw.get("milestone")),
        "report_section": _text(raw.get("report_section")),
        "evidence_link": _text(raw.get("evidence_link")),
        "remarks": _text(raw.get("remarks")),
    }
    if sub["member"] not in member_names:
        errors.append(f"{where}: unknown member {sub['member']!r}")
    if not MILESTONE_RE.match(sub["milestone"]):
        errors.append(f"{where}: milestone must be M1–M{MAX_MILESTONES}, "
                      f"got {sub['milestone']!r}")
    else:
        referenced_milestones.add(sub["milestone"])
    if (sub["member"], sub["milestone"]) in seen_subs:
        errors.append(f"{where}: duplicate submission for {sub['member']!r} "
                      f"in {sub['milestone']}")
    seen_subs.add((sub["member"], sub["milestone"]))
    for field in SUBMISSION_YN_FIELDS:
        value = _text(raw.get(field)).upper()
        if value not in ("", "Y", "N"):
            errors.append(f"{where}: {field} must be Y, N, or blank, got {raw.get(field)!r}")
            value = ""
        sub[field] = value
    return sub


def _validate_call(raw, where, member_names, seen_call_nos, referenced_milestones, errors):
    call = {"entries": []}

    try:
        call["call_no"] = int(str(raw.get("call_no", "")).strip())
        if call["call_no"] < 1:
            raise ValueError
    except ValueError:
        errors.append(f"{where}: call_no must be a positive number, got {raw.get('call_no')!r}")
        call["call_no"] = None
    if call["call_no"] in seen_call_nos:
        errors.append(f"{where}: duplicate call_no {call['call_no']}")
    seen_call_nos.add(call["call_no"])

    call["week"] = _text(raw.get("week"))
    call["milestone"] = _text(raw.get("milestone"))
    if not MILESTONE_RE.match(call["milestone"]):
        errors.append(f"{where}: milestone must be M1–M{MAX_MILESTONES}, "
                      f"got {raw.get('milestone')!r}")
    else:
        referenced_milestones.add(call["milestone"])

    call["date"] = None
    raw_date = _text(raw.get("date"))
    if raw_date:
        try:
            call["date"] = date.fromisoformat(raw_date)
        except ValueError:
            errors.append(f"{where}: date must be YYYY-MM-DD, got {raw_date!r}")

    seen_members = set()
    for i, e in enumerate(raw.get("entries") or []):
        call["entries"].append(
            _validate_entry(e, f"{where}.entries[{i}]", member_names, seen_members, errors)
        )
    return call


def _validate_entry(raw, where, member_names, seen_members, errors):
    entry = {"member": _text(raw.get("member"))}
    if entry["member"] not in member_names:
        errors.append(f"{where}: unknown member {entry['member']!r} "
                      "(names must match the team's members exactly)")
    if entry["member"] in seen_members:
        errors.append(f"{where}: duplicate entry for {entry['member']!r}")
    seen_members.add(entry["member"])
    try:
        entry["present"] = _yn(raw.get("present"), default=True)
        entry["spoke"] = _yn(raw.get("spoke"), default=False)
    except ValueError as exc:
        errors.append(f"{where}: {exc}")
        entry["present"], entry["spoke"] = True, False
    for field in ENTRY_TEXT_FIELDS:
        entry[field] = _text(raw.get(field))
    for name, _label, max_value in SCORE_FIELDS:
        try:
            entry[name] = parse_score(raw.get(name), max_value)
        except ValueError as exc:
            errors.append(f"{where}: {name}: {exc}")
            entry[name] = None
    return entry


def _derive_tasks_for_next(team):
    """Backfill tasks_for_next from the next call's carried-forward tasks."""
    calls = sorted((c for c in team["calls"] if c["call_no"]), key=lambda c: c["call_no"])
    for current, following in zip(calls, calls[1:]):
        carried = {e["member"]: e["tasks_assigned_prev"] for e in following["entries"]}
        for entry in current["entries"]:
            if not entry["tasks_for_next"] and carried.get(entry["member"]):
                entry["tasks_for_next"] = carried[entry["member"]]


def _create_team(ta, team):
    """Write one validated team; returns counts of created rows."""
    record = Team(
        ta_id=ta.id,
        team_number=team["team_number"],
        project_name=team["project_name"],
        repo_url=team["repo_url"],
    )
    record.milestones_json = json.dumps(team["milestones"])
    members = {}
    for m in team["members"]:
        member = Member(name=m["name"], role=m["role"], email=m["email"])
        record.members.append(member)
        members[m["name"]] = member
    db.session.add(record)

    entry_count = 0
    for c in team["calls"]:
        call = Call(team=record, call_no=c["call_no"], week=c["week"],
                    milestone=c["milestone"], date=c["date"])
        for e in c["entries"]:
            call.entries.append(
                CallEntry(
                    member=members[e["member"]],
                    present=e["present"],
                    spoke=e["spoke"],
                    tasks_assigned_prev=e["tasks_assigned_prev"],
                    tasks_for_next=e["tasks_for_next"],
                    progress=e["progress"],
                    evidence_link=e["evidence_link"],
                    remarks=e["remarks"],
                    **{name: e[name] for name, _label, _max in SCORE_FIELDS},
                )
            )
            entry_count += 1
        db.session.add(call)

    for s in team["milestone_submissions"]:
        db.session.add(
            MilestoneSubmission(
                team=record,
                member=members[s["member"]],
                milestone=s["milestone"],
                report_section=s["report_section"],
                code=s["code"],
                tests=s["tests"],
                demo=s["demo"],
                evidence_link=s["evidence_link"],
                remarks=s["remarks"],
            )
        )
    return {
        "members": len(team["members"]),
        "calls": len(team["calls"]),
        "entries": entry_count,
        "submissions": len(team["milestone_submissions"]),
    }


def import_payload(ta, payload):
    """Validate and import. Returns {"ok": True, "summary": …}
    or {"ok": False, "errors": […]} — with NOTHING written on error."""
    if isinstance(payload, list):  # accept a bare teams array too
        payload = {"teams": payload}
    if not isinstance(payload, dict) or not isinstance(payload.get("teams"), list) \
            or not payload["teams"]:
        return {"ok": False, "errors": ['Payload must be {"teams": [ … ]} with at least one team.']}

    errors, seen_numbers = [], set()
    teams = [_validate_team(t if isinstance(t, dict) else {}, i, seen_numbers, errors)
             for i, t in enumerate(payload["teams"])]

    numbers = [t["team_number"] for t in teams if t["team_number"] is not None]
    for existing in Team.query.filter(Team.ta_id == ta.id, Team.team_number.in_(numbers)):
        errors.append(
            f"Team {existing.display_number} already exists in your account — "
            "delete it (Edit team → Delete team) or renumber it in the payload."
        )

    if errors:
        return {"ok": False, "errors": errors}

    summary = {"teams": 0, "members": 0, "calls": 0, "entries": 0, "submissions": 0}
    for team in teams:
        _derive_tasks_for_next(team)
        counts = _create_team(ta, team)
        summary["teams"] += 1
        for key, count in counts.items():
            summary[key] += count
    db.session.commit()
    summary["team_numbers"] = [f"{t['team_number']:03d}" for t in teams]
    return {"ok": True, "summary": summary}
