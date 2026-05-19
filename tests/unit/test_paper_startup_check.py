import subprocess
from types import SimpleNamespace

from scripts import paper_startup_check


def test_paper_startup_check_repairs_validates_then_preflights(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD=strong-postgres-secret",
                "DASHBOARD_TOKEN=strong-dashboard-token",
                "PAPER_TRADING=false",
                "REDIS_HOST=redis",
                "POSTGRES_HOST=postgres",
                "POSTGRES_PORT=5432",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    calls = []

    def validate_after_repair(values):
        calls.append(("validate", values["PAPER_TRADING"], values["POSTGRES_HOST"]))
        return []

    def preflight_after_validation(path):
        calls.append(("preflight", path.read_text(encoding="utf-8")))
        return ["Docker is unreachable: test"]

    monkeypatch.setattr(paper_startup_check.validate_deploy_env, "validate", validate_after_repair)
    monkeypatch.setattr(paper_startup_check, "check_running_action_containers", lambda: [])
    monkeypatch.setattr(paper_startup_check, "count_unresolved_reconciliation_rows", lambda: 0)
    monkeypatch.setattr(paper_startup_check, "check_unresolved_reconciliation_rows", lambda: [])
    monkeypatch.setattr(
        paper_startup_check.bug_hunt_audit,
        "check_paper_startup_dependencies",
        preflight_after_validation,
    )

    result = paper_startup_check.run_check(env_file)

    assert result == 1
    assert calls[0] == ("validate", "true", "localhost")
    assert calls[1][0] == "preflight"
    assert "PAPER_TRADING=true" in calls[1][1]
    assert "POSTGRES_HOST=localhost" in calls[1][1]
    assert "POSTGRES_PORT=5433" in calls[1][1]


def test_paper_startup_check_blocks_unresolved_reconciliation_rows(
    monkeypatch, tmp_path, capsys
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD=strong-postgres-secret",
                "DASHBOARD_TOKEN=strong-dashboard-token",
                "PAPER_TRADING=true",
                "REDIS_HOST=localhost",
                "POSTGRES_HOST=localhost",
                "POSTGRES_PORT=5433",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    preflight_calls = []

    monkeypatch.setattr(paper_startup_check.validate_deploy_env, "validate", lambda values: [])
    monkeypatch.setattr(paper_startup_check, "check_running_action_containers", lambda: [])
    monkeypatch.setattr(
        paper_startup_check.bug_hunt_audit,
        "check_paper_startup_dependencies",
        lambda path: preflight_calls.append(path) or [],
    )
    monkeypatch.setattr(paper_startup_check, "count_unresolved_reconciliation_rows", lambda: 12)
    monkeypatch.setattr(
        paper_startup_check,
        "check_unresolved_reconciliation_rows",
        lambda: [
            {
                "id": "ledger-1",
                "order_id": "ORPHAN_abc",
                "ticker": "BTC-USD",
                "status": "FAILED",
                "venue": "ALPACA",
            }
        ],
    )

    result = paper_startup_check.run_check(env_file)

    assert result == 1
    assert preflight_calls == [env_file]
    output = capsys.readouterr().out
    assert "Paper startup reconciliation guard failed:" in output
    assert "12 unresolved ledger rows require reconciliation" in output
    assert "id=ledger-1" in output
    assert "ticker=BTC-USD" in output


def test_paper_startup_check_passes_after_reconciliation_guard_clears(
    monkeypatch, tmp_path, capsys
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD=strong-postgres-secret",
                "DASHBOARD_TOKEN=strong-dashboard-token",
                "PAPER_TRADING=true",
                "REDIS_HOST=localhost",
                "POSTGRES_HOST=localhost",
                "POSTGRES_PORT=5433",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    guard_calls = []

    monkeypatch.setattr(paper_startup_check.validate_deploy_env, "validate", lambda values: [])
    monkeypatch.setattr(paper_startup_check, "check_running_action_containers", lambda: [])
    monkeypatch.setattr(
        paper_startup_check.bug_hunt_audit,
        "check_paper_startup_dependencies",
        lambda path: [],
    )
    monkeypatch.setattr(
        paper_startup_check,
        "count_unresolved_reconciliation_rows",
        lambda: guard_calls.append("count") or 0,
    )
    monkeypatch.setattr(
        paper_startup_check,
        "check_unresolved_reconciliation_rows",
        lambda: guard_calls.append("rows") or [],
    )

    result = paper_startup_check.run_check(env_file)

    assert result == 0
    assert guard_calls == ["count", "rows"]
    assert "Paper startup check passed." in capsys.readouterr().out


def test_paper_startup_check_blocks_running_action_containers(
    monkeypatch, tmp_path, capsys
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD=strong-postgres-secret",
                "DASHBOARD_TOKEN=strong-dashboard-token",
                "PAPER_TRADING=true",
                "REDIS_HOST=localhost",
                "POSTGRES_HOST=localhost",
                "POSTGRES_PORT=5433",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    preflight_calls = []

    monkeypatch.setattr(paper_startup_check.validate_deploy_env, "validate", lambda values: [])
    monkeypatch.setattr(paper_startup_check, "subprocess", subprocess, raising=False)
    monkeypatch.setattr(
        paper_startup_check.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="infra-bot-1\ninfra-redis-1\n",
            stderr="",
        ),
    )
    monkeypatch.setattr(
        paper_startup_check.bug_hunt_audit,
        "check_paper_startup_dependencies",
        lambda path: preflight_calls.append(path) or [],
    )

    result = paper_startup_check.run_check(env_file)

    assert result == 1
    assert preflight_calls == []
    output = capsys.readouterr().out
    assert "Paper startup container guard failed:" in output
    assert "infra-bot-1" in output


def test_paper_startup_check_blocks_running_frontend_container(
    monkeypatch, tmp_path, capsys
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD=strong-postgres-secret",
                "DASHBOARD_TOKEN=strong-dashboard-token",
                "PAPER_TRADING=true",
                "REDIS_HOST=localhost",
                "POSTGRES_HOST=localhost",
                "POSTGRES_PORT=5433",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    preflight_calls = []

    monkeypatch.setattr(paper_startup_check.validate_deploy_env, "validate", lambda values: [])
    monkeypatch.setattr(paper_startup_check, "subprocess", subprocess, raising=False)
    monkeypatch.setattr(
        paper_startup_check.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="infra-frontend-1\ninfra-redis-1\n",
            stderr="",
        ),
    )
    monkeypatch.setattr(
        paper_startup_check.bug_hunt_audit,
        "check_paper_startup_dependencies",
        lambda path: preflight_calls.append(path) or [],
    )

    result = paper_startup_check.run_check(env_file)

    assert result == 1
    assert preflight_calls == []
    output = capsys.readouterr().out
    assert "Paper startup container guard failed:" in output
    assert "infra-frontend-1" in output
