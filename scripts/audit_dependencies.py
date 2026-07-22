from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

REPORT_PATH = Path("pip-audit-report.json")
REQUIREMENTS_PATH = Path("requirements.txt")


@dataclass(frozen=True)
class AuditException:
    package: str
    version: str
    expires: date
    rationale: str


STARLETTE_EXCEPTION_EXPIRY = date(2026, 10, 31)
AUDIT_EXCEPTIONS = {
    "PYSEC-2026-161": AuditException(
        package="starlette",
        version="0.52.1",
        expires=STARLETTE_EXCEPTION_EXPIRY,
        rationale="TrustedHostMiddleware validates production Host headers.",
    ),
    "PYSEC-2026-248": AuditException(
        package="starlette",
        version="0.52.1",
        expires=STARLETTE_EXCEPTION_EXPIRY,
        rationale="The app does not use request.url for security decisions.",
    ),
    "PYSEC-2026-249": AuditException(
        package="starlette",
        version="0.52.1",
        expires=STARLETTE_EXCEPTION_EXPIRY,
        rationale="All request bodies are JSON; request.form() is not used.",
    ),
    "PYSEC-2026-2280": AuditException(
        package="starlette",
        version="0.52.1",
        expires=STARLETTE_EXCEPTION_EXPIRY,
        rationale="The app does not register Starlette HTTPEndpoint subclasses.",
    ),
    "PYSEC-2026-2281": AuditException(
        package="starlette",
        version="0.52.1",
        expires=STARLETTE_EXCEPTION_EXPIRY,
        rationale="The Linux container does not use Starlette StaticFiles.",
    ),
}


def evaluate_report(
    report: dict[str, Any], *, today: date
) -> tuple[list[str], list[str]]:
    accepted: list[str] = []
    rejected: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    for dependency in report.get("dependencies", []):
        package = str(dependency.get("name", "")).lower()
        version = str(dependency.get("version", ""))
        for vulnerability in dependency.get("vulns", []):
            vulnerability_id = str(vulnerability.get("id", ""))
            finding = (package, version, vulnerability_id)
            if finding in seen:
                continue
            seen.add(finding)

            exception = AUDIT_EXCEPTIONS.get(vulnerability_id)
            if exception is None:
                rejected.append(
                    f"{package}=={version}: {vulnerability_id} is not allowlisted"
                )
                continue
            if package != exception.package or version != exception.version:
                rejected.append(
                    f"{package}=={version}: {vulnerability_id} does not match its "
                    f"allowlisted {exception.package}=={exception.version}"
                )
                continue
            if today > exception.expires:
                rejected.append(
                    f"{package}=={version}: {vulnerability_id} exception expired "
                    f"on {exception.expires.isoformat()}"
                )
                continue
            accepted.append(
                f"{package}=={version}: {vulnerability_id} accepted until "
                f"{exception.expires.isoformat()} ({exception.rationale})"
            )

    return accepted, rejected


def run_audit() -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "-r",
            str(REQUIREMENTS_PATH),
            "-f",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in {0, 1}:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"pip-audit failed with exit code {result.returncode}")
    if not result.stdout.strip():
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("pip-audit did not produce a JSON report")
    report = json.loads(result.stdout)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = run_audit()
    accepted, rejected = evaluate_report(report, today=date.today())
    for finding in accepted:
        print(f"ACCEPTED: {finding}")
    for finding in rejected:
        print(f"REJECTED: {finding}", file=sys.stderr)
    if rejected:
        return 1
    print(f"Dependency audit passed with {len(accepted)} temporary exception(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
