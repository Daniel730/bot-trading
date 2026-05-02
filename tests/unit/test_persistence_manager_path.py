"""
Tests for the PR change to src/models/persistence.py:

PR changed the default db_path from:
    os.path.join(os.getcwd(), "logs", "trading_bot.db")   (absolute, CWD-dependent)
to:
    "logs/trading_bot.db"                                  (relative)

The change was motivated by dropping the Windows-specific absolute-path
workaround; on any platform the fallback is now a simple relative path.
"""
import os
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(db_path=None, *, settings_db_path=None):
    """
    Create a PersistenceManager without touching the real filesystem or DB.
    Patches _init_db and os.makedirs so no files are actually created.
    """
    from src.models.persistence import PersistenceManager

    with patch.object(PersistenceManager, "_init_db"), \
         patch("src.models.persistence.os.makedirs"):
        if settings_db_path is not None:
            with patch("src.models.persistence.settings") as mock_settings:
                mock_settings.DB_PATH = settings_db_path
                return PersistenceManager(db_path)
        else:
            return PersistenceManager(db_path)


# ---------------------------------------------------------------------------
# Default db_path is now relative "logs/trading_bot.db"
# ---------------------------------------------------------------------------

class TestPersistenceManagerDefaultPath:
    def test_default_path_is_relative_logs_trading_bot_db(self):
        """
        The PR changed the default from os.path.join(os.getcwd(), ...) to the
        plain relative string "logs/trading_bot.db".
        When no db_path is passed and settings has no DB_PATH, the instance
        must use the relative string default.
        """
        from src.models.persistence import PersistenceManager

        with patch.object(PersistenceManager, "_init_db"), \
             patch("src.models.persistence.os.makedirs"), \
             patch("src.models.persistence.settings") as mock_settings:
            # Simulate settings without DB_PATH attribute
            del mock_settings.DB_PATH  # ensure getattr returns default
            mock_settings.configure_mock(spec=[])  # no DB_PATH attribute
            # getattr(settings, "DB_PATH", "logs/trading_bot.db") falls through to default
            mgr = PersistenceManager(db_path=None)

        # db_path should be the relative fallback
        assert mgr.db_path == "logs/trading_bot.db"

    def test_default_path_is_not_absolute_when_no_settings(self):
        """The old default used os.path.join(os.getcwd(), ...) → absolute path.
        After the PR the default should be relative (not os.sep-prefixed)."""
        from src.models.persistence import PersistenceManager

        with patch.object(PersistenceManager, "_init_db"), \
             patch("src.models.persistence.os.makedirs"), \
             patch("src.models.persistence.settings") as mock_settings:
            mock_settings.configure_mock(spec=[])
            mgr = PersistenceManager(db_path=None)

        # Relative path → does not start with os.sep
        assert not os.path.isabs(mgr.db_path)

    def test_explicit_db_path_is_used_directly(self):
        """An explicit db_path argument must always be used verbatim."""
        mgr = _make_manager("/tmp/custom_test.db")
        assert mgr.db_path == "/tmp/custom_test.db"

    def test_settings_db_path_takes_precedence_over_default(self):
        """settings.DB_PATH, when present, overrides the coded default."""
        mgr = _make_manager(settings_db_path="/var/data/bot.db")
        assert mgr.db_path == "/var/data/bot.db"

    def test_in_memory_db_path_is_preserved(self):
        """':memory:' special path must pass through unchanged."""
        from src.models.persistence import PersistenceManager

        with patch.object(PersistenceManager, "_init_db"):
            mgr = PersistenceManager(":memory:")

        assert mgr.db_path == ":memory:"
        # In-memory connections should set the URI
        assert mgr._memory_uri is not None

    def test_none_db_path_falls_back_to_settings_or_default(self):
        """Passing None explicitly should fall back just like omitting the arg."""
        mgr = _make_manager(None, settings_db_path="logs/trading_bot.db")
        assert mgr.db_path == "logs/trading_bot.db"


# ---------------------------------------------------------------------------
# Regression: old absolute default is gone
# ---------------------------------------------------------------------------

def test_default_path_does_not_use_getcwd():
    """
    The PR removed the os.path.join(os.getcwd(), ...) computation.
    Even if CWD changes, the default path must not embed the original CWD.
    This is a regression guard against re-introducing the absolute-path pattern.
    """
    import os
    from src.models.persistence import PersistenceManager

    original_cwd = os.getcwd()
    with patch.object(PersistenceManager, "_init_db"), \
         patch("src.models.persistence.os.makedirs"), \
         patch("src.models.persistence.settings") as mock_settings:
        mock_settings.configure_mock(spec=[])
        mgr = PersistenceManager(db_path=None)

    # If the default had been os.path.join(os.getcwd(), ...) the path would
    # contain the CWD string. After the PR it must not.
    assert original_cwd not in mgr.db_path or mgr.db_path == "logs/trading_bot.db"