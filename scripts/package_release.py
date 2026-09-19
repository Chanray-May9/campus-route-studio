#!/usr/bin/env python3
"""Create release archives without including local build products or secrets."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", "__pycache__", ".pytest_cache", ".wrangler", "node_modules", "build", "dist", "backend"}


def source_files():
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if path.is_file() and not any(part in EXCLUDED for part in relative.parts):
            if path.suffix not in {".pyc", ".apk", ".keystore", ".jks"}:
                yield path, relative


def archive(target: Path, root_name: str, helper: Path | None = None) -> None:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path, relative in source_files():
            output.write(path, Path(root_name) / relative)
        if helper:
            output.write(helper, Path(root_name) / "campus-route-helper.apk")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--android-build", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    mobile = args.android_build / "CampusRoute-Mobile.apk"
    helper = args.android_build / "campus-route-helper.apk"
    shutil.copy2(mobile, args.output / mobile.name)
    shutil.copy2(helper, args.output / helper.name)
    archive(args.output / "CampusRouteStudio-Windows.zip", "CampusRouteStudio", helper)
    archive(args.output / "CampusRoute-Source.zip", "campus-route-studio")


if __name__ == "__main__":
    main()
