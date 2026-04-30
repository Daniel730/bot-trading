import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate_deploy_env.py"


def run_validator(env_file: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(env_file)],
        capture_output=True,
        text=True,
    )


def test_validate_deploy_env_accepts_non_default_secrets(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD=strong-postgres-secret",
                "DASHBOARD_TOKEN=strong-dashboard-token",
                "DATABASE_URL=",
            ]
        ),
        encoding="utf-8",
    )

    result = run_validator(env_file)

    assert result.returncode == 0
    assert "OK" in result.stdout


def test_validate_deploy_env_blocks_values_that_crash_runtime_config(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD=bot_pass",
                "DASHBOARD_TOKEN=arbi-elite-2026",
                "DATABASE_URL=postgresql://bot_admin:bot_pass@postgres:5432/trading_bot",
            ]
        ),
        encoding="utf-8",
    )

    result = run_validator(env_file)

    assert result.returncode == 1
    assert "POSTGRES_PASSWORD" in result.stdout
    assert "DASHBOARD_TOKEN" in result.stdout
    assert "DATABASE_URL" in result.stdout
    assert "bot_pass" not in result.stdout
    assert "arbi-elite-2026" not in result.stdout


def test_validate_deploy_env_blocks_invalid_json_objects(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD=strong-postgres-secret",
                "DASHBOARD_TOKEN=strong-dashboard-token",
                "CRYPTO_TOKEN_MAPPING=not-json",
            ]
        ),
        encoding="utf-8",
    )

    result = run_validator(env_file)

    assert result.returncode == 1
    assert "CRYPTO_TOKEN_MAPPING" in result.stdout
