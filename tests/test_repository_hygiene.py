from pathlib import Path
import subprocess

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATED_ARTIFACTS = (
    "pip-audit-report.json",
    "bandit-report.json",
    ".DS_Store",
)


@pytest.mark.parametrize("artifact", GENERATED_ARTIFACTS)
def test_generated_artifacts_are_ignored_at_any_depth(artifact: str):
    for relative_path in (artifact, f"reports/{artifact}"):
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", relative_path],
            cwd=REPO_ROOT,
            check=False,
        )

        assert result.returncode == 0, relative_path


def test_generated_artifacts_are_not_tracked():
    result = subprocess.run(
        ["git", "ls-files", "--cached"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )

    tracked_artifacts = [
        path
        for path in result.stdout.splitlines()
        if Path(path).name in GENERATED_ARTIFACTS
    ]
    assert tracked_artifacts == []
