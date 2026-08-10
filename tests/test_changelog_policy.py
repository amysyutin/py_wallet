from pathlib import Path
import subprocess

import pytest

from scripts.check_changelog import (
    ChangelogPolicyError,
    changed_paths,
    require_changelog,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def test_policy_rejects_pull_request_without_changelog():
    with pytest.raises(ChangelogPolicyError, match="CHANGELOG.md must change"):
        require_changelog({"app/main.py", "tests/test_api.py"})


def test_policy_accepts_changelog_with_other_changes():
    require_changelog({"CHANGELOG.md", "app/main.py"})


def test_changed_paths_uses_pull_request_three_dot_diff(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n")
    subprocess.run(["git", "add", "CHANGELOG.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    base_ref = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    (tmp_path / "app.py").write_text("enabled = True\n")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "feature"], cwd=tmp_path, check=True)

    assert changed_paths(base_ref, repo_root=tmp_path) == frozenset({"app.py"})


def test_ci_has_blocking_changelog_job_with_full_history():
    workflow = CI_WORKFLOW.read_text()

    assert "  changelog:\n" in workflow
    assert "fetch-depth: 0" in workflow
    assert "python scripts/check_changelog.py" in workflow
    assert "${{ github.event.pull_request.base.sha }}" in workflow
    assert "needs: [changelog, test, security]" in workflow
