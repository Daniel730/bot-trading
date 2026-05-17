import os
import subprocess
import sys


def test_sec_service_import_allows_deprecation_warnings_as_errors():
    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "error::DeprecationWarning"

    result = subprocess.run(
        [sys.executable, "-c", "import src.services.sec_service"],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
