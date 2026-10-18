"""SQLAlchemy models for SE-Tracker.

Computed metrics (avg score, statuses, risk flags) are intentionally NOT
stored anywhere here — they are always derived in metrics.py so they can
never go stale or divide by zero.
"""

import json

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

DEFAULT_MILESTONES = ["M1", "M2", "M3", "M4", "M5"]
MAX_MILESTONES = 6
DEFAULT_COHORT = "SEP2026"

# (field name, label, max) for the three rubric items. Min is 0, step 0.5.
SCORE_FIELDS = [
    ("role_fulfillment", "Role Fulfillment", 3),
    ("client_interaction", "Client Interaction", 2),
    ("initiative", "Initiative", 2),
]


class Setting(db.Model):
    key = db.Column(db.String, primary_key=True)
    value = db.Column(db.String, nullable=False)


def get_setting(key, default=""):
    row = db.session.get(Setting, key)
    return row.value if row else default


def set_setting(key, value):
    row = db.session.get(Setting, key)
    if row:
        row.value = value
    else:
        db.session.add(Setting(key=key, value=value))


def cohort_label():
    return get_setting("cohort_label", DEFAULT_COHORT)


class TA(db.Model):
    """A TA account. Each TA sees and exports only their own teams."""

    __tablename__ = "ta"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    email = db.Column(db.String, unique=True, nullable=False)
    password_hash = db.Column(db.String, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Nullable so adding this column to a pre-TA database stays a pure
    # ALTER TABLE; rows are backfilled to a default TA on startup.
    ta_id = db.Column(db.Integer, db.ForeignKey("ta.id"), nullable=True)
    # Unique per TA, not app-wide: two TAs (and the demo) may each have Team 1.
    team_number = db.Column(db.Integer, nullable=False)
    project_name = db.Column(db.String, nullable=False, default="")
    repo_url = db.Column(db.String, nullable=False, default="")
    milestones_json = db.Column(
        db.Text, nullable=False, default=lambda: json.dumps(DEFAULT_MILESTONES)
    )

    members = db.relationship(
        "Member", backref="team", order_by="Member.id", cascade="all, delete-orphan"
    )
    calls = db.relationship(
        "Call", backref="team", order_by="Call.call_no", cascade="all, delete-orphan"
    )
    submissions = db.relationship(
        "MilestoneSubmission", backref="team", cascade="all, delete-orphan"
    )

    __table_args__ = (db.UniqueConstraint("ta_id", "team_number"),)

    @property
    def display_number(self):
        return f"{self.team_number:03d}"

    @property
    def milestones(self):
        return json.loads(self.milestones_json)

    @property
    def next_milestone(self):
        """Next milestone that can be added (e.g. 'M6'), or None at the cap."""
        count = len(self.milestones)
        return f"M{count + 1}" if count < MAX_MILESTONES else None

    def add_next_milestone(self):
        nxt = self.next_milestone
        if nxt:
            self.milestones_json = json.dumps(self.milestones + [nxt])
        return nxt


class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    name = db.Column(db.String, nullable=False)
    role = db.Column(db.String, nullable=False, default="")
    email = db.Column(db.String, nullable=False, default="")


class Call(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    call_no = db.Column(db.Integer, nullable=False)
    week = db.Column(db.String, nullable=False, default="")
    milestone = db.Column(db.String, nullable=False, default="M1")
    date = db.Column(db.Date, nullable=True)

    entries = db.relationship(
        "CallEntry",
        backref="call",
        order_by="CallEntry.member_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (db.UniqueConstraint("team_id", "call_no"),)


class CallEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    call_id = db.Column(db.Integer, db.ForeignKey("call.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    member = db.relationship("Member")

    present = db.Column(db.Boolean, nullable=False, default=True)
    spoke = db.Column(db.Boolean, nullable=False, default=False)
    tasks_assigned_prev = db.Column(db.Text, nullable=False, default="")
    tasks_for_next = db.Column(db.Text, nullable=False, default="")
    progress = db.Column(db.Text, nullable=False, default="")
    evidence_link = db.Column(db.String, nullable=False, default="")
    # Scores allow 0.5 increments and blank (NULL) — hence nullable Float.
    role_fulfillment = db.Column(db.Float, nullable=True)
    client_interaction = db.Column(db.Float, nullable=True)
    initiative = db.Column(db.Float, nullable=True)
    remarks = db.Column(db.Text, nullable=False, default="")

    __table_args__ = (db.UniqueConstraint("call_id", "member_id"),)

    @property
    def scores(self):
        return (self.role_fulfillment, self.client_interaction, self.initiative)


class MilestoneSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    member = db.relationship("Member")

    milestone = db.Column(db.String, nullable=False)
    report_section = db.Column(db.Text, nullable=False, default="")
    code = db.Column(db.String, nullable=False, default="")   # "Y" / "N" / ""
    tests = db.Column(db.String, nullable=False, default="")  # "Y" / "N" / ""
    demo = db.Column(db.String, nullable=False, default="")   # "Y" / "N" / ""
    evidence_link = db.Column(db.String, nullable=False, default="")
    remarks = db.Column(db.Text, nullable=False, default="")

    __table_args__ = (db.UniqueConstraint("team_id", "member_id", "milestone"),)
