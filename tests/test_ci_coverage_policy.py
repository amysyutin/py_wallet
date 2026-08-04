from configparser import ConfigParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOWS = (
    REPO_ROOT / ".github" / "workflows" / "ci.yml",
    REPO_ROOT / ".github" / "workflows" / "main-build.yml",
)


def test_coverage_baseline_is_an_explicit_app_ratchet():
    config = ConfigParser()
    config.read(REPO_ROOT / ".coveragerc")

    assert config.get("run", "source").split() == ["app"]
    assert config.getint("report", "fail_under") == 74
    assert config.getboolean("report", "show_missing") is True


def test_ci_test_jobs_enforce_the_shared_coverage_policy():
    for workflow in CI_WORKFLOWS:
        contents = workflow.read_text()

        assert "--cov --cov-report=term-missing" in contents, workflow
        assert "--cov-fail-under" not in contents, workflow


def test_pytest_cov_is_pinned_for_reproducible_ci():
    requirements = (REPO_ROOT / "requirements-dev.txt").read_text().splitlines()

    assert "pytest-cov==7.1.0" in requirements
