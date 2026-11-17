#!/usr/bin/env python3
"""Work out the next release version.

Versions have two decimal places. A minor release goes up by 0.01 (0.13 to
0.14, ... 0.99 to 1.00), and a major release to the next whole number (0.13 to
1.00, 1.05 to 2.00). The version lives in the integration's manifest.json, and
release tags use it as is, with no "v" in front.

  python3 scripts/bump_version.py                       # print the next minor version
  python3 scripts/bump_version.py --bump major          # or the next major one
  python3 scripts/bump_version.py --bump major --write  # and save it in manifest.json

The Release workflow (.github/workflows/release.yml) runs this.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MANIFEST = Path(__file__).resolve().parent.parent / "custom_components" / "breville_cooking" / "manifest.json"
VERSION_RE = re.compile(r"(0|[1-9]\d*)\.(\d\d)")
MANIFEST_VERSION_RE = re.compile(r'"version"\s*:\s*"[^"]*"')


def parse_version(version: str) -> int:
    """Return a version as a count of hundredths: "1.05" is 105."""
    match = VERSION_RE.fullmatch(version)
    if match is None:
        raise ValueError(f"{version!r} isn't a version like 0.01")
    return int(match[1]) * 100 + int(match[2])


def format_version(hundredths: int) -> str:
    """Return the version for a count of hundredths: 105 is "1.05"."""
    major, minor = divmod(hundredths, 100)
    return f"{major}.{minor:02d}"


BUMPS = ("minor", "major")


def next_version(version: str, bump: str = "minor") -> str:
    """Return the version after this one.

    Minor: "0.13" is followed by "0.14", and "0.99" by "1.00".
    Major: "0.13" is followed by "1.00", and "1.05" by "2.00".
    """
    hundredths = parse_version(version)
    if bump == "minor":
        return format_version(hundredths + 1)
    if bump == "major":
        return format_version((hundredths // 100 + 1) * 100)
    raise ValueError(f"{bump!r} isn't one of {', '.join(BUMPS)}")


def write_version(path: Path, version: str) -> None:
    """Change only the version in manifest.json, keeping its formatting."""
    text = path.read_text()
    manifest = json.loads(text)
    updated, count = MANIFEST_VERSION_RE.subn(f'"version": "{version}"', text)
    if count != 1 or json.loads(updated) != {**manifest, "version": version}:
        raise SystemExit(f"{path}: couldn't find the version to change")
    path.write_text(updated)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bump", choices=BUMPS, default="minor", help="minor (default) or major")
    parser.add_argument("--write", action="store_true", help="save the new version in manifest.json")
    parser.add_argument("--manifest", type=Path, default=MANIFEST, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    current = json.loads(args.manifest.read_text()).get("version", "")
    try:
        version = next_version(current, args.bump)
    except ValueError as err:
        raise SystemExit(f"{args.manifest}: {err}") from None
    if args.write:
        write_version(args.manifest, version)
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
