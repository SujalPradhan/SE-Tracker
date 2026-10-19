"""/admin: Google sign-in, allowlist enforcement, read-only cross-TA view."""

from unittest import mock

import pytest

import admin
from conftest import make_call, make_ta, make_team, sign_in
from demo_seed import ensure_demo_ta

ALLOWED = "23f2004759@ds.study.iitm.ac.in"


@pytest.fixture()
def google(app):
    app.config["GOOGLE_CLIENT_ID"] = "test-client"
    app.config["GOOGLE_CLIENT_SECRET"] = "test-secret"
    admin.oauth.register("google", client_id="test-client", client_secret="test-secret",
                         server_metadata_url=admin.GOOGLE_DISCOVERY_URL, overwrite=True)
    return app


def _callback(client, userinfo):
    with mock.patch.object(admin.oauth.google, "authorize_access_token",
                           return_value={"userinfo": userinfo}):
        return client.get("/admin/callback")


def test_admin_requires_sign_in(app, client):
    resp = client.get("/admin")
    assert resp.status_code == 302 and "/admin/login" in resp.headers["Location"]
    assert client.get("/admin/teams/1").status_code == 302


def test_ta_session_is_not_admin(app, client):
    sign_in(client, make_ta(email=ALLOWED))  # even a TA whose email is on the list
    assert client.get("/admin").status_code == 302


def test_allowlisted_google_account_gets_in(google, client):
    resp = _callback(client, {"email": ALLOWED.upper(), "email_verified": True, "name": "Sujal"})
    assert resp.status_code == 302 and resp.headers["Location"].rstrip("/").endswith("/admin")
    assert client.get("/admin").status_code == 200


def test_other_google_account_is_refused(google, client):
    resp = _callback(client, {"email": "someone@gmail.com", "email_verified": True})
    assert resp.status_code == 403
    assert client.get("/admin").status_code == 302
    with client.session_transaction() as sess:
        assert "admin_email" not in sess


def test_unverified_email_is_refused(google, client):
    resp = _callback(client, {"email": ALLOWED, "email_verified": False})
    assert resp.status_code == 403


def test_allowlist_env_override_and_revocation(google, client):
    _callback(client, {"email": ALLOWED, "email_verified": True})
    assert client.get("/admin").status_code == 200
    google.config["ADMIN_EMAILS"] = "other@study.iitm.ac.in"
    assert client.get("/admin").status_code == 302  # removed from the list → out


def test_admin_sees_all_tas_but_not_demo(google, client):
    ta_a = make_ta(name="Alpha TA", email="a@test.local")
    ta_b = make_ta(name="Beta TA", email="b@test.local")
    team_a = make_team(number=1, ta=ta_a, member_names=("Asha",))
    team_b = make_team(number=1, ta=ta_b, member_names=("Zed",))
    make_call(team_b, 1, entries=[{"present": True, "spoke": True, "role_fulfillment": 3}])
    demo = ensure_demo_ta()

    _callback(client, {"email": ALLOWED, "email_verified": True})
    body = client.get("/admin").get_data(as_text=True)
    assert "Asha" in body and "Zed" in body and "Alpha TA" in body
    assert "Aarav Mehta" not in body  # demo student

    filtered = client.get(f"/admin?ta={ta_a.id}").get_data(as_text=True)
    assert "Asha" in filtered and "Zed" not in filtered

    assert client.get(f"/admin/teams/{team_a.id}").status_code == 200
    demo_team = demo and __import__("models").Team.query.filter_by(ta_id=demo.id).first()
    assert client.get(f"/admin/teams/{demo_team.id}").status_code == 404
    resp = client.get("/admin/export-all")
    assert resp.status_code == 200
    import io, zipfile
    names = zipfile.ZipFile(io.BytesIO(resp.data)).namelist()
    assert len(names) == 2 and len(set(names)) == 2  # both "Team 001"s survive
    assert client.get(f"/admin/teams/{team_b.id}/export").status_code == 200


def test_dev_bypass_only_in_debug(app, client):
    app.config["ADMIN_DEV_EMAIL"] = ALLOWED
    assert client.get("/admin/login").status_code == 200  # not debug → login page
    app.debug = True
    assert client.get("/admin/login").status_code == 302
    assert client.get("/admin").status_code == 200


def test_login_page_without_google_config(app, client):
    body = client.get("/admin/login").get_data(as_text=True)
    assert "isn't set up" in body


def test_default_allowlist_has_all_staff(app):
    emails = admin.admin_emails()
    assert len(emails) == 13
    assert {"kubra@study.iitm.ac.in", "23f2000887@ds.study.iitm.ac.in", ALLOWED} <= emails
