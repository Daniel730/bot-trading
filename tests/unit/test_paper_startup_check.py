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
