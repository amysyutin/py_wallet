#!/usr/bin/env python3
"""Require every pull request to document its change in CHANGELOG.md."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path
import subprocess

CHANGELOG_PATH = "CHANGELOG.md"


class ChangelogPolicyError(RuntimeError):
    """Raised when the branch violates the changelog policy."""


def changed_paths(
    base_ref: str,
    *,
    head_ref: str = "HEAD",
    repo_root: Path | None = None,
) -> frozenset[str]:
    root = repo_root or Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "git diff failed"
        raise ChangelogPolicyError(detail)
    return frozenset(line for line in result.stdout.splitlines() if line)


def require_changelog(paths: Iterable[str]) -> None:
    changed = frozenset(paths)
    if changed and CHANGELOG_PATH not in changed:
        raise ChangelogPolicyError(
            "CHANGELOG.md must change in every pull request. "
            "Add a bullet under [Unreleased]."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-ref",
        required=True,
        help="Base commit or ref used for the three-dot pull-request diff.",
    )
    parser.add_argument("--head-ref", default="HEAD")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        paths = changed_paths(args.base_ref, head_ref=args.head_ref)
        require_changelog(paths)
    except ChangelogPolicyError as exc:
        print(f"Changelog policy failed: {exc}")
        return 1
    print("Changelog policy passed: CHANGELOG.md is included in the diff.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
