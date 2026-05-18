import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "repair_paper_env.py"


def test_repair_paper_env_updates_only_non_secret_startup_keys(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD=keep-this-secret",
                "DASHBOARD_TOKEN=keep-this-token",
                "PAPER_TRADING=false",
                "LIVE_CAPITAL_DANGER=true",
                "REDIS_HOST=redis",
                "REDIS_PORT=6379",
                "POSTGRES_HOST=postgres",
                "POSTGRES_PORT=5432",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(env_file)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "keep-this-secret" not in result.stdout
    assert "keep-this-token" not in result.stdout

    repaired = env_file.read_text(encoding="utf-8")
    assert "POSTGRES_PASSWORD=keep-this-secret" in repaired
    assert "DASHBOARD_TOKEN=keep-this-token" in repaired
    assert "PAPER_TRADING=true" in repaired
    assert "LIVE_CAPITAL_DANGER=false" in repaired
    assert "REDIS_HOST=localhost" in repaired
    assert "REDIS_PORT=6379" in repaired
    assert "POSTGRES_HOST=localhost" in repaired
    assert "POSTGRES_PORT=5433" in repaired
