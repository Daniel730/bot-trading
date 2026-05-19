import re
from pathlib import Path

import yaml


BACKEND_COMPOSE = Path(__file__).resolve().parents[2] / "infra" / "docker-compose.backend.yml"
FRONTEND_COMPOSE = Path(__file__).resolve().parents[2] / "infra" / "docker-compose.frontend.yml"


def test_backend_compose_requires_postgres_password_without_default():
    compose_text = BACKEND_COMPOSE.read_text(encoding="utf-8")

    assert "TBRZVATNGUXD" not in compose_text

    password_line = re.search(
        r"^\s*POSTGRES_PASSWORD:\s*(?P<value>.+)$",
        compose_text,
        flags=re.MULTILINE,
    )

    assert password_line is not None
    value = password_line.group("value").strip()
    assert value == "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"
    assert not re.search(r"\$\{POSTGRES_PASSWORD(?::-|-)[^}]*\}", value)
    assert re.search(r"\$\{POSTGRES_PASSWORD(?::\?|\?)[^}]*\}", value)

    compose = yaml.safe_load(compose_text)
    assert (
        compose["services"]["postgres"]["environment"]["POSTGRES_PASSWORD"]
        == "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"
    )


def test_backend_compose_does_not_auto_restart_trading_services():
    compose = yaml.safe_load(BACKEND_COMPOSE.read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["redis"]["restart"] == "always"
    assert services["postgres"]["restart"] == "always"

    for service_name in ("bot", "mcp-server", "execution-engine", "sec-worker"):
        assert services[service_name]["restart"] == "no"


def test_frontend_compose_does_not_auto_restart():
    compose = yaml.safe_load(FRONTEND_COMPOSE.read_text(encoding="utf-8"))

    assert compose["services"]["frontend"]["restart"] == "no"


def test_execution_engine_uses_compose_dependency_hosts():
    compose = yaml.safe_load(BACKEND_COMPOSE.read_text(encoding="utf-8"))
    environment = compose["services"]["execution-engine"]["environment"]

    assert environment["REDIS_HOST"] == "redis"
    assert environment["POSTGRES_HOST"] == "postgres"
    assert environment["POSTGRES_PORT"] == "5432"


def test_bot_uses_compose_dependency_hosts():
    compose = yaml.safe_load(BACKEND_COMPOSE.read_text(encoding="utf-8"))
    environment = compose["services"]["bot"]["environment"]

    assert environment["REDIS_HOST"] == "redis"
    assert environment["POSTGRES_HOST"] == "postgres"
    assert environment["POSTGRES_PORT"] == "5432"


def test_mcp_server_uses_compose_redis_host():
    compose = yaml.safe_load(BACKEND_COMPOSE.read_text(encoding="utf-8"))
    environment = compose["services"]["mcp-server"]["environment"]

    assert environment["REDIS_HOST"] == "redis"


def test_sec_worker_uses_compose_redis_host():
    compose = yaml.safe_load(BACKEND_COMPOSE.read_text(encoding="utf-8"))
    environment = compose["services"]["sec-worker"]["environment"]

    assert environment["REDIS_HOST"] == "redis"
