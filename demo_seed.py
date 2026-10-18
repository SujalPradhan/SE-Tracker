"""Seeded, read-only demo account behind /demo.

ensure_demo_ta() is idempotent: the first visit to /demo builds the data, later
visits reuse it. Data is generated from a fixed random seed, so every
deployment shows the same story: a mix of strong, steady, quiet, and
struggling students across four teams.
"""

import json
import random
import secrets
from datetime import date, timedelta

from sqlalchemy.exc import IntegrityError

from models import TA, Call, CallEntry, Member, MilestoneSubmission, Team, db

DEMO_EMAIL = "demo@se-tracker.local"
DEMO_NAME = "Demo TA"

# archetype: (P(present), P(spoke | present), score level 0..1, evidence rate)
ARCHETYPES = {
    "star": (0.97, 0.95, 0.92, 0.95),
    "steady": (0.9, 0.75, 0.72, 0.85),
    "quiet": (0.85, 0.25, 0.5, 0.6),
    "absent": (0.4, 0.5, 0.35, 0.3),
    "fading": (0.75, 0.4, 0.42, 0.5),
}

TEAMS = [
    (12, "Campus Eats", "https://github.com/se-demo/campus-eats", 7, [
        ("Aarav Mehta", "Team Lead + Backend", "star"),
        ("Diya Sharma", "Frontend Developer", "steady"),
        ("Kabir Nair", "Backend Developer + Tester", "steady"),
        ("Meera Iyer", "UI/UX + Documentation", "quiet"),
        ("Rohan Gupta", "DevOps", "steady"),
    ]),
    (27, "StudySync", "https://github.com/se-demo/studysync", 6, [
        ("Ananya Rao", "Scrum Master", "star"),
        ("Vihaan Joshi", "Full-stack Developer", "star"),
        ("Isha Kulkarni", "Tester", "steady"),
        ("Arjun Reddy", "Backend Developer", "absent"),
    ]),
    (41, "LabSlot", "https://github.com/se-demo/labslot", 6, [
        ("Saanvi Pillai", "Team Lead", "steady"),
        ("Aditya Verma", "Frontend Developer", "fading"),
        ("Nisha Menon", "Backend Developer", "quiet"),
        ("Yash Patil", "Tester + Docs", "absent"),
        ("Tara Bose", "Database Designer", "steady"),
    ]),
    (58, "GreenRoute", "https://github.com/se-demo/greenroute", 5, [
        ("Kiara Das", "Product Owner", "star"),
        ("Dev Malhotra", "Backend Developer", "steady"),
        ("Riya Chatterjee", "Frontend Developer", "steady"),
        ("Neel Saxena", "Tester", "quiet"),
    ]),
]

TASKS = [
    "Finalise user stories for the next sprint",
    "Wire the login page to the API",
    "Write unit tests for the booking service",
    "Fix review comments on the PR",
    "Draft the milestone report section",
    "Set up CI for the repo",
    "Design the dashboard wireframes",
    "Add input validation to the forms",
    "Prepare the client demo script",
    "Document the API endpoints",
]
PROGRESS = [
    "Completed and merged",
    "Mostly done — one PR in review",
    "Started; blocked on API contract",
    "Done, demoed to the client",
    "Partially done",
    "",
]
REMARKS_GOOD = ["Good", "Clear updates, owns their tasks", "Led the client discussion"]
REMARKS_LOW = ["Has to interact more in client meets", "Needs to share progress proactively",
               "Missed follow-ups from last call"]
TERM_START = date(2026, 9, 1)  # latest seeded call lands mid-October


def _score(rng, level, max_value):
    raw = max_value * level + rng.uniform(-0.25, 0.25) * max_value
    return min(max(round(raw * 2) / 2, 0), max_value)


def _build(ta):
    rng = random.Random(2026)
    for number, project, repo, n_calls, roster in TEAMS:
        team = Team(ta_id=ta.id, team_number=number, project_name=project, repo_url=repo,
                    milestones_json=json.dumps(["M1", "M2", "M3", "M4", "M5"]))
        for name, role, _ in roster:
            email = name.split()[0].lower() + str(rng.randint(100, 999)) + "@ds.study.iitm.ac.in"
            team.members.append(Member(name=name, role=role, email=email))
        db.session.add(team)
        db.session.flush()
        kinds = [k for _, _, k in roster]

        prev_tasks = {}
        for call_no in range(1, n_calls + 1):
            milestone = "M1" if call_no <= 3 else ("M2" if call_no <= 6 else "M3")
            call = Call(team=team, call_no=call_no, milestone=milestone, week=f"W{call_no}",
                        date=TERM_START + timedelta(weeks=call_no - 1, days=number % 4))
            db.session.add(call)
            for member, kind in zip(team.members, kinds):
                p_present, p_spoke, level, p_evidence = ARCHETYPES[kind]
                if kind == "fading":  # starts fine, drifts off
                    level -= 0.06 * call_no
                    p_spoke -= 0.05 * call_no
                present = rng.random() < p_present
                spoke = present and rng.random() < p_spoke
                next_task = rng.choice(TASKS)
                entry = CallEntry(
                    member=member,
                    present=present,
                    spoke=spoke,
                    tasks_assigned_prev=prev_tasks.get(member.name, ""),
                    tasks_for_next=next_task if present else prev_tasks.get(member.name, ""),
                    progress=rng.choice(PROGRESS) if present else "",
                    evidence_link=(f"{repo}/pull/{rng.randint(3, 90)}"
                                   if present and rng.random() < p_evidence else repo),
                )
                if present:
                    entry.role_fulfillment = _score(rng, level, 3)
                    entry.client_interaction = _score(rng, level if spoke else level * 0.5, 2)
                    entry.initiative = _score(rng, level, 2)
                    entry.remarks = rng.choice(REMARKS_GOOD if level >= 0.6 else REMARKS_LOW)
                call.entries.append(entry)
                prev_tasks[member.name] = entry.tasks_for_next

        for milestone in ("M1", "M2", "M3")[: 2 + (n_calls >= 7)]:
            for member, kind in zip(team.members, kinds):
                level = ARCHETYPES[kind][2]
                db.session.add(MilestoneSubmission(
                    team_id=team.id, member_id=member.id, milestone=milestone,
                    report_section=rng.choice(["Requirements", "Design", "API spec", "Testing",
                                               "Implementation", "Deployment"]),
                    code="Y" if rng.random() < level + 0.15 else "N",
                    tests="Y" if rng.random() < level else "N",
                    demo="Y" if rng.random() < level + 0.05 else "N",
                    evidence_link=f"{repo}/tree/{milestone.lower()}",
                    remarks=rng.choice(REMARKS_GOOD if level >= 0.6 else REMARKS_LOW),
                ))


def ensure_demo_ta():
    """The demo TA, creating and seeding it on first use."""
    ta = TA.query.filter_by(email=DEMO_EMAIL).first()
    if ta:
        return ta
    ta = TA(name=DEMO_NAME, email=DEMO_EMAIL)
    ta.set_password(secrets.token_urlsafe(32))  # nobody can sign in with it
    db.session.add(ta)
    try:
        db.session.flush()
        _build(ta)
        db.session.commit()
    except IntegrityError:  # another worker seeded it at the same moment
        db.session.rollback()
        ta = TA.query.filter_by(email=DEMO_EMAIL).one()
    return ta


def is_demo(ta):
    return bool(ta) and ta.email == DEMO_EMAIL
