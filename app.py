"""SE-Tracker — client-call tracking for Software Engineering course TAs.

Run with:  pip install -r requirements.txt && python app.py

Each TA has an account (email + password); teams, calls, and exports are
scoped to the signed-in TA.
"""

import io
import os
import secrets
from datetime import date
from pathlib import Path

from flask import (
    Blueprint,
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

import export
import importer
import metrics
import services
from models import (
    SCORE_FIELDS,
    TA,
    Call,
    Member,
    Team,
    cohort_label,
    db,
    get_setting,
    set_setting,
)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TEAM_FORM_TEMPLATE = "team_form.html"
MIN_PASSWORD_LENGTH = 6

bp = Blueprint("main", __name__)


# ---------- auth ----------

AUTH_ENDPOINTS = {"main.login", "main.register"}


@bp.before_request
def load_signed_in_ta():
    """Resolve the signed-in TA; everything except login/register requires one."""
    g.ta = db.session.get(TA, session["ta_id"]) if "ta_id" in session else None
    if g.ta or request.endpoint in AUTH_ENDPOINTS:
        return None
    if request.path.startswith("/api/"):
        return jsonify(ok=False, error="Not signed in."), 401
    return redirect(url_for("main.login"))


def sign_in(ta):
    session.permanent = True
    session["ta_id"] = ta.id


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        ta = TA.query.filter_by(email=email).first()
        if ta and ta.check_password(request.form.get("password", "")):
            sign_in(ta)
            return redirect(url_for("main.home"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")


def validate_registration(form):
    """Returns (name, email, password, error) — error is None when valid."""
    name = form.get("name", "").strip()
    email = form.get("email", "").strip().lower()
    password = form.get("password", "")
    error = None
    if not name or not email:
        error = "Name and email are required."
    elif len(password) < MIN_PASSWORD_LENGTH:
        error = f"Password needs at least {MIN_PASSWORD_LENGTH} characters."
    elif TA.query.filter_by(email=email).first():
        error = "An account with that email already exists."
    return name, email, password, error


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name, email, password, error = validate_registration(request.form)
        if error:
            flash(error, "error")
        else:
            first_account = TA.query.count() == 0
            ta = TA(name=name, email=email)
            ta.set_password(password)
            db.session.add(ta)
            db.session.flush()
            if first_account:
                # Teams from a pre-accounts database belong to whoever
                # registers first (the TA upgrading their own install).
                claimed = Team.query.filter(Team.ta_id.is_(None)).update({"ta_id": ta.id})
                if claimed:
                    flash(f"Adopted {claimed} existing team(s) into your account.", "ok")
            db.session.commit()
            sign_in(ta)
            flash(f"Welcome, {ta.name}!", "ok")
            return redirect(url_for("main.home"))
    return render_template("register.html")


@bp.post("/logout")
def logout():
    session.pop("ta_id", None)
    return redirect(url_for("main.login"))


# ---------- helpers ----------


def owned_team_or_404(team_id):
    team = db.get_or_404(Team, team_id)
    if team.ta_id != g.ta.id:
        abort(404)  # another TA's team — invisible, not forbidden
    return team


def owned_call_or_404(call_id):
    call = db.get_or_404(Call, call_id)
    if call.team.ta_id != g.ta.id:
        abort(404)
    return call


def parse_members_form(form, team):
    """Apply member rows (member_id/name/role/email lists) to a team."""
    ids = form.getlist("member_id")
    names = form.getlist("member_name")
    roles = form.getlist("member_role")
    emails = form.getlist("member_email")
    for mid, name, role, email in zip(ids, names, roles, emails):
        name, role, email = name.strip(), role.strip(), email.strip()
        if mid:  # existing member — edits propagate everywhere
            member = db.session.get(Member, int(mid))
            if member and member.team_id == team.id and name:
                member.name, member.role, member.email = name, role, email
        elif name:
            team.members.append(Member(name=name, role=role, email=email))


def member_form_rows(team=None, form=None, min_rows=5):
    """Rows for the team form: existing members, re-submitted values, or blanks."""
    rows = []
    if team:
        rows = [{"id": m.id, "name": m.name, "role": m.role, "email": m.email}
                for m in team.members]
    elif form:
        rows = [
            {"id": i, "name": n, "role": r, "email": e}
            for i, n, r, e in zip(
                form.getlist("member_id"),
                form.getlist("member_name"),
                form.getlist("member_role"),
                form.getlist("member_email"),
            )
        ]
    while len(rows) < min_rows:
        rows.append({"id": "", "name": "", "role": "", "email": ""})
    return rows


def validate_team_number(form, current_team=None):
    """Returns (team_number, error_message) — exactly one is None."""
    raw = form.get("team_number", "").strip()
    if not raw.isdigit():
        return None, "Team number must be a whole number."
    number = int(raw)
    query = Team.query.filter(Team.team_number == number)
    if current_team:
        query = query.filter(Team.id != current_team.id)
    if query.first():
        return None, f"Team {number:03d} already exists."
    return number, None


# ---------- teams ----------


@bp.get("/")
def home():
    teams = services.teams_for(g.ta)
    if teams:
        return redirect(url_for("main.team_page", team_id=teams[0].id))
    return render_template("index.html")


@bp.get("/teams/new")
def new_team_form():
    return render_template(TEAM_FORM_TEMPLATE, team=None, member_rows=member_form_rows())


@bp.post("/teams")
def create_team():
    number, error = validate_team_number(request.form)
    if error:
        flash(error, "error")
        return (
            render_template(
                TEAM_FORM_TEMPLATE,
                team=None,
                form=request.form,
                member_rows=member_form_rows(form=request.form),
            ),
            400,
        )
    team = Team(
        ta_id=g.ta.id,
        team_number=number,
        project_name=request.form.get("project_name", "").strip(),
        repo_url=request.form.get("repo_url", "").strip(),
    )
    parse_members_form(request.form, team)
    db.session.add(team)
    db.session.commit()
    flash(f"Team {team.display_number} created.", "ok")
    return redirect(url_for("main.team_page", team_id=team.id))


@bp.get("/teams/<int:team_id>")
def team_page(team_id):
    team = owned_team_or_404(team_id)
    tab = request.args.get("tab", "calls")
    if tab not in ("calls", "milestones", "summary"):
        tab = "calls"
    context = {"team": team, "tab": tab}
    if tab == "milestones":
        milestone = request.args.get("m", "")
        if milestone not in team.milestones:
            milestone = team.milestones[0] if team.milestones else ""
        context["milestone"] = milestone
        context["grid_rows"] = services.milestone_grid(team, milestone) if milestone else []
        context["chips"] = services.remark_chips()
    elif tab == "summary":
        context["summary"] = services.team_summary(team)
        context["legend"] = metrics.THRESHOLD_LEGEND
    else:
        context["calls"] = list(reversed(services.sorted_calls(team)))
    return render_template("team.html", **context)


def edit_rows(team):
    # One trailing blank row so a new member can be added without JS.
    return member_form_rows(team=team, min_rows=len(team.members) + 1)


@bp.get("/teams/<int:team_id>/edit")
def edit_team_form(team_id):
    team = owned_team_or_404(team_id)
    return render_template(TEAM_FORM_TEMPLATE, team=team, member_rows=edit_rows(team))


@bp.post("/teams/<int:team_id>/edit")
def edit_team(team_id):
    team = owned_team_or_404(team_id)
    number, error = validate_team_number(request.form, current_team=team)
    if error:
        flash(error, "error")
        return render_template(TEAM_FORM_TEMPLATE, team=team, member_rows=edit_rows(team)), 400
    team.team_number = number
    team.project_name = request.form.get("project_name", "").strip()
    team.repo_url = request.form.get("repo_url", "").strip()
    parse_members_form(request.form, team)
    db.session.commit()
    flash("Team updated — roster changes apply everywhere.", "ok")
    return redirect(url_for("main.team_page", team_id=team.id))


@bp.post("/teams/<int:team_id>/delete")
def delete_team(team_id):
    team = owned_team_or_404(team_id)
    number = team.display_number
    db.session.delete(team)  # cascades members, calls, entries, submissions
    db.session.commit()
    flash(f"Team {number} and all its data deleted.", "ok")
    return redirect(url_for("main.home"))


@bp.post("/teams/<int:team_id>/milestones")
def add_milestone(team_id):
    team = owned_team_or_404(team_id)
    added = team.add_next_milestone()
    db.session.commit()
    if added:
        flash(f"{added} added to Team {team.display_number}.", "ok")
    return redirect(
        url_for("main.team_page", team_id=team.id, tab="milestones", **({"m": added} if added else {}))
    )


# ---------- calls ----------


@bp.post("/teams/<int:team_id>/calls")
def new_call(team_id):
    team = owned_team_or_404(team_id)
    if not team.members:
        flash("Add team members before logging a call.", "error")
        return redirect(url_for("main.edit_team_form", team_id=team.id))
    call = services.create_next_call(team)
    return redirect(url_for("main.call_form", call_id=call.id))


@bp.get("/calls/<int:call_id>")
def call_form(call_id):
    call = owned_call_or_404(call_id)
    entries = {e.member_id: e for e in call.entries}
    member_entries = [(m, entries[m.id]) for m in call.team.members if m.id in entries]
    return render_template(
        "call_form.html",
        call=call,
        team=call.team,
        member_entries=member_entries,
        chips=services.remark_chips(),
    )


@bp.post("/calls/<int:call_id>/delete")
def delete_call(call_id):
    call = owned_call_or_404(call_id)
    team_id = call.team_id
    call_no = call.call_no
    db.session.delete(call)
    db.session.commit()
    flash(f"Call #{call_no} deleted.", "ok")
    return redirect(url_for("main.team_page", team_id=team_id, tab="calls"))


def _apply_call_header(call, data):
    """Week / milestone / date from the save payload. Returns error or None."""
    call.week = str(data.get("week", "")).strip()
    milestone = str(data.get("milestone", call.milestone))
    if milestone in call.team.milestones:
        call.milestone = milestone
    raw_date = data.get("date")
    if raw_date:
        try:
            call.date = date.fromisoformat(raw_date)
        except ValueError:
            return f"Bad date: {raw_date}"
    return None


def _apply_entry_row(entry, row):
    """One member's fields from the save payload. Returns error or None."""
    entry.present = bool(row.get("present", True))
    entry.spoke = bool(row.get("spoke", False))
    entry.tasks_assigned_prev = str(row.get("tasks_assigned_prev", ""))
    entry.tasks_for_next = str(row.get("tasks_for_next", ""))
    entry.progress = str(row.get("progress", ""))
    entry.evidence_link = str(row.get("evidence_link", "")).strip()
    entry.remarks = str(row.get("remarks", ""))
    try:
        for name, _label, max_value in SCORE_FIELDS:
            setattr(entry, name, services.parse_score(row.get(name), max_value))
    except ValueError as exc:
        return f"Bad score value ({exc})."
    return None


@bp.put("/api/calls/<int:call_id>")
def save_call(call_id):
    call = owned_call_or_404(call_id)
    data = request.get_json(silent=True)
    if not data:
        return jsonify(ok=False, error="No data received."), 400

    error = _apply_call_header(call, data)
    if not error:
        entries = {e.member_id: e for e in call.entries}
        for row in data.get("entries", []):
            try:
                entry = entries.get(int(row.get("member_id")))
            except (TypeError, ValueError):
                error = "Bad member_id in payload."
                break
            if entry:
                error = _apply_entry_row(entry, row)
                if error:
                    break
    if error:
        db.session.rollback()
        return jsonify(ok=False, error=error), 400
    db.session.commit()
    return jsonify(ok=True)


# ---------- milestone grid ----------


@bp.put("/api/teams/<int:team_id>/milestones/<milestone>")
def save_milestones(team_id, milestone):
    team = owned_team_or_404(team_id)
    if milestone not in team.milestones:
        return jsonify(ok=False, error=f"Unknown milestone {milestone}."), 400
    data = request.get_json(silent=True)
    if not data or "rows" not in data:
        return jsonify(ok=False, error="No data received."), 400
    for row in data["rows"]:
        for field in ("code", "tests", "demo"):
            if row.get(field, "") not in ("", "Y", "N"):
                return jsonify(ok=False, error=f"{field} must be Y, N, or blank."), 400
    services.save_milestone_grid(team, milestone, data["rows"])
    return jsonify(ok=True)


# ---------- import ----------


@bp.get("/import")
def import_page():
    return render_template("import.html")


@bp.post("/api/import")
def run_import():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify(ok=False, errors=["Request body is not valid JSON."]), 400
    result = importer.import_payload(g.ta, payload)
    return jsonify(**result), 200 if result["ok"] else 400


# ---------- export ----------


@bp.get("/teams/<int:team_id>/export")
def export_team(team_id):
    team = owned_team_or_404(team_id)
    return send_file(
        io.BytesIO(export.workbook_bytes(team)),
        as_attachment=True,
        download_name=export.team_filename(team, cohort_label()),
        mimetype=XLSX_MIME,
    )


@bp.get("/export-all")
def export_all():
    teams = services.teams_for(g.ta)
    if not teams:
        flash("No teams to export yet.", "error")
        return redirect(url_for("main.home"))
    cohort = cohort_label()
    return send_file(
        export.all_teams_zip(teams, cohort),
        as_attachment=True,
        download_name=f"{cohort}-all-teams.zip",
        mimetype="application/zip",
    )


# ---------- settings ----------


@bp.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        label = request.form.get("cohort_label", "").strip()
        if label:
            set_setting("cohort_label", label)
        name = request.form.get("ta_name", "").strip()
        if name:
            g.ta.name = name
        password = request.form.get("new_password", "")
        if password:
            if len(password) < MIN_PASSWORD_LENGTH:
                flash(f"Password needs at least {MIN_PASSWORD_LENGTH} characters.", "error")
                return render_template("settings.html"), 400
            g.ta.set_password(password)
        db.session.commit()
        flash("Settings saved.", "ok")
        return redirect(url_for("main.settings"))
    return render_template("settings.html")


# ---------- app factory ----------


def _upgrade_pre_accounts_db():
    """Add team.ta_id to databases created before TA accounts existed.

    Purely additive (one ALTER TABLE). Orphaned teams are adopted by the
    first account that registers — see register().
    """
    columns = {row[1] for row in db.session.execute(db.text("PRAGMA table_info(team)"))}
    if columns and "ta_id" not in columns:
        db.session.execute(db.text("ALTER TABLE team ADD COLUMN ta_id INTEGER"))
        db.session.commit()


def _stable_secret_key():
    """A persistent secret so sign-in sessions survive server restarts."""
    key = get_setting("secret_key")
    if not key:
        key = secrets.token_hex(32)
        set_setting("secret_key", key)
        db.session.commit()
    return key


def create_app(database_uri=None):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        database_uri
        or os.environ.get("DATABASE_URL")
        or "sqlite:///" + str(Path(app.root_path) / "se_tracker.db")
    )
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Set HTTPS_ONLY=1 on hosts that serve HTTPS (see DEPLOY.md); left off
    # locally so plain-http `python app.py` sign-in keeps working.
    app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("HTTPS_ONLY"))
    db.init_app(app)
    with app.app_context():
        _upgrade_pre_accounts_db()
        db.create_all()
        app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or _stable_secret_key()

    @app.context_processor
    def inject_sidebar():
        ta = getattr(g, "ta", None)
        return {
            "sidebar_teams": (
                [services.team_sidebar_info(t) for t in services.teams_for(ta)] if ta else []
            ),
            "cohort": cohort_label(),
            "score_fields": SCORE_FIELDS,
        }

    app.register_blueprint(bp)
    return app


if __name__ == "__main__":
    # 5050 because macOS AirPlay listens on the Flask default 5000.
    create_app().run(debug=True, port=5050)
