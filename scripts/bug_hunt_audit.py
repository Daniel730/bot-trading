"""Fast deploy-readiness checks for recurring trading-bot footguns.

This intentionally uses only the Python standard library so CI can run it
before dependency installation has had a chance to fail.
"""

from __future__ import annotations

import ast
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
    if "quality:" not in text or "needs: quality" not in text:
        fail("deploy.yml must keep the quality job as a build dependency")


def main() -> None:
    assert_no_default_secrets()
    assert_broker_uses_session_pool()
    assert_async_order_tests_are_awaited()
    assert_deploy_requires_quality_gate()
    print("BUG_HUNT_AUDIT passed")


if __name__ == "__main__":
    main()
