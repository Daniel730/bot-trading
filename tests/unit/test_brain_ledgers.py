from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_brain_ledgers_do_not_publish_historical_next_recommendations():
    offenders = []
    for relative_path in [".brain/04_AUDIT_LEDGER.md", ".brain/05_BUG_LEDGER.md"]:
        path = ROOT / relative_path
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "Next recommended task" in line:
                offenders.append(f"{relative_path}:{line_number}: {line.strip()}")

    assert offenders == [], (
        "Historical notes must not publish active-looking next-task guidance; "
        "use .brain/12_FIX_PRIORITY_QUEUE.md as the canonical pending-fix source.\n"
        + "\n".join(offenders)
    )


def test_release_checklist_does_not_keep_verified_postgres_secret_gate_open():
    checklist = (ROOT / ".brain/10_RELEASE_CHECKLIST.md").read_text(encoding="utf-8")

    assert "- [ ] Restore no-default PostgreSQL password behavior" not in checklist


def test_brain_does_not_claim_resolved_focused_monitor_failures_are_active():
    checked_files = [
        ".brain/00_START_HERE.md",
        ".brain/08_TESTING_PROTOCOL.md",
        ".brain/10_RELEASE_CHECKLIST.md",
    ]
    stale_phrases = [
        "6 failed",
        "six focused unit test failures",
        "active execution-safety branch has failing focused tests",
    ]

    offenders = []
    for relative_path in checked_files:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for phrase in stale_phrases:
            if phrase in text:
                offenders.append(f"{relative_path}: {phrase}")

    assert offenders == [], (
        "Brain docs still describe the old 2026-05-07 focused monitor failures as active.\n"
        + "\n".join(offenders)
    )


def test_brain_does_not_claim_monitor_fixture_isolation_is_unresolved():
    checked_files = [
        ".brain/04_AUDIT_LEDGER.md",
        ".brain/08_TESTING_PROTOCOL.md",
        ".brain/10_RELEASE_CHECKLIST.md",
    ]
    stale_phrases = [
        "Test did not mock fill polling correctly",
        "execution tried to update real Postgres",
        "Fix test isolation before using the whole monitor unit file",
        "- [ ] Ensure monitor tests mock fill polling and persistence boundaries correctly.",
    ]

    offenders = []
    for relative_path in checked_files:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for phrase in stale_phrases:
            if phrase in text:
                offenders.append(f"{relative_path}: {phrase}")

    assert offenders == [], (
        "Brain docs still describe resolved monitor fixture-isolation problems as active.\n"
        + "\n".join(offenders)
    )


def test_brain_does_not_claim_risk_fixture_max_allowed_fiat_is_unresolved():
    checked_files = [
        ".brain/04_AUDIT_LEDGER.md",
        ".brain/10_RELEASE_CHECKLIST.md",
    ]
    stale_phrases = [
        "older crypto tests omit `max_allowed_fiat`",
        "Full `tests/unit/test_monitor.py -q --asyncio-mode=auto` still fails outside this patch",
        "- [ ] Ensure risk-service test fixtures include `max_allowed_fiat` when monitor reads it.",
    ]

    offenders = []
    for relative_path in checked_files:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for phrase in stale_phrases:
            if phrase in text:
                offenders.append(f"{relative_path}: {phrase}")

    assert offenders == [], (
        "Brain docs still describe resolved risk fixture max_allowed_fiat problems as active.\n"
        + "\n".join(offenders)
    )


def test_release_checklist_confirms_alpaca_ambiguous_submit_coverage():
    checklist = (ROOT / ".brain/10_RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
    alpaca_tests = (ROOT / "tests/unit/test_alpaca_provider.py").read_text(encoding="utf-8")
    required_tests = [
        "test_place_value_order_timeout_reconciles_client_order_id_before_fallback",
        "test_place_value_order_timeout_returns_unknown_when_reconcile_fails",
    ]

    for test_name in required_tests:
        assert f"async def {test_name}" in alpaca_tests

    assert "- [x] Confirm Alpaca ambiguous-submit tests cover both reconciled and unreconciled outcomes." in checklist
    assert "- [ ] Confirm Alpaca ambiguous-submit tests cover both reconciled and unreconciled outcomes." not in checklist
