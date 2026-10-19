"""Compile C++ and compare both kits against 1000 shared engine positions."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from ottv2 import Board

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    cases = json.loads((ROOT / "engine/fixtures/positions.json").read_text())["cases"]
    with tempfile.TemporaryDirectory() as tmp:
        executable = Path(tmp) / "crosscheck.exe"
        subprocess.run([args.cxx, "-std=c++20", "-O2", "-I", str(ROOT / "starter-kits/cpp"), str(ROOT / "starter-kits/tests/crosscheck.cpp"), "-o", str(executable)], check=True)
        result = subprocess.run([str(executable)], input="\n".join(c["fen"] for c in cases) + "\n", capture_output=True, text=True, check=True)
        lines = result.stdout.splitlines()
        assert len(lines) == len(cases) * 2
        for i, case in enumerate(cases):
            board = Board.from_fen(case["fen"])
            for j, side in enumerate(("BLUE", "RED")):
                assert sorted(board.legal_moves(side)) == case[side] == lines[2*i+j].split(), (i, side)
                for move in case[side]:
                    undo = board.push(move, side); board.pop(undo)
                    assert board.fen() == case["fen"]
    print(f"PASS: {len(cases)} positions, both sides, Python/C++ legal moves and apply/undo")


if __name__ == "__main__":
    main()
