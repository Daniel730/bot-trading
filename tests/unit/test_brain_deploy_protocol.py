from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_brain_local_compose_protocol_exports_postgres_password():
    protocol = (REPO_ROOT / ".brain" / "08_TESTING_PROTOCOL.md").read_text(
        encoding="utf-8"
    )

    assert "python scripts/validate_deploy_env.py .env" in protocol
    assert 'POSTGRES_PASSWORD="$(grep' in protocol
    assert "docker compose -f infra/docker-compose.yml" in protocol
    assert "-f infra/docker-compose.local.yml up -d --build --remove-orphans" in protocol
    assert "PowerShell" in protocol
