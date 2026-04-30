"""
Project-level pytest configuration.

Seeds the minimum required environment variables so that ``src.config.Settings``
can be instantiated during test collection without a real .env file.  Individual
tests may override specific env vars via ``monkeypatch.setenv``.
"""
import os

# ---------------------------------------------------------------------------
# Required secrets – use obviously fake values so CI/CD never silently uses
# a real credential. The values must satisfy the validator constraints
# (non-empty, not equal to the default sentinel).
# ---------------------------------------------------------------------------
os.environ.setdefault("POSTGRES_PASSWORD", "test-postgres-secret")
os.environ.setdefault("DASHBOARD_TOKEN", "test-dashboard-token-for-pytest")
