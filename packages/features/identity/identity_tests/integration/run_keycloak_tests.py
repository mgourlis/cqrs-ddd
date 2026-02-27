#!/usr/bin/env python3
"""Script to run Keycloak integration tests."""

import subprocess
import sys
from collections.abc import Sequence


def run_tests(args: Sequence[str] | None = None) -> int:
    """Run the integration tests."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/integration/",
        "-m",
        "integration",
        "-v",
    ]

    if args:
        cmd.extend(args)

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd="..")  # noqa: S603

    return result.returncode


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(run_tests(args))
