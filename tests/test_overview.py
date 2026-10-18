"""Overview dashboard numbers, scoping, and the per-TA fixes."""

import overview
import services
from conftest import make_call, make_ta, make_team, sign_in
from models import MilestoneSubmission, db

FULL = {"present": True, "spoke": True, "role_fulfillment": 3, "client_interaction": 2, "initiative": 2}
ABSENT = {"present": False, "spoke": False}


def test_kpis_and_trend(app):
    team = make_team(member_names=("Asha", "Bilal"))
    make_call(team, 1, entries=[FULL, ABSENT])
    make_call(team, 2, entries=[FULL, {"present": True, "spoke": False, "role_fulfillment": 1}])

    data = overview.build_overview([team])
    k = data["kpis"]
    assert (k["teams"], k["students"], k["calls"]) == (1, 2, 2)
    assert k["attendance"] == 75          # 3 of 4 entries present
    assert k["speaking"] == 67            # 2 of 3 present spoke
    assert k["avg"] == 3.75               # mean of Asha 7.0 and Bilal 0.5
    assert [r["attendance"] for r in data["trend"]] == [50, 100]

    asha, bilal = data["students"]
    assert asha["name"] == "Asha" and asha["status"] == "active"
    assert bilal["series"] == [None, 1.0]  # absent call is a gap, not a zero
    assert bilal["status"] == "low" and bilal["reasons"]
    assert data["flagged"] == [bilal]


def test_milestones_counted_only_for_given_teams(app):
    ta_a = make_ta(name="A", email="a@test.local")
    ta_b = make_ta(name="B", email="b@test.local")
    team_a = make_team(number=1, ta=ta_a, member_names=("Asha", "Bilal"))
    team_b = make_team(number=1, ta=ta_b, member_names=("Chen",))
    db.session.add_all([
        MilestoneSubmission(team_id=team_a.id, member_id=team_a.members[0].id, milestone="M1",
                            code="Y", tests="Y", demo="N"),
        MilestoneSubmission(team_id=team_b.id, member_id=team_b.members[0].id, milestone="M1",
                            code="Y", tests="Y", demo="Y"),
    ])
    db.session.commit()

    cell = overview.build_overview([team_a])["teams"][0]["milestones"]["M1"]
    assert cell == {"code": 50, "tests": 50, "demo": 0, "done": 33}
    assert overview.build_overview([team_a])["teams"][0]["milestones"]["M2"] is None


def test_empty_overview(app):
    data = overview.build_overview([])
    assert data["kpis"]["students"] == 0 and data["kpis"]["avg"] is None
    assert data["teams"] == [] and data["trend"] == []


def test_dashboard_shows_only_own_students(app, client):
    ta_a = make_ta(name="A", email="a@test.local")
    ta_b = make_ta(name="B", email="b@test.local")
    make_team(number=1, ta=ta_a, member_names=("Asha",))
    make_team(number=2, ta=ta_b, member_names=("Zed",))
    sign_in(client, ta_a)
    body = client.get("/dashboard").get_data(as_text=True)
    assert "Asha" in body and "Zed" not in body


def test_dashboard_empty_state(app, client):
    sign_in(client, make_ta())
    assert client.get("/dashboard").status_code == 200


def test_two_tas_can_both_have_team_1(app, client):
    ta_a = make_ta(name="A", email="a@test.local")
    ta_b = make_ta(name="B", email="b@test.local")
    make_team(number=1, ta=ta_a)
    sign_in(client, ta_b)
    resp = client.post("/teams", data={"team_number": "1", "member_id": [""],
                                       "member_name": ["X"], "member_role": [""], "member_email": [""]})
    assert resp.status_code == 302
    # ...but still not twice for the same TA.
    resp = client.post("/teams", data={"team_number": "1"})
    assert resp.status_code == 400


def test_remark_chips_scoped_to_ta(app):
    ta_a = make_ta(name="A", email="a@test.local")
    ta_b = make_ta(name="B", email="b@test.local")
    team_b = make_team(number=2, ta=ta_b, member_names=("Zed",))
    make_call(team_b, 1, entries=[{"remarks": "Secret remark about Zed"}])
    assert "Secret remark about Zed" not in services.remark_chips(ta_a)
    assert "Secret remark about Zed" in services.remark_chips(ta_b)
