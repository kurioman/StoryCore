"""Compile pydantic-core for Android (used by .github/workflows/mobile-apk.yml).

pydantic-core (the Rust heart of pydantic, needed by FastAPI) has no Android build on PyPI or in Chaquopy's index.
This script cross-compiles it from its PyPI source with maturin + the Android NDK, against the Android Python that
Chaquopy publishes on Maven Central. Result: e.g. ``pydantic_core-2.50.2-cp313-cp313-android_24_arm64_v8a.whl``.

Recipe adapted from kohaku-lab/android-dep-collection (MIT), which builds the same package for Chaquopy.

Needs (provided by the workflow): Python 3.13, Rust with the Android target, the Android NDK (ANDROID_NDK_ROOT),
maturin >= 1.13.3.

    python mobile/tools/build_wheel.py --abi arm64-v8a --out mobile/android/wheels
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

PACKAGE = "pydantic-core"
ANDROID_API = 24           # Android 7.0 (Chaquopy's minimum)
CHAQUOPY_PYTHON = "3.13.7"  # any 3.13 works: the wheel targets the 3.13 ABI
TRIPLES = {"arm64-v8a": "aarch64-linux-android", "x86_64": "x86_64-linux-android"}


def download(url: str, dest: Path) -> Path:
    print(f"  download {url}", flush=True)
    with urllib.request.urlopen(url, timeout=300) as r:
        dest.write_bytes(r.read())
    return dest


def fetch_source(version: str, work: Path) -> Path:
    meta = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/{PACKAGE}/{version}/json", timeout=60))
    sdist = next(u for u in meta["urls"] if u["packagetype"] == "sdist")
    archive = download(sdist["url"], work / sdist["filename"])
    with tarfile.open(archive) as t:
        t.extractall(work, filter="data")
    src = work / sdist["filename"].removesuffix(".tar.gz")
    if not (src / "Cargo.toml").is_file():
        raise SystemExit(f"unexpected source layout in {src}")
    return src


def fetch_android_python(triple: str, work: Path) -> Path:
    """Chaquopy's Android Python (libpython3.13.so + sysconfig), needed to link the extension."""
    base = f"https://repo1.maven.org/maven2/com/chaquo/python/python/{CHAQUOPY_PYTHON}"
    archive = download(f"{base}/python-{CHAQUOPY_PYTHON}-{triple}.tar.gz", work / f"python-{triple}.tar.gz")
    dest = work / f"python-{triple}"
    with tarfile.open(archive) as t:
        t.extractall(dest, filter="data")
    lib = dest / "prefix" / "lib"
    short = CHAQUOPY_PYTHON.rsplit(".", 1)[0]
    if not (lib / f"libpython{short}.so").is_file():
        raise SystemExit(f"libpython{short}.so not found under {lib}")
    return lib


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--abi", choices=sorted(TRIPLES), default="arm64-v8a")
    ap.add_argument("--version", default="2.50.2", help="must match the pin of pydantic (requirements-mobile.txt)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--work", type=Path, default=Path(".wheel-build"))
    a = ap.parse_args()

    triple = TRIPLES[a.abi]
    ndk = os.environ.get("ANDROID_NDK_ROOT") or os.environ.get("ANDROID_NDK_HOME")
    if not ndk:
        raise SystemExit("ANDROID_NDK_ROOT is not set")
    a.work.mkdir(parents=True, exist_ok=True)
    a.out.mkdir(parents=True, exist_ok=True)

    src = fetch_source(a.version, a.work)
    lib = fetch_android_python(triple, a.work)
    short = CHAQUOPY_PYTHON.rsplit(".", 1)[0]

    bin_dir = Path(ndk) / "toolchains" / "llvm" / "prebuilt" / "linux-x86_64" / "bin"
    clang = bin_dir / f"{triple}{ANDROID_API}-clang"
    if not clang.is_file():
        raise SystemExit(f"NDK compiler not found: {clang}")
    cargo = triple.upper().replace("-", "_")

    env = os.environ.copy()
    env.update({
        "ANDROID_API_VERSION": str(ANDROID_API),         # maturin: tag the wheel android_24_<abi>
        "PYO3_CROSS_LIB_DIR": str(lib),
        "PYO3_CROSS_PYTHON_VERSION": short,
        f"CARGO_TARGET_{cargo}_LINKER": str(clang),
        f"CARGO_TARGET_{cargo}_AR": str(bin_dir / "llvm-ar"),
        f"CC_{triple}": str(clang),
        f"AR_{triple}": str(bin_dir / "llvm-ar"),
        "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
        "RUSTFLAGS": f"-L native={lib} {env.get('RUSTFLAGS', '')}".strip(),
    })
    cmd = [sys.executable, "-m", "maturin", "build", "--release", "--target", triple,
           "--interpreter", f"python{short}", "--out", str(a.out.resolve()), "--compatibility", "off"]
    print("  " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=src, env=env, check=True)

    built = sorted(a.out.glob("pydantic_core-*.whl"))
    print("  built: " + ", ".join(w.name for w in built))
    if not any(f"android_{ANDROID_API}_" in w.name for w in built):
        raise SystemExit("the wheel is not tagged for Android (maturin too old?)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
