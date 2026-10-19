"""TA accounts: login, registration, and per-TA scoping of teams."""

import services
from app import create_app
from conftest import TEST_PASSWORD, make_ta, make_team, sign_in
from models import TA, Team, db


def test_deploy_env_vars_are_honored(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("HTTPS_ONLY", "1")
    app = create_app()
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite://"
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"

    monkeypatch.delenv("DATABASE_URL")
    monkeypatch.delenv("HTTPS_ONLY")
    app = create_app("sqlite://")  # explicit arg still wins; local http stays fine
    assert app.config["SESSION_COOKIE_SECURE"] is False


def test_pages_require_sign_in(app, client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_api_returns_401_json_when_signed_out(app, client):
    resp = client.put("/api/calls/1", json={})
    assert resp.status_code == 401
    assert resp.get_json()["ok"] is False


def test_register_signs_in_and_login_works(app, client):
    resp = client.post(
        "/register",
        data={"name": "Priya", "email": "Priya@Study.iitm.ac.in", "password": "secret1"},
    )
    assert resp.status_code == 302  # signed in, sent to home
    assert TA.query.filter_by(email="priya@study.iitm.ac.in").first()  # stored lowercase

    client.post("/logout")
    assert client.get("/").status_code == 302  # signed out again

    resp = client.post(
        "/login", data={"email": "priya@study.iitm.ac.in", "password": "secret1"}
    )
    assert resp.status_code == 302
    assert client.get("/").status_code in (200, 302)  # home renders (or first team)


def test_bad_password_rejected(app, client):
    ta = make_ta()
    resp = client.post("/login", data={"email": ta.email, "password": "wrong"})
    assert resp.status_code == 200
    assert "don&#39;t match an account" in resp.get_data(as_text=True)


def test_register_rejects_duplicate_email_and_short_password(app, client):
    make_ta(email="taken@test.local")
    resp = client.post(
        "/register", data={"name": "X", "email": "taken@test.local", "password": "secret1"}
    )
    assert "already exists" in resp.get_data(as_text=True)
    resp = client.post(
        "/register", data={"name": "X", "email": "new@test.local", "password": "abc"}
    )
    assert "at least 6" in resp.get_data(as_text=True)


def test_teams_scoped_per_ta(app):
    ta_a = make_ta(name="A", email="a@test.local")
    ta_b = make_ta(name="B", email="b@test.local")
    team_a = make_team(number=1, ta=ta_a)
    team_b = make_team(number=2, ta=ta_b)
    assert services.teams_for(ta_a) == [team_a]
    assert services.teams_for(ta_b) == [team_b]


def test_other_tas_team_is_invisible(app, client):
    ta_a = make_ta(name="A", email="a@test.local")
    ta_b = make_ta(name="B", email="b@test.local")
    own = make_team(number=1, ta=ta_a)
    other = make_team(number=2, ta=ta_b)
    other_call = services.create_next_call(other)

    sign_in(client, ta_a)
    assert client.get(f"/teams/{own.id}").status_code == 200
    assert client.get(f"/teams/{other.id}").status_code == 404
    assert client.get(f"/calls/{other_call.id}").status_code == 404
    assert client.put(f"/api/calls/{other_call.id}", json={"entries": []}).status_code == 404
    assert client.get(f"/teams/{other.id}/export").status_code == 404


def test_first_account_adopts_pre_migration_teams(app, client):
    # A team with no owner — what an upgraded pre-accounts database contains.
    orphan = Team(team_number=96, project_name="Legacy", repo_url="")
    db.session.add(orphan)
    db.session.commit()

    client.post(
        "/register",
        data={"name": "First", "email": "first@test.local", "password": "secret1"},
    )
    assert orphan.ta_id == TA.query.filter_by(email="first@test.local").one().id

    # Later accounts adopt nothing.
    client.post("/logout")
    client.post(
        "/register",
        data={"name": "Second", "email": "second@test.local", "password": "secret1"},
    )
    second = TA.query.filter_by(email="second@test.local").one()
    assert services.teams_for(second) == []


def test_settings_updates_name_and_password(app, client):
    ta = make_ta()
    sign_in(client, ta)
    resp = client.post(
        "/settings",
        data={"cohort_label": "MAY2026", "ta_name": "Renamed", "new_password": "newpass1"},
    )
    assert resp.status_code == 302
    assert ta.name == "Renamed"
    assert ta.check_password("newpass1")

    client.post("/logout")
    assert client.post(
        "/login", data={"email": ta.email, "password": TEST_PASSWORD}
    ).status_code == 200  # old password no longer valid → re-rendered with error
