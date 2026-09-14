#!/usr/bin/env python3
"""Build the Android helper using an installed Android SDK and JDK, without Gradle.

Generates a local development signing key inside ignored build/. Do not distribute
that key. The resulting APK is for direct installation, not a Play Store release.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str | Path]) -> None:
    command = [str(part) for part in args]
    completed = subprocess.run(command, text=True, encoding="utf-8", errors="replace",
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if completed.returncode:
        raise RuntimeError(f"{Path(command[0]).name} failed:\n{completed.stdout}")
    if completed.stdout.strip():
        print(completed.stdout.strip())


def version(path: Path) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", path.name))


def discover_sdk(explicit: str | None) -> Path:
    candidates = [explicit, os.environ.get("ANDROID_SDK_ROOT"), os.environ.get("ANDROID_HOME")]
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(str(Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk"))
    candidates.extend([str(Path.home() / "Android" / "Sdk"), str(Path.home() / "Library" / "Android" / "sdk")])
    for candidate in candidates:
        if candidate and (Path(candidate) / "platforms").is_dir():
            return Path(candidate).resolve()
    raise RuntimeError("Android SDK not found. Set ANDROID_SDK_ROOT or pass --sdk.")


def jdk_tool(name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    if os.environ.get("JAVA_HOME"):
        candidate = Path(os.environ["JAVA_HOME"]) / "bin" / (name + suffix)
        if candidate.is_file():
            return candidate
    found = shutil.which(name)
    if found:
        return Path(found)
    raise RuntimeError(f"JDK tool {name} not found; install JDK 17+ and set JAVA_HOME or PATH.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", help="Android SDK path (API 35+ and build-tools 35+)")
    parser.add_argument("--build-dir", help="Override build output directory (default: repository build/)")
    parser.add_argument('--source-dir', help='Android source directory (default: android/)')
    parser.add_argument('--apk-name', default='campus-route-helper.apk')
    args = parser.parse_args()
    source = Path(args.source_dir).resolve() if args.source_dir else ROOT / 'android'
    sdk = discover_sdk(args.sdk)
    platforms = sorted((p for p in (sdk / "platforms").glob("android-*") if version(p) >= (35,)), key=version)
    build_tools = sorted((p for p in (sdk / "build-tools").iterdir() if p.is_dir() and version(p) >= (35,)), key=version)
    if not platforms or not build_tools:
        raise RuntimeError("Install Android SDK platform API 35+ and build-tools 35+.")
    platform = platforms[-1] / "android.jar"
    tools = build_tools[-1]
    java, javac, keytool = (jdk_tool(name) for name in ("java", "javac", "keytool"))
    suffix = ".exe" if os.name == "nt" else ""
    output = Path(args.build_dir).resolve() if args.build_dir else ROOT / "build"
    output.mkdir(parents=True, exist_ok=True)
    key = output / "android-helper-debug.keystore"
    if not key.exists():
        run([keytool, "-genkeypair", "-keystore", key, "-storepass", "android", "-keypass", "android",
             "-alias", "androiddebugkey", "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
             "-dname", "CN=Local Route Studio Development", "-noprompt"])
    with tempfile.TemporaryDirectory(prefix="android-build-", dir=output) as directory:
        temporary = Path(directory)
        classes = temporary / "classes"
        dex = temporary / "dex"
        classes.mkdir()
        dex.mkdir()
        sources = sorted((source / 'src').rglob('*.java'))
        run([javac, "-encoding", "UTF-8", "--release", "8", "-classpath", platform, "-d", classes, *sources])
        run([java, "-cp", tools / "lib" / "d8.jar", "com.android.tools.r8.D8", "--min-api", "26",
             "--lib", platform, "--output", dex, *sorted(classes.rglob("*.class"))])
        unsigned = temporary / "unsigned.apk"
        asset_args = ['-A', source / 'assets'] if (source / 'assets').is_dir() else []
        run([tools / ("aapt2" + suffix), "link", "-I", platform, "--manifest", source / "AndroidManifest.xml", *asset_args,
             "--min-sdk-version", "26", "--target-sdk-version", "35", "-o", unsigned])
        with zipfile.ZipFile(unsigned, "a", compression=zipfile.ZIP_DEFLATED) as archive:
            for dex_file in sorted(dex.glob("*.dex")):
                archive.write(dex_file, dex_file.name)
        aligned = temporary / "aligned.apk"
        run([tools / ("zipalign" + suffix), "-f", "-p", "4", unsigned, aligned])
        apk = output / args.apk_name
        run([java, "-jar", tools / "lib" / "apksigner.jar", "sign", "--ks", key,
             "--ks-key-alias", "androiddebugkey", "--ks-pass", "pass:android", "--key-pass", "pass:android",
             "--out", apk, aligned])
        run([java, "-jar", tools / "lib" / "apksigner.jar", "verify", "--verbose", apk])
        run([tools / ("aapt2" + suffix), "dump", "badging", apk])
    print(f"\nBuilt {apk}")
    print("Development signing key remains in ignored build/. Never publish the key.")


if __name__ == "__main__":
    main()
