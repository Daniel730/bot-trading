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
