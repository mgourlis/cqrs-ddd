#!/usr/bin/env python3
"""Script to run Keycloak integration tests."""

import subprocess
import sys


def run_tests(args=None):
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
    result = subprocess.run(cmd, cwd="..")  # Run from tests/ directory parent

    return result.returncode


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(run_tests(args))
