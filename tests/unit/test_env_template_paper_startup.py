from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_template_values() -> dict[str, str]:
    values = {}
    for raw_line in (ROOT / ".env.template").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def test_env_template_uses_host_reachable_paper_startup_endpoints():
    values = _load_template_values()

    assert values["PAPER_TRADING"] == "true"
    assert values["REDIS_HOST"] == "localhost"
    assert values["REDIS_PORT"] == "6379"
    assert values["POSTGRES_HOST"] == "localhost"
    assert values["POSTGRES_PORT"] == "5433"
