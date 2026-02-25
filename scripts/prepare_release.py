#!/usr/bin/env python3
"""Prepare release artifacts: version bump + changelog + release notes."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from brainstem.release import (
    prepend_changelog_entry,
    render_changelog_entry,
    update_pyproject_version,
    validate_release_version,
)


def _run_git(args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _last_tag() -> str | None:
    try:
        tag = _run_git(["describe", "--tags", "--abbrev=0"])
    except subprocess.CalledProcessError:
        return None
    return tag or None


def _collect_changes() -> list[str]:
    last_tag = _last_tag()
    rev_range = f"{last_tag}..HEAD" if last_tag else "HEAD"
    output = _run_git(["log", "--pretty=format:%s", rev_range])
    changes = [line.strip() for line in output.splitlines() if line.strip()]
    return changes[:200]


def run(args: argparse.Namespace) -> int:
    validate_release_version(args.version)

    pyproject_path = Path(args.pyproject_path)
    changelog_path = Path(args.changelog_path)
    notes_path = Path(args.notes_path)

    pyproject_original = pyproject_path.read_text(encoding="utf-8")
    pyproject_updated = update_pyproject_version(pyproject_original, args.version)
    pyproject_path.write_text(pyproject_updated, encoding="utf-8")

    existing_changelog = (
        changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else ""
    )
    changes = _collect_changes()
    entry = render_changelog_entry(version=args.version, changes=changes)
    updated_changelog = prepend_changelog_entry(existing_changelog, entry)
    changelog_path.write_text(updated_changelog, encoding="utf-8")

    notes_path.write_text(entry, encoding="utf-8")

    print(f"Prepared release artifacts for v{args.version}")
    print(f"Updated: {pyproject_path}")
    print(f"Updated: {changelog_path}")
    print(f"Wrote notes: {notes_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare Brainstem release artifacts.")
    parser.add_argument("--version", required=True, help="Release version (MAJOR.MINOR.PATCH)")
    parser.add_argument("--pyproject-path", default="pyproject.toml")
    parser.add_argument("--changelog-path", default="CHANGELOG.md")
    parser.add_argument("--notes-path", default=".release-notes.md")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as exc:
        print(f"Release preparation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

