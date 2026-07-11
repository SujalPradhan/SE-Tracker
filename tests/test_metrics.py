"""Pure metric computations — no app or database needed."""

import metrics  # importable because conftest.py puts the project root on sys.path


def rec(present=True, spoke=True, evidence="", scores=(None, None, None)):
    return {"present": present, "spoke": spoke, "evidence_link": evidence, "scores": scores}


# ---------- call totals ----------


def test_call_total_sums_non_null_components():
    assert metrics.call_total((3, 2, 2)) == 7
    assert metrics.call_total((1.5, None, 2)) == 3.5  # 0.5 steps are real values
    assert metrics.call_total((None, None, None)) == 0


# ---------- counts and average ----------


def test_basic_counts():
    records = [
        rec(present=True, spoke=True, evidence="https://x"),
        rec(present=True, spoke=False),
        rec(present=False, spoke=False),
    ]
    m = metrics.member_metrics(records)
    assert m["calls_logged"] == 3
    assert m["calls_attended"] == 2
    assert m["silent_calls"] == 1  # present but silent; absent calls don't count
    assert m["calls_with_evidence"] == 1


def test_avg_counts_unscored_call_as_zero():
    records = [rec(scores=(2, 1, 1)), rec(scores=(None, None, None))]
    m = metrics.member_metrics(records)
    assert m["avg_score"] == 2.0  # (4 + 0) / 2


def test_zero_calls_shows_dash_never_an_error():
    m = metrics.member_metrics([])
    assert m["avg_score"] is None
    assert m["avg_display"] == "—"
    assert m["contribution_status"] == metrics.STATUS_NO_CALLS
    assert m["risk_signal"] == metrics.RISK_NONE


# ---------- contribution status bands ----------


def test_status_bands_at_boundaries():
    assert metrics.contribution_status(4.0) == metrics.STATUS_ACTIVE
    assert metrics.contribution_status(4.5) == metrics.STATUS_ACTIVE
    assert metrics.contribution_status(3.99) == metrics.STATUS_AT_RISK
    assert metrics.contribution_status(2.5) == metrics.STATUS_AT_RISK
    assert metrics.contribution_status(2.49) == metrics.STATUS_LOW
    assert metrics.contribution_status(0) == metrics.STATUS_LOW
    assert metrics.contribution_status(None) == metrics.STATUS_NO_CALLS


# ---------- risk rules ----------

GOOD = (3, 2, 2)  # total 7, keeps the average above every threshold


def test_no_risk_when_healthy():
    records = [rec(scores=GOOD), rec(scores=GOOD)]
    m = metrics.member_metrics(records)
    assert m["risk_signal"] == metrics.RISK_NONE
    assert m["risk_evidence"] == ""


def test_single_call_never_flags():
    # Every rule needs at least 2 logged calls.
    m = metrics.member_metrics([rec(present=False, spoke=False)])
    assert m["risk_signal"] == metrics.RISK_NONE


def test_silent_majority_rule():
    # Silent in exactly 50% of attended calls fires the rule (>= 50%).
    records = [rec(spoke=False, scores=GOOD), rec(spoke=True, scores=GOOD),
               rec(spoke=False, scores=GOOD), rec(spoke=True, scores=GOOD)]
    reasons = metrics.risk_reasons(records)
    assert metrics.REASON_SILENT_MAJORITY in reasons

    records = [rec(spoke=True, scores=GOOD), rec(spoke=True, scores=GOOD),
               rec(spoke=False, scores=GOOD), rec(spoke=True, scores=GOOD)]
    assert metrics.REASON_SILENT_MAJORITY not in metrics.risk_reasons(records)


def test_recent_consecutive_silence_rule():
    records = [rec(spoke=True, scores=GOOD),
               rec(spoke=False, scores=GOOD), rec(spoke=False, scores=GOOD)]
    assert metrics.REASON_PRESENT_INACTIVE in metrics.risk_reasons(records)

    # Silence must be in the MOST RECENT consecutive calls.
    records = [rec(spoke=False, scores=GOOD), rec(spoke=False, scores=GOOD),
               rec(spoke=True, scores=GOOD)]
    assert metrics.REASON_PRESENT_INACTIVE not in metrics.risk_reasons(records)

    # Absent in the latest call breaks the "present but silent" streak.
    records = [rec(spoke=False, scores=GOOD), rec(present=False, spoke=False, scores=GOOD)]
    assert metrics.REASON_PRESENT_INACTIVE not in metrics.risk_reasons(records)


def test_missing_majority_rule():
    records = [rec(present=False), rec(present=False), rec(scores=GOOD)]
    assert metrics.REASON_MISSING_MAJORITY in metrics.risk_reasons(records)

    # Attending exactly 50% is not "less than 50%".
    records = [rec(present=False), rec(scores=GOOD)]
    assert metrics.REASON_MISSING_MAJORITY not in metrics.risk_reasons(records)


def test_low_scores_rule():
    records = [rec(scores=(1, 1, None)), rec(scores=(1, 1, None))]  # avg 2.0
    assert metrics.REASON_LOW_SCORES in metrics.risk_reasons(records)

    records = [rec(scores=(1.5, 1, 0.5)), rec(scores=(1.5, 0.5, 0.5))]  # avg 2.75
    assert metrics.REASON_LOW_SCORES not in metrics.risk_reasons(records)


def test_evidence_string_joins_reasons_in_order():
    # Present-but-silent throughout with low scores: rules 1, 2, and 4 fire.
    records = [rec(spoke=False, scores=(1, None, None)),
               rec(spoke=False, scores=(1, None, None))]
    m = metrics.member_metrics(records)
    assert m["risk_signal"] == metrics.RISK_LOW
    assert m["risk_evidence"] == (
        f"{metrics.REASON_SILENT_MAJORITY}; "
        f"{metrics.REASON_PRESENT_INACTIVE}; "
        f"{metrics.REASON_LOW_SCORES}"
    )
