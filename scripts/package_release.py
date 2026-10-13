#!/usr/bin/env python3
"""Create release archives without including local build products or secrets."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", "__pycache__", ".pytest_cache", ".wrangler", "node_modules", "build", "dist", "backend"}


def source_files():
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode('utf-8').split('\0')
    for name in sorted(set(names)):
        if not name:
            continue
        relative = Path(name)
        path = ROOT / relative
        if path.is_file() and not any(part in EXCLUDED for part in relative.parts) and path.suffix not in {'.pyc', '.apk', '.keystore', '.jks'}:
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
    parser.add_argument("--windows-build", type=Path, required=True, help='Directory produced by build_windows.py')
    parser.add_argument('--skip-mobile', action='store_true', help='Package Windows only')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    mobile = args.android_build / "CampusRoute-Mobile.apk"
    helper = args.android_build / "campus-route-helper.apk"
    if not args.skip_mobile:
        shutil.copy2(mobile, args.output / mobile.name)
    shutil.copy2(helper, args.output / helper.name)
    for pattern in ('CampusRouteStudio-Windows-Setup-*.exe', 'CampusRouteStudio-Windows.zip'):
        for source in args.windows_build.glob(pattern):
            if source.resolve() != (args.output / source.name).resolve():
                shutil.copy2(source, args.output / source.name)
    archive(args.output / "CampusRoute-Source.zip", "campus-route-studio")


if __name__ == "__main__":
    main()
