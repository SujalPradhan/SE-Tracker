"""JSON import: validation, atomicity, and the tasks_for_next derivation."""

import importer
import services
from conftest import make_ta, make_team, sign_in
from models import Call, MilestoneSubmission, Team, db


def payload():
    """A payload shaped like a converted legacy workbook (2 calls, 1 submission)."""
    return {
        "teams": [
            {
                "team_number": "096",  # numeric string, like a zero-padded Team ID
                "project_name": "Campus Eats",
                "repo_url": "https://github.com/org/repo",
                "members": [
                    {"name": "Ananya Rao", "role": "PM", "email": "a@x.in"},
                    {"name": "Bilal Khan", "role": "Backend", "email": "b@x.in"},
                ],
                "calls": [
                    {
                        "call_no": 1,
                        "week": "W1",
                        "milestone": "M1",
                        "entries": [
                            {"member": "Ananya Rao", "present": "Y", "spoke": "Y",
                             "role_fulfillment": 2.5, "client_interaction": None,
                             "initiative": 1, "remarks": "Good"},
                            {"member": "Bilal Khan", "present": "N", "spoke": "N"},
                        ],
                    },
                    {
                        "call_no": 2,
                        "week": "W2",
                        "milestone": "M1",
                        "date": "2026-06-27",
                        "entries": [
                            {"member": "Ananya Rao", "present": "Y", "spoke": "Y",
                             "tasks_assigned_prev": "Draft requirements",
                             "progress": "Doc shared",
                             "evidence_link": "https://github.com/org/repo/pull/3",
                             "role_fulfillment": 3, "client_interaction": 2,
                             "initiative": 1.5},
                            {"member": "Bilal Khan", "present": "Y", "spoke": "N",
                             "tasks_assigned_prev": "Set up CI"},
                        ],
                    },
                ],
                "milestone_submissions": [
                    {"member": "Ananya Rao", "milestone": "M1",
                     "report_section": "Intro", "code": "Y", "tests": "N", "demo": ""},
                ],
            }
        ]
    }


def test_happy_path_import(app):
    ta = make_ta()
    result = importer.import_payload(ta, payload())
    assert result["ok"], result
    assert result["summary"] == {
        "teams": 1, "members": 2, "calls": 2, "entries": 4, "submissions": 1,
        "team_numbers": ["096"],
    }

    team = Team.query.filter_by(team_number=96).one()
    assert team.ta_id == ta.id
    assert [m.name for m in team.members] == ["Ananya Rao", "Bilal Khan"]
    assert MilestoneSubmission.query.filter_by(team_id=team.id).count() == 1

    call1, call2 = services.sorted_calls(team)
    by_member = {e.member.name: e for e in call1.entries}
    assert by_member["Ananya Rao"].role_fulfillment == 2.5
    assert by_member["Ananya Rao"].client_interaction is None  # blank stays blank
    assert by_member["Bilal Khan"].present is False
    assert call2.date is not None

    # Metrics work immediately on imported data.
    summary = services.team_summary(team)
    assert summary[0][1]["avg_display"] != "—"


def test_tasks_for_next_derived_from_next_call(app):
    ta = make_ta()
    importer.import_payload(ta, payload())
    team = Team.query.filter_by(team_number=96).one()
    call1, _call2 = services.sorted_calls(team)
    by_member = {e.member.name: e for e in call1.entries}
    # Call 2's "Tasks Assigned (Prev Call)" flowed back into call 1's tasks_for_next…
    assert by_member["Ananya Rao"].tasks_for_next == "Draft requirements"
    assert by_member["Bilal Khan"].tasks_for_next == "Set up CI"
    # …so the NEXT (live) call carries tasks forward like native data.
    call3 = services.create_next_call(team)
    entry = {e.member.name: e for e in call3.entries}
    assert entry["Ananya Rao"].tasks_assigned_prev == ""  # call 2 set no tasks_for_next
    assert call3.call_no == 3


def test_milestones_auto_extend_to_referenced(app):
    ta = make_ta()
    data = payload()
    data["teams"][0]["calls"][1]["milestone"] = "M6"
    result = importer.import_payload(ta, data)
    assert result["ok"], result
    team = Team.query.filter_by(team_number=96).one()
    assert team.milestones == ["M1", "M2", "M3", "M4", "M5", "M6"]


def test_invalid_payload_imports_nothing(app):
    ta = make_ta()
    data = payload()
    data["teams"][0]["calls"][0]["entries"][0]["member"] = "Nobody"
    data["teams"][0]["calls"][1]["entries"][0]["role_fulfillment"] = "abc"
    result = importer.import_payload(ta, data)
    assert not result["ok"]
    assert any("unknown member 'Nobody'" in e for e in result["errors"])
    assert any("role_fulfillment" in e for e in result["errors"])
    # Atomic: nothing was created despite team itself being valid.
    assert Team.query.count() == 0
    assert Call.query.count() == 0


def test_existing_team_number_rejected(app):
    ta = make_ta()
    make_team(number=96, ta=ta)
    result = importer.import_payload(ta, payload())
    assert not result["ok"]
    assert any("already exists" in e for e in result["errors"])
    assert Team.query.count() == 1  # just the pre-existing one


def test_bad_shapes_rejected(app):
    ta = make_ta()
    assert not importer.import_payload(ta, {"nope": 1})["ok"]
    assert not importer.import_payload(ta, {"teams": []})["ok"]
    result = importer.import_payload(ta, {"teams": [{"team_number": "x", "members": []}]})
    assert not result["ok"]
    assert any("team_number" in e for e in result["errors"])
    assert any("at least one member" in e for e in result["errors"])


def test_import_endpoint_scopes_to_signed_in_ta(app, client):
    ta = make_ta()
    sign_in(client, ta)
    resp = client.post("/api/import", json=payload())
    assert resp.status_code == 200
    assert Team.query.filter_by(team_number=96).one().ta_id == ta.id

    resp = client.post("/api/import", json=payload())  # same numbers again
    assert resp.status_code == 400

    client.post("/logout")
    assert client.post("/api/import", json=payload()).status_code == 401


def test_delete_team_removes_everything_and_is_scoped(app, client):
    ta = make_ta()
    other = make_ta(name="Other", email="other@test.local")
    team = make_team(number=1, ta=ta)
    services.create_next_call(team)
    foreign = make_team(number=2, ta=other)

    sign_in(client, ta)
    assert client.post(f"/teams/{foreign.id}/delete").status_code == 404

    resp = client.post(f"/teams/{team.id}/delete")
    assert resp.status_code == 302
    assert db.session.get(Team, team.id) is None
    assert Call.query.count() == 0  # cascaded
    assert db.session.get(Team, foreign.id) is not None
