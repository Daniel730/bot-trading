"""Fast deploy-readiness checks for recurring trading-bot footguns.

This intentionally uses only the Python standard library so CI can run it
before dependency installation has had a chance to fail.
"""

from __future__ import annotations

import ast
import argparse
import socket
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"BUG_HUNT_AUDIT failed: {message}")


def assert_no_default_secrets() -> None:
    checked = [
        ROOT / ".env.template",
        ROOT / "infra" / "docker-compose.backend.yml",
    ]
    forbidden = ["bot_pass", "arbi-elite-2026"]
    for path in checked:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                fail(f"{path.relative_to(ROOT)} contains forbidden default secret {token!r}")


def assert_broker_uses_session_pool() -> None:
    path = ROOT / "src" / "services" / "brokerage_service.py"
    text = path.read_text(encoding="utf-8")
    if "requests.post" in text:
        fail("brokerage_service.py uses module-level requests.post instead of the session pool")


class AwaitVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.awaited_calls: set[ast.AST] = set()
        self.unawaited_order_calls: list[int] = []

    def visit_Await(self, node: ast.Await) -> None:
        self.awaited_calls.add(node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in {"place_value_order", "place_market_order"}
            and node not in self.awaited_calls
        ):
            self.unawaited_order_calls.append(node.lineno)
        self.generic_visit(node)


def assert_async_order_tests_are_awaited() -> None:
    for path in (ROOT / "tests").rglob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = AwaitVisitor()
        visitor.visit(tree)
        if visitor.unawaited_order_calls:
            lines = ", ".join(str(line) for line in visitor.unawaited_order_calls)
            fail(f"{path.relative_to(ROOT)} has unawaited async order calls on lines {lines}")


def assert_deploy_requires_quality_gate() -> None:
    path = ROOT / ".github" / "workflows" / "deploy.yml"
    text = path.read_text(encoding="utf-8")
    # The workflow uses three split quality jobs rather than a single monolithic one.
    # Verify each lane's quality job is defined and referenced as a build dependency.
    required_jobs = ["quality_python:", "quality_java:", "quality_frontend:"]
    required_needs = ["- quality_python", "- quality_java", "- quality_frontend"]
    for job in required_jobs:
        if job not in text:
            fail(f"deploy.yml must keep the quality job as a build dependency (missing job: {job.rstrip(':')})")
    for need in required_needs:
        if need not in text:
            fail(f"deploy.yml must keep the quality job as a build dependency (missing needs entry: {need.lstrip('- ')})")


def _load_env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _check_tcp(name: str, host: str, port: str) -> str | None:
    try:
        numeric_port = int(port)
    except ValueError:
        return f"{name} is unreachable: invalid port {port!r}."
    try:
        with socket.create_connection((host, numeric_port), timeout=3):
            return None
    except OSError as exc:
        return f"{name} is unreachable at {host}:{numeric_port}: {exc}"


def check_paper_startup_dependencies(env_file: Path) -> list[str]:
    values = _load_env_values(env_file)
    errors: list[str] = []

    try:
        result = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"Docker is unreachable: {exc}")
    else:
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "docker version failed").splitlines()[0]
            errors.append(f"Docker is unreachable: {detail}")

    redis_error = _check_tcp(
        "Redis",
        values.get("REDIS_HOST", "localhost"),
        values.get("REDIS_PORT", "6379"),
    )
    if redis_error:
        errors.append(redis_error)

    postgres_error = _check_tcp(
        "Postgres",
        values.get("POSTGRES_HOST", "localhost"),
        values.get("POSTGRES_PORT", "5432"),
    )
    if postgres_error:
        errors.append(postgres_error)

    return errors


def assert_paper_startup_dependencies(env_file: Path) -> None:
    errors = check_paper_startup_dependencies(env_file)
    if errors:
        fail("paper startup dependencies unavailable: " + " | ".join(errors))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fast deploy-readiness checks.")
    parser.add_argument(
        "--paper-startup-preflight",
        type=Path,
        help="Also verify Docker, Redis, and Postgres are reachable using this env file.",
    )
    args = parser.parse_args()

    assert_no_default_secrets()
    assert_broker_uses_session_pool()
    assert_async_order_tests_are_awaited()
    assert_deploy_requires_quality_gate()
    if args.paper_startup_preflight:
        assert_paper_startup_dependencies(args.paper_startup_preflight)
    print("BUG_HUNT_AUDIT passed")


if __name__ == "__main__":
    main()
