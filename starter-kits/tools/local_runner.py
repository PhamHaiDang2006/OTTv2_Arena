"""Compatibility wrapper: python starter-kits/tools/local_runner.py bot_a bot_b --games 10.

Also forwards subcommands, e.g. practice my_bot --vs greedy --games 10."""
import sys
from ottv2.cli import main

if len(sys.argv) < 2 or sys.argv[1] not in ("play", "practice", "-h", "--help"):
    sys.argv.insert(1, "play")
main()
