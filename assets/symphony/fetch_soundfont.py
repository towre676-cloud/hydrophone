"""Fetch pinned playback assets with byte checks; never opens an audio device."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import urllib.request


ROOT = Path(__file__).resolve().parent


def fetch(url, target, sha256, expected_bytes=None):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == sha256:
        return target
    temporary = target.with_suffix(target.suffix + ".part")
    digest = hashlib.sha256()
    total = 0
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Hydrophone-Symphony/1"})
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as stream:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if expected_bytes is not None and total > expected_bytes:
                    raise ValueError("Downloaded asset exceeds pinned size")
                digest.update(chunk)
                stream.write(chunk)
        if digest.hexdigest() != sha256 or (expected_bytes is not None and total != expected_bytes):
            raise ValueError("Downloaded asset differs from pinned SHA256/size")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def soundfont():
    record = json.loads((ROOT / "soundfont.json").read_text(encoding="utf-8"))
    return fetch(record["download_url"], ROOT / record["local_file"], record["sha256"], record["bytes"])


def native_linux():
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        raise ValueError("Pinned native helper supports Linux x86_64; install FluidSynth for your platform")
    record = json.loads((ROOT / "native_linux.json").read_text(encoding="utf-8"))
    runtime = ROOT / "native" / "runtime"
    for package in record["packages"]:
        path = fetch(package["url"], ROOT / "native" / package["filename"],
                     package["sha256"], package["bytes"])
        subprocess.run(["dpkg-deb", "-x", str(path), str(runtime)], check=True)
    return runtime / "usr/lib/x86_64-linux-gnu/libfluidsynth.so.3"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-linux", action="store_true", help="Also prepare isolated Linux x86_64 FluidSynth libraries")
    args = parser.parse_args()
    result = {"soundfont": str(soundfont()), "hardware_commands_issued": 0}
    if args.native_linux:
        result["fluidsynth_library"] = str(native_linux())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
