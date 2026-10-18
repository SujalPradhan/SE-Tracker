"""The /demo account: seeded once, browsable, and read-only server-side."""

from conftest import make_ta, sign_in
from demo_seed import DEMO_EMAIL, ensure_demo_ta
from models import TA, Call, Team


def test_demo_seeds_once_and_signs_in(app, client):
    resp = client.get("/demo")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/dashboard")
    demo = TA.query.filter_by(email=DEMO_EMAIL).one()
    teams = Team.query.filter_by(ta_id=demo.id).count()
    calls = Call.query.count()
    assert teams == 4 and calls > 20

    client.get("/demo")
    ensure_demo_ta()
    assert TA.query.filter_by(email=DEMO_EMAIL).count() == 1
    assert Call.query.count() == calls  # idempotent


def test_demo_pages_render(app, client):
    client.get("/demo")
    demo = TA.query.filter_by(email=DEMO_EMAIL).one()
    team = Team.query.filter_by(ta_id=demo.id).first()
    body = client.get("/dashboard").get_data(as_text=True)
    assert "Sample data" in body and "Team ranking" in body
    for tab in ("calls", "milestones", "summary"):
        assert client.get(f"/teams/{team.id}?tab={tab}").status_code == 200
    page = client.get(f"/calls/{team.calls[0].id}").get_data(as_text=True)
    assert 'data-readonly="1"' in page and 'id="save-call"' not in page
    assert client.get(f"/teams/{team.id}/export").status_code == 200
    for path in ("/settings", "/import", "/teams/new", f"/teams/{team.id}/edit"):
        assert client.get(path).status_code == 302


def test_demo_writes_are_refused(app, client):
    client.get("/demo")
    demo = TA.query.filter_by(email=DEMO_EMAIL).one()
    team = Team.query.filter_by(ta_id=demo.id).first()
    call = team.calls[0]
    before = Call.query.count()

    assert client.post(f"/teams/{team.id}/calls").status_code == 302
    assert client.post(f"/teams/{team.id}/delete").status_code == 302
    assert client.post("/teams", data={"team_number": "99"}).status_code == 302
    assert client.post("/settings", data={"cohort_label": "HACKED"}).status_code == 302
    resp = client.put(f"/api/calls/{call.id}", json={"entries": []})
    assert resp.status_code == 403 and resp.get_json()["ok"] is False
    assert client.put(f"/api/teams/{team.id}/milestones/M1", json={"rows": []}).status_code == 403
    assert client.post("/api/import", json={"teams": []}).status_code == 403

    assert Call.query.count() == before
    assert Team.query.filter_by(ta_id=demo.id).count() == 4
    # Exiting the demo is allowed.
    assert client.post("/logout").status_code == 302
    assert client.get("/dashboard").status_code == 302


def test_demo_account_cannot_be_claimed(app, client):
    ensure_demo_ta()
    resp = client.post("/register", data={"name": "X", "email": DEMO_EMAIL, "password": "secret1"})
    assert b"already exists" in resp.data


def test_demo_does_not_steal_first_account_adoption(app, client):
    ensure_demo_ta()
    orphan = Team(team_number=96, project_name="Legacy", repo_url="")
    from models import db
    db.session.add(orphan)
    db.session.commit()
    client.post("/register", data={"name": "First", "email": "first@test.local", "password": "secret1"})
    assert orphan.ta_id == TA.query.filter_by(email="first@test.local").one().id


def test_real_ta_is_not_read_only(app, client):
    ta = make_ta()
    sign_in(client, ta)
    assert client.post("/teams", data={"team_number": "5"}).status_code == 302
