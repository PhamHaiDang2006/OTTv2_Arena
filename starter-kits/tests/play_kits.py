"""Validate packaged ZIPs with runner extraction, compile, and play both colors."""
import argparse
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from ottv2.cli import default_config, play
from ottv2.local import bot_command

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "runner"), str(ROOT / "contracts")]
from ottv2_runner.archive import extract_source
from validate import validator, replay_errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    subprocess.run([sys.executable, str(ROOT / "starter-kits/tools/package.py")], check=True)
    manifest = json.loads((ROOT / "starter-kits/dist/manifest.json").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        bots = {}
        for item in manifest:
            name = item["language"] + "-" + item["strategy"]
            folder = Path(tmp) / name
            folder.mkdir()
            extract_source((ROOT / "starter-kits/dist" / item["file"]).read_bytes(), folder, item["language"])
            if item["language"] == "cpp":
                subprocess.run([args.cxx, "-std=c++20", "-O2", "-pipe", str(folder / "main.cpp"), "-o", str(folder / ("main.exe" if os.name == "nt" else "main"))], check=True)
            bots[name] = bot_command(folder)
        for python in ("python-random", "python-greedy"):
            for cpp in ("cpp-random", "cpp-greedy"):
                for blue, red in ((python, cpp), (cpp, python)):
                    result = asyncio.run(play(bots[blue], bots[red], default_config()))
                    validator("EngineResult").validate(asdict(result))
                    assert not replay_errors(result.replay)
                    assert result.reason not in {"CRASH", "TIMEOUT", "ILLEGAL_MOVE"}, (blue, red, result.reason)
                    print(f"PASS {blue} vs {red}: {result.reason} ({result.plies} ply)", flush=True)


if __name__ == "__main__":
    main()
