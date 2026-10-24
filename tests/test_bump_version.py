"""Tests for the release version script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from awesomeversion import AwesomeVersion, AwesomeVersionStrategy

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "bump_version.py"
spec = importlib.util.spec_from_file_location("bump_version", SCRIPT_PATH)
bump_version = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bump_version
spec.loader.exec_module(bump_version)


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("0.00", "0.01"),
        ("0.01", "0.02"),
        ("0.09", "0.10"),
        ("0.10", "0.11"),
        ("0.99", "1.00"),
        ("1.00", "1.01"),
        ("9.99", "10.00"),
    ],
)
def test_next_version(version: str, expected: str) -> None:
    assert bump_version.next_version(version) == expected


@pytest.mark.parametrize("version", ["v0.01", "0.1", "0.001", "0.1.0", "01.00", "1", ""])
def test_rejects_other_formats(version: str) -> None:
    with pytest.raises(ValueError):
        bump_version.parse_version(version)


def test_manifest_version_can_be_bumped() -> None:
    manifest = json.loads(bump_version.MANIFEST.read_text())
    bump_version.parse_version(manifest["version"])


def test_versions_load_and_sort_in_home_assistant() -> None:
    """Home Assistant accepts the versions, and HACS sees each as newer."""
    versions = ["0.00", "0.01", "0.09", "0.10", "0.99", "1.00", "1.01", "9.99", "10.00"]
    for version in versions:
        # The check Home Assistant's loader makes before loading a custom integration.
        AwesomeVersion(
            version,
            ensure_strategy=[
                AwesomeVersionStrategy.CALVER,
                AwesomeVersionStrategy.SEMVER,
                AwesomeVersionStrategy.SIMPLEVER,
                AwesomeVersionStrategy.BUILDVER,
                AwesomeVersionStrategy.PEP440,
            ],
        )
    for older, newer in zip(versions, versions[1:]):
        assert AwesomeVersion(newer) > AwesomeVersion(older)


def test_write_changes_only_the_version(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    original = bump_version.MANIFEST.read_text()
    current = json.loads(original)["version"]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(original.replace(f'"version": "{current}"', '"version": "0.99"'))

    assert bump_version.main(["--manifest", str(manifest), "--write"]) == 0

    assert capsys.readouterr().out == "1.00\n"
    assert manifest.read_text() == original.replace(f'"version": "{current}"', '"version": "1.00"')


def test_print_only_leaves_manifest_alone(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"domain": "breville_cooking", "version": "0.04"}\n')

    bump_version.main(["--manifest", str(manifest)])

    assert capsys.readouterr().out == "0.05\n"
    assert json.loads(manifest.read_text())["version"] == "0.04"


def test_bad_manifest_version_fails(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"domain": "breville_cooking", "version": "0.1.0"}\n')

    with pytest.raises(SystemExit, match="isn't a version like 0.01"):
        bump_version.main(["--manifest", str(manifest), "--write"])
    assert json.loads(manifest.read_text())["version"] == "0.1.0"
