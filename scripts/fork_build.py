#!/usr/bin/env python3
"""Build the fork's HACS archive without touching upstream-owned files.

The committed manifest keeps upstream's ``"version": "0.0.0"`` placeholder and
the committed translations stay identical to upstream. This script copies the
integration, merges the fork strings (see ``quirk_translations.py``), writes
the release version into the copied manifest and zips the result.

    python scripts/fork_build.py --next-version patch   # prints e.g. 2026.9.6
    python scripts/fork_build.py --version 2026.9.6     # writes dist/echonet_lite.zip
    python scripts/fork_build.py --requirement          # prints the pyhems pin
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "echonet_lite"
_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import quirk_translations  # noqa: E402


def _manifest() -> dict:
    return json.loads((INTEGRATION / "manifest.json").read_text(encoding="utf-8"))


def requirement() -> str:
    """Return the pyhems requirement pinned by the manifest."""
    return next(r for r in _manifest()["requirements"] if r.startswith("pyhems"))


def next_version(bump: str) -> str:
    """Return the next fork version after the highest ``vX.Y.Z`` tag."""
    tags = subprocess.check_output(
        ["git", "tag", "--list", "v*"], cwd=ROOT, text=True
    ).split()
    versions = [
        tuple(map(int, match.groups()))
        for tag in tags
        if (match := _VERSION.fullmatch(tag.removeprefix("v")))
    ]
    if not versions:
        raise SystemExit("No vX.Y.Z tag found; pass --version explicitly")
    major, minor, patch = max(versions)
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _tracked_files() -> list[Path]:
    """Return committed integration files (ignores local, untracked output)."""
    listed = subprocess.check_output(
        ["git", "ls-files", "-z", "--", str(INTEGRATION.relative_to(ROOT))],
        cwd=ROOT,
    ).split(b"\0")
    files = []
    for raw in filter(None, listed):
        path = ROOT / raw.decode()
        relative = path.relative_to(INTEGRATION)
        # quirks/translations/ is build input, merged into translations/.
        if relative.parts[:2] == ("quirks", "translations"):
            continue
        if "__pycache__" in relative.parts:
            continue
        files.append(path)
    return files


def build(version: str, output: Path) -> None:
    """Write the release archive for ``version`` to ``output``."""
    if not _VERSION.fullmatch(version):
        raise SystemExit(f"Invalid version {version!r}")
    with tempfile.TemporaryDirectory() as temp:
        staging = Path(temp) / "echonet_lite"
        for source in _tracked_files():
            target = staging / source.relative_to(INTEGRATION)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        quirk_translations.write(staging)

        manifest_path = staging / "manifest.json"
        text, count = re.subn(
            r'("version"\s*:\s*)"0\.0\.0"',
            lambda match: f'{match.group(1)}"{version}"',
            manifest_path.read_text(encoding="utf-8"),
        )
        if count != 1:
            raise SystemExit('manifest.json must contain "version": "0.0.0"')
        manifest_path.write_text(text, encoding="utf-8")
        shutil.copyfile(ROOT / "LICENSE", staging / "LICENSE")

        output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(p for p in staging.rglob("*") if p.is_file()):
                info = ZipInfo(
                    path.relative_to(staging).as_posix(), (1980, 1, 1, 0, 0, 0)
                )
                info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
    print(f"Built {output} ({version})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--version", help="release version, e.g. 2026.9.6")
    group.add_argument("--next-version", choices=("major", "minor", "patch"))
    group.add_argument("--requirement", action="store_true")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "dist" / "echonet_lite.zip"
    )
    args = parser.parse_args()
    if args.requirement:
        print(requirement())
    elif args.next_version:
        print(next_version(args.next_version))
    else:
        build(args.version, args.output)


if __name__ == "__main__":
    main()
