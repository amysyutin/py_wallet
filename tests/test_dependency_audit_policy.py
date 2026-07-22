from datetime import date

from scripts.audit_dependencies import evaluate_report


def _report(package: str, version: str, vulnerability_id: str) -> dict:
    return {
        "dependencies": [
            {
                "name": package,
                "version": version,
                "vulns": [{"id": vulnerability_id}],
            }
        ]
    }


def test_current_starlette_exception_is_accepted():
    accepted, rejected = evaluate_report(
        _report("starlette", "0.52.1", "PYSEC-2026-161"),
        today=date(2026, 7, 22),
    )

    assert len(accepted) == 1
    assert rejected == []


def test_new_vulnerability_is_rejected():
    accepted, rejected = evaluate_report(
        _report("example", "1.0.0", "CVE-2099-0001"),
        today=date(2026, 7, 22),
    )

    assert accepted == []
    assert rejected == ["example==1.0.0: CVE-2099-0001 is not allowlisted"]


def test_exception_is_version_bounded_and_expires():
    _, wrong_version = evaluate_report(
        _report("starlette", "0.52.2", "PYSEC-2026-161"),
        today=date(2026, 7, 22),
    )
    _, expired = evaluate_report(
        _report("starlette", "0.52.1", "PYSEC-2026-161"),
        today=date(2026, 11, 1),
    )

    assert "does not match" in wrong_version[0]
    assert "exception expired" in expired[0]
