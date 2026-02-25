"""Release automation helpers."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
PYPROJECT_VERSION_PATTERN = re.compile(r'(?m)^version = "([^"]+)"$')


def validate_release_version(version: str) -> None:
    if not VERSION_PATTERN.match(version):
        raise ValueError("version must match MAJOR.MINOR.PATCH (e.g. 0.2.0)")


def update_pyproject_version(pyproject_text: str, version: str) -> str:
    validate_release_version(version)
    if not PYPROJECT_VERSION_PATTERN.search(pyproject_text):
        raise ValueError("unable to find version field in pyproject.toml")
    return PYPROJECT_VERSION_PATTERN.sub(f'version = "{version}"', pyproject_text, count=1)


def changelog_heading(version: str, release_date: date | None = None) -> str:
    validate_release_version(version)
    effective_date = release_date if release_date is not None else datetime.now(UTC).date()
    return f"## {version} - {effective_date.isoformat()}"


def render_changelog_entry(
    *,
    version: str,
    changes: list[str],
    release_date: date | None = None,
) -> str:
    header = changelog_heading(version, release_date)
    lines = [header, "", "### Changes"]
    if changes:
        lines.extend(f"- {change}" for change in changes)
    else:
        lines.append("- No notable changes recorded.")
    lines.append("")
    return "\n".join(lines)


def prepend_changelog_entry(existing: str, entry: str) -> str:
    normalized_existing = existing.strip()
    if not normalized_existing:
        return "# Changelog\n\n" + entry.strip() + "\n"

    if normalized_existing.startswith("# Changelog"):
        without_title = normalized_existing[len("# Changelog") :].lstrip("\n")
        return "# Changelog\n\n" + entry.strip() + "\n\n" + without_title.strip() + "\n"
    return "# Changelog\n\n" + entry.strip() + "\n\n" + normalized_existing + "\n"

