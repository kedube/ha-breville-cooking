#!/usr/bin/env python3
"""Keep CHANGELOG.md and the GitHub release notes in step with each release.

Changes go under "## Unreleased" in CHANGELOG.md as they're made. The Release
workflow (.github/workflows/release.yml) then runs:

  python3 scripts/changelog.py rotate 0.14
      Turn "## Unreleased" into "## 0.14 — <today>", with a fresh, empty
      "## Unreleased" above it. If nothing was written under Unreleased, the
      section lists the commit subjects since the last release instead, so no
      release is missing from the changelog. Prints "rotated" or "generated".

  python3 scripts/changelog.py notes 0.14 release_notes.md
      Write the release notes: the version's changelog section as Highlights,
      the commits since the previous release, and a link comparing the two.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
DEFAULT_REPO = "kedube/ha-breville-cooking"

# Release tags are the bare version (scripts/bump_version.py), and the
# workflow's commit for one is "Release <version>".
RELEASE_TAG_RE = re.compile(r"(0|[1-9]\d*)\.\d\d")
RELEASE_COMMIT_RE = re.compile(r"Release (0|[1-9]\d*)\.\d\d")
# The heading on a line of its own, so prose that mentions it, or a deeper
# "### Unreleased" heading, is never taken for it.
UNRELEASED_RE = re.compile(r"^## Unreleased[ \t]*\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
FIRST_SECTION_RE = re.compile(r"^## ", re.MULTILINE)
# A link to a file in the repository (docs/api.md#…, README.md#options). On a
# release page it would resolve under /releases/tag/, so the notes pin it.
RELATIVE_LINK_RE = re.compile(r"\]\((?!https?://|mailto:|#)([^)\s]+)\)")
NO_CHANGES = "- No user-facing changes."


def rotate_changelog(
    text: str, version: str, today: str, commit_subjects: list[str]
) -> tuple[str, str]:
    """Return the changelog with a section for the version, and "rotated" or "generated".

    commit_subjects are used only when the Unreleased section is empty.
    """
    heading = f"## {version} — {today}"
    match = UNRELEASED_RE.search(text)
    if match is not None and match.group(1).strip():
        body = match.group(1).strip("\n")
        outcome = "rotated"
    else:
        body = "\n".join(f"- {subject}" for subject in commit_subjects) or NO_CHANGES
        outcome = "generated"

    section = f"## Unreleased\n\n{heading}\n{body}\n\n"
    if match is not None:
        return text[: match.start()] + section + text[match.end() :], outcome
    first = FIRST_SECTION_RE.search(text)
    if first is None:
        return text.rstrip("\n") + "\n\n" + section.rstrip("\n") + "\n", outcome
    return text[: first.start()] + section + text[first.start() :], outcome


def changelog_section(text: str, version: str) -> str:
    """The body of a version's section, or "" if there's none."""
    match = re.search(
        rf"^## {re.escape(version)} [^\n]*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    return match.group(1).strip() if match else ""


def pin_links(markdown: str, repo: str, ref: str) -> str:
    """Point links to repository files at the release's tag, so each release's
    notes show the docs as that version shipped them."""

    def pin(match: re.Match[str]) -> str:
        path = re.sub(r"^\./", "", match.group(1))
        return f"](https://github.com/{repo}/blob/{ref}/{path})"

    return RELATIVE_LINK_RE.sub(pin, markdown)


def previous_release(tags: list[str], version: str) -> str | None:
    """The latest release tag other than the version being released."""
    releases = [tag for tag in tags if RELEASE_TAG_RE.fullmatch(tag) and tag != version]
    return max(releases, key=lambda tag: tuple(int(part) for part in tag.split(".")), default=None)


def is_bookkeeping(subject: str) -> bool:
    """A release workflow commit, which says nothing about the changes."""
    return bool(RELEASE_COMMIT_RE.fullmatch(subject))


def release_notes(version: str, highlights: str, commits: list[str], previous: str | None, repo: str) -> str:
    sections = []
    if highlights:
        sections.append(f"## Highlights\n\n{pin_links(highlights, repo, version)}")
    if commits:
        sections.append("## Commits\n\n" + "\n".join(f"- {commit}" for commit in commits))
    if previous:
        sections.append(f"**Full Changelog**: https://github.com/{repo}/compare/{previous}...{version}")
    return "\n\n".join(sections) if sections else f"Release {version}."


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def _commits_since(previous: str | None) -> list[tuple[str, str]]:
    """The subject and short hash of each commit since the previous release, newest first."""
    log_range = f"{previous}..HEAD" if previous else "HEAD"
    commits = []
    for line in _git("log", "--no-merges", "--format=%h%x09%s", log_range).splitlines():
        short, _, subject = line.partition("\t")
        if subject and not is_bookkeeping(subject):
            commits.append((subject, short))
    return commits


def rotate(version: str, path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = UNRELEASED_RE.search(text)
    subjects: list[str] = []
    if match is None or not match.group(1).strip():
        previous = previous_release(_git("tag").splitlines(), version)
        subjects = [subject for subject, _ in _commits_since(previous)]
    updated, outcome = rotate_changelog(text, version, datetime.date.today().isoformat(), subjects)
    path.write_text(updated, encoding="utf-8")
    return outcome


def notes(version: str, path: Path) -> str:
    previous = previous_release(_git("tag").splitlines(), version)
    highlights = changelog_section(path.read_text(encoding="utf-8"), version) if path.exists() else ""
    repo = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO)
    commits = [f"{subject} ({short})" for subject, short in _commits_since(previous)]
    return release_notes(version, highlights, commits, previous, repo)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--changelog", type=Path, default=CHANGELOG, help="the changelog to use")
    sub = parser.add_subparsers(dest="command", required=True)
    rotate_cmd = sub.add_parser("rotate", help="make the Unreleased section the version's")
    rotate_cmd.add_argument("version")
    notes_cmd = sub.add_parser("notes", help="write the version's release notes")
    notes_cmd.add_argument("version")
    notes_cmd.add_argument("output", type=Path, nargs="?", help="where to write them (default: print)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if not RELEASE_TAG_RE.fullmatch(args.version):
        raise SystemExit(f"{args.version!r} isn't a version like 0.14")
    if args.command == "rotate":
        print(rotate(args.version, args.changelog))
        return 0
    body = notes(args.version, args.changelog)
    if args.output:
        args.output.write_text(body + "\n", encoding="utf-8")
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
