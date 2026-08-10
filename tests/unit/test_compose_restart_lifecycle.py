"""Deterministic restart-policy matrix for bot soak safety (#137 / unless-stopped).

Docker semantics are encoded as expected outcomes from the Compose restart policy
string — we do not simulate dockerd here. Intentional vs accidental:

- Intentional stop: operator `docker stop` / Compose stop → unless-stopped does NOT restart.
- Accidental: process crash (non-zero exit), host reboot, dockerd restart → unless-stopped DOES restart.
"""

from pathlib import Path

import yaml

BACKEND_COMPOSE = Path(__file__).resolve().parents[2] / "infra" / "docker-compose.backend.yml"


def _bot_restart_policy() -> str:
    compose = yaml.safe_load(BACKEND_COMPOSE.read_text(encoding="utf-8"))
    return compose["services"]["bot"]["restart"]


def _expected_auto_restart(policy: str, event: str) -> bool:
    """Map lifecycle event → whether Docker should bring the container back."""
    if policy == "no":
        return False
    if policy == "always":
        # always restarts even after explicit stop (on daemon start).
        return True
    if policy == "unless-stopped":
        return event in {
            "B_process_crash",
            "C_host_reboot",
            "D_docker_daemon_restart",
            "container_recreate_then_daemon_start",
        }
    raise AssertionError(f"unknown restart policy {policy!r}")


def test_bot_compose_policy_is_unless_stopped():
    assert _bot_restart_policy() == "unless-stopped"


def test_lifecycle_A_intentional_docker_stop_does_not_auto_restart():
    """A — intentional `docker stop`: unless-stopped must stick until operator start."""
    assert _expected_auto_restart(_bot_restart_policy(), "A_intentional_docker_stop") is False


def test_lifecycle_B_process_crash_auto_restarts():
    """B — monitor/process crash (container exits unexpectedly): must come back."""
    assert _expected_auto_restart(_bot_restart_policy(), "B_process_crash") is True


def test_lifecycle_C_host_reboot_auto_restarts():
    """C — host reboot (the #137 failure mode under restart:no): must come back."""
    assert _expected_auto_restart(_bot_restart_policy(), "C_host_reboot") is True


def test_lifecycle_D_docker_daemon_restart_auto_restarts():
    """D — dockerd restart without explicit stop: must come back."""
    assert _expected_auto_restart(_bot_restart_policy(), "D_docker_daemon_restart") is True


def test_lifecycle_intentional_process_stop_via_docker_stop_is_not_crash():
    """
    Ambiguity callout encoded as a contract:

    Stopping only the Python process *inside* a running container without
    stopping the container is not modeled by Compose restart policy — PID1/exit
    handling is image-specific. Safest paper-daemon recommendation: use
    `docker stop` for intentional downtime (sticks under unless-stopped) and
    never rely on killing PID1 alone as an intentional stop signal.
    """
    # Intentional operator stop uses docker stop → no auto-restart.
    assert _expected_auto_restart(_bot_restart_policy(), "A_intentional_docker_stop") is False
    # Accidental container exit uses crash path → auto-restart.
    assert _expected_auto_restart(_bot_restart_policy(), "B_process_crash") is True


def test_redis_postgres_use_always_while_bot_is_unless_stopped():
    compose = yaml.safe_load(BACKEND_COMPOSE.read_text(encoding="utf-8"))
    assert compose["services"]["redis"]["restart"] == "always"
    assert compose["services"]["postgres"]["restart"] == "always"
    assert compose["services"]["bot"]["restart"] == "unless-stopped"
