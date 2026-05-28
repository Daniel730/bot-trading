import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_local_setup_uses_locked_requirements():
    readme = _read("README.md")
    operations = _read("docs/OPERATIONS.md")
    deploy = _read(".github/workflows/deploy.yml")
    dockerfile = _read("infra/Dockerfile")

    assert re.search(r"python-version:\s*[\"']3\.11[\"']", deploy)
    assert "requirements.lock" in deploy
    assert "FROM python:3.11-slim" in dockerfile
    assert "requirements.lock" in dockerfile

    for doc_name, doc_text in {
        "README.md": readme,
        "docs/OPERATIONS.md": operations,
    }.items():
        assert "uv pip install -r requirements.lock" in doc_text, (
            f"{doc_name} must use the same locked dependency install as CI/Docker."
        )
        assert "pip install -r requirements.txt" not in doc_text

    assert "Python 3.11" in readme
    assert "Python 3.10+" not in readme


def test_docs_use_ordered_paper_startup_check():
    command = "python scripts/paper_startup_check.py .env"
    for doc_name in ("README.md", "docs/OPERATIONS.md"):
        doc_text = _read(doc_name)
        assert command in doc_text, (
            f"{doc_name} must document the ordered paper startup check."
        )


def test_docs_include_paper_startup_container_cleanup():
    cleanup_command = (
        "docker stop infra-bot-1 infra-execution-engine-1 infra-mcp-server-1 "
        "infra-sec-worker-1 infra-frontend-1"
    )
    for doc_name in ("README.md", "docs/OPERATIONS.md"):
        doc_text = _read(doc_name)
        assert cleanup_command in doc_text, (
            f"{doc_name} must document the paper startup app-container cleanup."
        )


def test_docs_describe_monitor_execution_route_without_java_default():
    routing_statement = (
        "`src/monitor.py` order routing: `PAPER_TRADING=true` calls "
        "`shadow_service`; broker-connected mode submits both legs through "
        "Python `BrokerageService`. The Java execution engine is a dry-run/audit "
        "sidecar and is not the monitor's default order path."
    )
    for doc_name in ("README.md", "docs/ARCHITECTURE.md", "src/README.md"):
        doc_text = _read(doc_name)
        assert routing_statement in doc_text, (
            f"{doc_name} must document the active monitor execution route."
        )

    readme = _read("README.md")
    architecture = _read("docs/ARCHITECTURE.md")
    assert "Python monitor loop ---- gRPC ---- Java execution engine" not in readme
    assert "Monitor --> Java" not in architecture


def test_local_runtime_docs_match_current_tooling_limits():
    required_notes = [
        "Validated backend commands use the repo WSL/Python 3.11 virtualenv",
        "Windows `python`/`py` may resolve to Python 3.14",
        "If `npm` is not installed, frontend gates are not runnable locally",
        "No Gradle wrapper is committed; use an installed `gradle` command",
    ]

    for doc_name in ("README.md", "docs/OPERATIONS.md"):
        doc_text = _read(doc_name)
        for note in required_notes:
            assert note in doc_text, f"{doc_name} must document: {note}"
