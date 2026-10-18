import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from models import TA, Call, CallEntry, Member, Team, db  # noqa: E402

TEST_PASSWORD = "test-password"


@pytest.fixture()
def app():
    app = create_app("sqlite://")  # in-memory
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        yield app
        db.session.remove()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_ta(name="Test TA", email="ta@test.local"):
    ta = TA.query.filter_by(email=email).first()
    if not ta:
        ta = TA(name=name, email=email)
        ta.set_password(TEST_PASSWORD)
        db.session.add(ta)
        db.session.commit()
    return ta


def sign_in(client, ta):
    return client.post("/login", data={"email": ta.email, "password": TEST_PASSWORD})


def make_team(number=96, project="Sample Project", repo="https://github.com/org/repo",
              member_names=("Asha", "Bilal"), ta=None):
    team = Team(ta_id=(ta or make_ta()).id, team_number=number,
                project_name=project, repo_url=repo)
    for i, name in enumerate(member_names):
        team.members.append(
            Member(name=name, role=f"Role {i + 1}", email=f"{name.lower()}@study.iitm.ac.in")
        )
    db.session.add(team)
    db.session.commit()
    return team


def make_call(team, call_no, milestone="M1", week="W1", entries=()):
    """entries: list of dicts keyed by member index with CallEntry fields."""
    call = Call(team=team, call_no=call_no, milestone=milestone, week=week,
                date=date(2026, 7, call_no))
    db.session.add(call)
    for i, member in enumerate(team.members):
        fields = entries[i] if i < len(entries) else {}
        call.entries.append(CallEntry(member=member, **fields))
    db.session.commit()
    return call
