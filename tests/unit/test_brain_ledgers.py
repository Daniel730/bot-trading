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
