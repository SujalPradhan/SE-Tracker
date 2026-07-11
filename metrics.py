"""Pure metric computations — no database, no Flask.

Everything here takes plain data so it is trivially unit-testable and the
derived values can never be stored stale. A "record" is one logged team call
seen from one member's perspective:

    {
        "present": bool,
        "spoke": bool,
        "evidence_link": str,
        "scores": (role_fulfillment, client_interaction, initiative),  # float | None each
    }

Records must be ordered oldest call → newest call.
"""

STATUS_ACTIVE = "🟢 Active"
STATUS_AT_RISK = "🟡 At Risk"
STATUS_LOW = "🔴 Low Contribution"
STATUS_NO_CALLS = "— No calls yet"

RISK_NONE = "🟢 No Risk"
RISK_LOW = "🔴 Risk: Low Contribution"

REASON_SILENT_MAJORITY = "Silent in majority of calls"
REASON_PRESENT_INACTIVE = "Frequently present but inactive"
REASON_MISSING_MAJORITY = "Missing from majority of calls"
REASON_LOW_SCORES = "Consistently low scores"

# Shown in the Summary tab legend so the TA can defend a flag to a student.
THRESHOLD_LEGEND = [
    (STATUS_ACTIVE, "average score ≥ 4"),
    (STATUS_AT_RISK, "average score between 2.5 and 4"),
    (STATUS_LOW, "average score < 2.5"),
    (REASON_SILENT_MAJORITY, "silent in ≥ 50% of attended calls (min 2 calls logged)"),
    (REASON_PRESENT_INACTIVE, "present but silent in the 2+ most recent consecutive calls"),
    (REASON_MISSING_MAJORITY, "attended < 50% of logged calls (min 2 calls logged)"),
    (REASON_LOW_SCORES, "average score < 2.5 (min 2 calls logged)"),
]


def call_total(scores):
    """Total for one call: sum of the non-null rubric components."""
    return sum(s for s in scores if s is not None)


def contribution_status(avg):
    if avg is None:
        return STATUS_NO_CALLS
    if avg >= 4:
        return STATUS_ACTIVE
    if avg >= 2.5:
        return STATUS_AT_RISK
    return STATUS_LOW


def format_avg(avg):
    """Display form of the average — '—' when there are no calls, never an error."""
    return "—" if avg is None else f"{round(avg, 2):g}"


def _tallies(records):
    """(logged, attended, silent, avg) for one member's records.

    An unscored call has a total of 0, so it drags the average down —
    that is the spec, not an accident. Zero records → avg is None.
    """
    logged = len(records)
    attended = sum(1 for r in records if r["present"])
    silent = sum(1 for r in records if r["present"] and not r["spoke"])
    avg = sum(call_total(r["scores"]) for r in records) / logged if logged else None
    return logged, attended, silent, avg


def risk_reasons(records):
    """Evidence reasons for the risk flag, in a fixed order. Empty list = no risk."""
    logged, attended, silent, avg = _tallies(records)

    reasons = []
    if logged >= 2 and attended > 0 and silent * 2 >= attended:
        reasons.append(REASON_SILENT_MAJORITY)
    if logged >= 2 and all(r["present"] and not r["spoke"] for r in records[-2:]):
        reasons.append(REASON_PRESENT_INACTIVE)
    if logged >= 2 and attended * 2 < logged:
        reasons.append(REASON_MISSING_MAJORITY)
    if logged >= 2 and avg is not None and avg < 2.5:
        reasons.append(REASON_LOW_SCORES)
    return reasons


def member_metrics(records):
    """All derived per-member numbers and flags, from that member's records."""
    logged, attended, silent, avg = _tallies(records)
    with_evidence = sum(1 for r in records if (r["evidence_link"] or "").strip())
    reasons = risk_reasons(records)

    return {
        "calls_logged": logged,
        "calls_attended": attended,
        "silent_calls": silent,
        "calls_with_evidence": with_evidence,
        "avg_score": avg,
        "avg_display": format_avg(avg),
        "contribution_status": contribution_status(avg),
        "risk_signal": RISK_LOW if reasons else RISK_NONE,
        "risk_evidence": "; ".join(reasons),
    }
