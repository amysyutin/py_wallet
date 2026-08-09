from pathlib import Path
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOWS = (
    REPO_ROOT / ".github" / "workflows" / "ci.yml",
    REPO_ROOT / ".github" / "workflows" / "main-build.yml",
)


def test_mypy_scope_is_incremental_and_strict():
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["tool"]["mypy"]

    assert config["files"] == ["app/core", "app/services"]
    assert config["follow_imports"] == "silent"
    assert config["python_version"] == "3.11"
    assert config["disallow_untyped_defs"] is True
    assert config["no_implicit_optional"] is True
    assert config["warn_unused_ignores"] is True
    assert "ignore_errors" not in config


def test_ci_test_jobs_run_mypy():
    for workflow in CI_WORKFLOWS:
        contents = workflow.read_text()

        assert "- name: Type check\n        run: mypy" in contents, workflow


def test_mypy_is_pinned_for_reproducible_ci():
    requirements = (REPO_ROOT / "requirements-dev.txt").read_text().splitlines()

    assert "mypy==2.3.0" in requirements
