"""The zero-re-typing rules: tasks flow between calls, evidence remembers itself."""

import services
from conftest import make_ta, make_team, sign_in
from models import db


def test_first_call_prefills_from_roster_and_repo(app):
    team = make_team()
    call = services.create_next_call(team)

    assert call.call_no == 1
    assert call.milestone == "M1"  # first milestone in the team's list
    assert call.date is not None
    assert len(call.entries) == len(team.members)
    for entry in call.entries:
        assert entry.present is True  # Present defaults to Y
        assert entry.spoke is False
        assert entry.tasks_assigned_prev == ""  # nothing to carry yet
        assert entry.evidence_link == team.repo_url  # repo fallback


def test_tasks_for_next_carries_into_next_calls_tasks_assigned_prev(app):
    team = make_team()
    call1 = services.create_next_call(team)
    call1.entries[0].tasks_for_next = "Finish the login API"
    call1.entries[1].tasks_for_next = "Write integration tests"
    db.session.commit()

    call2 = services.create_next_call(team)

    assert call2.call_no == 2
    by_member = {e.member_id: e for e in call2.entries}
    assert by_member[team.members[0].id].tasks_assigned_prev == "Finish the login API"
    assert by_member[team.members[1].id].tasks_assigned_prev == "Write integration tests"


def test_milestone_defaults_to_most_recent_calls_milestone(app):
    team = make_team()
    call1 = services.create_next_call(team)
    call1.milestone = "M2"
    db.session.commit()

    call2 = services.create_next_call(team)
    assert call2.milestone == "M2"


def test_evidence_prefills_from_last_non_empty_link(app):
    team = make_team()
    call1 = services.create_next_call(team)
    call1.entries[0].evidence_link = "https://github.com/org/repo/pull/12"
    call1.entries[1].evidence_link = ""  # member 2 never gave a specific link
    db.session.commit()

    call2 = services.create_next_call(team)
    call2.entries[0].evidence_link = ""  # cleared this call — history still counts
    db.session.commit()

    call3 = services.create_next_call(team)
    by_member = {e.member_id: e for e in call3.entries}
    # Last NON-EMPTY link wins, even if a later call left it blank.
    assert by_member[team.members[0].id].evidence_link == "https://github.com/org/repo/pull/12"
    # No personal link ever -> team repo fallback.
    assert by_member[team.members[1].id].evidence_link == team.repo_url


def test_call_numbers_keep_incrementing(app):
    team = make_team()
    for expected_no in (1, 2, 3):
        assert services.create_next_call(team).call_no == expected_no


def test_milestone_grid_prefills_roster_and_evidence(app):
    team = make_team()
    call = services.create_next_call(team)
    call.entries[0].evidence_link = "https://github.com/org/repo/pull/7"
    db.session.commit()

    rows = services.milestone_grid(team, "M1")
    assert [r["member"].id for r in rows] == [m.id for m in team.members]
    assert rows[0]["evidence_link"] == "https://github.com/org/repo/pull/7"
    assert rows[1]["evidence_link"] == team.repo_url
    assert rows[0]["report_section"] == ""  # fresh input, not carried


def test_saving_milestone_grid_then_reloading(app):
    team = make_team()
    services.save_milestone_grid(
        team,
        "M1",
        [
            {
                "member_id": team.members[0].id,
                "report_section": "Requirements",
                "code": "Y",
                "tests": "N",
                "demo": "",
                "evidence_link": "https://example.com/pr/1",
                "remarks": "Good",
            }
        ],
    )
    rows = services.milestone_grid(team, "M1")
    assert rows[0]["report_section"] == "Requirements"
    assert rows[0]["code"] == "Y"
    assert rows[0]["tests"] == "N"
    assert rows[0]["demo"] == ""


def test_add_next_milestone_caps_at_m6(app):
    team = make_team()
    assert team.milestones == ["M1", "M2", "M3", "M4", "M5"]
    assert team.add_next_milestone() == "M6"
    db.session.commit()
    assert team.milestones[-1] == "M6"
    assert team.add_next_milestone() is None  # capped


def test_save_call_endpoint_roundtrip(app, client):
    ta = make_ta()
    team = make_team(ta=ta)
    sign_in(client, ta)
    call = services.create_next_call(team)
    payload = {
        "week": "W3",
        "milestone": "M2",
        "date": "2026-07-10",
        "entries": [
            {
                "member_id": team.members[0].id,
                "present": True,
                "spoke": True,
                "tasks_assigned_prev": "Prev tasks",
                "tasks_for_next": "Next tasks",
                "progress": "Shipped the API",
                "evidence_link": "https://example.com/pr/2",
                "role_fulfillment": "1.5",  # 0.5 steps accepted
                "client_interaction": "",   # blank stays blank
                "initiative": 2,
                "remarks": "Good",
            }
        ],
    }
    resp = client.put(f"/api/calls/{call.id}", json=payload)
    assert resp.status_code == 200

    db.session.refresh(call)
    entry = next(e for e in call.entries if e.member_id == team.members[0].id)
    assert call.week == "W3"
    assert call.milestone == "M2"
    assert entry.role_fulfillment == 1.5
    assert entry.client_interaction is None
    assert entry.initiative == 2
    assert entry.tasks_for_next == "Next tasks"
