"""Edge cases in the sign-in and sign-up flows."""

from unittest import mock

import app as app_module
from conftest import TEST_PASSWORD, make_ta, make_team, sign_in
from models import TA


def test_failed_login_keeps_the_email(app, client):
    make_ta(email="ta@test.local")
    body = client.post("/login", data={"email": "ta@test.local", "password": "nope"}).get_data(as_text=True)
    assert 'value="ta@test.local"' in body


def test_login_trims_and_ignores_case(app, client):
    make_ta(email="ta@test.local")
    resp = client.post("/login", data={"email": "  TA@Test.Local ", "password": TEST_PASSWORD})
    assert resp.status_code == 302


def test_login_returns_to_the_page_you_wanted(app, client):
    ta = make_ta()
    team = make_team(ta=ta)
    resp = client.get(f"/teams/{team.id}?tab=summary")
    assert resp.status_code == 302 and "next=" in resp.headers["Location"]

    resp = client.post("/login", data={"email": ta.email, "password": TEST_PASSWORD,
                                       "next": f"/teams/{team.id}?tab=summary"})
    assert resp.headers["Location"] == f"/teams/{team.id}?tab=summary"


def test_next_cannot_send_you_off_site(app, client):
    ta = make_ta()
    for bad in ("https://evil.example/x", "//evil.example/x", "/\\evil.example", "javascript:alert(1)"):
        client.post("/logout")
        resp = client.post("/login", data={"email": ta.email, "password": TEST_PASSWORD, "next": bad})
        assert resp.status_code == 302
        assert "evil" not in resp.headers["Location"] and "javascript" not in resp.headers["Location"]


def test_signed_in_users_skip_the_forms(app, client):
    sign_in(client, make_ta())
    assert client.get("/login").status_code == 302
    assert client.get("/register").status_code == 302


def test_demo_visitor_can_still_reach_the_login_page(app, client):
    client.get("/demo")
    assert client.get("/login").status_code == 200
    ta = make_ta()
    client.post("/login", data={"email": ta.email, "password": TEST_PASSWORD})
    assert client.get("/settings").status_code == 200  # a real TA now, not the demo


def test_register_rejects_bad_email_and_long_fields(app, client):
    for data, message in [
        ({"name": "X", "email": "not-an-email", "password": "secret1"}, "valid email"),
        ({"name": "X" * 121, "email": "x@test.local", "password": "secret1"}, "too long"),
        ({"name": "X", "email": "x@test.local", "password": "p" * 257}, "too long"),
        ({"name": "   ", "email": "x@test.local", "password": "secret1"}, "required"),
    ]:
        body = client.post("/register", data=data).get_data(as_text=True)
        assert message in body, data
    assert TA.query.count() == 0


def test_register_keeps_what_you_typed(app, client):
    body = client.post("/register", data={"name": "Asha", "email": "asha@test.local",
                                          "password": "abc"}).get_data(as_text=True)
    assert 'value="Asha"' in body and 'value="asha@test.local"' in body


def test_simultaneous_signup_with_same_email_is_not_a_crash(app, client):
    make_ta(email="race@test.local")
    # Pretend validation ran before the other request committed.
    with mock.patch.object(app_module, "validate_registration",
                           return_value=("Race", "race@test.local", "secret1", None)):
        resp = client.post("/register", data={})
    assert resp.status_code == 200
    assert "already exists" in resp.get_data(as_text=True)
    assert TA.query.filter_by(email="race@test.local").count() == 1


def test_throttle_is_per_address_and_email(app, client):
    app_module._login_failures.clear()
    make_ta(email="a@test.local")
    make_ta(email="b@test.local")
    for _ in range(app_module.LOGIN_MAX_FAILURES):
        client.post("/login", data={"email": "a@test.local", "password": "wrong"})
    blocked = client.post("/login", data={"email": "a@test.local", "password": TEST_PASSWORD})
    assert blocked.status_code == 429
    # Someone else on the same network isn't locked out.
    ok = client.post("/login", data={"email": "b@test.local", "password": TEST_PASSWORD})
    assert ok.status_code == 302
    app_module._login_failures.clear()


def test_expired_form_gets_a_friendly_retry_not_a_400(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    make_ta(email="ta@test.local")
    resp = client.post("/login", data={"email": "ta@test.local", "password": TEST_PASSWORD})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/login")
    assert "expired" in client.get("/login").get_data(as_text=True)

    resp = client.put("/api/calls/1", json={})
    assert resp.status_code in (400, 401)
    assert resp.is_json


def test_logout_by_get_does_not_405(app, client):
    sign_in(client, make_ta())
    resp = client.get("/logout")
    assert resp.status_code == 302
