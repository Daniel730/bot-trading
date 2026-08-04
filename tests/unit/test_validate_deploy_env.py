import subprocess
import sys
from pathlib import Path

from scripts import validate_deploy_env as vde


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate_deploy_env.py"
VALID_BASE = [
    "POSTGRES_PASSWORD=strong-postgres-secret",
    "DASHBOARD_TOKEN=strong-dashboard-token",
    "REDIS_PASSWORD=strong-redis-password-32",
]


def run_validator(env_file: Path, *extra_args: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(env_file), *extra_args],
        capture_output=True,
        text=True,
    )


def _write_env(tmp_path: Path, lines: list[str]) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(lines), encoding="utf-8")
    return env_file


def test_validate_deploy_env_accepts_non_default_secrets(tmp_path):
    env_file = _write_env(tmp_path, VALID_BASE + ["DATABASE_URL="])

    result = run_validator(env_file)

    assert result.returncode == 0
    assert "OK" in result.stdout


def test_validate_deploy_env_requires_redis_password(tmp_path):
    env_file = _write_env(
        tmp_path,
        [
            "POSTGRES_PASSWORD=strong-postgres-secret",
            "DASHBOARD_TOKEN=strong-dashboard-token",
            "REDIS_PASSWORD=",
        ],
    )

    result = run_validator(env_file, "--skip-compose")

    assert result.returncode == 1
    assert "REDIS_PASSWORD" in result.stdout


def test_validate_deploy_env_blocks_values_that_crash_runtime_config(tmp_path):
    env_file = _write_env(
        tmp_path,
        [
            "POSTGRES_PASSWORD=bot_pass",
            "DASHBOARD_TOKEN=arbi-elite-2026",
            "DATABASE_URL=postgresql://bot_admin:bot_pass@postgres:5432/trading_bot",
        ],
    )

    result = run_validator(env_file, "--skip-compose")

    assert result.returncode == 1
    assert "POSTGRES_PASSWORD" in result.stdout
    assert "DASHBOARD_TOKEN" in result.stdout
    assert "DATABASE_URL" in result.stdout
    assert "bot_pass" not in result.stdout
    assert "arbi-elite-2026" not in result.stdout


def test_validate_deploy_env_blocks_invalid_json_objects(tmp_path):
    env_file = _write_env(tmp_path, VALID_BASE + ["CRYPTO_TOKEN_MAPPING=not-json"])

    result = run_validator(env_file, "--skip-compose")

    assert result.returncode == 1
    assert "CRYPTO_TOKEN_MAPPING" in result.stdout


def test_validate_deploy_env_blocks_paper_trading_false(tmp_path):
    env_file = _write_env(tmp_path, VALID_BASE + ["PAPER_TRADING=false"])

    result = run_validator(env_file, "--skip-compose")

    assert result.returncode == 1
    assert "PAPER_TRADING must be true" in result.stdout


def test_validate_deploy_env_allows_paper_trading_false_on_alpaca_paper_api(tmp_path):
    env_file = _write_env(
        tmp_path,
        VALID_BASE
        + [
            "PAPER_TRADING=false",
            "ALPACA_BASE_URL=https://paper-api.alpaca.markets",
        ],
    )

    result = run_validator(env_file, "--skip-compose")

    assert result.returncode == 0
    assert "Deploy environment OK" in result.stdout


def test_validate_deploy_env_blocks_template_alpaca_credentials(tmp_path):
    env_file = _write_env(
        tmp_path,
        VALID_BASE
        + [
            "ALPACA_API_KEY=your_alpaca_key",
            "ALPACA_API_SECRET=your_alpaca_secret",
        ],
    )

    result = run_validator(env_file, "--skip-compose")

    assert result.returncode == 1
    assert "ALPACA_API_KEY" in result.stdout
    assert "ALPACA_API_SECRET" in result.stdout
    assert "your_alpaca_key" not in result.stdout
    assert "your_alpaca_secret" not in result.stdout


def test_validate_deploy_env_blocks_low_monitor_entry_zscore(tmp_path):
    env_file = _write_env(tmp_path, VALID_BASE + ["MONITOR_ENTRY_ZSCORE=0.5"])

    result = run_validator(env_file, "--skip-compose")

    assert result.returncode == 1
    assert "MONITOR_ENTRY_ZSCORE" in result.stdout
    assert "must be >=" in result.stdout


def test_validate_deploy_env_allows_healthy_monitor_entry_zscore(tmp_path):
    env_file = _write_env(tmp_path, VALID_BASE + ["MONITOR_ENTRY_ZSCORE=2.0"])

    result = run_validator(env_file, "--skip-compose")

    assert result.returncode == 0


def test_validate_deploy_env_blocks_low_orchestrator_timeout(tmp_path):
    env_file = _write_env(tmp_path, VALID_BASE + ["ORCHESTRATOR_TIMEOUT_SECONDS=10"])

    result = run_validator(env_file, "--skip-compose")

    assert result.returncode == 1
    assert "ORCHESTRATOR_TIMEOUT_SECONDS" in result.stdout


def test_validate_deploy_env_allows_healthy_orchestrator_timeout(tmp_path):
    env_file = _write_env(tmp_path, VALID_BASE + ["ORCHESTRATOR_TIMEOUT_SECONDS=60"])

    result = run_validator(env_file, "--skip-compose")

    assert result.returncode == 0


def test_validate_deploy_env_blocks_non_loopback_mcp_without_allow(tmp_path):
    env_file = _write_env(tmp_path, VALID_BASE + ["MCP_HOST=0.0.0.0"])

    result = run_validator(env_file, "--skip-compose")

    assert result.returncode == 1
    assert "MCP_HOST" in result.stdout
    assert "loopback" in result.stdout.lower() or "MCP_ALLOW_NON_LOOPBACK" in result.stdout


def test_validate_deploy_env_allows_non_loopback_mcp_with_explicit_flag(tmp_path):
    env_file = _write_env(
        tmp_path,
        VALID_BASE
        + [
            "MCP_HOST=0.0.0.0",
            "MCP_ALLOW_NON_LOOPBACK=true",
        ],
    )

    result = run_validator(env_file, "--skip-compose")

    assert result.returncode == 0


def test_validate_compose_loopback_accepts_repo_backend_compose():
    compose = Path(__file__).resolve().parents[2] / "infra" / "docker-compose.backend.yml"
    assert compose.exists()
    assert vde.validate_compose_loopback(compose) == []


def test_validate_compose_loopback_rejects_public_redis_bind(tmp_path):
    compose = tmp_path / "docker-compose.backend.yml"
    compose.write_text(
        "\n".join(
            [
                "services:",
                "  redis:",
                "    ports:",
                '      - "0.0.0.0:6379:6379"',
                "    command: [\"redis-server\", \"--requirepass\", \"x\"]",
                "  postgres:",
                "    ports:",
                '      - "127.0.0.1:5433:5432"',
                "  mcp-server:",
                "    ports:",
                '      - "127.0.0.1:8000:8000"',
                "  execution-engine:",
                "    ports:",
                '      - "127.0.0.1:50051:50051"',
            ]
        ),
        encoding="utf-8",
    )

    errors = vde.validate_compose_loopback(compose)

    assert any("redis" in e and "127.0.0.1:6379:6379" in e for e in errors)
    assert any("0.0.0.0" in e for e in errors)


def test_validate_deploy_env_cli_checks_compose_by_default(tmp_path):
    env_file = _write_env(tmp_path, VALID_BASE)
    bad_compose = tmp_path / "bad-compose.yml"
    bad_compose.write_text(
        "\n".join(
            [
                "services:",
                "  redis:",
                "    ports:",
                '      - "6379:6379"',
                "  postgres:",
                "    ports:",
                '      - "127.0.0.1:5433:5432"',
                "  mcp-server:",
                "    ports:",
                '      - "127.0.0.1:8000:8000"',
                "  execution-engine:",
                "    ports:",
                '      - "127.0.0.1:50051:50051"',
            ]
        ),
        encoding="utf-8",
    )

    result = run_validator(env_file, "--compose-file", str(bad_compose))

    assert result.returncode == 1
    assert "redis" in result.stdout.lower() or "loopback" in result.stdout.lower()
    assert "requirepass" in result.stdout.lower() or "REDIS_PASSWORD" in result.stdout
