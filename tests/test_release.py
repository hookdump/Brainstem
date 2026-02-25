from __future__ import annotations

from datetime import date

import pytest

from brainstem.release import (
    prepend_changelog_entry,
    render_changelog_entry,
    update_pyproject_version,
    validate_release_version,
)


def test_validate_release_version() -> None:
    validate_release_version("1.2.3")
    with pytest.raises(ValueError):
        validate_release_version("1.2")


def test_update_pyproject_version() -> None:
    text = '\n[project]\nname = "brainstem"\nversion = "0.1.0"\n'
    updated = update_pyproject_version(text, "0.2.0")
    assert 'version = "0.2.0"' in updated
    assert 'version = "0.1.0"' not in updated


def test_render_and_prepend_changelog_entry() -> None:
    entry = render_changelog_entry(
        version="0.2.0",
        changes=["Add release pipeline", "Add changelog generator"],
        release_date=date(2026, 2, 25),
    )
    assert "## 0.2.0 - 2026-02-25" in entry
    assert "- Add release pipeline" in entry

    existing = "# Changelog\n\n## 0.1.0 - 2026-02-24\n\n### Changes\n- Initial release\n"
    updated = prepend_changelog_entry(existing, entry)
    assert updated.startswith("# Changelog")
    assert updated.find("## 0.2.0 - 2026-02-25") < updated.find("## 0.1.0 - 2026-02-24")

