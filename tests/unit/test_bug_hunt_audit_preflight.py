from types import SimpleNamespace

from scripts import bug_hunt_audit


def test_paper_startup_preflight_reports_unreachable_dependencies(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "REDIS_HOST=redis",
                "REDIS_PORT=6379",
                "POSTGRES_HOST=postgres",
                "POSTGRES_PORT=5432",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        bug_hunt_audit.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="failed to connect to docker API",
        ),
    )

    def refuse_connection(address, timeout):
        raise OSError(f"refused {address[0]}:{address[1]}")

    monkeypatch.setattr(bug_hunt_audit.socket, "create_connection", refuse_connection)

    errors = bug_hunt_audit.check_paper_startup_dependencies(env_file)

    assert any("Docker is unreachable" in error for error in errors)
    assert any("Redis is unreachable at redis:6379" in error for error in errors)
    assert any("Postgres is unreachable at postgres:5432" in error for error in errors)
