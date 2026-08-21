import subprocess
import sys
from pathlib import Path


def test_sentry_initializes_without_jinja2():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
sys.modules["jinja2"] = None
sys.modules["markupsafe"] = None

import sentry_sdk

sentry_sdk.init(dsn="https://public@example.invalid/1")
""",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_runtime_lockfile_excludes_jinja2():
    requirements = Path(__file__).parents[1] / "requirements.txt"

    assert not any(line.startswith("jinja2==") for line in requirements.read_text().splitlines())
