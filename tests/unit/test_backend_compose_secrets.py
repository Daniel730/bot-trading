import re
from pathlib import Path

import yaml


BACKEND_COMPOSE = Path(__file__).resolve().parents[2] / "infra" / "docker-compose.backend.yml"
FRONTEND_COMPOSE = Path(__file__).resolve().parents[2] / "infra" / "docker-compose.frontend.yml"
GITATTRIBUTES = Path(__file__).resolve().parents[2] / ".gitattributes"


def test_compose_files_are_pinned_to_lf_line_endings():
    attributes = GITATTRIBUTES.read_text(encoding="utf-8").splitlines()

    assert "infra/docker-compose*.yml text eol=lf" in attributes


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


def test_backend_compose_restart_policies():
    compose = yaml.safe_load(BACKEND_COMPOSE.read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["redis"]["restart"] == "always"
    assert services["postgres"]["restart"] == "always"

    # Bot/MCP stay manual-restart so crashes stay visible to operators.
    for service_name in ("bot", "mcp-server"):
        assert services[service_name]["restart"] == "no"
    # SEC worker auto-recovers: empty Redis fundamentals silently block live equity entries.
    assert services["sec-worker"]["restart"] == "unless-stopped"
    # Dry-run sidecar may recover without operator intervention.
    assert services["execution-engine"]["restart"] == "unless-stopped"


def test_frontend_compose_restarts_unless_stopped():
    compose = yaml.safe_load(FRONTEND_COMPOSE.read_text(encoding="utf-8"))

    assert compose["services"]["frontend"]["restart"] == "unless-stopped"


def test_execution_engine_uses_compose_dependency_hosts():
    compose = yaml.safe_load(BACKEND_COMPOSE.read_text(encoding="utf-8"))
    environment = compose["services"]["execution-engine"]["environment"]

    assert environment["REDIS_HOST"] == "redis"
    assert environment["POSTGRES_HOST"] == "postgres"
    assert environment["POSTGRES_PORT"] == "5432"


def test_execution_engine_forces_dry_run_sidecar_mode():
    compose = yaml.safe_load(BACKEND_COMPOSE.read_text(encoding="utf-8"))
    environment = compose["services"]["execution-engine"]["environment"]

    assert environment["DRY_RUN"] == "true"
    assert environment["LIVE_CAPITAL_DANGER"] == "false"


def test_sensitive_backend_ports_are_loopback_only():
    """Host publishes must not expose Redis/Postgres/MCP/gRPC on LAN or public IPv6."""
    compose = yaml.safe_load(BACKEND_COMPOSE.read_text(encoding="utf-8"))
    expected = {
        "redis": "127.0.0.1:6379:6379",
        "postgres": "127.0.0.1:5433:5432",
        "mcp-server": "127.0.0.1:8000:8000",
        "execution-engine": "127.0.0.1:50051:50051",
    }
    for service_name, binding in expected.items():
        ports = compose["services"][service_name].get("ports") or []
        assert binding in ports, f"{service_name} must publish {binding} only"
        assert not any(
            isinstance(p, str) and p.startswith("0.0.0.0:") for p in ports
        )
        assert not any(
            isinstance(p, str) and re.fullmatch(r"\d+:\d+", p) for p in ports
        ), f"{service_name} must not use unscoped host binds like 'PORT:PORT'"


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


def test_bot_python_services_mount_persistent_data_volume():
    compose = yaml.safe_load(BACKEND_COMPOSE.read_text(encoding="utf-8"))
    services = compose["services"]

    for service_name in ("bot", "mcp-server", "sec-worker"):
        volumes = services[service_name].get("volumes") or []
        assert "bot_data:/app/data" in volumes

    assert compose["volumes"]["bot_data"]["name"] == "trading-bot_bot_data"
    assert compose["volumes"]["bot_data"]["external"] is True


def test_sec_worker_uses_compose_postgres_host():
    compose = yaml.safe_load(BACKEND_COMPOSE.read_text(encoding="utf-8"))
    environment = compose["services"]["sec-worker"]["environment"]

    assert environment["POSTGRES_HOST"] == "postgres"
    assert environment["POSTGRES_PORT"] == "5432"


def test_backend_compose_hardens_host_publishes_to_loopback():
    compose = yaml.safe_load(BACKEND_COMPOSE.read_text(encoding="utf-8"))
    expected = {
        "redis": "127.0.0.1:6379:6379",
        "postgres": "127.0.0.1:5433:5432",
        "mcp-server": "127.0.0.1:8000:8000",
        "execution-engine": "127.0.0.1:50051:50051",
    }
    for service_name, publish in expected.items():
        ports = compose["services"][service_name]["ports"]
        assert publish in ports
        assert not any(p.startswith("0.0.0.0:") for p in ports)
        assert not any(isinstance(p, str) and p.startswith(publish.split(":")[1] + ":") for p in ports)


def test_backend_compose_requires_redis_password_and_requirepass():
    compose_text = BACKEND_COMPOSE.read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)
    redis = compose["services"]["redis"]

    assert redis["environment"]["REDIS_PASSWORD"] == (
        "${REDIS_PASSWORD:?REDIS_PASSWORD must be set}"
    )
    assert "--requirepass" in redis["command"]
    assert "${REDIS_PASSWORD:?REDIS_PASSWORD must be set}" in redis["command"]
    health = redis["healthcheck"]["test"]
    assert any("REDIS_PASSWORD" in part for part in health if isinstance(part, str))
