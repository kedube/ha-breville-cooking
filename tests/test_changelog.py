"""Tests for CHANGELOG.md and the script the Release workflow keeps it with."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "changelog.py"
spec = importlib.util.spec_from_file_location("changelog", SCRIPT_PATH)
changelog = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = changelog
spec.loader.exec_module(changelog)

INTRO = "# Changelog\n\nNotable changes. Add entries under **Unreleased**.\n\n"
HEADING_RE = re.compile(r"^## (.+)$", re.MULTILINE)


def test_rotates_unreleased_entries_and_leaves_a_fresh_heading() -> None:
    text = INTRO + "## Unreleased\n- **A fix.** Details.\n\n## 0.13 — 2026-11-03\n- Old.\n"

    updated, outcome = changelog.rotate_changelog(text, "0.14", "2026-11-17", ["ignored"])

    assert outcome == "rotated"
    assert updated == (
        INTRO
        + "## Unreleased\n\n## 0.14 — 2026-11-17\n- **A fix.** Details.\n\n"
        + "## 0.13 — 2026-11-03\n- Old.\n"
    )


@pytest.mark.parametrize("unreleased", ["", "## Unreleased\n\n"])
def test_lists_the_commits_when_nothing_was_written(unreleased: str) -> None:
    """A release is never left out of the changelog."""
    text = INTRO + unreleased + "## 0.13 — 2026-11-03\n- Old.\n"

    updated, outcome = changelog.rotate_changelog(
        text, "0.14", "2026-11-17", ["Fix the thing", "Update CI"]
    )

    assert outcome == "generated"
    assert updated == (
        INTRO
        + "## Unreleased\n\n## 0.14 — 2026-11-17\n- Fix the thing\n- Update CI\n\n"
        + "## 0.13 — 2026-11-03\n- Old.\n"
    )


def test_says_so_when_a_release_changed_nothing() -> None:
    updated, _ = changelog.rotate_changelog(INTRO, "0.14", "2026-11-17", [])
    assert updated.endswith("## Unreleased\n\n## 0.14 — 2026-11-17\n- No user-facing changes.\n")


def test_rotates_only_the_real_unreleased_heading() -> None:
    text = (
        "# Changelog\n\nSee ## Unreleased below.\n\n### Unreleased ideas\n- keep me\n\n"
        "## Unreleased\n- Real entry.\n\n## 0.13 — 2026-11-03\n- Old.\n"
    )

    updated, _ = changelog.rotate_changelog(text, "0.14", "2026-11-17", [])

    assert "See ## Unreleased below." in updated
    assert "### Unreleased ideas\n- keep me" in updated
    assert "## 0.14 — 2026-11-17\n- Real entry.\n" in updated


def test_finds_a_versions_section_and_not_a_longer_one() -> None:
    text = INTRO + "## 0.130 — 2027-01-01\n- Later.\n\n## 0.13 — 2026-11-03\n### Joule\n- Old.\n"
    assert changelog.changelog_section(text, "0.13") == "### Joule\n- Old."
    assert changelog.changelog_section(text, "0.12") == ""


def test_release_notes_link_to_the_docs_as_the_release_shipped_them() -> None:
    """On a release page, a relative link would resolve under /releases/tag/."""
    text = (
        "See [the API](docs/api.md#start-a-cook), [options](./README.md#options), "
        "[the issue](https://github.com/kedube/ha-breville-cooking/issues/1) and [below](#commits)."
    )
    assert changelog.pin_links(text, "kedube/ha-breville-cooking", "0.14") == (
        "See [the API](https://github.com/kedube/ha-breville-cooking/blob/0.14/docs/api.md#start-a-cook), "
        "[options](https://github.com/kedube/ha-breville-cooking/blob/0.14/README.md#options), "
        "[the issue](https://github.com/kedube/ha-breville-cooking/issues/1) and [below](#commits)."
    )


def test_previous_release_is_the_latest_other_tag() -> None:
    tags = ["0.09", "0.10", "0.99", "1.00", "0.14", "v2.00", "backup", "1.00-test"]
    assert changelog.previous_release(tags, "1.01") == "1.00"
    assert changelog.previous_release(tags, "1.00") == "0.99"
    assert changelog.previous_release(["0.14"], "0.14") is None


def test_release_commits_are_left_out() -> None:
    assert changelog.is_bookkeeping("Release 0.13")
    assert not changelog.is_bookkeeping("Release notes from the changelog")
    assert not changelog.is_bookkeeping("Fix Release 0.13's zip")


def test_release_notes() -> None:
    notes = changelog.release_notes(
        "0.14", "- **A fix.** See [the API](docs/api.md).", ["Fix the thing (abc1234)"], "0.13",
        "kedube/ha-breville-cooking",
    )
    assert notes == (
        "## Highlights\n\n- **A fix.** See "
        "[the API](https://github.com/kedube/ha-breville-cooking/blob/0.14/docs/api.md).\n\n"
        "## Commits\n\n- Fix the thing (abc1234)\n\n"
        "**Full Changelog**: https://github.com/kedube/ha-breville-cooking/compare/0.13...0.14"
    )
    assert changelog.release_notes("0.01", "", [], None, "o/r") == "Release 0.01."


def test_rotate_and_notes_from_the_command_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "CHANGELOG.md"
    path.write_text(INTRO + "## Unreleased\n- **A fix.**\n")
    assert changelog.main(["--changelog", str(path), "rotate", "0.14"]) == 0
    assert capsys.readouterr().out.strip() == "rotated"
    assert changelog.changelog_section(path.read_text(), "0.14") == "- **A fix.**"
    with pytest.raises(SystemExit):
        changelog.main(["--changelog", str(path), "rotate", "v0.14"])


# -- the changelog itself ------------------------------------------------------


def _changelog() -> str:
    return (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def _version_key(version: str) -> tuple[int, int]:
    major, minor = version.split(".")
    return int(major), int(minor)


def test_releases_have_sections_newest_first() -> None:
    """The workflow adds a section as it releases each version, so the newest is the manifest's.

    A major release skips versions (0.13 is followed by 1.00), so there are gaps.
    """
    manifest = json.loads((ROOT / "custom_components" / "breville_cooking" / "manifest.json").read_text())

    headings = HEADING_RE.findall(_changelog())
    assert headings[0] == "Unreleased"
    versions = []
    for heading in headings[1:]:
        match = re.fullmatch(r"(\d+\.\d\d) — (\d{4}-\d\d-\d\d)", heading)
        assert match, f"heading {heading!r} isn't '<version> — <date>'"
        versions.append(match[1])
    assert versions[0] == manifest["version"]
    assert versions[-1] == "0.01"
    assert versions == sorted(versions, key=_version_key, reverse=True)
    assert len(set(versions)) == len(versions)
    for version in versions:
        assert changelog.changelog_section(_changelog(), version), f"{version} has no entries"


def test_every_release_up_to_0_13_has_a_section() -> None:
    """Those were all minor releases, written up when the changelog began."""
    versions = set(re.findall(r"^## (\d+\.\d\d) — ", _changelog(), re.MULTILINE))
    assert {f"0.{n:02d}" for n in range(1, 14)} <= versions


def test_changelog_links_resolve() -> None:
    for target in changelog.RELATIVE_LINK_RE.findall(_changelog()):
        path = target.split("#", 1)[0]
        assert (ROOT / path).exists(), f"CHANGELOG.md links to missing {target}"
