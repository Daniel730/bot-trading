"""Static safety gates for the Java dry-run execution sidecar.

These assert source/compose invariants so Python CI catches accidental live-order
bypass or LAN exposure even when Gradle is unavailable on the runner host.
"""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
EE = ROOT / "execution-engine"
BACKEND_COMPOSE = ROOT / "infra" / "docker-compose.backend.yml"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_application_refuses_boot_without_dry_run():
    application = _read("execution-engine/src/main/java/com/arbitrage/engine/Application.java")
    assert "if (!EnvironmentConfig.isDryRun())" in application
    assert "Execution engine live brokerage is not implemented" in application
    assert "throw new IllegalStateException" in application


def test_brokerage_router_never_returns_live_broker():
    router = _read(
        "execution-engine/src/main/java/com/arbitrage/engine/broker/BrokerageRouter.java"
    )
    assert "new MockBroker" in router
    assert "new LiveBroker" not in router
    assert "throw new IllegalStateException" in router
    assert "Set DRY_RUN=true" in router


def test_live_broker_is_fail_closed():
    live = _read("execution-engine/src/main/java/com/arbitrage/engine/broker/LiveBroker.java")
    assert "UnsupportedOperationException" in live
    assert "DRY_RUN=true" in live
    assert "Mono.just(new BrokerExecutionResponse(false" not in live


def test_dockerfile_defaults_dry_run_true():
    dockerfile = _read("execution-engine/Dockerfile")
    assert "ENV DRY_RUN=true" in dockerfile
    assert "ENV LIVE_CAPITAL_DANGER=false" in dockerfile


def test_application_yml_defaults_dry_run_true():
    yml = _read("execution-engine/src/main/resources/application.yml")
    assert "dry-run: ${DRY_RUN:true}" in yml
    assert "dry-run: ${DRY_RUN:false}" not in yml


def test_compose_execution_engine_loopback_and_dry_run():
    text = BACKEND_COMPOSE.read_text(encoding="utf-8")
    assert '"127.0.0.1:50051:50051"' in text
    assert re.search(r"DRY_RUN:\s*[\"']true[\"']", text)
    assert re.search(r"LIVE_CAPITAL_DANGER:\s*[\"']false[\"']", text)
    # Unscoped / all-interfaces publish must not reappear.
    assert re.search(r'^\s*-\s*"50051:50051"\s*$', text, flags=re.MULTILINE) is None


def test_monitor_order_path_does_not_call_java_execution_client():
    monitor = _read("src/monitor.py")
    assert "execution_service_client" not in monitor
    assert "execution_client" not in monitor
    assert "shadow_service" in monitor


def test_mcp_execute_trade_does_not_dispatch_to_java():
    mcp = _read("src/mcp_server.py")
    # Tool body must reject before any gRPC dispatch.
    assert "FastMCP execute_trade is disabled" in mcp
    tool_body = mcp.split("async def execute_trade", 1)[1].split("@mcp.tool()", 1)[0]
    assert "execution_client.execute_trade" not in tool_body
    assert "await execution_client" not in tool_body
