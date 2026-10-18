"""Read-only admin overview across every TA, behind Google Sign-In.

Only emails on the allowlist get in (ADMIN_EMAILS env var, comma-separated,
overrides the default list below). The allowlist is re-checked on every
request, so removing an email revokes access immediately. Admin sessions live
under their own session key and never act as a TA.
"""

import io
import os
import re

from authlib.integrations.flask_client import OAuth
from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

import export
import metrics
import overview
import services
from demo_seed import DEMO_EMAIL
from models import TA, Team, cohort_label, db

DEFAULT_ADMIN_EMAILS = (
    "arup@study.iitm.ac.in",
    "23f3002094@ds.study.iitm.ac.in",
    "22f2000931@ds.study.iitm.ac.in",
    "22f3002094@ds.study.iitm.ac.in",
    "nidhishkumar@study.iitm.ac.in",
    "23f1001171@ds.study.iitm.ac.in",
    "pravins@study.iitm.ac.in",
    "23f2003488@ds.study.iitm.ac.in",
    "22f3002293@ds.study.iitm.ac.in",
    "23f2005347@ds.study.iitm.ac.in",
    "23f2004759@ds.study.iitm.ac.in",
)
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
PUBLIC_ENDPOINTS = {"admin.login", "admin.login_google", "admin.callback", "admin.logout"}

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
oauth = OAuth()


def admin_emails():
    raw = current_app.config.get("ADMIN_EMAILS") or ""
    emails = [e for e in raw.split(",") if e.strip()] or DEFAULT_ADMIN_EMAILS
    return {e.strip().lower() for e in emails}


def is_admin_email(email):
    return bool(email) and email.strip().lower() in admin_emails()


def google_configured():
    return bool(current_app.config.get("GOOGLE_CLIENT_ID"))


@admin_bp.before_request
def require_admin():
    email = session.get("admin_email")
    g.admin_email = email if is_admin_email(email) else None
    if g.admin_email is None:
        session.pop("admin_email", None)
        session.pop("admin_name", None)
    if g.admin_email or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    return redirect(url_for("admin.login"))


@admin_bp.get("/login")
def login():
    if g.admin_email:
        return redirect(url_for("admin.dashboard"))
    dev_email = current_app.config.get("ADMIN_DEV_EMAIL")
    if current_app.debug and dev_email and is_admin_email(dev_email):
        # Local development only: no Google round-trip.
        session["admin_email"] = dev_email.lower()
        session["admin_name"] = "Dev admin"
        return redirect(url_for("admin.dashboard"))
    return render_template("admin_login.html", configured=google_configured())


@admin_bp.get("/login/google")
def login_google():
    if not google_configured():
        return redirect(url_for("admin.login"))
    return oauth.google.authorize_redirect(
        url_for("admin.callback", _external=True), prompt="select_account"
    )


@admin_bp.get("/callback")
def callback():
    if not google_configured():
        abort(404)
    try:
        token = oauth.google.authorize_access_token()
    except Exception:  # noqa: BLE001 — any OAuth failure is just "try again"
        return render_template("admin_login.html", configured=True,
                               error="Google sign-in didn't complete. Try again."), 400
    info = token.get("userinfo") or {}
    email = (info.get("email") or "").lower()
    if not info.get("email_verified") or not is_admin_email(email):
        return render_template("admin_denied.html", email=email), 403
    session.permanent = True
    session["admin_email"] = email
    session["admin_name"] = info.get("name") or email
    return redirect(url_for("admin.dashboard"))


@admin_bp.post("/logout")
def logout():
    session.pop("admin_email", None)
    session.pop("admin_name", None)
    return redirect(url_for("admin.login"))


def _real_tas():
    return TA.query.filter(TA.email != DEMO_EMAIL).order_by(TA.name).all()


def _real_teams(tas):
    ids = [ta.id for ta in tas]
    if not ids:
        return []
    return Team.query.filter(Team.ta_id.in_(ids)).order_by(Team.team_number).all()


@admin_bp.get("")
@admin_bp.get("/")
def dashboard():
    all_tas = _real_tas()
    ta_filter = next((ta for ta in all_tas if str(ta.id) == request.args.get("ta")), None)
    tas = [ta_filter] if ta_filter else all_tas
    teams = _real_teams(tas)
    data = _with_urls(overview.build_overview(teams, {ta.id: ta.name for ta in tas}))
    data["admin"] = overview.build_admin_extras(teams, tas, data)
    return render_template("admin.html", data=data, scope="admin",
                           all_tas=all_tas, ta_filter=ta_filter)


def _with_urls(data):
    for row in data["teams"]:
        row["url"] = url_for("admin.team", team_id=row["id"])
    return data


@admin_bp.get("/teams/<int:team_id>")
def team(team_id):
    team = db.get_or_404(Team, team_id)
    owner = db.session.get(TA, team.ta_id) if team.ta_id else None
    if owner is None or owner.email == DEMO_EMAIL:
        abort(404)
    data = _with_urls(overview.build_overview([team], {owner.id: owner.name}))
    return render_template(
        "admin_team.html",
        scope="team",
        team=team,
        owner=owner,
        data=data,
        summary=services.team_summary(team),
        legend=metrics.THRESHOLD_LEGEND,
    )


@admin_bp.get("/export-all")
def export_all():
    tas = _real_tas()
    teams = _real_teams(tas)
    if not teams:
        return redirect(url_for("admin.dashboard"))
    cohort = cohort_label()
    folders = {ta.id: re.sub(r"[^A-Za-z0-9._-]+", "_", f"{ta.name}-{ta.id}") for ta in tas}
    return send_file(
        export.all_teams_zip(teams, cohort, folder_for=lambda t: folders[t.ta_id]),
        as_attachment=True,
        download_name=f"{cohort}-all-tas.zip",
        mimetype="application/zip",
    )


@admin_bp.get("/teams/<int:team_id>/export")
def export_team(team_id):
    team = db.get_or_404(Team, team_id)
    owner = db.session.get(TA, team.ta_id) if team.ta_id else None
    if owner is None or owner.email == DEMO_EMAIL:
        abort(404)
    return send_file(
        io.BytesIO(export.workbook_bytes(team)),
        as_attachment=True,
        download_name=export.team_filename(team, cohort_label()),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def init_admin(app):
    app.config.setdefault("ADMIN_EMAILS", os.environ.get("ADMIN_EMAILS", ""))
    app.config.setdefault("ADMIN_DEV_EMAIL", os.environ.get("ADMIN_DEV_EMAIL", ""))
    app.config.setdefault("GOOGLE_CLIENT_ID", os.environ.get("GOOGLE_CLIENT_ID", ""))
    app.config.setdefault("GOOGLE_CLIENT_SECRET", os.environ.get("GOOGLE_CLIENT_SECRET", ""))
    oauth.init_app(app)
    if app.config["GOOGLE_CLIENT_ID"]:
        oauth.register(
            "google",
            server_metadata_url=GOOGLE_DISCOVERY_URL,
            client_kwargs={"scope": "openid email profile"},
            overwrite=True,
        )
    app.register_blueprint(admin_bp)
