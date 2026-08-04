#!/usr/bin/env python3
"""Validate deployment-only secrets and deploy-checklist gates without printing secrets."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


BLOCKED_POSTGRES_PASSWORDS = {"bot_pass", "postgres", "password", "changeme"}
BLOCKED_DASHBOARD_TOKENS = {"arbi-elite-2026", "dashboard-token", "changeme"}
BLOCKED_ALPACA_VALUES = {
    "your_alpaca_key",
    "your_alpaca_secret",
}
JSON_OBJECT_KEYS = {"CRYPTO_TOKEN_MAPPING"}

# Keep in sync with src.config.MONITOR_ENTRY_ZSCORE_MIN and ops_overnight_check.sh.
MONITOR_ENTRY_ZSCORE_MIN = 1.0
ORCHESTRATOR_TIMEOUT_MIN_SECONDS = 30.0
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})
_TRUTHY = frozenset({"1", "true", "yes", "on"})

# Host publishes that must stay loopback-only on bot-server (LAN + public IPv6).
REQUIRED_LOOPBACK_PUBLISHES = (
    ("redis", "127.0.0.1:6379:6379", "6379"),
    ("postgres", "127.0.0.1:5433:5432", "5433"),
    ("mcp-server", "127.0.0.1:8000:8000", "8000"),
    ("execution-engine", "127.0.0.1:50051:50051", "50051"),
)


def _clean_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.strip()


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _clean_value(value)
    return values


def _parse_float(raw: str, key: str, errors: list[str]) -> float | None:
    try:
        return float(raw)
    except ValueError:
        errors.append(f"{key} must be a number.")
        return None


def _is_truthy(raw: str) -> bool:
    return raw.strip().lower() in _TRUTHY


def validate(values: dict[str, str]) -> list[str]:
    errors: list[str] = []

    postgres_password = values.get("POSTGRES_PASSWORD", "")
    if not postgres_password:
        errors.append("POSTGRES_PASSWORD is missing or empty.")
    elif postgres_password.lower() in BLOCKED_POSTGRES_PASSWORDS:
        errors.append("POSTGRES_PASSWORD is still a blocked default value.")

    redis_password = values.get("REDIS_PASSWORD", "")
    if not redis_password:
        errors.append("REDIS_PASSWORD is missing or empty.")
    elif len(redis_password) < 16:
        errors.append("REDIS_PASSWORD must be at least 16 characters long.")

    dashboard_token = values.get("DASHBOARD_TOKEN", "")
    if not dashboard_token:
        errors.append("DASHBOARD_TOKEN is missing or empty.")
    elif dashboard_token in BLOCKED_DASHBOARD_TOKENS:
        errors.append("DASHBOARD_TOKEN is still a blocked default value.")
    elif len(dashboard_token) < 16:
        errors.append("DASHBOARD_TOKEN must be at least 16 characters long.")

    database_url = values.get("DATABASE_URL", "")
    if database_url and "bot_pass" in database_url:
        errors.append("DATABASE_URL still contains the default Postgres password.")

    for key in ("ALPACA_API_KEY", "ALPACA_API_SECRET"):
        value = values.get(key, "")
        if value in BLOCKED_ALPACA_VALUES:
            errors.append(f"{key} is still a template placeholder.")

    paper_trading = values.get("PAPER_TRADING", "")
    alpaca_base = (
        values.get("ALPACA_BASE_URL")
        or values.get("APCA_API_BASE_URL")
        or ""
    ).lower()
    alpaca_broker_paper = "paper-api.alpaca.markets" in alpaca_base
    # PAPER_TRADING=false is allowed only when routing to Alpaca's paper API
    # (real paper fills, not internal shadow). Live money URLs still require
    # PAPER_TRADING=true for deploy gating.
    if paper_trading and paper_trading.lower() != "true" and not alpaca_broker_paper:
        errors.append("PAPER_TRADING must be true for paper-trading startup validation.")

    z_raw = values.get("MONITOR_ENTRY_ZSCORE", "").strip()
    if z_raw:
        z_score = _parse_float(z_raw, "MONITOR_ENTRY_ZSCORE", errors)
        if z_score is not None and z_score < MONITOR_ENTRY_ZSCORE_MIN:
            errors.append(
                f"MONITOR_ENTRY_ZSCORE must be >= {MONITOR_ENTRY_ZSCORE_MIN:g} "
                "(never 0.5; runtime clamps but deploy should not ship that intent)."
            )

    timeout_raw = values.get("ORCHESTRATOR_TIMEOUT_SECONDS", "").strip()
    if timeout_raw:
        timeout = _parse_float(timeout_raw, "ORCHESTRATOR_TIMEOUT_SECONDS", errors)
        if timeout is not None and timeout < ORCHESTRATOR_TIMEOUT_MIN_SECONDS:
            errors.append(
                f"ORCHESTRATOR_TIMEOUT_SECONDS must be >= {ORCHESTRATOR_TIMEOUT_MIN_SECONDS:g}."
            )

    # Loopback awareness for host-side MCP binds in the shared deploy env.
    # Compose may override MCP_HOST inside the mcp-server container; the shared
    # env_file must not silently allow a non-loopback bind without the explicit flag.
    mcp_host = values.get("MCP_HOST", "").strip()
    if mcp_host and mcp_host not in _LOOPBACK_HOSTS:
        if not _is_truthy(values.get("MCP_ALLOW_NON_LOOPBACK", "")):
            errors.append(
                "MCP_HOST is non-loopback without MCP_ALLOW_NON_LOOPBACK=true "
                "(Docker compose sets both inside the container; host publish must stay 127.0.0.1)."
            )

    for key in JSON_OBJECT_KEYS:
        value = values.get(key, "")
        if not value:
            continue
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            errors.append(f"{key} must be valid JSON.")
            continue
        if not isinstance(parsed, dict):
            errors.append(f"{key} must be a JSON object.")

    return errors


def _service_ports_block(compose_text: str, service: str) -> str | None:
    """Return the indented ports list body for a top-level compose service, if any."""
    svc_re = re.compile(rf"^  {re.escape(service)}:\s*$", re.MULTILINE)
    match = svc_re.search(compose_text)
    if not match:
        return None
    rest = compose_text[match.end() :]
    next_svc = re.search(r"^  [A-Za-z0-9_-]+:\s*$", rest, re.MULTILINE)
    block = rest if next_svc is None else rest[: next_svc.start()]
    ports_match = re.search(r"^    ports:\s*$", block, re.MULTILINE)
    if not ports_match:
        return ""
    ports_rest = block[ports_match.end() :]
    end = re.search(r"^    [A-Za-z0-9_-]+:\s*$", ports_rest, re.MULTILINE)
    return ports_rest if end is None else ports_rest[: end.start()]


def validate_compose_loopback(compose_path: Path) -> list[str]:
    """Fail closed if sensitive host publishes are missing or not loopback-only."""
    errors: list[str] = []
    if not compose_path.exists():
        errors.append(f"Compose file does not exist: {compose_path}")
        return errors

    text = compose_path.read_text(encoding="utf-8")
    for service, binding, host_port in REQUIRED_LOOPBACK_PUBLISHES:
        ports_body = _service_ports_block(text, service)
        if ports_body is None:
            errors.append(f"Compose service '{service}' is missing (loopback publish required).")
            continue
        if binding not in ports_body:
            errors.append(
                f"Compose {service} must publish {binding} (loopback-only host bind)."
            )
        if re.search(rf"0\.0\.0\.0:{host_port}:", ports_body):
            errors.append(
                f"Compose {service} must not publish 0.0.0.0:{host_port} (use 127.0.0.1)."
            )
        # Unscoped host binds like "6379:6379" reopen LAN/IPv6 on bot-server.
        for line in ports_body.splitlines():
            stripped = line.strip().lstrip("-").strip().strip("\"'")
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith(f"{host_port}:") and not stripped.startswith("127.0.0.1:"):
                errors.append(
                    f"Compose {service} has an unscoped host publish '{stripped}'; "
                    "bind 127.0.0.1 only."
                )

    if "requirepass" not in text:
        errors.append("Compose redis wiring must include --requirepass (REDIS_PASSWORD).")

    return errors


def default_compose_path() -> Path | None:
    candidate = Path(__file__).resolve().parents[1] / "infra" / "docker-compose.backend.yml"
    return candidate if candidate.exists() else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate deployment env secrets and deploy-checklist gates "
            "(REDIS_PASSWORD, MONITOR_ENTRY_ZSCORE, ORCHESTRATOR_TIMEOUT, loopback binds) "
            "before Docker Compose starts services."
        )
    )
    parser.add_argument("env_file", type=Path, help="Path to the deployment .env file")
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=None,
        help="Compose file to check for loopback-only sensitive publishes "
        "(default: infra/docker-compose.backend.yml next to this repo).",
    )
    parser.add_argument(
        "--skip-compose",
        action="store_true",
        help="Skip compose loopback publish checks (env-only validation).",
    )
    args = parser.parse_args()

    if not args.env_file.exists():
        print(f"Deploy environment validation failed: {args.env_file} does not exist.")
        return 1

    errors = validate(load_env(args.env_file))

    if not args.skip_compose:
        compose_path = args.compose_file or default_compose_path()
        if compose_path is None:
            errors.append(
                "Could not locate infra/docker-compose.backend.yml for loopback checks; "
                "pass --compose-file or use --skip-compose."
            )
        else:
            errors.extend(validate_compose_loopback(compose_path))

    if errors:
        print("Deploy environment validation failed:")
        for error in errors:
            print(f"- {error}")
        print(
            "Fix the persistent deployment env file with strong values before starting "
            "containers. If POSTGRES_PASSWORD changes for an existing Postgres volume, "
            "rotate the database user's password too. REDIS_PASSWORD must be set (≥16 chars) "
            "so compose can enable Redis --requirepass. Keep redis/postgres/mcp/gRPC host "
            "publishes on 127.0.0.1; MONITOR_ENTRY_ZSCORE >= 1.0; "
            "ORCHESTRATOR_TIMEOUT_SECONDS >= 30."
        )
        return 1

    print(
        "Deploy environment OK: required secrets are set and non-default; "
        "entry z-score / orchestrator timeout / loopback publishes look safe."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
