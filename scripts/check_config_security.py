"""CI gate: JWT config security checks for py_wallet."""

from __future__ import annotations

import os
import secrets
import subprocess
import sys

_CONFIG_ENV_KEYS = frozenset({"APP_ENV", "JWT_SECRET", "JWT_ALG"})


def run_settings(env: dict[str, str]) -> tuple[int, str]:
    code = "\n".join(
        [
            "from app.core.config import Settings",
            "Settings(_env_file=None)",
            "print('ok')",
        ]
    )
    base_env = {k: v for k, v in os.environ.items() if k not in _CONFIG_ENV_KEYS}
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**base_env, **env},
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    return result.returncode, output


def expect_fail(
    name: str,
    env: dict[str, str],
    *,
    forbidden_in_output: str | None = None,
) -> None:
    code, output = run_settings(env)
    if code == 0:
        print(f"FAIL: {name} — expected ValidationError")
        sys.exit(1)
    if forbidden_in_output and forbidden_in_output in output:
        print(f"FAIL: {name} — secret leaked in error output")
        sys.exit(1)
    print(f"OK: {name}")


def expect_ok(name: str, env: dict[str, str]) -> None:
    code, output = run_settings(env)
    if code != 0:
        print(f"FAIL: {name} — expected success")
        print(output)
        sys.exit(1)
    print(f"OK: {name}")


def main() -> None:
    valid = secrets.token_urlsafe(48)
    short_secret = "my-short-secret-value"

    expect_fail("production + missing JWT_SECRET", {"APP_ENV": "production"})
    expect_fail(
        "production + dev-insecure-change-me",
        {"APP_ENV": "production", "JWT_SECRET": "dev-insecure-change-me"},
    )
    expect_fail(
        "production + ci-test-secret",
        {"APP_ENV": "production", "JWT_SECRET": "ci-test-secret"},
    )
    expect_fail(
        "production + short secret",
        {"APP_ENV": "production", "JWT_SECRET": "short"},
    )
    expect_fail(
        "production + JWT_ALG=none",
        {"APP_ENV": "production", "JWT_SECRET": valid, "JWT_ALG": "none"},
    )
    expect_fail(
        "production + short secret omits value in error output",
        {"APP_ENV": "production", "JWT_SECRET": short_secret},
        forbidden_in_output=short_secret,
    )
    expect_ok(
        "production + valid generated secret",
        {"APP_ENV": "production", "JWT_SECRET": valid},
    )

    expect_fail("staging + missing JWT_SECRET", {"APP_ENV": "staging"})
    expect_fail(
        "staging + dev-insecure-change-me",
        {"APP_ENV": "staging", "JWT_SECRET": "dev-insecure-change-me"},
    )
    expect_ok(
        "staging + valid generated secret",
        {"APP_ENV": "staging", "JWT_SECRET": valid},
    )

    expect_ok("test + default (no JWT_SECRET)", {"APP_ENV": "test"})
    expect_ok(
        "test + ci-test-secret",
        {"APP_ENV": "test", "JWT_SECRET": "ci-test-secret"},
    )

    print("All config security checks passed.")


if __name__ == "__main__":
    main()
