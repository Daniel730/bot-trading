import re
from pathlib import Path


BACKEND_COMPOSE = Path(__file__).resolve().parents[2] / "infra" / "docker-compose.backend.yml"


def test_backend_compose_requires_postgres_password_without_default():
    compose_text = BACKEND_COMPOSE.read_text(encoding="utf-8")

    password_line = re.search(
        r"^\s*POSTGRES_PASSWORD:\s*(?P<value>.+)$",
        compose_text,
        flags=re.MULTILINE,
    )

    assert password_line is not None
    value = password_line.group("value").strip()
    assert not re.search(r"\$\{POSTGRES_PASSWORD(?::-|-)[^}]*\}", value)
    assert re.search(r"\$\{POSTGRES_PASSWORD(?::\?|\?)[^}]*\}", value)
